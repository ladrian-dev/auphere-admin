"""El medidor sabe la tarea, la decisión y la partida — spec 047, T023 (ola 1).

``usage_records`` gana:

- ``task``: el código de la taxonomía del router (``contracts/router-and-catalog.md``
  §1). Sin CHECK: la taxonomía es un dato versionado (``router_taxonomy``) y la
  valida quien escribe; una llamada sin tarea falla en los tests.
- ``route_decision_id``: enlaza la fila con la decisión del router, que va al log
  estructurado (``llm.route_decision``), no a una tabla.
- ``line``: la partida que ve el partner en Consumo (``conversations``, ``build``
  o ``companion``), o ``platform``: lo que paga Auphere fuera de las partidas
  del partner (las certificaciones que lanza Auphere, requisito 42.6). Se deriva de ``source`` **al escribir**; las filas de antes se
  quedan en NULL y quien las lee la deriva igual (``channel`` → conversaciones,
  ``qa`` → construcción, ``companion`` → Companion). Sin relleno: la tabla está
  particionada y es grande, y reescribirla no aporta nada.

``source`` gana los orígenes de la partida «Construcción y pruebas»
(requisito 46.4): el constructor, las pruebas, la lectura de webs, la
indexación, las sugerencias y las certificaciones del partner.

Revision ID: 0177_usage_task_and_line
Revises: 0176_inbound_reasons_and_turns
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0177_usage_task_and_line"
down_revision: str | Sequence[str] | None = "0176_inbound_reasons_and_turns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_SOURCES = ("channel", "qa", "companion")
_NEW_SOURCES = (
    *_OLD_SOURCES,
    "builder",
    "tests",
    "reader",
    "indexer",
    "suggestions",
    "certification",
)
LINES = ("conversations", "build", "companion", "platform")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _source_check(values: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE usage_records DROP CONSTRAINT IF EXISTS ck_usage_source")
    op.execute(
        f"ALTER TABLE usage_records ADD CONSTRAINT ck_usage_source CHECK (source IN ({_in(values)}))"
    )


def upgrade() -> None:
    op.execute("ALTER TABLE usage_records ADD COLUMN task varchar(32)")
    op.execute("ALTER TABLE usage_records ADD COLUMN route_decision_id uuid")
    op.execute("ALTER TABLE usage_records ADD COLUMN line varchar(16)")
    op.execute(
        "ALTER TABLE usage_records ADD CONSTRAINT ck_usage_line "
        f"CHECK (line IS NULL OR line IN ({_in(LINES)}))"
    )
    _source_check(_NEW_SOURCES)
    op.execute(
        "CREATE INDEX ix_usage_tenant_line ON usage_records (tenant_id, line, occurred_at DESC) "
        "WHERE line IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_usage_tenant_line")
    # The build sources fold back into the playground's, the one build source
    # the old CHECK knew: the spend stays, only its finer label goes.
    op.execute(f"UPDATE usage_records SET source = 'qa' WHERE source NOT IN ({_in(_OLD_SOURCES)})")
    _source_check(_OLD_SOURCES)
    op.execute("ALTER TABLE usage_records DROP CONSTRAINT IF EXISTS ck_usage_line")
    op.execute("ALTER TABLE usage_records DROP COLUMN IF EXISTS line")
    op.execute("ALTER TABLE usage_records DROP COLUMN IF EXISTS route_decision_id")
    op.execute("ALTER TABLE usage_records DROP COLUMN IF EXISTS task")
