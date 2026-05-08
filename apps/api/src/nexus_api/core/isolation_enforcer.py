"""Isolation enforcer — blocks SQL ops on tenant-scoped tables that escape RLS.

Listens to SQLAlchemy `before_cursor_execute` events. If a SELECT/INSERT/UPDATE/
DELETE touches a tenant-scoped table and the connection has no `app.tenant_id`
GUC set, it counts the violation and (in prod / when configured) raises.

This is belt-and-suspenders alongside the Postgres RLS policies. Even when RLS
silently returns zero rows, the enforcer catches the missing scope at the SQL
layer so we surface a logical bug instead of a "row not found" mystery.

Spec: architecture/agent-isolation.md, garantía 1 + tabla "Capas".
"""

from __future__ import annotations

import re

import structlog
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from nexus_api.config import get_settings
from nexus_api.core.errors import IsolationViolation
from nexus_api.core.metrics import ISOLATION_UNSCOPED_QUERY, counters

log = structlog.get_logger()

# Tables covered by RLS in migration 0002. Source of truth: the SCOPED_TABLES
# constant there. We duplicate it here on purpose — the enforcer must not import
# alembic, and CI parity is asserted by tests/unit/test_isolation_enforcer.py.
_SCOPED_TABLES = frozenset(
    {
        "agent_configs",
        "channels",
        "tenant_credentials",
        "kg_nodes",
        "kg_edges",
        "customers",
        "conversations",
        "messages",
        "usage_events",
        "audit_log",
    }
)

# Quick SQL pattern: words after FROM/JOIN/INTO/UPDATE that match a scoped table.
# Not airtight (no full SQL parser), but block-B grade — we avoid CTEs and views
# in repositories. Tests assert behaviour for each pattern we care about.
_TABLE_REF = re.compile(
    r"(?:FROM|JOIN|UPDATE|INTO|DELETE\s+FROM)\s+\"?([a-z_][a-z_0-9]*)\"?",
    re.IGNORECASE,
)


def _statement_touches_scoped_table(statement: str) -> bool:
    matches = _TABLE_REF.findall(statement)
    return any(t.lower() in _SCOPED_TABLES for t in matches)


def _connection_has_tenant(conn: Connection) -> bool:
    """True iff `app.tenant_id` is set and non-empty on this connection.

    Uses `current_setting('app.tenant_id', true)` (the `true` second arg means
    "missing returns NULL instead of raising"). The result is empty string when
    unset.
    """
    cursor = conn.connection.cursor()
    try:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        row = cursor.fetchone()
        value = row[0] if row else None
    finally:
        cursor.close()
    return bool(value)


def install(engine: AsyncEngine) -> None:
    """Attach the enforcer to a (sync) engine. Call this at app startup.

    Works on the AsyncEngine's underlying sync engine because SQLAlchemy events
    fire on the sync layer.
    """
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        # Skip migration / setting / health statements.
        upper = statement.lstrip().upper()
        if not upper.startswith(("SELECT", "INSERT", "UPDATE", "DELETE")):
            return
        if not _statement_touches_scoped_table(statement):
            return
        if _connection_has_tenant(conn):
            return

        counters.incr(ISOLATION_UNSCOPED_QUERY)
        settings = get_settings()
        log.warning(
            "isolation.unscoped_query",
            statement=statement[:200],
        )
        if settings.is_prod or settings.isolation_enforcer_raise_in_dev:
            raise IsolationViolation("SQL on tenant-scoped table without app.tenant_id")
