"""Spec 031 · entrar desde el teléfono y quedarse — R1.2, R1.3, R2.1, R2.2, R2.4,
R7.6, R13 (tareas T037 a T039).

El canje del código de un uso y la renovación, como los usa la app:

1. La vuelta de Google en la API emite un código para la persona
   (``issue_session_code`` con ``purpose=client_phone``; el recorrido entero con
   Google está en ``test_app_sign_in_google.py``).
2. La app lo canjea en ``POST /app/sign-in/google`` con su verificador PKCE.
3. Renueva en ``POST /app/phones/refresh`` sin volver a escribir nada.

La entrada con contraseña está en ``test_app_sign_in_password.py``.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.db.models import AuditLog, ClientMembership, ClientPhone
from nexus_api.services.session_codes import PURPOSE_PHONE, issue_session_code
from tests.conftest import make_client_access, make_console_account

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

REDEEM = "/app/sign-in/google"

VERIFIER = "verificador-de-la-app-suficientemente-largo-0123456789-abcdef"


def _challenge(verifier: str = VERIFIER) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@pytest.fixture
async def person(db_session, console_world) -> dict[str, Any]:
    """Una persona de cliente con cuenta de verdad: su ``user_id`` es el id."""
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    account = await make_console_account(db_session)
    membership_id = uuid.uuid4()
    db_session.add(
        ClientMembership(
            id=membership_id,
            partner_id=w["partner_id"],
            tenant_id=w["tenant_id"],
            user_id=str(account),
            email="valeria@minegocio.test",
            display_name="Valeria Ríos",
            status="active",
        )
    )
    await db_session.commit()
    return {"account": account, "membership_id": membership_id, "world": w, "db": db_session}


def _enroll_body(code: str, **over: Any) -> dict[str, Any]:
    body = {
        "code": code,
        "code_verifier": VERIFIER,
        "platform": "ios",
        "display_name": "iPhone de Valeria",
        "install_id": uuid.uuid4().hex,
        "app_version": "1.0.0",
        "locale": "es",
    }
    body.update(over)
    return body


async def _code(_client, person) -> str:
    """El código que emite la vuelta de Google para esta persona."""
    db = person["db"]
    async with db.begin():
        return await issue_session_code(
            db,
            principal_id=person["account"],
            code_challenge=_challenge(),
            purpose=PURPOSE_PHONE,
        )


async def test_the_whole_flow_lands_inside_with_the_clients_modules(client, person) -> None:
    code = await _code(client, person)

    resp = await client.post(REDEEM, json=_enroll_body(code))

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {"phone_id", "access_token", "expires_in", "refresh_token"}
    assert body["expires_in"] == 3600
    me = await client.get(
        "/console/lite/me",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
            "X-App-Platform": "ios",
            "X-App-Version": "1.0.0",
        },
    )
    assert me.status_code == 200, me.text
    assert me.json()["nav"] == ["panel", "inbox", "usage"]


async def test_a_code_is_single_use(client, person) -> None:
    code = await _code(client, person)
    first = await client.post(REDEEM, json=_enroll_body(code))
    second = await client.post(REDEEM, json=_enroll_body(code))

    assert first.status_code == 201
    assert second.status_code == 422
    assert second.json() == {"code": "invalid_grant"}


async def test_a_wrong_verifier_gets_the_same_rejection(client, person) -> None:
    code = await _code(client, person)
    resp = await client.post(REDEEM, json=_enroll_body(code, code_verifier="otro" + VERIFIER[4:]))
    assert resp.status_code == 422
    assert resp.json() == {"code": "invalid_grant"}


async def test_an_expired_code_gets_the_same_rejection(client, db_session, person) -> None:
    code = await _code(client, person)
    await db_session.execute(
        sa.text(
            "UPDATE console_auth.session_codes SET expires_at = now() - interval '1 minute' "
            "WHERE principal_id = :p"
        ),
        {"p": str(person["account"])},
    )
    await db_session.commit()

    resp = await client.post(REDEEM, json=_enroll_body(code))

    assert resp.status_code == 422
    assert resp.json() == {"code": "invalid_grant"}


async def test_a_desktop_code_does_not_open_a_phone(client, db_session, person) -> None:
    async with db_session.begin():
        code = await issue_session_code(
            db_session,
            principal_id=person["account"],
            code_challenge=_challenge(),
            purpose="desktop_session",
        )
    resp = await client.post(REDEEM, json=_enroll_body(code))
    assert resp.status_code == 422


async def test_signing_in_again_on_the_same_phone_replaces_the_session(
    client, db_session, person
) -> None:
    install = uuid.uuid4().hex
    first = await client.post(
        REDEEM, json=_enroll_body(await _code(client, person), install_id=install)
    )
    second = await client.post(
        REDEEM, json=_enroll_body(await _code(client, person), install_id=install)
    )
    assert first.status_code == second.status_code == 201

    rows = (
        await db_session.execute(
            sa.select(ClientPhone.id, ClientPhone.revoked_reason)
            .where(ClientPhone.install_id == install)
            .order_by(ClientPhone.enrolled_at)
        )
    ).all()
    assert [r.revoked_reason for r in rows] == ["signed_out", None]
    audit = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "client_phone.signed_in")
    )
    assert audit == 2


async def test_access_turned_off_between_code_and_enroll_gives_no_phone(
    client, db_session, person
) -> None:
    code = await _code(client, person)
    await db_session.execute(
        sa.text("UPDATE client_access SET enabled = false WHERE tenant_id = :t"),
        {"t": str(person["world"]["tenant_id"])},
    )
    await db_session.commit()

    resp = await client.post(REDEEM, json=_enroll_body(code))

    assert resp.status_code == 403
    assert resp.json() == {"code": "no_access"}


async def test_an_old_app_cannot_enroll(client, person, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "customers_app_min_version_android", "3.0.0")
    code = await _code(client, person)

    resp = await client.post(
        REDEEM, json=_enroll_body(code, platform="android", app_version="2.1.0")
    )

    assert resp.status_code == 403
    assert resp.json() == {"code": "app_update_required", "minimum_version": "3.0.0"}


# ── renovar ────────────────────────────────────────────────────────────


async def _enrolled(client, person) -> dict[str, Any]:
    resp = await client.post(REDEEM, json=_enroll_body(await _code(client, person)))
    assert resp.status_code == 201
    return dict(resp.json())


async def test_refresh_rotates_and_keeps_the_person_inside(client, person) -> None:
    tokens = await _enrolled(client, person)

    resp = await client.post(
        "/app/phones/refresh",
        json={"refresh_token": tokens["refresh_token"], "app_version": "1.0.1"},
    )

    assert resp.status_code == 200, resp.text
    rotated = resp.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]
    me = await client.get(
        "/console/lite/me",
        headers={
            "Authorization": f"Bearer {rotated['access_token']}",
            "X-App-Platform": "ios",
            "X-App-Version": "1.0.1",
        },
    )
    assert me.status_code == 200
    # El acceso viejo es de la generación anterior: ya no vale.
    old = await client.get(
        "/console/lite/me",
        headers={
            "Authorization": f"Bearer {tokens['access_token']}",
            "X-App-Platform": "ios",
            "X-App-Version": "1.0.0",
        },
    )
    assert old.status_code == 401


async def test_the_previous_refresh_is_honoured_for_sixty_seconds(client, person) -> None:
    tokens = await _enrolled(client, person)
    first = await client.post(
        "/app/phones/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    again = await client.post(
        "/app/phones/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert first.status_code == 200
    assert again.status_code == 200


async def test_an_old_refresh_after_the_grace_closes_the_phone(client, db_session, person) -> None:
    tokens = await _enrolled(client, person)
    await client.post("/app/phones/refresh", json={"refresh_token": tokens["refresh_token"]})
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == uuid.UUID(tokens["phone_id"]))
        .values(refresh_rotated_at=datetime.now(UTC) - timedelta(minutes=5))
    )
    await db_session.commit()

    resp = await client.post("/app/phones/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert resp.status_code == 401
    assert resp.json() == {"code": "phone_closed", "reason": "refresh_reused"}
    db_session.expire_all()
    reason = await db_session.scalar(
        sa.select(ClientPhone.revoked_reason).where(ClientPhone.id == uuid.UUID(tokens["phone_id"]))
    )
    assert reason == "refresh_reused"


async def test_ninety_days_unused_closes_the_phone(client, db_session, person) -> None:
    tokens = await _enrolled(client, person)
    await db_session.execute(
        sa.update(ClientPhone)
        .where(ClientPhone.id == uuid.UUID(tokens["phone_id"]))
        .values(last_seen_at=datetime.now(UTC) - timedelta(days=91))
    )
    await db_session.commit()

    resp = await client.post("/app/phones/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert resp.status_code == 401
    assert resp.json() == {"code": "phone_closed", "reason": "abandoned"}


async def test_an_unknown_refresh_is_rejected_without_detail(client, person) -> None:
    resp = await client.post("/app/phones/refresh", json={"refresh_token": "x" * 43})
    assert resp.status_code == 401
    assert resp.json() == {"code": "invalid_grant"}


async def test_refresh_never_opens_a_web_session(client, db_session, person) -> None:
    tokens = await _enrolled(client, person)
    before = await db_session.scalar(
        sa.text("SELECT count(*) FROM console_auth.principal_sessions WHERE principal_id = :p"),
        {"p": str(person["account"])},
    )
    await client.post("/app/phones/refresh", json={"refresh_token": tokens["refresh_token"]})
    after = await db_session.scalar(
        sa.text("SELECT count(*) FROM console_auth.principal_sessions WHERE principal_id = :p"),
        {"p": str(person["account"])},
    )
    assert after == before


# ── configuración pública ─────────────────────────────────────────────


async def test_app_config_is_public_and_cacheable(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "customers_app_min_version_ios", "1.2.0")

    resp = await client.get("/app/config")

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=300"
    body = resp.json()
    assert body["min_version"] == {"ios": "1.2.0", "android": None}
    assert body["console_url"].startswith("http")


# ── nadie bloquea a todos (a /app se llega sin la BFF: no hay IP de fiar) ──


async def test_garbage_refreshes_from_anyone_never_stop_a_real_one(client, person) -> None:
    """Sin la cabecera de la BFF todos los teléfonos comparten «IP». Un límite
    por IP sería uno solo para todos: unas pocas renovaciones basura dejarían a
    todas las personas sin renovar. La renovación es un secreto de 256 bits;
    no hay nada que adivinar y no lleva límite."""
    tokens = await _enrolled(client, person)
    for i in range(12):
        bad = await client.post(
            "/app/phones/refresh", json={"refresh_token": f"basura-{i}-" + "x" * 30}
        )
        assert bad.status_code == 401

    good = await client.post("/app/phones/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert good.status_code == 200, good.text


async def test_garbage_codes_from_anyone_never_stop_a_real_sign_in(client, person) -> None:
    for i in range(12):
        bad = await client.post(REDEEM, json=_enroll_body(f"ZZ{i:02d}ZZZZ"))
        assert bad.status_code == 422

    good = await client.post(REDEEM, json=_enroll_body(await _code(client, person)))

    assert good.status_code == 201, good.text


async def test_guessing_the_verifier_of_one_code_is_cut_for_that_code(client, person) -> None:
    code = await _code(client, person)
    statuses = [
        (
            await client.post(
                REDEEM, json=_enroll_body(code, code_verifier=f"intento-{i}-" + "v" * 40)
            )
        ).status_code
        for i in range(7)
    ]

    assert statuses[:5] == [422] * 5
    assert 429 in statuses[5:]
