"""WP-25 — scripts/seed_synthetic.py contra la BD de test real.

El seeder corre con su propio engine (fuera del savepoint del conftest),
así que cada test limpia lo suyo con ``--wipe`` / borrado explícito para
no contaminar al resto de la suite.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "seed_synthetic.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("seed_synthetic", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_seed_creates_volumes_and_wipe_is_idempotent():
    mod = _load_module()

    created = await mod.seed(tenants=2, conversations=4, messages=16, seed=1, wipe=True)
    assert created == {"tenants": 2, "conversations": 4, "messages": 16}

    from nexus_api.db.models import Conversation, Message, Tenant

    engine = create_async_engine(mod._dsn())
    try:
        async with engine.begin() as conn:
            tenant_rows = (
                (
                    await conn.execute(
                        sa.select(Tenant.__table__.c.id).where(
                            Tenant.__table__.c.slug.like("synthetic-%")
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(tenant_rows) == 2

            # Reparto exacto por tenant (el enforcement RLS en sí lo cubre
            # tests/isolation/ con roles no-superuser; el user del compose
            # local es superuser y bypassa RLS, así que aquí contamos
            # explícito).
            for tid in tenant_rows:
                per_tenant = await conn.scalar(
                    sa.select(sa.func.count())
                    .select_from(Message.__table__)
                    .where(Message.__table__.c.tenant_id == tid)
                )
                assert per_tenant == 8  # 16 mensajes repartidos entre 2 tenants

        # Re-seed con wipe: mismo estado final, no acumulación.
        created2 = await mod.seed(tenants=2, conversations=4, messages=16, seed=2, wipe=True)
        assert created2["tenants"] == 2

        async with engine.begin() as conn:
            total = await conn.scalar(
                sa.select(sa.func.count())
                .select_from(Tenant.__table__)
                .where(Tenant.__table__.c.slug.like("synthetic-%"))
            )
            assert total == 2
    finally:
        # Limpieza total para el resto de la suite.
        await mod.seed(tenants=1, conversations=1, messages=1, seed=3, wipe=True)
        async with engine.begin() as conn:
            rows = (
                await conn.execute(
                    sa.select(Tenant.__table__.c.id, Tenant.__table__.c.slug).where(
                        Tenant.__table__.c.slug.like("synthetic-%")
                    )
                )
            ).all()
            for tid, _ in rows:
                await conn.execute(
                    sa.text("SELECT set_config('app.tenant_id', :tid, false)"),
                    {"tid": str(tid)},
                )
                await conn.execute(
                    sa.delete(Conversation.__table__).where(
                        Conversation.__table__.c.tenant_id == tid
                    )
                )
                await conn.execute(
                    sa.text("DELETE FROM customers WHERE tenant_id = :tid"),
                    {"tid": str(tid)},
                )
                await conn.execute(
                    sa.text("DELETE FROM channels WHERE tenant_id = :tid"),
                    {"tid": str(tid)},
                )
                await conn.execute(sa.delete(Tenant.__table__).where(Tenant.__table__.c.id == tid))
        await engine.dispose()


async def test_seeded_channel_resolves_like_the_meta_webhook():
    """El seed solo vale para carga si el webhook resuelve tenant con él.

    ``resolve_channel_tenant('meta', <identifier>)`` es literalmente lo que
    llama ``api/webhooks/meta.py``. El seeder nació escribiendo
    ``provider='whatsapp_meta'``, con lo que la función devolvía NULL, el
    webhook contestaba 200 y descartaba el evento: la rampa de carga medía
    el ack y NADA del pipeline (visto en staging el 2026-08-09).
    """
    mod = _load_module()

    await mod.seed(tenants=1, conversations=1, messages=1, seed=7, wipe=True)

    engine = create_async_engine(mod._dsn())
    try:
        async with engine.begin() as conn:
            identifier = await conn.scalar(
                sa.text(
                    "SELECT provider_identifier FROM channels "
                    "WHERE config->>'synthetic' = 'true' LIMIT 1"
                )
            )
            assert identifier is not None, "el seed debe dejar un canal sintético"

            resolved = await conn.scalar(
                sa.text("SELECT resolve_channel_tenant('meta', :i)"),
                {"i": identifier},
            )
            assert resolved is not None, (
                "el canal sembrado no resuelve tenant para provider='meta' — "
                "el webhook descartaría todo el tráfico de la rampa"
            )
    finally:
        async with engine.begin() as conn:
            await mod._wipe_synthetic(conn)
        await engine.dispose()


async def test_seed_refuses_on_non_synthetic_tenants():
    """Guarda GDPR: una BD con tenants reales jamás es destino del seed."""
    mod = _load_module()

    from nexus_api.db.models import Tenant, TenantPlan, TenantStatus

    engine = create_async_engine(mod._dsn())
    real_id = uuid.uuid4()
    try:
        async with engine.begin() as conn:
            await conn.execute(
                sa.insert(Tenant.__table__).values(
                    id=real_id,
                    name="Cliente Real SpA",
                    slug=f"realco-{real_id.hex[:8]}",
                    plan=TenantPlan.PRO.value,
                    status=TenantStatus.ACTIVE.value,
                )
            )

        with pytest.raises(SystemExit, match="no sintéticos"):
            await mod.seed(tenants=1, conversations=1, messages=1, seed=1, wipe=False)
    finally:
        async with engine.begin() as conn:
            await conn.execute(sa.delete(Tenant.__table__).where(Tenant.__table__.c.id == real_id))
        await engine.dispose()


def test_refuses_production_environment(monkeypatch):
    mod = _load_module()
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "production")
    with pytest.raises(SystemExit, match="producción"):
        mod._refuse_if_production()
