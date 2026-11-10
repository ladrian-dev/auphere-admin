"""Spec 056, T029 — el owner o admin del partner abre la consola de su cliente
(historia 3; requisitos 3.3, 3.4, 3.6, 3.7 y 3.8; ``contracts/api.md``).

La pestaña «Acceso» del partner hace exactamente lo que hace la del panel (D3):
llama a los mismos servicios (``services/client_access.py``) con las mismas
reglas. Lo que cambia es quién firma: ``console:<correo>`` en la auditoría, con
la frase «{actor} cambió…» (0225), y que invitar tiene un límite por partner y
minuto (``console_client_invites_per_minute``), porque Resend se comparte.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    ClientInvitation,
    ClientMembership,
    ClientPhone,
    Reservation,
)
from tests.conftest import (
    add_client_member,
    add_client_phone,
    add_console_member,
    make_client_access,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _access(ref: str) -> str:
    return f"/console/clients/{ref}/client-access"


def _members(ref: str) -> str:
    return f"/console/clients/{ref}/client-members"


@pytest.fixture
def mails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """El correo de la invitación, sin salir: lo que se habría mandado."""
    sent: list[dict[str, Any]] = []

    async def _fake(kind: Any, **kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr("nexus_api.services.email.send_template", _fake)
    return sent


async def _whatsapp(db_session: AsyncSession, tenant_id: uuid.UUID) -> None:
    async with tenant_scoped_session(db_session, tenant_id):
        db_session.add(
            Channel(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=f"+3460000{uuid.uuid4().int % 10000:04d}",
                config={"phone_number_id": "PN"},
                status=ChannelStatus.ACTIVE,
            )
        )
    await db_session.commit()


async def _audit(db_session: AsyncSession, tenant_id: uuid.UUID, action: str) -> list[AuditLog]:
    await db_session.commit()
    async with tenant_scoped_session(db_session, tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at)
            )
        ).all()
    await db_session.commit()
    return list(rows)


async def _live_booking(tenant_id: uuid.UUID) -> None:
    sm = get_sessionmaker()
    starts = datetime.now(UTC) + timedelta(days=2)
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        session.add(
            Reservation(
                tenant_id=tenant_id,
                mode="capacity",
                status="confirmed",
                starts_at=starts,
                ends_at=starts + timedelta(minutes=90),
                party_size=4,
                origin="person",
                channel="phone",
                created_by_kind="person",
                contact_name="Ana",
                contact_phone="+56911112222",
            )
        )


# ── la tarjeta «Consola del cliente» ───────────────────────────────────────


async def test_the_owner_opens_panel_and_reservas_and_signs_the_audit(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """Historia 3, escenario 1, y 3.8: queda guardado y auditado con su nombre."""
    a = console_world["a"]
    resp = await client.put(
        _access(a["ref"]),
        headers=a["headers"](),
        json={
            "enabled": True,
            "modules": ["reservas", "panel"],
            "reservas": {"mode": "capacity", "capacity_kind": "bar"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["enabled"] is True
    assert body["modules"] == ["panel", "reservas"]
    assert body["reservas"]["mode"] == "capacity"
    assert "partner" not in body

    read = await client.get(_access(a["ref"]), headers=a["headers"]())
    assert read.status_code == 200 and read.json() == body

    (row,) = await _audit(db_session, a["tenant_id"], "client_access.updated")
    assert row.actor == "console:owner-a@example.com"
    items = (await client.get("/console/audit?lang=es", headers=a["headers"]())).json()["items"]
    (line,) = [i for i in items if i["action"] == "client_access.updated"]
    assert line["summary"].startswith("owner-a@example.com cambió el acceso de")
    assert "Auphere" not in line["summary"]


async def test_an_admin_of_the_partner_can_too(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    a = console_world["a"]
    admin = await add_console_member(db_session, partner_id=a["partner_id"], role="admin")
    resp = await client.put(
        _access(a["ref"]), headers=admin["headers"](), json={"enabled": True, "modules": ["panel"]}
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.parametrize("retired", ["agents", "business"])
async def test_agents_and_business_are_unknown_modules(
    retired: str, client: Any, console_world: dict[str, Any]
) -> None:
    """2.3: tampoco desde el partner."""
    a = console_world["a"]
    resp = await client.put(
        _access(a["ref"]),
        headers=a["headers"](),
        json={"enabled": True, "modules": ["panel", retired]},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "unknown_module"


async def test_the_same_rules_as_the_panel(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """3.3: encendida exige un módulo, la Bandeja un WhatsApp y Reservas su modo."""
    a = console_world["a"]
    cases = [
        ({"enabled": True, "modules": []}, "no_modules"),
        ({"enabled": True, "modules": ["inbox"]}, "inbox_requires_whatsapp"),
        ({"enabled": True, "modules": ["reservas"]}, "reservas_mode_required"),
    ]
    for body, code in cases:
        resp = await client.put(_access(a["ref"]), headers=a["headers"](), json=body)
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == code, resp.text

    await _whatsapp(db_session, a["tenant_id"])
    resp = await client.put(
        _access(a["ref"]),
        headers=a["headers"](),
        json={"enabled": True, "modules": ["inbox", "panel"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["modules"] == ["panel", "inbox"]
    assert resp.json()["whatsapp_connected"] is True


async def test_a_mode_change_with_future_bookings_asks_first(
    client: Any, console_world: dict[str, Any]
) -> None:
    """3.3: cambiar el modo con reservas futuras pide decidir antes de guardar."""
    a = console_world["a"]
    first = await client.put(
        _access(a["ref"]),
        headers=a["headers"](),
        json={
            "enabled": True,
            "modules": ["reservas"],
            "reservas": {"mode": "capacity", "capacity_kind": "bar"},
        },
    )
    assert first.status_code == 200, first.text
    await _live_booking(a["tenant_id"])

    refused = await client.put(
        _access(a["ref"]),
        headers=a["headers"](),
        json={"enabled": True, "modules": ["reservas"], "reservas": {"mode": "services"}},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == {"code": "live_reservations", "count": 1}

    done = await client.put(
        _access(a["ref"]),
        headers=a["headers"](),
        json={
            "enabled": True,
            "modules": ["reservas"],
            "reservas": {"mode": "services", "on_live": "cancel_and_notify"},
        },
    )
    assert done.status_code == 200, done.text
    assert done.json()["reservas"]["mode"] == "services"


# ── la tarjeta «Personas» ──────────────────────────────────────────────────


async def test_inviting_answers_the_link_once_and_sends_the_mail(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], mails: list[Any]
) -> None:
    """3.6: el enlace de un solo uso (21 días), enseñado una vez, y el correo."""
    a = console_world["a"]
    off = await client.post(
        _members(a["ref"]), headers=a["headers"](), json={"email": "ana@negocio.test"}
    )
    assert off.status_code == 409 and off.json()["detail"]["code"] == "access_disabled"

    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    resp = await client.post(
        _members(a["ref"]),
        headers=a["headers"](),
        json={"email": "Ana@Negocio.test", "name": "Ana"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "ana@negocio.test"
    assert body["status"] == "pending"
    assert body["email_sent"] is True
    token = body["accept_path"].rsplit("/", 1)[-1]
    assert body["accept_url"].endswith(f"/invite/{token}")
    assert mails[-1]["variables"]["ACCEPT_URL"] == body["accept_url"]
    row = await db_session.scalar(
        sa.select(ClientInvitation).where(ClientInvitation.id == uuid.UUID(body["id"]))
    )
    assert row is not None and token not in row.token_hash
    assert row.invited_by == "console:owner-a@example.com"
    assert timedelta(days=20) < row.expires_at - datetime.now(UTC) <= timedelta(days=21)

    listed = (await client.get(_access(a["ref"]), headers=a["headers"]())).json()["members"]
    (person,) = [m for m in listed if m["id"] == body["id"]]
    assert person["status"] == "pending" and "accept" not in str(person)

    resent = await client.post(f"{_members(a['ref'])}/{body['id']}/resend", headers=a["headers"]())
    assert resent.status_code == 201, resent.text
    assert resent.json()["accept_path"] != body["accept_path"]
    (row,) = await _audit(db_session, a["tenant_id"], "client_member.resent")
    assert row.actor == "console:owner-a@example.com"


async def test_a_partner_member_cannot_be_invited(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], mails: list[Any]
) -> None:
    """Acota el riesgo aceptado en D3: el partner no se invita a sí mismo."""
    from nexus_api.services import console_identity

    a = console_world["a"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    # Una persona del equipo del partner, con su cuenta de consola.
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    email = f"equipo-{uuid.uuid4().hex[:6]}@agencia.test"
    async with db_session.begin():
        account = await console_identity.create_account(
            db_session, email=email, password="una-clave-larga-y-segura-2026"
        )
        await db_session.execute(
            sa.text("UPDATE partner_memberships SET user_id = :u, email = :e WHERE id = :m"),
            {"u": str(account.id), "e": email, "m": builder["membership_id"]},
        )
    resp = await client.post(_members(a["ref"]), headers=a["headers"](), json={"email": email})
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "account_is_partner_member"
    assert mails == []


async def test_revoking_closes_the_sessions_and_the_phones(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """3.7: en la misma operación, y la respuesta trae la fila ya revocada."""
    a = console_world["a"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    person = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    phone = await add_client_phone(db_session, membership_id=person["membership_id"])
    assert (await client.get("/console/lite/me", headers=person["headers"]())).status_code == 200

    url = f"{_members(a['ref'])}/{person['membership_id']}/revoke"
    for _ in range(2):  # idempotente
        resp = await client.post(url, headers=a["headers"]())
        assert resp.status_code == 200, resp.text
        assert resp.json()["member"]["id"] == str(person["membership_id"])
        assert resp.json()["member"]["status"] == "revoked"

    db_session.expire_all()
    member = await db_session.get(ClientMembership, person["membership_id"])
    assert member is not None and member.status == "revoked"
    closed = await db_session.get(ClientPhone, phone["phone_id"])
    assert closed is not None and closed.revoked_reason == "member_removed"
    await db_session.commit()
    assert (await client.get("/console/lite/me", headers=person["headers"]())).status_code == 403
    assert (await client.get("/console/lite/me", headers=phone["headers"]())).status_code == 403
    (row,) = await _audit(db_session, a["tenant_id"], "client_member.revoked")
    assert row.actor == "console:owner-a@example.com"


async def test_switching_off_closes_everyone(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """3.7: apagar el acceso cierra las sesiones y los teléfonos de todos."""
    a = console_world["a"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    person = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    phone = await add_client_phone(db_session, membership_id=person["membership_id"])
    resp = await client.put(
        _access(a["ref"]), headers=a["headers"](), json={"enabled": False, "modules": ["panel"]}
    )
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    closed = await db_session.get(ClientPhone, phone["phone_id"])
    assert closed is not None and closed.revoked_reason == "access_disabled"
    await db_session.commit()
    assert (await client.get("/console/lite/me", headers=person["headers"]())).status_code == 403


async def test_inviting_has_a_limit_per_partner_and_minute(
    client: Any,
    db_session: AsyncSession,
    console_world: dict[str, Any],
    mails: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Research R3: Resend se comparte (100 al día). Por encima del límite, 429 y
    ningún correo más."""
    monkeypatch.setattr(get_settings(), "console_client_invites_per_minute", 2)
    a = console_world["a"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    codes = []
    for i in range(3):
        resp = await client.post(
            _members(a["ref"]), headers=a["headers"](), json={"email": f"p{i}@negocio.test"}
        )
        codes.append(resp.status_code)
    assert codes == [201, 201, 429], codes
    assert len(mails) == 2
    assert resp.json()["detail"]["code"] == "rate_limited"


async def test_the_default_limit_is_five() -> None:
    assert get_settings().console_client_invites_per_minute == 5
