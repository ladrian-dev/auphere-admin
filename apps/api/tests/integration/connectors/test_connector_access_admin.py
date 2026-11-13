"""Spec 060, T030 — la API del panel para el acceso a conectores por partner,
contra ``contracts/admin-api.md`` (requisitos 1.7, 2, 3 y 4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    AuditLog,
    ConnectorAccessDefault,
    ConnectorPartnerAccess,
    Partner,
)

from ..business._business_world import Biz, new_business
from ._activation_world import SLUG, agent_with_spec, connect, seed_integration

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def world(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> tuple[Biz, Biz]:
    a = await new_business(client, db_session, console_world, name="Tienda A", label="a")
    b = await new_business(client, db_session, console_world, name="Tienda B", label="b")
    for biz in (a, b):
        partner = await db_session.get(Partner, biz.partner_id)
        assert partner is not None
        partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    return a, b


@pytest.fixture
async def operator_id(db_session: AsyncSession) -> str:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return str(account.id)


async def _put_partner(
    client: Any, headers: dict[str, str], partner_id: uuid.UUID, body: dict[str, Any]
) -> Any:
    return await client.put(
        f"/admin/connectors/{SLUG}/partners/{partner_id}", json=body, headers=headers
    )


async def test_both_views_show_and_write_the_same_decision(
    client: Any,
    db_session: AsyncSession,
    world: tuple[Biz, Biz],
    admin_headers: dict[str, str],
    seeded_catalog: None,
    fake_composio: Any,
    operator_id: str,
) -> None:
    a, b = world
    await seed_integration(db_session)
    h = {**admin_headers, "X-Operator-Id": str(operator_id)}

    view = await client.get(f"/admin/partners/{a.partner_id}/connectors", headers=h)
    assert view.status_code == 200, view.text
    item = next(i for i in view.json()["items"] if i["slug"] == SLUG)
    assert item["partner_state"] == "default" and item["effective"] is True, "1.1 y 2.1"
    assert all(
        i["slug"] not in {"whatsapp_meta", "tiktok_bm", "googlecalendar"}
        for i in view.json()["items"]
    )

    done = await _put_partner(client, h, b.partner_id, {"state": "disabled", "reason": "Solo A"})
    assert done.status_code == 200, done.text
    assert done.json()["partner_state"] == "disabled" and done.json()["effective"] is False

    access = await client.get(f"/admin/connectors/{SLUG}/access", headers=h)
    assert access.status_code == 200, access.text
    decision = next(p for p in access.json()["partners"] if p["partner_id"] == str(b.partner_id))
    assert decision["state"] == "disabled" and decision["reason"] == "Solo A", "3.3"

    back = await _put_partner(client, h, b.partner_id, {"state": "default", "reason": "Vuelve"})
    assert back.status_code == 200 and back.json()["partner_state"] == "default", "2.3"

    audits = (
        await db_session.scalars(
            sa.select(AuditLog).where(AuditLog.action == "connector_access.partner_changed")
        )
    ).all()
    assert len(audits) == 2
    assert audits[0].after_json == {"enabled": False, "reason": "Solo A"}
    assert audits[1].before_json == {"enabled": False}


async def test_reason_and_managed_connectors_are_checked(
    client: Any,
    db_session: AsyncSession,
    world: tuple[Biz, Biz],
    admin_headers: dict[str, str],
    seeded_catalog: None,
    fake_composio: Any,
    operator_id: str,
) -> None:
    a, _b = world
    await seed_integration(db_session)
    h = {**admin_headers, "X-Operator-Id": str(operator_id)}
    no_reason = await _put_partner(client, h, a.partner_id, {"state": "disabled", "reason": " "})
    assert no_reason.status_code == 422 and no_reason.json()["detail"]["code"] == "reason_required"
    channel = await client.put(
        f"/admin/connectors/whatsapp_meta/partners/{a.partner_id}",
        json={"state": "disabled", "reason": "No aplica"},
        headers=h,
    )
    assert channel.status_code == 422, channel.text
    assert channel.json()["detail"]["code"] == "connector_not_managed"
    unknown = await client.put(
        f"/admin/connectors/no_existe_060/partners/{a.partner_id}",
        json={"state": "disabled", "reason": "No aplica"},
        headers=h,
    )
    assert unknown.status_code == 404


async def test_losing_access_with_live_clients_asks_to_confirm_first(
    client: Any,
    db_session: AsyncSession,
    world: tuple[Biz, Biz],
    admin_headers: dict[str, str],
    seeded_catalog: None,
    fake_composio: Any,
    operator_id: str,
) -> None:
    """Requisitos 4.1, 4.2 y 4.4."""
    _a, b = world
    connector = await seed_integration(db_session)
    await agent_with_spec(db_session, b, "Ventas")
    await connect(db_session, b, connector)
    h = {**admin_headers, "X-Operator-Id": str(operator_id)}

    asked = await _put_partner(client, h, b.partner_id, {"state": "disabled", "reason": "Solo A"})
    assert asked.status_code == 409, asked.text
    detail = asked.json()["detail"]
    assert detail["code"] == "confirm_required"
    assert detail["totals"]["clients"] == 1
    assert detail["affected"][0]["clients"][0]["tenant_id"] == str(b.tenant_id)
    # El agente nombra sus herramientas sin activación: también cuenta.
    assert detail["totals"]["agents"] == 1
    assert (
        await db_session.scalar(sa.select(sa.func.count()).select_from(ConnectorPartnerAccess))
    ) == 0

    confirmed = await _put_partner(
        client, h, b.partner_id, {"state": "disabled", "reason": "Solo A", "confirm": True}
    )
    assert confirmed.status_code == 200, confirmed.text


async def test_the_default_flip_reaches_undecided_partners_and_partnerless_clients(
    client: Any,
    db_session: AsyncSession,
    world: tuple[Biz, Biz],
    admin_headers: dict[str, str],
    seeded_catalog: None,
    fake_composio: Any,
    operator_id: str,
) -> None:
    """Requisitos 3.2 y 4.1: quien tiene decisión propia «habilitado» no cuenta."""
    a, b = world
    connector = await seed_integration(db_session)
    for biz in (a, b):
        await agent_with_spec(db_session, biz, "Ventas")
        await connect(db_session, biz, connector)
    h = {**admin_headers, "X-Operator-Id": str(operator_id)}
    keep = await _put_partner(client, h, a.partner_id, {"state": "enabled", "reason": "Suyo"})
    assert keep.status_code == 200, keep.text

    asked = await client.put(
        f"/admin/connectors/{SLUG}/access/default",
        json={"enabled": False, "reason": "Solo para A"},
        headers=h,
    )
    assert asked.status_code == 409, asked.text
    affected = {c["tenant_id"] for p in asked.json()["detail"]["affected"] for c in p["clients"]}
    assert affected == {str(b.tenant_id)}

    done = await client.put(
        f"/admin/connectors/{SLUG}/access/default",
        json={"enabled": False, "reason": "Solo para A", "confirm": True},
        headers=h,
    )
    assert done.status_code == 200, done.text
    assert done.json()["default_enabled"] is False
    row = await db_session.get(ConnectorAccessDefault, SLUG)
    assert row is not None and row.enabled is False

    catalog = await client.get("/admin/connectors", headers=h)
    entry = next(c for c in catalog.json() if c["slug"] == SLUG)
    assert entry["access"] == {"default_enabled": False, "partner_decisions": 1}, "3.4"

    installs = await client.get(f"/admin/tenants/{b.tenant_id}/connectors", headers=h)
    mine = next(c for c in installs.json() if c["connector_slug"] == SLUG)
    assert mine["available_for_partner"] is False, "3.5"


async def test_a_partners_default_connector_cannot_be_taken_away(
    client: Any,
    db_session: AsyncSession,
    world: tuple[Biz, Biz],
    admin_headers: dict[str, str],
    seeded_catalog: None,
    fake_composio: Any,
    operator_id: str,
) -> None:
    """Requisito 4.3: aunque venga ``confirm``."""
    _a, b = world
    await seed_integration(db_session)
    partner = await db_session.get(Partner, b.partner_id)
    assert partner is not None
    partner.default_connector_slug = SLUG
    await db_session.commit()
    h = {**admin_headers, "X-Operator-Id": str(operator_id)}
    refused = await _put_partner(
        client, h, b.partner_id, {"state": "disabled", "reason": "No aplica", "confirm": True}
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "partner_default_connector"
    assert refused.json()["detail"]["partners"][0]["id"] == str(b.partner_id)


async def test_a_deleted_partner_takes_its_decisions_with_it(
    db_session: AsyncSession, world: tuple[Biz, Biz]
) -> None:
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="Efímero", slug=f"ef-{pid.hex[:6]}"))
    await db_session.flush()
    db_session.add(
        ConnectorPartnerAccess(
            connector_slug=SLUG, partner_id=pid, enabled=False, reason="t", set_by="t"
        )
    )
    await db_session.commit()
    await db_session.execute(sa.delete(Partner).where(Partner.id == pid))
    await db_session.commit()
    left = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConnectorPartnerAccess)
        .where(ConnectorPartnerAccess.partner_id == pid)
    )
    assert left == 0


async def test_only_auphere_reaches_these_routes(client: Any, world: tuple[Biz, Biz]) -> None:
    """Requisito 1.7: sin el token del panel, nada; con el de un partner, tampoco."""
    a, _b = world
    anon = await client.get(f"/admin/partners/{a.partner_id}/connectors")
    assert anon.status_code in (401, 403)
    as_partner = await client.get(f"/admin/connectors/{SLUG}/access", headers=a.headers())
    assert as_partner.status_code in (401, 403)


async def test_a_partner_cannot_take_as_default_a_connector_it_cannot_use(
    client: Any,
    db_session: AsyncSession,
    world: tuple[Biz, Biz],
    admin_headers: dict[str, str],
    seeded_catalog: None,
    fake_composio: Any,
) -> None:
    """Requisito 4.3, del otro lado: el alta de sus clientes fallaría."""
    _a, b = world
    await seed_integration(db_session)
    db_session.add(
        ConnectorPartnerAccess(
            connector_slug=SLUG, partner_id=b.partner_id, enabled=False, reason="t", set_by="t"
        )
    )
    await db_session.commit()
    resp = await client.patch(
        f"/admin/partners/{b.partner_id}",
        json={"default_connector_slug": SLUG},
        headers=admin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "default_connector_unavailable"
