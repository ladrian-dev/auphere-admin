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
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import fakeredis.aioredis
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
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

# ── Partner console (CP-03): one Ed25519 keypair per test session ──────────
# The API only ever holds the PUBLIC key; tests mint tokens with the private
# half through the ``mint_console_token`` fixture below, exactly like the
# BFF does. Generated here (before ``nexus_api`` is imported) so the cached
# settings pick it up.
from cryptography.hazmat.primitives import serialization as _ser  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey as _Ed25519PrivateKey,
)

CONSOLE_TEST_PRIVATE_KEY = _Ed25519PrivateKey.generate()
CONSOLE_TEST_PRIVATE_PEM = CONSOLE_TEST_PRIVATE_KEY.private_bytes(
    encoding=_ser.Encoding.PEM,
    format=_ser.PrivateFormat.PKCS8,
    encryption_algorithm=_ser.NoEncryption(),
).decode()
CONSOLE_TEST_PUBLIC_PEM = (
    CONSOLE_TEST_PRIVATE_KEY.public_key()
    .public_bytes(
        encoding=_ser.Encoding.PEM,
        format=_ser.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode()
)
os.environ.setdefault("NEXUS_CONSOLE_ENABLED", "true")
os.environ.setdefault("NEXUS_CONSOLE_JWT_PUBLIC_KEY", CONSOLE_TEST_PUBLIC_PEM)

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
        # ADR-032: la identidad de la consola vive en ``console_auth``. Sin
        # esta línea, la segunda sesión de tests choca con las tablas que
        # dejó la primera y ``alembic upgrade head`` falla en 0088.
        "DROP SCHEMA IF EXISTS console_auth CASCADE; "
        # CO-01: lo mismo para el Companion — sus cuatro tablas viven en el
        # esquema ``companion`` (0090) y sobrevivirían al DROP de ``public``.
        "DROP SCHEMA IF EXISTS companion CASCADE; "
        "DROP SCHEMA IF EXISTS operator_auth CASCADE; "
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


# ── per-test WhatsApp template cache reset ─────────────────────────────────────
# ``services/whatsapp_templates`` memoises Meta's template list per WABA in a
# module-level dict for a few seconds, so a fan-out of sends doesn't fire one
# Graph API call per recipient. Tests build their WABAs from the same fixtures
# and therefore share the key: without this reset, the first test to populate
# the cache silently satisfies the next one's ``respx`` mock, whose
# ``assert_all_called`` then fails on a route that never had to be called.


@pytest.fixture(autouse=True)
def _reset_template_cache() -> Iterator[None]:
    from nexus_api.services.whatsapp_templates import invalidate_template_cache

    invalidate_template_cache()
    yield
    invalidate_template_cache()


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
    "usage_ledger",
    "partner_allocations",
    "partner_wallets",
    "partner_model_allowlist",
    "partner_tenants",
    "api_keys",
    # Migration 0080 — console principals. Invitations FK memberships
    # (SET NULL) and both FK partners (CASCADE): clear them first.
    "admin_impersonation_sessions",
    "partner_invitations",
    "partner_memberships",
    "partners",
    "operator_auth.principals",
    "kg_edges",
    "kg_nodes",
    "tenant_credentials",
    "channels",
    "agent_configs",
    "tenants",
)


async def _truncate_with_diagnosis(engine: Any, statement: str) -> None:
    """Vacía la base y, si hay deadlock, **dice contra quién**.

    CI falla de forma intermitente con ``DeadlockDetectedError`` en este
    ``TRUNCATE``: otra conexión sostiene un lock sobre una de las tablas y
    el vaciado sostiene otra. El mensaje de Postgres da los PID pero no las
    consultas ("See server log for query details"), y el log del contenedor
    de Postgres de CI no se recoge — así que el rojo llega sin la mitad que
    hace falta para arreglarlo.

    En vez de adivinar quién es, se pregunta: al detectar el deadlock se lee
    ``pg_stat_activity`` y se imprime qué estaba haciendo cada conexión viva.
    Después se reintenta una vez, porque un deadlock aborta **una** de las
    dos transacciones y la otra ya terminó.

    Esto NO es el arreglo del rojo: es lo que permite escribirlo con la causa
    delante en vez de con una hipótesis.
    """
    for intento in (1, 2):
        try:
            async with engine.begin() as conn:
                await conn.execute(text(statement))
            return
        except DBAPIError as exc:
            if "DeadlockDetected" not in repr(exc.orig) or intento == 2:
                raise
            try:
                async with engine.connect() as diag:
                    rows = (
                        await diag.execute(
                            text(
                                "SELECT pid, state, wait_event_type, wait_event, "
                                "left(query, 200) AS query FROM pg_stat_activity "
                                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                            )
                        )
                    ).fetchall()
                print("[deadlock en el TRUNCATE de tests] conexiones vivas:", file=sys.stderr)
                for row in rows:
                    print(
                        f"  pid={row.pid} {row.state} {row.wait_event_type}/{row.wait_event} :: {row.query}",
                        file=sys.stderr,
                    )
            except Exception as diag_exc:  # pragma: no cover - diagnóstico best-effort
                print(f"[deadlock] no se pudo leer pg_stat_activity: {diag_exc}", file=sys.stderr)
            await asyncio.sleep(0.5)


async def _drain_companion_runs(timeout: float = 15.0) -> None:
    """Espera a que mueran los runs del Companion antes de vaciar la base.

    ``POST /console/companion/runs/{id}/resume`` responde **202 y sigue
    trabajando**: el run de continuación es una tarea de asyncio que escribe
    en la misma base. Un test que asserta el 202 y vuelve deja esa tarea
    viva, y el ``TRUNCATE`` de aquí abajo pide ``AccessExclusiveLock`` sobre
    tablas que la tarea tiene tomadas con ``AccessShareLock``: **deadlock
    detectado**, en un test que ya había pasado.

    Se drena aquí y no test a test a propósito. Añadir un ``await`` en cada
    llamada a ``resume`` arregla las de hoy y no las que alguien escriba
    mañana; drenar en el desmontaje lo hace estructuralmente imposible.

    Vaciar ``_local_runs`` además evita que un handle de un test se cuele en
    el tope de concurrencia del siguiente.
    """
    try:
        from nexus_api.api.companion_streaming import _local_runs
    except Exception:  # pragma: no cover - la app puede no estar importada
        return

    tasks = [h.task for h in list(_local_runs.values()) if h.task is not None and not h.task.done()]
    _local_runs.clear()
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    if pending:
        # Se espera también a las canceladas: una tarea cancelada sigue
        # dentro de su transacción hasta que el ``CancelledError` sube.
        await asyncio.gather(*pending, return_exceptions=True)


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
        # Antes de vaciar: que no quede ninguna tarea del Companion escribiendo.
        await _drain_companion_runs()
        # Truncate via a fresh connection so we ignore any RLS state.
        await _truncate_with_diagnosis(
            test_engine,
            "TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE",
        )
        async with test_engine.begin() as conn:
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


# ── partner console tokens (CP-03) ─────────────────────────────────────────


def mint_console_token(
    *,
    user_id: str,
    partner_id: uuid.UUID | str | None,
    role: str | None = None,
    ttl: int = 60,
    jti: str | None = None,
    service: bool = False,
    issued_at: int | None = None,
    private_pem: str = CONSOLE_TEST_PRIVATE_PEM,
    **extra: Any,
) -> str:
    """Mint a console JWT the way ``apps/console`` does. ``service=True``
    produces the pre-membership service token (``svc: "console"``)."""
    import time as _time

    import jwt as _jwt

    settings = get_settings()
    now = issued_at if issued_at is not None else int(_time.time())
    claims: dict[str, Any] = {
        "iss": settings.console_jwt_issuer,
        "aud": settings.console_jwt_audience,
        "sub": user_id,
        "iat": now,
        "exp": now + ttl,
        "jti": jti or uuid.uuid4().hex,
    }
    if service:
        claims["svc"] = "console"
    else:
        claims["partner_id"] = str(partner_id)
        if role is not None:
            claims["role"] = role
    claims.update(extra)
    return _jwt.encode(claims, private_pem, algorithm="EdDSA")


def console_headers(**kwargs: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_console_token(**kwargs)}"}


@pytest.fixture(autouse=True)
def _reset_console_replay_cache() -> Iterator[None]:
    from nexus_api.core.console_auth import reset_replay_cache_for_tests

    reset_replay_cache_for_tests()
    yield
    reset_replay_cache_for_tests()


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


# ── partner console world (CP-02..CP-06) ───────────────────────────────────


@pytest_asyncio.fixture
async def console_world(db_session: AsyncSession) -> dict[str, Any]:
    """Two console-enabled partners, each with one client (tenant + mapping)
    and one active ``owner`` membership. Returns ids plus ready-made auth
    headers per partner and role.

    Shape::

        {"a": {"partner_id", "slug", "tenant_id", "ref", "user_id",
               "membership_id", "headers"}, "b": {...}}
    """
    from nexus_api.db.models import (
        MembershipStatus,
        Partner,
        PartnerAllocation,
        PartnerMembership,
        PartnerSubscription,
        PartnerTenant,
        Tenant,
        TenantPlan,
        TenantStatus,
    )

    world: dict[str, Any] = {}
    for label in ("a", "b"):
        partner_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        membership_id = uuid.uuid4()
        slug = f"cp-{label}-{partner_id.hex[:6]}"
        user_id = f"user_{label}_{partner_id.hex[:8]}"
        ref = f"client-{label}-1"
        db_session.add(
            Partner(
                id=partner_id,
                name=f"Console Partner {label.upper()}",
                slug=slug,
                console_enabled=True,
                # CO-08 §10: la bandera del Companion es ``false`` por
                # defecto en producción (el piloto es interno). Aquí se
                # enciende para que las suites del Companion prueben el
                # camino normal; el test de la garantía E8 la apaga a mano
                # sobre la fila para probar el camino apagado.
                companion_enabled=True,
                max_clients=3,
                # Spec 004 (R2): el tamaño del pool semanal se declara aquí en
                # vez de heredar el defecto de la columna (115 000). Las suites
                # de consola comparan cifras concretas contra este mundo, y un
                # número heredado las ata a un defecto que puede cambiar por
                # motivos de producto que nada tienen que ver con lo que
                # prueban.
                weekly_pool_tokens=500_000,
            )
        )
        db_session.add(
            Tenant(
                id=tenant_id,
                name=f"Client {label.upper()} One",
                slug=f"p-{slug}-one",
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
                partner_id=partner_id,
            )
        )
        await db_session.flush()
        # Spec 005 (R1): el partner de consola tiene una membresía de pago.
        # Sin ella sería Free — cero teammates, cero ejecución en la máquina —
        # y las suites que prueban esas cosas verían un tope donde quieren
        # probar comportamiento. Un partner NUEVO de producción sí nace Free;
        # éste representa uno que ya paga.
        db_session.add(
            PartnerSubscription(
                partner_id=partner_id,
                tier_code="business",
                state="current",
            )
        )
        db_session.add(
            PartnerTenant(
                partner_id=partner_id,
                external_client_ref=ref,
                tenant_id=tenant_id,
                client_name=f"Client {label.upper()} One",
            )
        )
        db_session.add(
            PartnerMembership(
                id=membership_id,
                partner_id=partner_id,
                user_id=user_id,
                email=f"owner-{label}@example.com",
                display_name=f"Owner {label.upper()}",
                role="owner",
                status=MembershipStatus.ACTIVE.value,
            )
        )
        db_session.add(
            PartnerAllocation(
                partner_id=partner_id,
                tenant_id=tenant_id,
                cap=500_000,
                remaining=500_000,
            )
        )
        world[label] = {
            "partner_id": partner_id,
            "slug": slug,
            "tenant_id": tenant_id,
            "ref": ref,
            "user_id": user_id,
            "membership_id": membership_id,
        }
    await db_session.commit()
    for label in ("a", "b"):
        w = world[label]
        w["headers"] = lambda w=w, **kw: console_headers(
            user_id=w["user_id"], partner_id=w["partner_id"], **kw
        )
    return world


async def add_console_member(
    db_session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    role: str,
    status: str = "active",
) -> dict[str, Any]:
    """Add one more member to a console partner; returns ids + headers factory."""
    from nexus_api.db.models import PartnerMembership

    membership_id = uuid.uuid4()
    user_id = f"user_{role}_{membership_id.hex[:8]}"
    db_session.add(
        PartnerMembership(
            id=membership_id,
            partner_id=partner_id,
            user_id=user_id,
            email=f"{role}-{membership_id.hex[:6]}@example.com",
            display_name=role,
            role=role,
            status=status,
        )
    )
    await db_session.commit()
    return {
        "membership_id": membership_id,
        "user_id": user_id,
        "headers": lambda **kw: console_headers(user_id=user_id, partner_id=partner_id, **kw),
    }


# ── Spec 004: el libro del partner ──────────────────────────────────────────
#
# Dos fábricas que las cuatro historias de la spec 004 necesitan. Viven aquí
# y no en cada suite porque el montaje es idéntico y repetirlo es cómo dos
# tests acaban probando estados distintos creyendo que prueban el mismo.


async def make_partner_with_wallet(
    db_session: AsyncSession,
    *,
    included: int = 500_000,
    purchased: int = 0,
    expires_at: Any = None,
    monthly_cap: int | None = None,
) -> dict[str, Any]:
    """A console partner whose wallet sits in a known state.

    The wallet row is NOT created here: migration 0094 installs a trigger
    (``trg_partners_seed_wallet``) that seeds one on every partner insert,
    with ``companion_monthly_token_cap`` and the end of the calendar month.
    Creating a second one would hit the primary key; this updates the row the
    trigger already wrote, which is also what production does.

    ``expires_at=None`` keeps whatever the trigger picked. Pass a datetime to
    place the wallet before or after its own expiry — that is how the renewal
    tests move time without touching the clock.
    """
    from nexus_api.db.models import Partner, PartnerWallet

    # The pool SIZE defaults to whatever the wallet starts with. Letting them
    # drift apart would make every ``used`` assertion in the suite wrong by a
    # constant, which is the kind of thing that gets "fixed" by changing the
    # expected number instead of the setup.
    monthly_cap = included if monthly_cap is None else monthly_cap

    partner_id = uuid.uuid4()
    slug = f"w-{partner_id.hex[:8]}"
    db_session.add(
        Partner(
            id=partner_id,
            name=f"Wallet Partner {slug}",
            slug=slug,
            console_enabled=True,
            companion_enabled=True,
            companion_monthly_token_cap=monthly_cap,
            # Spec 004 (R2): el tamaño del pool vive aquí desde la 0115.
            weekly_pool_tokens=monthly_cap,
        )
    )
    await db_session.flush()  # fires the trigger

    wallet = await db_session.get(PartnerWallet, partner_id)
    assert wallet is not None, "trigger trg_partners_seed_wallet did not seed the wallet"
    wallet.included_remaining = included
    wallet.purchased_remaining = purchased
    if expires_at is not None:
        wallet.included_expires_at = expires_at
    await db_session.commit()
    return {"partner_id": partner_id, "slug": slug, "monthly_cap": monthly_cap}


#: Idempotency-key prefix of each lane that spends the wallet. Kept in one
#: place because the whole point of spec 004 is that the three lanes debit
#: the same book in the same unit; a test that invents its own prefix would
#: prove nothing about the lane it claims to exercise.
WALLET_LANES: dict[str, str] = {
    "companion": "companion:",  # api/console/companion.py
    "channel": "channel:",  # nexus_worker/metering/consumer.py
    "local_exec": "local_exec:",  # services/local_workstation_metering.py
}


async def spend_from_wallet(
    *,
    partner_id: uuid.UUID,
    qty: int,
    lane: str,
    tenant_id: uuid.UUID | None = None,
    ref: str | None = None,
) -> Any:
    """Debit ``qty`` through one lane, using that lane's real key prefix.

    Calls the production ``debit_wallet`` rather than writing a ledger row by
    hand: the split between buckets, the row lock and the idempotency are the
    behaviour under test, so faking them would test the fake.
    """
    from nexus_api.metering.wallet import debit_wallet

    if lane not in WALLET_LANES:
        raise ValueError(f"unknown lane {lane!r}; expected one of {sorted(WALLET_LANES)}")
    key = f"{WALLET_LANES[lane]}{ref or uuid.uuid4()}"
    return await debit_wallet(
        partner_id=partner_id,
        qty=qty,
        idempotency_key=key,
        tenant_id=tenant_id,
        # The channel may not touch the included pool (R5.2). The factory
        # mirrors what each lane really passes, so a test that claims to
        # exercise a lane exercises that lane's rules too.
        allow_included=lane != "channel",
    )


async def drain_wallet(db_session: AsyncSession, partner_id: uuid.UUID, *, leave: int = 0) -> None:
    """Leave a partner with ``leave`` included tokens and nothing purchased.

    ``leave=1`` is the "one more turn and then paused" setup: the turn starts
    because the book is not empty, drains it, and the next one is refused.

    Spec 004 (R4.6): the cap **is** the book. Lowering
    ``companion_monthly_token_cap`` used to pause a partner because that column
    was compared against a sum over ``companion.runs``; it no longer gates
    anything, so a test that wants "this partner is out of budget" has to say so
    where the platform reads it.
    """
    from nexus_api.db.models import Partner, PartnerWallet

    wallet = await db_session.get(PartnerWallet, partner_id)
    assert wallet is not None
    wallet.included_remaining = leave
    wallet.purchased_remaining = 0
    # The pool SIZE follows the balance too. Leaving them apart would make
    # ``used`` (= size - balance) report a spend that never happened, which is
    # the sort of artefact that gets "fixed" by editing the expected number.
    partner = await db_session.get(Partner, partner_id)
    if partner is not None:
        partner.companion_monthly_token_cap = leave
        partner.weekly_pool_tokens = leave
    await db_session.commit()


async def register_machine(
    client: Any,
    db_session: AsyncSession,
    world: dict[str, Any],
    *,
    hostname: str = "mac.local",
    install_id: str | None = None,
) -> dict[str, Any]:
    """Da de alta una máquina **por el camino nuevo** (spec 012, R3).

    Existe porque varios tests usaban ``/device/pair`` como **preparación** y no
    como sujeto: lo que probaban era el latido, la auditoría o el medidor, y el
    emparejamiento solo era la forma de tener una máquina. Al retirar el código
    (R6) ese arranque se queda sin endpoint, y reescribirlo en cada fichero
    sería cuatro formas distintas de montar lo mismo.

    Registrar exige una **sesión recién confirmada**, así que aquí se crea una
    cuenta de consola de verdad, se le reapunta la membresía del partner y se
    le abre una sesión. Devuelve los encabezados nuevos —los del mundo llevan el
    ``user_id`` de antes, y con ése no hay membresía—, la credencial y el id.
    """
    import uuid as _uuid

    import sqlalchemy as _sa

    from nexus_api.db.models import PartnerMembership
    from nexus_api.services import console_identity

    account = await console_identity.create_account(
        db_session,
        email=f"maq-{_uuid.uuid4().hex[:8]}@example.com",
        password="una-contrasena-larga",
        display_name="Dueña de la máquina",
    )
    await db_session.commit()
    await db_session.execute(
        _sa.update(PartnerMembership)
        .where(PartnerMembership.partner_id == world["partner_id"])
        .values(user_id=str(account.id), email=account.email)
    )
    await db_session.commit()
    await console_identity.start_session(db_session, account)
    await db_session.commit()

    headers = console_headers(user_id=str(account.id), partner_id=world["partner_id"])
    registered = await client.post(
        "/console/workstation/machines",
        json={
            "hostname": hostname,
            "platform": "macos",
            "install_id": install_id or f"instalacion-{_uuid.uuid4().hex[:12]}",
        },
        headers=headers,
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    return {
        "account": account,
        "headers": lambda **kw: console_headers(
            user_id=str(account.id), partner_id=world["partner_id"], **kw
        ),
        "device_id": body["device_id"],
        "credential": body["credential"],
        "body": body,
    }
