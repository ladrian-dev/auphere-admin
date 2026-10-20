"""Spec 031 · R1 (enmienda del 2026-10-20) — entrar en la app con correo y
contraseña (tarea T114).

La app tiene su propia entrada; nada pasa por la consola de partners. Las
reglas son las del login de la web: el mismo hash, el mismo bloqueo de la
cuenta y límites por correo y por IP. Y un rechazo que no dice qué falló.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.db.models import AuditLog, ClientMembership, ClientPhone, PartnerMembership
from nexus_api.services.console_identity import hash_password
from tests.conftest import make_client_access, make_console_account

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SIGN_IN = "/app/sign-in/password"
PASSWORD = "Una-contraseña-de-prueba-1"


async def _with_password(db_session, account: uuid.UUID, password: str = PASSWORD) -> None:
    await db_session.execute(
        sa.text("UPDATE console_auth.principals SET password_hash = :h WHERE id = :i"),
        {"h": hash_password(password), "i": str(account)},
    )
    await db_session.commit()


@pytest.fixture
def email() -> str:
    """Único por prueba: las cuentas de ``console_auth`` no se vacían entre pruebas."""
    return f"valeria-{uuid.uuid4().hex[:8]}@minegocio.test"


@pytest.fixture
async def person(db_session, console_world, email) -> dict[str, Any]:
    """Una persona de cliente con cuenta y contraseña de verdad."""
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    account = await make_console_account(db_session, email=email)
    await _with_password(db_session, account)
    membership_id = uuid.uuid4()
    db_session.add(
        ClientMembership(
            id=membership_id,
            partner_id=w["partner_id"],
            tenant_id=w["tenant_id"],
            user_id=str(account),
            email=email,
            display_name="Valeria Ríos",
            status="active",
        )
    )
    await db_session.commit()
    return {"account": account, "membership_id": membership_id, "world": w, "email": email}


def _body(person: dict[str, Any], **over: Any) -> dict[str, Any]:
    body = {
        "email": person["email"],
        "password": PASSWORD,
        "platform": "android",
        "display_name": "Pixel de Valeria",
        "install_id": uuid.uuid4().hex,
        "app_version": "1.0.0",
        "locale": "es",
    }
    body.update(over)
    return body


async def test_the_right_password_lands_inside_with_the_clients_modules(client, person) -> None:
    resp = await client.post(SIGN_IN, json=_body(person, email=f"  {person['email'].upper()} "))

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {"phone_id", "access_token", "expires_in", "refresh_token"}
    me = await client.get(
        "/console/lite/me",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
            "X-App-Platform": "android",
            "X-App-Version": "1.0.0",
        },
    )
    assert me.status_code == 200, me.text
    assert me.json()["nav"] == ["panel", "inbox", "usage"]


@pytest.mark.parametrize(
    "over",
    [
        {"password": "otra-contraseña-que-no-es"},
        {"email": "nadie-que-exista@minegocio.test"},
    ],
    ids=["wrong_password", "unknown_email"],
)
async def test_a_wrong_password_and_an_unknown_email_say_the_same(
    client, person, over: dict[str, str]
) -> None:
    resp = await client.post(SIGN_IN, json=_body(person, **over))

    assert resp.status_code == 401
    assert resp.json() == {"code": "invalid_credentials"}


async def test_a_locked_account_says_the_same_even_with_the_right_password(
    client, db_session, person
) -> None:
    await db_session.execute(
        sa.text(
            "UPDATE console_auth.principals SET locked_until = now() + interval '10 minutes' "
            "WHERE id = :i"
        ),
        {"i": str(person["account"])},
    )
    await db_session.commit()

    resp = await client.post(SIGN_IN, json=_body(person))

    assert resp.status_code == 401
    assert resp.json() == {"code": "invalid_credentials"}


async def test_a_wrong_password_counts_towards_the_lock(client, db_session, person) -> None:
    await client.post(SIGN_IN, json=_body(person, password="otra-contraseña-que-no-es"))

    attempts = await db_session.scalar(
        sa.text("SELECT failed_attempts FROM console_auth.principals WHERE id = :i"),
        {"i": str(person["account"])},
    )
    assert attempts == 1


async def test_a_partner_member_is_told_the_app_is_not_for_them(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    email = f"socia-{uuid.uuid4().hex[:8]}@partner.test"
    account = await make_console_account(db_session, email=email)
    await _with_password(db_session, account)
    db_session.add(
        PartnerMembership(
            id=uuid.uuid4(),
            partner_id=w["partner_id"],
            user_id=str(account),
            email=email,
            display_name="Socia",
            role="owner",
            status="active",
        )
    )
    await db_session.commit()

    resp = await client.post(SIGN_IN, json=_body({"email": email}))

    assert resp.status_code == 403
    assert resp.json() == {"code": "not_a_client"}
    phones = await db_session.scalar(sa.select(sa.func.count()).select_from(ClientPhone))
    assert phones == 0


async def test_without_access_there_is_no_phone(client, db_session, person) -> None:
    await db_session.execute(
        sa.text("UPDATE client_access SET enabled = false WHERE tenant_id = :t"),
        {"t": str(person["world"]["tenant_id"])},
    )
    await db_session.commit()

    resp = await client.post(SIGN_IN, json=_body(person))

    assert resp.status_code == 403
    assert resp.json() == {"code": "no_access"}
    phones = await db_session.scalar(sa.select(sa.func.count()).select_from(ClientPhone))
    assert phones == 0


async def test_a_removed_person_has_no_access(client, db_session, person) -> None:
    await db_session.execute(
        sa.update(ClientMembership)
        .where(ClientMembership.id == person["membership_id"])
        .values(status="revoked")
    )
    await db_session.commit()

    resp = await client.post(SIGN_IN, json=_body(person))

    assert resp.status_code == 403
    assert resp.json() == {"code": "no_access"}


async def test_an_old_app_is_asked_to_update_before_anything(client, person, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "customers_app_min_version_android", "3.0.0")

    resp = await client.post(SIGN_IN, json=_body(person, app_version="2.1.0"))

    assert resp.status_code == 403
    assert resp.json() == {"code": "app_update_required", "minimum_version": "3.0.0"}


async def test_too_many_attempts_on_one_email_are_cut(client, person) -> None:
    codes = [
        (
            await client.post(SIGN_IN, json=_body(person, password=f"mala-{i}-contraseña"))
        ).status_code
        for i in range(12)
    ]

    assert 429 in codes
    limited = await client.post(SIGN_IN, json=_body(person))
    assert limited.status_code == 429
    assert limited.json() == {"code": "rate_limited"}
    assert limited.headers.get("Retry-After")


async def test_signing_in_leaves_a_trace_with_the_method(client, db_session, person) -> None:
    resp = await client.post(SIGN_IN, json=_body(person))
    assert resp.status_code == 201

    after = await db_session.scalar(
        sa.select(AuditLog.after_json).where(AuditLog.action == "client_phone.signed_in")
    )
    assert after is not None
    assert (after["email"], after["method"]) == (person["email"], "password")


async def test_the_password_is_never_stored_on_the_phone_row(client, db_session, person) -> None:
    resp = await client.post(SIGN_IN, json=_body(person))
    assert resp.status_code == 201

    row = (await db_session.execute(sa.select(ClientPhone))).scalar_one()
    assert PASSWORD not in repr(row.__dict__)
