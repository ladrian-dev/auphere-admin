"""Shared pytest fixtures.

Strategy:
- A single Postgres database (`nexus_test`) is created once per session.
- Migrations apply once per session.
- Each test runs inside a SAVEPOINT that rolls back at the end, so the DB returns
  to the post-migration state without paying the cost of dropping/recreating
  schemas. This is the standard SQLAlchemy "joining a transaction" pattern.

The fixtures override `nexus_api.config.get_settings` so the engine/redis/etc.
read the test config when they cache.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import fakeredis.aioredis
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── env: configure BEFORE importing nexus_api ───────────────────────────────────
TEST_DB_URL = os.environ.setdefault(
    "NEXUS_DATABASE_URL",
    "postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test",
)
os.environ.setdefault("NEXUS_REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("NEXUS_ENVIRONMENT", "dev")
os.environ.setdefault("NEXUS_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("NEXUS_WEBHOOK_HMAC_SECRET", "test-hmac-secret")
os.environ.setdefault("NEXUS_FERNET_KEY", Fernet.generate_key().decode())
os.environ.setdefault("NEXUS_ISOLATION_ENFORCER_RAISE_IN_DEV", "false")

# Importing after env vars set so settings cache picks them up.
from nexus_api.config import get_settings  # noqa: E402
from nexus_api.core import redis_client  # noqa: E402
from nexus_api.db import base as db_base  # noqa: E402

# ── helpers ─────────────────────────────────────────────────────────────────────


def _parse_dsn(url: str) -> dict[str, Any]:
    """Pull connection params out of NEXUS_DATABASE_URL.

    Accepts the asyncpg form (``postgresql+asyncpg://...``) AND the bare
    psycopg form (``postgresql://...``). Strips the asyncpg dialect tag
    before parsing.
    """
    from urllib.parse import urlparse

    cleaned = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(cleaned)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "nexus",
        "password": parsed.password or "",
        "database": (parsed.path or "/nexus_test").lstrip("/"),
    }


def _admin_dsn(test_dsn: dict[str, Any]) -> dict[str, Any]:
    """The 'admin' connection — same host/port/user but talking to the
    default ``nexus`` database (or ``postgres``) so we can CREATE/DROP
    the test database from there."""
    return {**test_dsn, "database": "nexus"}


def _run_admin_sql(sql: str, params: dict[str, Any] | None = None) -> Any:
    """Run a single SQL against the admin database via psycopg2 sync.

    Why a sync driver: we run this BEFORE pytest-asyncio sets up an event
    loop, in module-load time of the session-scoped ``_bootstrap_db``
    fixture. Using asyncpg here would require nesting an asyncio.run()
    call that conflicts with the test loop. psycopg2 is already a transitive
    dep via SQLAlchemy's psycopg drivers — no new install.
    """
    import psycopg2

    admin = _admin_dsn(_parse_dsn(TEST_DB_URL))
    with psycopg2.connect(**admin, connect_timeout=5) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            try:
                return cur.fetchall()
            except psycopg2.ProgrammingError:
                return None


def _ensure_test_db() -> None:
    """Create the ``nexus_test`` database if it doesn't exist.

    Local development uses ``docker exec`` against the nexus-postgres
    container; GitHub Actions exposes Postgres as a service container
    reachable directly via the DSN. We detect the environment by checking
    ``CI`` (set by GHA, GitLab, CircleCI, …).
    """
    test_db = _parse_dsn(TEST_DB_URL)["database"]
    if os.environ.get("CI"):
        rows = _run_admin_sql(
            "SELECT 1 FROM pg_database WHERE datname = %(name)s",
            {"name": test_db},
        )
        if not rows:
            # CREATE DATABASE cannot be parameterised — quote_ident-equivalent
            # done manually. test_db is internal (env-driven), no SQLi risk.
            _run_admin_sql(f'CREATE DATABASE "{test_db}"')
        return

    container = "nexus-postgres"
    cmd = [
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        "nexus",
        "-d",
        "nexus",
        "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname='{test_db}'",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if "1" not in out.stdout:
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "psql",
                "-U",
                "nexus",
                "-d",
                "nexus",
                "-c",
                f"CREATE DATABASE {test_db}",
            ],
            check=True,
            capture_output=True,
        )


def _run_migrations() -> None:
    here = os.path.dirname(__file__)
    api_root = os.path.dirname(here)
    env = {**os.environ, "NEXUS_DATABASE_URL": TEST_DB_URL}
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=api_root,
        env=env,
        check=True,
        capture_output=True,
    )


def _reset_test_db() -> None:
    """Drop & re-apply the schema before the session starts. Cheaper than dropping
    the database; idempotent with the migrations we have."""
    test_db = _parse_dsn(TEST_DB_URL)["database"]
    reset_sql = (
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public; "
        # Phase 3 (ADR-020): qa.* lives in its own schema; drop it too
        # so a previous test session's tables don't collide with the
        # fresh ``alembic upgrade head`` below.
        "DROP SCHEMA IF EXISTS qa CASCADE; "
        "CREATE EXTENSION IF NOT EXISTS pgcrypto; "
        "CREATE EXTENSION IF NOT EXISTS vector;"
    )
    if os.environ.get("CI"):
        import psycopg2

        # Connect directly to the test DB to drop/recreate its public schema.
        test_conn = {**_parse_dsn(TEST_DB_URL), "database": test_db}
        with psycopg2.connect(**test_conn, connect_timeout=5) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(reset_sql)
        return

    container = "nexus-postgres"
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-U",
            "nexus",
            "-d",
            test_db,
            "-c",
            reset_sql,
        ],
        check=True,
        capture_output=True,
    )


# ── session-scoped: bring up DB once ────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db() -> Iterator[None]:
    _ensure_test_db()
    _reset_test_db()
    _run_migrations()
    db_base.reset_engine_cache()
    yield


# ── fakeredis: override the Redis singleton ─────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def fake_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    redis_client.reset_redis_cache()
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "get_redis", lambda: fake)
    yield fake
    await fake.aclose()


# ── per-test engine reset ──────────────────────────────────────────────────────
# ``nexus_api.db.base.get_engine`` is LRU-cached. The block-C runtime tests
# drive code that opens NEW sessions inside the LangGraph pipeline (the
# checkpoint node, the AgentLoader). Without resetting the cache between
# tests, those sessions reuse asyncpg connections bound to the previous
# test's event loop and trip ``Event loop is closed`` / cross-loop futures.
# Cheap to recreate; cleaner than monkey-patching every internal import site.


@pytest_asyncio.fixture(autouse=True)
async def _reset_db_engine_cache() -> AsyncIterator[None]:
    db_base.reset_engine_cache()
    try:
        yield
    finally:
        await db_base.dispose_engine()
        db_base.reset_engine_cache()


# ── per-test transaction with rollback ──────────────────────────────────────────


@pytest_asyncio.fixture
async def test_engine() -> AsyncIterator[Any]:
    engine = create_async_engine(get_settings().database_url, poolclass=None)
    yield engine
    await engine.dispose()


_TRUNCATE_TABLES = (
    # Block L — connectors module (tenant-scoped FK to tenants must clear first).
    "tenant_connector_tool_overrides",
    "tenant_connectors",
    "isolation_events",
    "daily_cost_snapshots",
    "operator_notifications",
    # Migration 0018 — owner backchannel. ``owner_consultations`` FKs
    # ``conversations`` (CASCADE) so must clear before it; ``owner_phone_index``
    # FKs ``tenants`` (CASCADE) so must clear before tenants.
    "owner_consultations",
    "owner_phone_index",
    # Migration 0038 — Auphere multi-tenant backchannel channel
    # registry. ``owner_phone_index.auphere_channel_id`` FK SET NULL,
    # so we clear the channels table AFTER owner_phone_index.
    "auphere_owner_channels",
    "audit_log",
    "usage_events",
    "scheduled_jobs",
    "queue_entries",
    "appointments",
    "messages",
    "conversations",
    # Migration 0032 — Anthropic Memory tool backend. The versions
    # table is fed by a trigger on agent_memories; truncate both so
    # neither carries rows across tests. Both have FK CASCADE to tenants
    # so order matters: clear the versions first (FK to memories' tenant),
    # then the main table, then customers (FK target of memories).
    "agent_memory_versions",
    "agent_memories",
    "customers",
    # Migrations 0047/0048 — partner platform + broadcasts (ADR-028).
    "broadcast_recipients",
    "broadcasts",
    "embed_audit_log",
    "partner_tenants",
    "api_keys",
    "partners",
    "kg_edges",
    "kg_nodes",
    "tenant_credentials",
    "channels",
    "agent_configs",
    "tenants",
)


@pytest_asyncio.fixture
async def db_session(test_engine: Any) -> AsyncIterator[AsyncSession]:
    """Real session against the test DB. After each test we TRUNCATE all
    tenant-scoped tables + tenants. tool_catalog and kg_schemas keep their
    seed rows (migration-driven, not test-driven).

    Commits are real, so the FastAPI client (which uses its own connection
    from the same engine pool) sees the same data.
    """
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        # Truncate via a fresh connection so we ignore any RLS state.
        async with test_engine.begin() as conn:
            await conn.execute(
                text("TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")
            )
            # Block L — clean test-inserted tool_catalog rows. The baseline
            # rows are seeded by migrations 0003 (21 LLM-facing) + 0009 (6
            # agendapro internal) and must survive. Connector-derived rows
            # use mcp_server starting with "composio:" (see seed YAMLs) or
            # have a non-null connector_id (set by tools.sync). The
            # ``SHARED_TOOL_FOR_ISOLATION`` row from
            # test_overrides_are_tenant_scoped also uses ``composio:`` so
            # one rule cleans both.
            await conn.execute(
                text(
                    "DELETE FROM tool_catalog "
                    "WHERE connector_id IS NOT NULL "
                    "OR mcp_server LIKE 'composio:%'"
                )
            )
            await conn.execute(text("DELETE FROM connectors"))


# ── seed helpers ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seed_tenants(db_session: AsyncSession) -> dict[str, uuid.UUID]:
    from nexus_api.db.models import Tenant, TenantPlan

    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    db_session.add_all(
        [
            Tenant(id=a_id, name="Tenant A", slug="tenant-a", plan=TenantPlan.PRO),
            Tenant(id=b_id, name="Tenant B", slug="tenant-b", plan=TenantPlan.ESSENTIAL),
        ]
    )
    await db_session.commit()
    return {"a": a_id, "b": b_id}


@pytest_asyncio.fixture
async def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().admin_token}"}


# ── HTTP client wired to the FastAPI app ────────────────────────────────────────


@pytest_asyncio.fixture
async def client() -> AsyncIterator[Any]:
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from nexus_api.main import app

    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ── direct conn helper for raw RLS testing ──────────────────────────────────────


@pytest_asyncio.fixture
async def scoped_session_factory(test_engine: Any) -> AsyncIterator[Any]:
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async def _make(tenant_id: uuid.UUID) -> AsyncSession:
        s = factory()
        await s.begin()
        await s.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tenant_id)}
        )
        await s.execute(text("SET LOCAL ROLE nexus_app"))
        return s

    yield _make
