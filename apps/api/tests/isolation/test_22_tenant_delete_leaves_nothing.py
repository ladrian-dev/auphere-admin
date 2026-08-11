"""Borrar un tenant no deja filas suyas en ninguna tabla (WP-29, RGPD).

Hermano de ``test_21``: mismo método —enumerar ``pg_class``, no una lista
escrita a mano— aplicado al otro invariante. El 21 pregunta "¿esta tabla
filtra por tenant?"; este pregunta "¿esta tabla se va con el tenant?".

Existe porque la auditoría del catálogo devolvió dos clases de fallo, y
ninguna de las dos daba la cara:

- **cinco tablas BLOQUEABAN el borrado** con un ForeignKeyViolation que
  el endpoint traducía a un 502 sin decir cuál era la culpable
  (``whatsapp_opt_outs``, ``partner_tenants``, ``broadcasts`` vía
  ``channels``, y los dos conectores que el handler limpiaba a mano);
- **cuatro dejaban filas huérfanas en silencio** — ``agent_sales``,
  ``usage_records`` y ``embed_audit_log`` llevaban ``tenant_id`` sin
  ninguna clave foránea, y ``whatsapp_template_status`` con SET NULL.

Una tabla nueva con ``tenant_id`` y sin camino de borrado rompe la suite
el día que se crea, y quien la añade tiene que escribir por qué en la
lista de excepciones. Convierte un olvido en una decisión.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = pytest.mark.asyncio


# Tablas con ``tenant_id`` que NO deben irse con el tenant. Cada una
# necesita la razón por la que borrarlas sería peor que conservarlas.
KEEP_ON_DELETE: dict[str, str] = {
    "audit_log": (
        "Se ANONIMIZA, no se borra: el endpoint vacía before_json/after_json "
        "(donde vive cualquier dato personal) y la FK SET NULL deja la fila "
        "como acción de plataforma. El RGPD pide quitar el dato personal, no "
        "destruir el registro de quién hizo qué — con CASCADE se perdía "
        "entera, incluida la fila que registra el propio borrado."
    ),
    "invoices": (
        "Obligación legal de conservación de facturación; el art. 17.3.b del "
        "RGPD la excluye del derecho de supresión. FK en RESTRICT a propósito "
        "y el endpoint lo comprueba antes para responder 409 en vez de 502."
    ),
    "invoice_lines": "Cuelga de ``invoices``; misma obligación legal.",
    "api_keys": (
        "``tenant_id`` es NULL en las claves de nivel partner y la tabla se "
        "lee para autenticar antes de saber el tenant. Las claves atadas a un "
        "tenant sí cascadean (su FK ya es CASCADE); la excepción cubre el "
        "resto de la tabla, que no es dato de ningún tenant."
    ),
    "owner_phone_index": (
        "Índice teléfono → tenant. Su FK ya es CASCADE; se lista aquí porque "
        "el barrido lo encuentra por ``tenant_id`` y conviene dejar escrito "
        "que se comprobó."
    ),
}

# Reglas de borrado aceptables en una FK hacia ``tenants``. SET NULL vale
# porque es la forma de anonimizar sin perder la fila; RESTRICT NO vale
# salvo excepción justificada arriba, porque convierte el borrado en un
# error en vez de en un borrado.
_ACCEPTABLE = {"c", "n"}  # CASCADE, SET NULL

_INVENTORY_SQL = sa.text(
    """
    SELECT c.relname AS table_name,
           (SELECT string_agg(
                     CASE fk.confdeltype
                       WHEN 'c' THEN 'c' WHEN 'n' THEN 'n'
                       WHEN 'r' THEN 'r' WHEN 'a' THEN 'a' ELSE 'd' END, ',')
              FROM pg_constraint fk
             WHERE fk.contype = 'f'
               AND fk.conrelid = c.oid
               AND fk.confrelid = 'tenants'::regclass) AS delete_rules
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'tenant_id'
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r', 'p')
       AND c.relispartition IS FALSE
       AND a.attisdropped IS FALSE
     ORDER BY c.relname
    """
)

# Tablas que no necesitan FK propia porque su padre ya las arrastra. Se
# listan con el camino explícito: si mañana alguien suelta ese padre, el
# comentario dice dónde mirar.
CASCADES_VIA_PARENT: dict[str, str] = {
    "messages": (
        "``messages.conversation_id`` es NOT NULL con FK CASCADE a "
        "``conversations``, que a su vez cascadea del tenant (0070). Una FK "
        "propia sería redundante y obligaría a validar una tabla particionada "
        "entera bajo ACCESS EXCLUSIVE."
    ),
    "checkpoints": "Tablas de LangGraph: las crea la librería, las borra el endpoint.",
    "checkpoint_blobs": "Ídem.",
    "checkpoint_writes": "Ídem.",
}

# Tablas que NO crea ninguna migración: las crea ``setup()`` de LangGraph
# al arrancar el worker. En una base recién migrada (CI) no existen, así
# que el detector de excepciones caducadas no puede exigirlas — y el
# endpoint comprueba su existencia antes de borrar por el mismo motivo.
RUNTIME_CREATED = frozenset({"checkpoints", "checkpoint_blobs", "checkpoint_writes"})


async def test_every_tenant_table_has_a_delete_path() -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        rows = (await session.execute(_INVENTORY_SQL)).all()

    assert rows, "el barrido no encontró ninguna tabla con tenant_id — consulta rota"

    offenders: list[str] = []
    for table_name, delete_rules in rows:
        if table_name in KEEP_ON_DELETE or table_name in CASCADES_VIA_PARENT:
            continue
        if not delete_rules:
            offenders.append(
                f"{table_name}: lleva tenant_id y NINGUNA clave foránea a tenants — "
                "sus filas quedarían huérfanas al borrar el tenant"
            )
            continue
        bad = [r for r in delete_rules.split(",") if r not in _ACCEPTABLE]
        if bad:
            offenders.append(
                f"{table_name}: FK a tenants con regla {bad} — RESTRICT/NO ACTION "
                "convierte el borrado en un error, no en un borrado"
            )

    assert not offenders, "tablas sin camino de borrado:\n" + "\n".join(
        f"  - {o}" for o in offenders
    )


async def test_the_guard_detects_a_new_table_without_a_delete_path() -> None:
    """Un guardián que nunca falla no protege nada.

    Se crea una tabla real con ``tenant_id`` y sin clave foránea, y se
    comprueba que el barrido la señala. Sin esto, un error en la consulta
    del catálogo dejaría el test verde para siempre.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            sa.text("CREATE TABLE _tmp_sin_cascada (id serial PRIMARY KEY, tenant_id uuid)")
        )
        await session.commit()
    try:
        with pytest.raises(AssertionError, match="_tmp_sin_cascada"):
            await test_every_tenant_table_has_a_delete_path()
    finally:
        async with sm() as session:
            await session.execute(sa.text("DROP TABLE IF EXISTS _tmp_sin_cascada"))
            await session.commit()


async def test_the_exception_lists_do_not_rot() -> None:
    """Una excepción para una tabla que ya no existe es ruido que hace
    parecer justificado algo que nadie ha vuelto a mirar."""
    sm = get_sessionmaker()
    async with sm() as session:
        existing = set(
            (
                await session.execute(
                    sa.text(
                        "SELECT c.relname FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relkind IN ('r','p')"
                    )
                )
            )
            .scalars()
            .all()
        )

    stale = (set(KEEP_ON_DELETE) | set(CASCADES_VIA_PARENT)) - existing - RUNTIME_CREATED
    assert not stale, f"excepciones para tablas que ya no existen: {sorted(stale)}"
