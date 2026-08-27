"""F5 RLS: admin_impersonation_sessions is FORCE + app.is_admin, not partner."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker
from nexus_api.services import operator_identity

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_without_is_admin_nexus_app_sees_zero_rows(db_session, console_world) -> None:
    async with db_session.begin():
        account = await operator_identity.create_account(
            db_session,
            email="rls-ops@auphere.test",
            password="operator-password-1",
            role="admin",
        )
    partner_id = console_world["a"]["partner_id"]
    session_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(sa.text("SELECT set_config('app.is_admin', 'true', true)"))
        await session.execute(
            sa.text(
                "INSERT INTO admin_impersonation_sessions "
                "(id, operator_id, partner_id, reason, ttl_seconds, expires_at) "
                "VALUES (:id, :op, :p, :r, 900, :e)"
            ),
            {
                "id": str(session_id),
                "op": str(account.id),
                "p": str(partner_id),
                "r": "soporte ticket RLS",
                "e": datetime.now(UTC) + timedelta(minutes=15),
            },
        )
        await session.commit()

    async with sm() as session:
        await session.execute(sa.text("SELECT set_config('app.is_admin', '', true)"))
        await session.execute(sa.text("SET ROLE nexus_app"))
        hidden = await session.scalar(sa.text("SELECT count(*) FROM admin_impersonation_sessions"))
        assert hidden == 0
        await session.execute(sa.text("RESET ROLE"))

    async with sm() as session:
        await session.execute(sa.text("SELECT set_config('app.is_admin', 'true', true)"))
        await session.execute(sa.text("SET ROLE nexus_app"))
        visible = await session.scalar(sa.text("SELECT count(*) FROM admin_impersonation_sessions"))
        assert visible == 1
        await session.execute(sa.text("RESET ROLE"))

    async with sm() as session:
        await session.execute(
            sa.text("SELECT set_config('app.partner_id', :p, true)"), {"p": str(partner_id)}
        )
        await session.execute(sa.text("SELECT set_config('app.is_admin', '', true)"))
        await session.execute(sa.text("SET ROLE nexus_app"))
        by_partner = await session.scalar(
            sa.text("SELECT count(*) FROM admin_impersonation_sessions")
        )
        assert by_partner == 0
        await session.execute(sa.text("RESET ROLE"))


async def test_nexus_app_has_no_bypassrls() -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        flag = await session.scalar(
            sa.text("SELECT rolbypassrls FROM pg_roles WHERE rolname = 'nexus_app'")
        )
    assert flag is False


async def test_apply_partner_clears_is_admin_guc(console_world) -> None:
    from nexus_api.core.partner_context import apply_admin_to_session, apply_partner_to_session

    partner_id = console_world["a"]["partner_id"]
    sm = get_sessionmaker()
    async with sm() as session:
        await apply_admin_to_session(session)
        before = await session.scalar(sa.text("SELECT current_setting('app.is_admin', true)"))
        assert before == "true"
        await apply_partner_to_session(session, partner_id)
        after = await session.scalar(sa.text("SELECT current_setting('app.is_admin', true)"))
        assert after in ("", None)
