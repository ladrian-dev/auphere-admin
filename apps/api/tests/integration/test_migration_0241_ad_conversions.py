"""Spec 076 — la migración 0241: clics de anuncio, medición por número y cola de eventos.

Tres tablas de tenant (``customer_ad_referrals``, ``channel_ad_measurement`` y
``ad_conversion_events``), con RLS forzada, FK compuestas y sus CHECK, y la frase
de auditoría de ``console.channel.ad_measurement``.

Baja a 0240 y vuelve a subir en su propio proceso de Alembic, y deja la base en
head pase lo que pase.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0240_respond_bindings_to_agents"
_TABLES = ("customer_ad_referrals", "channel_ad_measurement", "ad_conversion_events")

_WORDS = """
SELECT summary_es, summary_en FROM console_audit_vocabulary
WHERE action = 'console.channel.ad_measurement'
"""


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args], cwd=_API, capture_output=True, text=True, check=False
    )


@pytest.fixture
def at_head_afterwards() -> Any:
    yield
    _alembic("upgrade", "head")


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _tables() -> set[str]:
    rows = await _exec(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY(:t)",
        t=list(_TABLES),
    )
    return {r[0] for r in rows}


async def _columns(table: str) -> dict[str, tuple[str, str, int | None]]:
    rows = await _exec(
        """
        SELECT column_name, data_type, is_nullable, character_maximum_length
        FROM information_schema.columns WHERE table_name = :t
        """,
        t=table,
    )
    return {name: (kind, nullable, length) for name, kind, nullable, length in rows}


async def _world() -> dict[str, uuid.UUID]:
    """Un tenant con un número, un contacto y su conversación."""
    pid, tid = uuid.uuid4(), uuid.uuid4()
    channel, customer, conversation = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _exec(
        "INSERT INTO partners (id, name, slug) VALUES (:i, 'P', :s)", i=pid, s=f"p-{pid.hex[:10]}"
    )
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:i, 'T', :s, 'pro', 'active')",
        i=tid,
        s=f"ad-{tid.hex[:10]}",
    )
    await _exec(
        "INSERT INTO channels (id, tenant_id, type, provider, provider_identifier, config) "
        "VALUES (:i, :t, 'whatsapp', 'meta', :n, '{}'::jsonb)",
        i=channel,
        t=tid,
        n=f"+569{tid.int % 10**8:08d}",
    )
    await _exec(
        "INSERT INTO customers (id, tenant_id, identifier, preferences) "
        "VALUES (:i, :t, '56911112222', '{}'::jsonb)",
        i=customer,
        t=tid,
    )
    await _exec(
        "INSERT INTO conversations (id, tenant_id, customer_id, channel_id, status) "
        "VALUES (:i, :t, :c, :ch, 'open')",
        i=conversation,
        t=tid,
        c=customer,
        ch=channel,
    )
    return {"tenant": tid, "channel": channel, "customer": customer, "conversation": conversation}


async def test_0241_creates_the_tables_and_takes_them_back(at_head_afterwards) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    assert await _tables() == set()
    assert await _exec(_WORDS) == []

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr
    assert await _tables() == set(_TABLES)

    # La frase de auditoría usa solo lo que la consola sabe rellenar.
    ((es, en),) = await _exec(_WORDS)
    assert "{actor}" in es and "{client}" in es and "{actor}" in en and "{client}" in en


async def test_0241_column_shapes() -> None:
    ref = await _columns("customer_ad_referrals")
    assert ref["provider_message_id"] == ("character varying", "NO", 512)
    assert ref["source_type"] == ("character varying", "NO", 8)
    assert ref["source_id"] == ("character varying", "YES", 64)
    assert ref["source_url"] == ("character varying", "YES", 512)
    assert ref["headline"] == ("character varying", "YES", 200)
    assert ref["ad_text"] == ("character varying", "YES", 500)
    assert ref["ctwa_clid"] == ("character varying", "YES", 256)
    assert ref["clicked_at"][:2] == ("timestamp with time zone", "NO")
    assert ref["conversation_id"][1] == "YES"

    m = await _columns("channel_ad_measurement")
    assert m["enabled"][:2] == ("boolean", "NO")
    assert m["meta_dataset_id"] == ("character varying", "YES", 64)
    assert m["last_error_code"] == ("character varying", "YES", 40)

    ev = await _columns("ad_conversion_events")
    assert ev["event_id"] == ("character varying", "NO", 128)
    assert ev["value_minor"][:2] == ("bigint", "YES")
    assert ev["currency"] == ("character varying", "YES", 3)
    assert ev["cancels_event_id"][1] == "YES"
    assert ev["lease_until"][:2] == ("timestamp with time zone", "YES")
    # Ni el teléfono ni su hash se guardan en la cola (research D7).
    assert not {"phone", "ph", "phone_hash", "recipient_phone"} & ev.keys()


async def test_0241_force_rls_and_policies() -> None:
    rows = await _exec(
        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(:t)",
        t=list(_TABLES),
    )
    assert {r[0]: (r[1], r[2]) for r in rows} == {t: (True, True) for t in _TABLES}
    policies = await _exec(
        "SELECT tablename, policyname FROM pg_policies WHERE tablename = ANY(:t)", t=list(_TABLES)
    )
    assert {(t, f"{t}_tenant_isolation") for t in _TABLES} <= set(policies)


async def test_0241_composite_foreign_keys() -> None:
    rows = await _exec(
        """
        SELECT conrelid::regclass::text, confrelid::regclass::text,
               array_length(conkey, 1)
        FROM pg_constraint WHERE contype = 'f' AND conrelid::regclass::text = ANY(:t)
        """,
        t=list(_TABLES),
    )
    refs = {(a, b, n) for a, b, n in rows}
    # Toda FK a una tabla de tenant es compuesta (tenant_id, x).
    for src, dst, n in refs:
        if dst != "tenants":
            assert n == 2, (src, dst)
    assert ("customer_ad_referrals", "customers", 2) in refs
    assert ("customer_ad_referrals", "conversations", 2) in refs
    assert ("customer_ad_referrals", "channels", 2) in refs
    assert ("channel_ad_measurement", "channels", 2) in refs
    assert ("ad_conversion_events", "customer_ad_referrals", 2) in refs
    assert ("ad_conversion_events", "ad_conversion_events", 2) in refs


async def test_0241_referral_is_unique_per_message() -> None:
    w = await _world()
    sql = (
        "INSERT INTO customer_ad_referrals (tenant_id, customer_id, conversation_id, channel_id, "
        "provider_message_id, source_type, clicked_at) "
        "VALUES (:t, :c, :cv, :ch, 'wamid.1', 'ad', now())"
    )
    params = {"t": w["tenant"], "c": w["customer"], "cv": w["conversation"], "ch": w["channel"]}
    await _exec(sql, **params)
    with pytest.raises(IntegrityError):
        await _exec(sql, **params)


async def test_0241_referral_source_type_check() -> None:
    w = await _world()
    with pytest.raises(IntegrityError):
        await _exec(
            "INSERT INTO customer_ad_referrals (tenant_id, customer_id, channel_id, "
            "provider_message_id, source_type, clicked_at) "
            "VALUES (:t, :c, :ch, 'wamid.x', 'story', now())",
            t=w["tenant"],
            c=w["customer"],
            ch=w["channel"],
        )


async def test_0241_measurement_is_one_per_number() -> None:
    w = await _world()
    sql = "INSERT INTO channel_ad_measurement (tenant_id, channel_id) VALUES (:t, :ch)"
    await _exec(sql, t=w["tenant"], ch=w["channel"])
    rows = await _exec(
        "SELECT enabled FROM channel_ad_measurement WHERE channel_id = :ch", ch=w["channel"]
    )
    assert rows == [(False,)]
    with pytest.raises(IntegrityError):
        await _exec(sql, t=w["tenant"], ch=w["channel"])


@pytest.mark.parametrize(
    ("column", "value"),
    [("event_name", "Schedule"), ("status", "queued"), ("source_kind", "appointment")],
)
async def test_0241_event_checks(column: str, value: str) -> None:
    w = await _world()
    values = {
        "event_name": "Purchase",
        "status": "pending",
        "source_kind": "reservation",
        column: value,
    }
    with pytest.raises(IntegrityError):
        await _exec(
            "INSERT INTO ad_conversion_events (tenant_id, channel_id, customer_id, source_kind, "
            "source_id, event_name, event_id, event_time, status) "
            "VALUES (:t, :ch, :c, :sk, 'x', :en, :eid, now(), :st)",
            t=w["tenant"],
            ch=w["channel"],
            c=w["customer"],
            sk=values["source_kind"],
            en=values["event_name"],
            eid=f"reservation:x:{values['event_name']}",
            st=values["status"],
        )


async def test_0241_event_id_is_unique_per_tenant() -> None:
    w = await _world()
    sql = (
        "INSERT INTO ad_conversion_events (tenant_id, channel_id, customer_id, source_kind, "
        "source_id, event_name, event_id, event_time) "
        "VALUES (:t, :ch, :c, 'reservation', 'r1', 'Purchase', 'reservation:r1:Purchase', now())"
    )
    await _exec(sql, t=w["tenant"], ch=w["channel"], c=w["customer"])
    with pytest.raises(IntegrityError):
        await _exec(sql, t=w["tenant"], ch=w["channel"], c=w["customer"])


async def test_0241_deleting_the_tenant_takes_everything() -> None:
    w = await _world()
    await _exec(
        "INSERT INTO customer_ad_referrals (tenant_id, customer_id, channel_id, "
        "provider_message_id, source_type, clicked_at) "
        "VALUES (:t, :c, :ch, 'wamid.del', 'ad', now())",
        t=w["tenant"],
        c=w["customer"],
        ch=w["channel"],
    )
    await _exec(
        "INSERT INTO channel_ad_measurement (tenant_id, channel_id) VALUES (:t, :ch)",
        t=w["tenant"],
        ch=w["channel"],
    )
    await _exec("DELETE FROM tenants WHERE id = :t", t=w["tenant"])
    for table in _TABLES:
        assert await _exec(f"SELECT 1 FROM {table} WHERE tenant_id = :t", t=w["tenant"]) == []
