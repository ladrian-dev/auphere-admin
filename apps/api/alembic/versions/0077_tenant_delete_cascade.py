"""Borrado de tenant sin filas huérfanas ni bloqueos sorpresa (WP-29, GDPR).

El plan decía "hoy ``tenant.delete`` no cascadea y deja ``agent_configs``
y ``audit_log`` huérfanos". Auditando `pg_constraint` —no el ORM— el
cuadro real es peor y de dos clases distintas, y ninguna de las dos daba
la cara hasta que alguien intentaba borrar un tenant con historia:

**Bloqueaban el borrado con un ForeignKeyViolation** (que el endpoint
convertía en un 502 sin explicar qué lo impedía): `whatsapp_opt_outs`,
`partner_tenants`, `broadcasts` (vía `channels` RESTRICT), y
`tenant_connectors` / `tenant_connector_tool_overrides`, estos dos
parcheados a mano en el handler — el propio docstring reconocía que la
migración era el arreglo durable y esto es esa migración.

**Dejaban filas huérfanas en silencio**: `whatsapp_template_status`
(SET NULL), y `agent_sales`, `usage_records` y `embed_audit_log`, que
llevan `tenant_id` **sin ninguna clave foránea**. Un borrado "correcto"
dejaba consumo facturable y registros de auditoría de embebido
apuntando a un tenant que ya no existe.

Decisiones que conviene no re-litigar:

- **`messages` NO recibe clave foránea a `tenants`.** Ya cascadea por
  `conversations` (0070 restauró justamente esa FK y `conversation_id`
  es NOT NULL), así que sería redundante — y añadirla obliga a validar
  una tabla particionada entera bajo ACCESS EXCLUSIVE. El test de filas
  residuales comprueba que efectivamente no queda ninguna.
- **`usage_records` SÍ la recibe**, porque no tiene ningún camino de
  cascada: su única FK apunta a `partners` con SET NULL. Va validada de
  golpe (Postgres 16 no admite `NOT VALID` en tablas particionadas);
  hoy son cientos de filas y el momento de pagar ese escaneo es ahora.
- **`audit_log` pasa de CASCADE a SET NULL: se anonimiza, no se borra.**
  Es lo que pide el plan y es la lectura correcta del RGPD — el derecho
  de supresión no obliga a destruir la traza de quién hizo qué, obliga a
  quitarle los datos personales. El endpoint vacía `before_json` /
  `after_json` (donde vive cualquier dato personal) y la fila sobrevive
  sin tenant, como cualquier acción de plataforma. Con CASCADE se perdía
  entera, incluida la fila que registra el propio borrado.
- **`invoices` e `invoice_lines` se quedan en RESTRICT.** Una factura
  emitida tiene una obligación legal de conservación que el artículo
  17.3.b del RGPD excluye expresamente del derecho de supresión;
  destruirla para satisfacer un borrado sería cambiar un problema por
  otro mayor. El endpoint pasa a comprobarlo ANTES y responder 409 con
  el motivo, en vez del 502 de ahora. Cuando llegue Stripe habrá que
  desnormalizar el nombre del cliente en la factura y soltar la FK; hoy
  el CHECK `ck_invoices_one_payer` lo impide.

Revision ID: 0077_tenant_delete_cascade
Revises: 0076_openai_model_prices
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0077_tenant_delete_cascade"
down_revision: str | Sequence[str] | None = "0076_openai_model_prices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (tabla, nombre de la constraint, columna, regla anterior)
_TO_CASCADE = [
    # Los dos que el handler limpiaba a mano. RESTRICT venía del bloque L
    # para que nadie borrase por accidente credenciales OAuth vivas; el
    # flujo de dos pasos archivar→borrar ya es esa confirmación explícita.
    ("tenant_connectors", "fk_tc_tenant", "RESTRICT"),
    ("tenant_connector_tool_overrides", "fk_tcto_tenant", "RESTRICT"),
    # Una baja de contacto solo significa algo mientras exista el negocio
    # que no debe contactar.
    ("whatsapp_opt_outs", "fk_optout_tenant", "RESTRICT"),
    # El mapeo partner↔cliente: si el cliente se va, el mapeo sobra.
    ("partner_tenants", "partner_tenants_tenant_id_fkey", "RESTRICT"),
    # SET NULL dejaba el estado de plantillas apuntando a la nada.
    ("whatsapp_template_status", "fk_tplstatus_tenant", "SET NULL"),
]

# Tablas con ``tenant_id`` y sin FK ninguna. `broadcast_recipients` cuelga
# de `broadcasts` con CASCADE, así que le bastaría con que su padre caiga
# — pero lleva `tenant_id` propio y el guardián de RLS enumera por esa
# columna: se le pone la suya para que el invariante sea uno solo.
_MISSING_FK = [
    ("agent_sales", "fk_agent_sales_tenant"),
    ("broadcasts", "fk_broadcasts_tenant"),
    ("broadcast_recipients", "fk_broadcast_recipients_tenant"),
    ("embed_audit_log", "fk_embed_audit_tenant"),
    ("usage_records", "fk_usage_records_tenant"),
]


def upgrade() -> None:
    for table, constraint, _previous in _TO_CASCADE:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE"
        )

    # Una difusión pertenece al canal por el que sale. Con RESTRICT, un
    # tenant que alguna vez difundió no se podía borrar y el error salía
    # nombrando `channels`, que no es donde el operador miraría.
    op.execute("ALTER TABLE broadcasts DROP CONSTRAINT broadcasts_channel_id_fkey")
    op.execute(
        "ALTER TABLE broadcasts ADD CONSTRAINT broadcasts_channel_id_fkey "
        "FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE"
    )

    for table, constraint in _MISSING_FK:
        # Filas huérfanas de borrados anteriores impedirían crear la FK.
        # Se limpian aquí: ya no pertenecen a ningún tenant y su única
        # función posible era ensuciar un panel de coste.
        op.execute(
            f"DELETE FROM {table} t WHERE NOT EXISTS "
            f"(SELECT 1 FROM tenants x WHERE x.id = t.tenant_id)"
        )
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE"
        )

    # Anonimizar, no borrar. Ver la cabecera: el endpoint vacía los
    # payloads antes de soltar el tenant y la fila queda como acción de
    # plataforma.
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_log_tenant_id_fkey")
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT audit_log_tenant_id_fkey "
        "FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_log_tenant_id_fkey")
    op.execute(
        "ALTER TABLE audit_log ADD CONSTRAINT audit_log_tenant_id_fkey "
        "FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE"
    )

    for table, constraint in _MISSING_FK:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")

    op.execute("ALTER TABLE broadcasts DROP CONSTRAINT broadcasts_channel_id_fkey")
    op.execute(
        "ALTER TABLE broadcasts ADD CONSTRAINT broadcasts_channel_id_fkey "
        "FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE RESTRICT"
    )

    for table, constraint, previous in _TO_CASCADE:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE {previous}"
        )
