"""Spec 047, T004 — la consola nueva se activa partner a partner (requisito 55.2).

- un partner sin activar ve la consola de hoy (``v1``); activado, la nueva (``v2``);
- activar y desactivar guardan **quién** y **cuándo** (``console_v2_enabled_by``
  y ``_at``) y dejan una fila de auditoría de plataforma con antes y después,
  nombrando a la persona de Auphere (§IV);
- repetir una activación no cambia quién ni cuándo, ni escribe otra fila;
- desactivar devuelve la consola de hoy (55.5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AuditLog, Partner
from nexus_api.services import console_v2


@pytest.fixture
async def partner_id(db_session: AsyncSession) -> uuid.UUID:
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="Facelad", slug=f"v2-{pid.hex[:8]}"))
    await db_session.commit()
    return pid


async def _partner(db_session: AsyncSession, pid: uuid.UUID) -> Partner:
    async with db_session.begin():
        partner = await db_session.scalar(
            sa.select(Partner).where(Partner.id == pid).execution_options(populate_existing=True)
        )
    assert partner is not None
    return partner


async def _audit(db_session: AsyncSession, pid: uuid.UUID) -> list[AuditLog]:
    async with db_session.begin():
        rows = await db_session.scalars(
            sa.select(AuditLog)
            .where(AuditLog.target == f"partner:{pid}")
            .order_by(AuditLog.created_at, AuditLog.id)
        )
        return list(rows)


def test_a_partner_without_activation_sees_the_console_of_today() -> None:
    assert console_v2.console_version(Partner(name="P", slug="p")) == "v1"


def test_an_activated_partner_sees_the_new_console() -> None:
    partner = Partner(
        name="P", slug="p", console_v2_enabled_at=datetime.now(UTC), console_v2_enabled_by="ana"
    )
    assert console_v2.console_version(partner) == "v2"


async def test_enabling_keeps_who_and_when_and_audits_it(
    db_session: AsyncSession, partner_id: uuid.UUID
) -> None:
    async with db_session.begin():
        state = await console_v2.enable_console_v2(
            db_session, partner_id, actor="operator:ana@auphere.com"
        )
    assert state.version == "v2"
    assert state.enabled_by == "operator:ana@auphere.com"
    assert state.enabled_at is not None

    partner = await _partner(db_session, partner_id)
    assert console_v2.console_version(partner) == "v2"
    assert partner.console_v2_enabled_by == "operator:ana@auphere.com"

    rows = await _audit(db_session, partner_id)
    assert [(r.action, r.actor, r.tenant_id) for r in rows] == [
        ("partner.console_v2_enabled", "operator:ana@auphere.com", None)
    ]
    assert rows[0].before_json == {"console_version": "v1"}
    assert rows[0].after_json == {"console_version": "v2"}


async def test_enabling_twice_changes_nothing(
    db_session: AsyncSession, partner_id: uuid.UUID
) -> None:
    async with db_session.begin():
        first = await console_v2.enable_console_v2(db_session, partner_id, actor="operator:ana")
    async with db_session.begin():
        again = await console_v2.enable_console_v2(db_session, partner_id, actor="operator:luis")

    assert (again.enabled_at, again.enabled_by) == (first.enabled_at, "operator:ana")
    assert len(await _audit(db_session, partner_id)) == 1


async def test_disabling_returns_the_console_of_today(
    db_session: AsyncSession, partner_id: uuid.UUID
) -> None:
    async with db_session.begin():
        await console_v2.enable_console_v2(db_session, partner_id, actor="operator:ana")
    async with db_session.begin():
        state = await console_v2.disable_console_v2(db_session, partner_id, actor="operator:luis")
    assert (state.version, state.enabled_at, state.enabled_by) == ("v1", None, None)

    partner = await _partner(db_session, partner_id)
    assert console_v2.console_version(partner) == "v1"
    assert (partner.console_v2_enabled_at, partner.console_v2_enabled_by) == (None, None)

    rows = await _audit(db_session, partner_id)
    assert [(r.action, r.actor) for r in rows] == [
        ("partner.console_v2_enabled", "operator:ana"),
        ("partner.console_v2_disabled", "operator:luis"),
    ]
    assert rows[1].before_json == {"console_version": "v2"}
    assert rows[1].after_json == {"console_version": "v1"}


async def test_disabling_a_partner_that_was_never_enabled_changes_nothing(
    db_session: AsyncSession, partner_id: uuid.UUID
) -> None:
    async with db_session.begin():
        state = await console_v2.disable_console_v2(db_session, partner_id, actor="operator:ana")
    assert state.version == "v1"
    assert await _audit(db_session, partner_id) == []


async def test_an_unknown_partner_is_a_named_no(db_session: AsyncSession) -> None:
    async with db_session.begin():
        with pytest.raises(console_v2.ConsoleV2Error) as err:
            await console_v2.enable_console_v2(db_session, uuid.uuid4(), actor="operator:ana")
    assert (err.value.code, err.value.status) == ("unknown_partner", 404)


async def test_the_person_is_required(db_session: AsyncSession, partner_id: uuid.UUID) -> None:
    async with db_session.begin():
        with pytest.raises(ValueError):
            await console_v2.enable_console_v2(db_session, partner_id, actor=" ")
