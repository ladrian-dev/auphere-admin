"""Allowlist F2: FORCE RLS, A no ve a B, sin GUC = cero filas."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"


async def _as_app(session, partner_id: uuid.UUID | None) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.partner_id', :p, false)"),
        {"p": "" if partner_id is None else str(partner_id)},
    )
    await session.execute(sa.text("SET ROLE nexus_app"))


async def _seed_partner(session, partner_id: uuid.UUID, slug: str) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO partners (id, name, slug, status, console_enabled) "
            "VALUES (:id, :n, :s, 'active', true) ON CONFLICT (id) DO NOTHING"
        ),
        {"id": str(partner_id), "n": slug, "s": slug},
    )


async def test_no_guc_yields_zero_allowlist_rows() -> None:
    a = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, a, f"al-{a.hex[:8]}")
        await session.commit()

    async with sm() as session:
        await _as_app(session, None)
        n = await session.scalar(sa.text("SELECT count(*) FROM partner_model_allowlist"))
        assert n == 0


async def test_partner_a_cannot_see_partner_b_allowlist() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_partner(session, a, f"ala-{a.hex[:8]}")
        await _seed_partner(session, b, f"alb-{b.hex[:8]}")
        await session.commit()

    async with sm() as session:
        await _as_app(session, a)
        ids = (await session.scalars(sa.text("SELECT model_id FROM partner_model_allowlist"))).all()
        assert SOL in ids
        assert TERRA in ids
        partners = (
            await session.scalars(
                sa.text("SELECT DISTINCT partner_id FROM partner_model_allowlist")
            )
        ).all()
        assert partners == [a]
