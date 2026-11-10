"""Spec 031 · la misma puerta con el teléfono — R2.4, R7.2, R13.1 (tarea T010).

La app no usa el JWT de 60 s de la BFF: trae su propia credencial. Lo que este
fichero fija es que, detrás de la puerta, **la persona es la misma**: el mismo
``ClientPrincipal``, los mismos módulos, la misma RLS. Y que cada petición
vuelve a mirar la fila del teléfono, así un teléfono cerrado deja de leer en
la siguiente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.core import phone_credential
from nexus_api.db.models import ClientMembership, ClientPhone
from tests.conftest import (
    add_client_member,
    add_client_phone,
    make_client_access,
    phone_headers,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def phone(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    ph = await add_client_phone(db_session, membership_id=member["membership_id"])
    return {**ph, "member": member, "world": w}


async def test_the_phone_is_the_same_person_as_the_web(client, phone) -> None:
    web = await client.get("/console/lite/me", headers=phone["member"]["headers"]())
    app = await client.get("/console/lite/me", headers=phone["headers"]())

    assert web.status_code == 200, web.text
    assert app.status_code == 200, app.text
    assert app.json() == web.json()


async def test_a_closed_phone_reads_nothing_on_the_next_request(client, db_session, phone) -> None:
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == phone["phone_id"])
        .values(revoked_at=datetime.now(UTC), revoked_reason="closed_by_person")
    )
    await db_session.commit()

    resp = await client.get("/console/lite/me", headers=phone["headers"]())

    assert resp.status_code == 403
    assert resp.json()["detail"] == {"code": "phone_closed", "reason": "closed_by_person"}


async def test_another_generation_is_unauthorized(client, phone) -> None:
    stale = phone_credential.issue_access_token(phone_id=phone["phone_id"], generation=99)

    resp = await client.get("/console/lite/me", headers=phone_headers(stale))

    assert resp.status_code == 401


async def test_a_phone_that_does_not_exist_is_unauthorized(client, phone) -> None:
    ghost = phone_credential.issue_access_token(phone_id=uuid.uuid4(), generation=1)

    resp = await client.get("/console/lite/me", headers=phone_headers(ghost))

    assert resp.status_code == 401


async def test_a_revoked_membership_closes_the_door(client, db_session, phone) -> None:
    await db_session.execute(
        sa.update(ClientMembership)
        .where(ClientMembership.id == phone["member"]["membership_id"])
        .values(status="revoked")
    )
    await db_session.commit()

    resp = await client.get("/console/lite/me", headers=phone["headers"]())

    assert resp.status_code == 403


@pytest.mark.parametrize("drop", ["X-App-Platform", "X-App-Version"])
async def test_the_app_headers_are_required(client, phone, drop: str) -> None:
    headers = phone["headers"]()
    headers.pop(drop)

    resp = await client.get("/console/lite/me", headers=headers)

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "app_headers_required"


async def test_an_old_app_is_asked_to_update(client, phone, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "customers_app_min_version_ios", "2.0.0")
    monkeypatch.setattr(get_settings(), "customers_app_min_version_reason", "security")

    resp = await client.get("/console/lite/me", headers=phone["headers"](app_version="1.9.9"))

    assert resp.status_code == 403
    assert resp.json()["detail"] == {
        "code": "app_update_required",
        "reason": "security",
        "minimum_version": "2.0.0",
    }
    ok = await client.get("/console/lite/me", headers=phone["headers"](app_version="2.0.0"))
    assert ok.status_code == 200


async def test_the_minimum_waits_for_its_date(client, phone, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "customers_app_min_version_ios", "2.0.0")
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    monkeypatch.setattr(get_settings(), "customers_app_min_version_from", future)

    resp = await client.get("/console/lite/me", headers=phone["headers"](app_version="1.0.0"))

    assert resp.status_code == 200


async def test_use_is_noted_at_most_every_five_minutes(client, db_session, phone) -> None:
    old = datetime.now(UTC) - timedelta(minutes=10)
    await db_session.execute(
        sa.update(ClientPhone).where(ClientPhone.id == phone["phone_id"]).values(last_seen_at=old)
    )
    await db_session.commit()

    await client.get("/console/lite/me", headers=phone["headers"]())
    db_session.expire_all()
    seen = await db_session.scalar(
        sa.select(ClientPhone.last_seen_at).where(ClientPhone.id == phone["phone_id"])
    )
    assert seen is not None and seen > old + timedelta(minutes=9)

    await client.get("/console/lite/me", headers=phone["headers"]())
    db_session.expire_all()
    again = await db_session.scalar(
        sa.select(ClientPhone.last_seen_at).where(ClientPhone.id == phone["phone_id"])
    )
    assert again == seen


async def test_the_web_cannot_use_phone_only_routes(client, phone) -> None:
    resp = await client.put(
        "/console/lite/phones/current/push",
        headers=phone["member"]["headers"](),
        json={"provider": "apns", "token": "a" * 64},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "phone_only"
