"""Spec 047, T062 — editar, archivar, restaurar y eliminar un cliente (historia 14).

``contracts/console-api.md`` §2 sobre ``/console/clients/{ref}``:

- **Editar** con el mismo modal del alta (``PATCH`` con ``If-Match``): nombre,
  nicho, información, país, zona, moneda de los precios y «Solo UE». La zona
  IANA se valida en el servidor (6.2) y el agente usa el nombre o la zona nuevos
  desde el siguiente mensaje: se avisa al runtime (6.3).
- **Archivar** (6.4): sus agentes quedan «Pausado · cliente archivado»
  recordando su estado, se cierra la consola lite y la app, y la respuesta trae
  «Deshacer».
- **Restaurar** (6.5): cada agente vuelve a su estado.
- **Eliminar** (6.6): ``clients:delete``, el cliente archivado y el nombre
  tecleado; ``409`` con la razón legal si es una línea de factura.
- **Auditoría** con antes y después (6.8).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
from nexus_api.core.client_auth import open_client
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AuditLog,
    BusinessProfile,
    Invoice,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from tests.conftest import add_client_member, add_console_member, make_client_access

from ._client_world import add_agent, new_client, roomy, tenant_of

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    await roomy(db_session, console_world)
    return console_world


async def _cultor(client: Any, db_session: AsyncSession, world: dict[str, Any]) -> dict[str, Any]:
    a = world["a"]
    created = await new_client(
        client, a["headers"](), name="Barbería Cultor", niche="Barbería de barrio", country="ES"
    )
    tenant_id = await tenant_of(db_session, a["partner_id"], created["ref"])
    return {
        "ref": created["ref"],
        "tenant_id": tenant_id,
        "url": f"/console/clients/{created['ref']}",
    }


async def _detail(client: Any, headers: dict[str, str], url: str) -> Any:
    resp = await client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp


async def _tenant(db_session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    async with db_session.begin():
        tenant = await db_session.get(Tenant, tenant_id, populate_existing=True)
    assert tenant is not None
    return tenant


# ── editar ──────────────────────────────────────────────────────────────────


async def test_editing_uses_the_modal_fields_with_if_match_and_tells_the_runtime(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    first = await _detail(client, a["headers"](), c["url"])
    body = first.json()
    assert body["niche"] == "Barbería de barrio" and body["lifecycle"] == "active"
    assert first.headers["ETag"] == f'"{body["revision"]}"'
    assert set(body["allowed"]) >= {"edit", "archive", "delete"}

    pubsub = fake_redis.pubsub()
    await pubsub.subscribe(PROMOTE_CHANNEL)
    resp = await client.patch(
        c["url"],
        json={
            "name": "Barbería Cultor Centro",
            "niche": "Barbería clásica",
            "info": "Desde 1998",
            "timezone": "Atlantic/Canary",
            "price_currency": "EUR",
            "eu_only": True,
        },
        headers={**a["headers"](), "If-Match": first.headers["ETag"]},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["name"] == "Barbería Cultor Centro" and out["timezone"] == "Atlantic/Canary"
    assert out["niche"] == "Barbería clásica" and out["info"] == "Desde 1998"
    assert out["revision"] == body["revision"] + 1
    assert resp.headers["ETag"] == f'"{out["revision"]}"'

    tenant = await _tenant(db_session, c["tenant_id"])
    assert (tenant.name, tenant.timezone) == ("Barbería Cultor Centro", "Atlantic/Canary")
    async with db_session.begin():
        mapping = await db_session.scalar(
            sa.select(PartnerTenant).where(PartnerTenant.tenant_id == c["tenant_id"])
        )
    assert mapping is not None and mapping.client_name == "Barbería Cultor Centro"
    async with tenant_scoped_session(db_session, c["tenant_id"]):
        profile = await db_session.get(BusinessProfile, c["tenant_id"], populate_existing=True)
        audit = (
            await db_session.scalars(
                sa.select(AuditLog).where(AuditLog.action == "console.client.update")
            )
        ).all()
    assert profile is not None and profile.timezone == "Atlantic/Canary" and profile.eu_only is True
    (row,) = audit
    assert (
        row.before_json["name"] == "Barbería Cultor"
        and row.after_json["name"] == "Barbería Cultor Centro"
    )
    assert row.before_json["timezone"] != row.after_json["timezone"]
    assert "price_currency" not in row.after_json  # no cambió: no se apunta

    # El runtime se entera: invalida la caché del agente (nombre y zona).
    message = None
    for _ in range(20):
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.05)
        if message:
            break
        await asyncio.sleep(0.01)
    assert message is not None and message["data"] == str(c["tenant_id"])
    await pubsub.aclose()


async def test_the_server_checks_the_iana_zone_and_the_revision(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    etag = (await _detail(client, a["headers"](), c["url"])).headers["ETag"]
    bad = await client.patch(
        c["url"], json={"timezone": "Europe/Madird"}, headers={**a["headers"](), "If-Match": etag}
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_timezone"
    blind = await client.patch(c["url"], json={"name": "Otra"}, headers=a["headers"]())
    assert blind.status_code == 428
    ok = await client.patch(
        c["url"], json={"name": "Cultor"}, headers={**a["headers"](), "If-Match": etag}
    )
    assert ok.status_code == 200
    stale = await client.patch(
        c["url"], json={"name": "Cultor 2"}, headers={**a["headers"](), "If-Match": etag}
    )
    assert stale.status_code == 412 and stale.json()["detail"]["code"] == "revision_conflict"
    # La moneda de la bolsa con saldo dentro se cambia desde Consumo (ola 7).
    fresh = (await _detail(client, a["headers"](), c["url"])).headers["ETag"]
    wallet = await client.patch(
        c["url"], json={"wallet_currency": "EUR"}, headers={**a["headers"](), "If-Match": fresh}
    )
    assert wallet.status_code == 409 and wallet.json()["detail"]["code"] == "bag_currency_locked"


async def test_a_partner_on_todays_console_edits_as_before(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """El partner B no tiene la consola nueva: su ``PATCH`` de siempre sigue."""
    b = world["b"]
    resp = await client.patch(
        f"/console/clients/{b['ref']}", json={"name": "Client B Renamed"}, headers=b["headers"]()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Client B Renamed"
    bad = await client.patch(
        f"/console/clients/{b['ref']}", json={"timezone": "Nowhere/City"}, headers=b["headers"]()
    )
    assert bad.status_code == 422


# ── archivar y restaurar ────────────────────────────────────────────────────


async def test_archiving_pauses_every_agent_closes_the_lite_and_offers_undo(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    citas = await add_agent(db_session, c["tenant_id"], "Citas")
    recordatorios = await add_agent(db_session, c["tenant_id"], "Recordatorios", channel=None)
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=c["tenant_id"])
    await add_client_member(db_session, partner_id=a["partner_id"], tenant_id=c["tenant_id"])

    resp = await client.post(f"{c['url']}/archive", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["lifecycle"] == "archived" and out["undo"] == "restore"
    states = {x["agent_id"]: x for x in out["agents"]}
    for agent in (citas, recordatorios):
        visible = states[str(agent["agent_id"])]["visible_state"]
        assert (visible["code"], visible["pause_reason"]) == ("paused", "client_archived")
    assert states[str(citas["agent_id"])]["before"]["code"] == "serving"
    assert states[str(recordatorios["agent_id"])]["before"]["code"] == "ready_no_channel"

    assert (await _tenant(db_session, c["tenant_id"])).status is TenantStatus.ARCHIVED
    async with db_session.begin():
        assert (
            await open_client(db_session, partner_id=a["partner_id"], tenant_id=c["tenant_id"])
            is None
        )
    again = await client.post(f"{c['url']}/archive", headers=a["headers"]())
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_archived"

    # Restaurar devuelve cada agente a su estado.
    back = await client.post(f"{c['url']}/restore", headers=a["headers"]())
    assert back.status_code == 200, back.text
    states = {x["agent_id"]: x["visible_state"]["code"] for x in back.json()["agents"]}
    assert states == {
        str(citas["agent_id"]): "serving",
        str(recordatorios["agent_id"]): "ready_no_channel",
    }
    assert back.json()["lifecycle"] == "active"
    async with db_session.begin():
        assert (
            await open_client(db_session, partner_id=a["partner_id"], tenant_id=c["tenant_id"])
            is not None
        )

    async with tenant_scoped_session(db_session, c["tenant_id"]):
        rows = (
            await db_session.scalars(
                sa.select(AuditLog)
                .where(AuditLog.action == "console.client.status")
                .order_by(AuditLog.created_at)
            )
        ).all()
    assert [(r.before_json["status"], r.after_json["status"]) for r in rows] == [
        ("active", "archived"),
        ("archived", "active"),
    ]
    assert rows[0].after_json["agents"][str(citas["agent_id"])] == "serving"


async def test_a_paused_client_comes_back_paused(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    async with db_session.begin():
        tenant = await db_session.get(Tenant, c["tenant_id"])
        assert tenant is not None
        tenant.status = TenantStatus.PAUSED
    assert (await client.post(f"{c['url']}/archive", headers=a["headers"]())).status_code == 200
    back = await client.post(f"{c['url']}/restore", headers=a["headers"]())
    assert back.status_code == 200 and back.json()["lifecycle"] == "paused"
    not_archived = await client.post(f"{c['url']}/restore", headers=a["headers"]())
    assert (
        not_archived.status_code == 409 and not_archived.json()["detail"]["code"] == "not_archived"
    )


# ── eliminar ────────────────────────────────────────────────────────────────


async def test_deleting_asks_for_the_permission_the_archive_and_the_name(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    c = await _cultor(client, db_session, world)
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    forbidden = await client.request(
        "DELETE", c["url"], json={"confirm_name": "Barbería Cultor"}, headers=builder["headers"]()
    )
    assert forbidden.status_code == 403

    active = await client.request(
        "DELETE", c["url"], json={"confirm_name": "Barbería Cultor"}, headers=a["headers"]()
    )
    assert active.status_code == 409 and active.json()["detail"]["code"] == "archive_first"
    await client.post(f"{c['url']}/archive", headers=a["headers"]())
    wrong = await client.request(
        "DELETE", c["url"], json={"confirm_name": "Barberia"}, headers=a["headers"]()
    )
    assert wrong.status_code == 409 and wrong.json()["detail"]["code"] == "name_mismatch"

    async with db_session.begin():
        db_session.add(Invoice(tenant_id=c["tenant_id"], period_year=2026, period_month=9))
    legal = await client.request(
        "DELETE", c["url"], json={"confirm_name": "Barbería Cultor"}, headers=a["headers"]()
    )
    assert legal.status_code == 409, legal.text
    detail = legal.json()["detail"]
    assert detail["code"] == "legal_retention" and detail["fix"] == "keep_archived"
    assert "17.3.b" in detail["message"]
    await db_session.execute(sa.delete(Invoice))
    await db_session.commit()

    gone = await client.request(
        "DELETE", c["url"], json={"confirm_name": "Barbería Cultor"}, headers=a["headers"]()
    )
    assert gone.status_code == 204, gone.text
    async with db_session.begin():
        assert await db_session.get(Tenant, c["tenant_id"]) is None
        trail = (
            await db_session.scalars(sa.select(AuditLog).where(AuditLog.action == "tenant.delete"))
        ).all()
    assert trail and trail[-1].actor.startswith("console:")
