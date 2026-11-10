"""Spec 047, requisito 68: una pasada completa por agente la paga Auphere; las demás, la bolsa.

- ``usage_records.source``: ``tests_client``, lo que mide una pasada a cargo de la bolsa.
- ``usage_records.line``: ``client_tests``, «Pruebas a cargo del cliente» en Consumo.
- ``agent_test_runs.paid_by``: ``client_bag``.
- ``agent_test_runs.scope``: ``failed``, «Repetir las que no pasan».
- ``client_wallet_entries.kind``: ``debit_tests``, para que el ritmo de la bolsa y el tope
  del agente sigan hablando de lo que gasta atendiendo.
- ``agents.tests_pass_returned_at``: el último cambio que Auphere le hizo al agente por su
  cuenta. Las pasadas de antes ya no gastan la que paga Auphere (68.14).

Revision ID: 0220_tests_on_the_clients_bag
Revises: 0219_partner_starts_without_pool
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0220_tests_on_the_clients_bag"
down_revision: str | Sequence[str] | None = "0219_partner_starts_without_pool"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCES = (
    "channel",
    "qa",
    "companion",
    "builder",
    "tests",
    "reader",
    "indexer",
    "suggestions",
    "certification",
)
_LINES = ("conversations", "build", "companion", "platform")
_PAID_BY = ("partner", "auphere")
_SCOPES = ("all", "affected", "one")
_ENTRY_KINDS = (
    "assign",
    "lower",
    "move_in",
    "move_out",
    "refill",
    "debit_turn",
    "currency_change",
    "migration",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _check(table: str, name: str, condition: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})")


def upgrade() -> None:
    # Una fila de Auditoría sin frase se lee como código.
    op.execute(
        """
        INSERT INTO console_audit_vocabulary (action, category, severity, summary_es, summary_en)
        VALUES (
            'agent.tests.charged_to_bag', 'agents', 'info',
            '{actor} ejecutó las pruebas de un agente de {client} con cargo a su bolsa.',
            '{actor} ran the tests of an agent of {client}, charged to their bag.'
        )
        ON CONFLICT (action) DO NOTHING
        """
    )
    op.execute("ALTER TABLE agents ADD COLUMN tests_pass_returned_at TIMESTAMPTZ")
    _check(
        "usage_records",
        "ck_usage_source",
        f"source IN ({_in((*_SOURCES, 'tests_client'))})",
    )
    _check(
        "usage_records",
        "ck_usage_line",
        f"line IS NULL OR line IN ({_in((*_LINES, 'client_tests'))})",
    )
    _check(
        "agent_test_runs",
        "ck_agent_test_runs_paid_by",
        f"paid_by IN ({_in((*_PAID_BY, 'client_bag'))})",
    )
    _check(
        "agent_test_runs",
        "ck_agent_test_runs_scope",
        f"scope IN ({_in((*_SCOPES, 'failed'))})",
    )
    _check(
        "client_wallet_entries",
        "ck_client_wallet_entries_kind",
        f"kind IN ({_in((*_ENTRY_KINDS, 'debit_tests'))})",
    )


def downgrade() -> None:
    op.execute("DELETE FROM console_audit_vocabulary WHERE action = 'agent.tests.charged_to_bag'")
    op.execute("ALTER TABLE agents DROP COLUMN tests_pass_returned_at")
    # Lo que ya se cobró sigue cobrado: vuelve a las categorías de antes. Con la RLS fuera,
    # como la 0205: si no, no se actualizaría nada y el CHECK de abajo abortaría.
    op.execute("SET LOCAL row_security = off")
    op.execute(
        "UPDATE usage_records SET source = 'tests', line = 'build' WHERE source = 'tests_client'"
    )
    op.execute("UPDATE agent_test_runs SET paid_by = 'partner' WHERE paid_by = 'client_bag'")
    op.execute("UPDATE agent_test_runs SET scope = 'affected' WHERE scope = 'failed'")
    op.execute("UPDATE client_wallet_entries SET kind = 'debit_turn' WHERE kind = 'debit_tests'")
    _check("usage_records", "ck_usage_source", f"source IN ({_in(_SOURCES)})")
    _check("usage_records", "ck_usage_line", f"line IS NULL OR line IN ({_in(_LINES)})")
    _check("agent_test_runs", "ck_agent_test_runs_paid_by", f"paid_by IN ({_in(_PAID_BY)})")
    _check("agent_test_runs", "ck_agent_test_runs_scope", f"scope IN ({_in(_SCOPES)})")
    _check(
        "client_wallet_entries", "ck_client_wallet_entries_kind", f"kind IN ({_in(_ENTRY_KINDS)})"
    )
