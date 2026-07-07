"""Unit tests for the isolation enforcer's pattern matcher."""

from nexus_api.core.isolation_enforcer import (
    _SCOPED_TABLES,
    _statement_touches_scoped_table,
)


def test_select_from_scoped_detected():
    assert _statement_touches_scoped_table("SELECT * FROM agent_configs WHERE id=1")


def test_select_from_global_not_detected():
    assert not _statement_touches_scoped_table("SELECT * FROM tool_catalog")


def test_join_into_scoped_detected():
    sql = "SELECT * FROM tenants t JOIN customers c ON c.tenant_id=t.id"
    assert _statement_touches_scoped_table(sql)


def test_insert_into_scoped_detected():
    assert _statement_touches_scoped_table("INSERT INTO conversations (id, tenant_id) VALUES (1,2)")


def test_update_scoped_detected():
    assert _statement_touches_scoped_table("UPDATE messages SET content='x'")


def test_delete_from_scoped_detected():
    assert _statement_touches_scoped_table("DELETE FROM kg_nodes WHERE id=1")


def test_quoted_table_names():
    # Use ``messages`` (RLS-enabled + always tenant-scoped) — ``audit_log``
    # used to live here but migration 0039/0040 made it dual-mode
    # (tenant rows + platform NULL-tenant rows) so the enforcer no
    # longer flags every audit_log SQL as scope-mandatory.
    assert _statement_touches_scoped_table('SELECT * FROM "messages"')


def test_settings_query_not_flagged():
    """Pure config-style queries don't flag."""
    assert not _statement_touches_scoped_table("SET LOCAL app.tenant_id = 'x'")


def test_alembic_version_not_in_scoped():
    """alembic_version is global; ensure it's not classified as scoped."""
    assert "alembic_version" not in _SCOPED_TABLES


def test_scoped_set_matches_migration_scope():
    """The enforcer's table list must match the RLS migration's coverage
    MINUS tables that became dual-mode (tenant + platform) post-Phase 1.

    As of migration 0039/0040, ``audit_log`` is RLS-enabled but
    accepts ``tenant_id IS NULL`` rows for platform-level audit
    (Auphere channel CRUD, global skill publish). The application
    enforcer must NOT raise on those writes — the RLS policy itself
    is the boundary now. ``audit_log`` is therefore intentionally
    absent from ``_SCOPED_TABLES`` while still appearing in the
    migration's ``SCOPED_TABLES``.
    """
    rls_enabled_in_migration = {
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
    # Enforcer set is the migration set MINUS dual-mode tables.
    dual_mode = {"audit_log"}
    assert rls_enabled_in_migration - dual_mode == _SCOPED_TABLES
