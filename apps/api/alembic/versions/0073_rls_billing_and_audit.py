"""RLS en las tablas con ``tenant_id`` que se habían quedado sin ella.

Encontrado auditando el catálogo entero de Postgres, no leyendo código:
siete tablas llevan ``tenant_id`` y ninguna tenía policy, y las siete son
alcanzables por ``nexus_app`` — el rol con el que corre el runtime dentro
de una sesión de tenant. Es decir, hoy un turno de un cliente puede leer
las facturas de todos los demás con un SELECT sin WHERE. No hace falta
que exista la consulta: basta con que un día alguien la escriba creyendo
que la RLS le cubre las espaldas, que es exactamente la suposición sobre
la que ``model_resolver`` está construido.

De las siete, tres se arreglan aquí y cuatro son excepciones legítimas
que quedan justificadas en ``test_21_rls_covers_every_tenant_table.py``.
La lista de excepciones vive en el test y no en un comentario porque así
añadir una tabla nueva sin RLS **rompe la suite** y obliga a escribir por
qué, en vez de pasar desapercibido.

**ENABLE sin FORCE, a diferencia del resto del repo.** No es un descuido:

- ``nexus_app`` (runtime con tenant) → la policy aplica → ve solo lo suyo.
- El rol dueño (paneles de admin y ``partner_receipt``, que leen a
  propósito por encima del tenant para emitir una factura de partner) →
  la salta.

Con FORCE, el segundo camino vería cero filas y la facturación de
partners dejaría de funcionar en silencio. La garantía que importa —que
el runtime de un cliente no lea datos de otro— se mantiene entera,
porque ``tenant_scoped_session`` siempre hace ``SET LOCAL ROLE
nexus_app`` antes de tocar nada.

``invoices`` y ``embed_audit_log`` tienen ``tenant_id`` NULL-able con
significado propio (factura de partner, evento a nivel de partner). La
policy los deja fuera del alcance de una sesión de tenant, que es lo
correcto: la factura de un partner no es asunto de ninguno de sus
clientes.

Revision ID: 0073_rls_billing_and_audit
Revises: 0072_model_profiles
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0073_rls_billing_and_audit"
down_revision: str | Sequence[str] | None = "0072_model_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# El patrón ``NULLIF`` del repo: con el GUC ausente, el cast de la cadena
# vacía lanzaría y convertiría un fallo de aislamiento en un 500 en vez de
# en cero filas. Fail-closed y silencioso es lo que queremos aquí.
_TENANT_MATCH = "tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid"

_TABLES = ("invoices", "invoice_lines", "embed_audit_log")


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} USING ({_TENANT_MATCH})"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
