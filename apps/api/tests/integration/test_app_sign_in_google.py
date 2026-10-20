"""Spec 031 · R1.3 (enmienda del 2026-10-20) — entrar en la app con Google
(tarea T115).

El recorrido lo aloja la API, no la consola: ``GET /app/sign-in/google`` manda a
Google, la vuelta llega a ``/app/sign-in/google/callback`` y de ahí a la app con
un código de un uso que solo se canjea con el verificador PKCE de la app.

**La regla del correo:** la cuenta de Google tiene que ser la del correo con el
que Auphere dio de alta a la persona en el cliente. Aunque el ``sub`` ya esté
vinculado: si el correo de Google cambió, no entra.

Google se simula: ``exchange_code`` y ``verify_id_token`` (que ya prueba su
propia suite) devuelven la identidad que cada caso necesita.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.db.models import ClientMembership, ClientPhone, PartnerMembership
from nexus_api.db.models.console_identity import PrincipalIdentity
from nexus_api.services import google_oidc
from tests.conftest import make_client_access, make_console_account

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

START = "/app/sign-in/google"
CALLBACK = "/app/sign-in/google/callback"
REDEEM = "/app/sign-in/google"
APP_RETURN = "auphere-customers://auth/callback"
VERIFIER = "verificador-de-la-app-suficientemente-largo-0123456789-abcdef"
APP_STATE = "estado-de-la-app-0123456789"


def _challenge(verifier: str = VERIFIER) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@pytest.fixture
def email() -> str:
    """Único por prueba: las cuentas de ``console_auth`` no se vacían entre pruebas."""
    return f"valeria-{uuid.uuid4().hex[:8]}@minegocio.test"


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch, email: str) -> dict[str, Any]:
    """Google configurado y simulado. ``as_`` fija quién vuelve de Google."""
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "web-client.apps.googleusercontent.com")
    monkeypatch.setattr(s, "google_client_secret", "secreto-de-prueba")
    monkeypatch.setattr(s, "google_redirect_uri", "http://localhost:3110/auth/google/callback")
    # El `sub` también es único: los vínculos de Google viven en `console_auth`
    # y sobreviven entre pruebas.
    subject = f"sub-{uuid.uuid4().hex[:10]}"
    who: dict[str, Any] = {
        "identity": google_oidc.GoogleIdentity(subject=subject, email=email, display_name=None),
        "error": None,
        "subject": subject,
    }

    async def exchange_code(**_: Any) -> str:
        return "id-token-simulado"

    def verify_id_token(_token: str, *, client_id: str, **__: Any) -> google_oidc.GoogleIdentity:
        assert client_id == "web-client.apps.googleusercontent.com"
        if who["error"] is not None:
            raise who["error"]
        return who["identity"]

    monkeypatch.setattr(google_oidc, "exchange_code", exchange_code)
    monkeypatch.setattr(google_oidc, "verify_id_token", verify_id_token)

    def as_(email: str, subject: str | None = None) -> None:
        subject = subject or f"sub-{uuid.uuid4().hex[:10]}"
        who["identity"] = google_oidc.GoogleIdentity(
            subject=subject, email=email, display_name=None
        )

    who["as_"] = as_
    return who


@pytest.fixture
async def person(db_session, console_world, email) -> dict[str, Any]:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    account = await make_console_account(db_session, email=email)
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
    return {"account": account, "membership_id": membership_id, "world": w}


async def _to_google(client) -> dict[str, list[str]]:
    resp = await client.get(START, params={"state": APP_STATE, "code_challenge": _challenge()})
    assert resp.status_code == 302, resp.text
    url = urlparse(resp.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == google_oidc.AUTH_ENDPOINT
    return parse_qs(url.query)


async def _back_from_google(client, **params: str) -> dict[str, str]:
    resp = await client.get(CALLBACK, params=params)
    assert resp.status_code == 302, resp.text
    url = urlparse(resp.headers["location"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == APP_RETURN
    return {k: v[0] for k, v in parse_qs(url.query).items()}


async def _round_trip(client) -> dict[str, str]:
    google_query = await _to_google(client)
    return await _back_from_google(client, code="codigo-de-google", state=google_query["state"][0])


def _redeem_body(code: str, **over: Any) -> dict[str, Any]:
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


# ── la ida ────────────────────────────────────────────────────────────


async def test_the_start_sends_to_google_choosing_the_account(client, google) -> None:
    query = await _to_google(client)

    assert query["prompt"] == ["select_account"]
    assert query["code_challenge_method"] == ["S256"]
    # El reto con Google es de la API, no el de la app: el de la app no sale.
    assert query["code_challenge"] != [_challenge()]
    assert query["redirect_uri"] == [f"{get_settings().public_api_base_url}{CALLBACK}"]
    assert APP_STATE not in query["state"][0]


async def test_the_start_only_takes_an_rfc7636_challenge(client, google) -> None:
    hex_challenge = hashlib.sha256(VERIFIER.encode()).hexdigest()
    resp = await client.get(START, params={"state": APP_STATE, "code_challenge": hex_challenge})

    assert resp.status_code == 400
    assert resp.json() == {"code": "invalid_request"}


async def test_without_google_configured_the_app_hears_it(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "google_client_id", "")

    resp = await client.get(START, params={"state": APP_STATE, "code_challenge": _challenge()})
    config = await client.get("/app/config")

    assert resp.status_code == 302
    back = parse_qs(urlparse(resp.headers["location"]).query)
    assert back == {"error": ["google_unavailable"], "state": [APP_STATE]}
    assert config.json()["sign_in"] == {"google": False}


async def test_with_google_configured_the_config_says_so(client, google) -> None:
    config = await client.get("/app/config")

    assert config.json()["sign_in"] == {"google": True}


# ── la vuelta y el canje ──────────────────────────────────────────────


async def test_the_right_account_lands_inside(client, google, person) -> None:
    back = await _round_trip(client)

    assert back["state"] == APP_STATE
    assert set(back) == {"code", "state"}
    resp = await client.post(REDEEM, json=_redeem_body(back["code"]))
    assert resp.status_code == 201, resp.text
    me = await client.get(
        "/console/lite/me",
        headers={
            "Authorization": f"Bearer {resp.json()['access_token']}",
            "X-App-Platform": "ios",
            "X-App-Version": "1.0.0",
        },
    )
    assert me.status_code == 200, me.text


async def test_the_code_only_opens_with_the_apps_verifier(client, google, person) -> None:
    back = await _round_trip(client)

    wrong = await client.post(
        REDEEM, json=_redeem_body(back["code"], code_verifier="otro" + VERIFIER[4:])
    )
    again = await client.post(REDEEM, json=_redeem_body(back["code"]))

    assert wrong.status_code == 422
    assert wrong.json() == {"code": "invalid_grant"}
    # Con otro verificador no se gasta: la app, que tiene el bueno, sigue
    # pudiendo canjearlo (una vez; lo prueba el caso siguiente).
    assert again.status_code == 201


async def test_a_code_is_single_use(client, google, person) -> None:
    back = await _round_trip(client)

    first = await client.post(REDEEM, json=_redeem_body(back["code"]))
    second = await client.post(REDEEM, json=_redeem_body(back["code"]))

    assert first.status_code == 201
    assert second.status_code == 422
    assert second.json() == {"code": "invalid_grant"}


async def test_a_google_account_of_another_email_is_refused(client, google, person) -> None:
    google["as_"](f"valeria.personal-{uuid.uuid4().hex[:6]}@gmail.com")

    back = await _round_trip(client)

    assert back == {"error": "google_account_mismatch", "state": APP_STATE}


async def test_an_account_whose_email_is_not_the_configured_one_is_refused(
    client, db_session, google, console_world, email
) -> None:
    """La cuenta existe con el correo de Google, pero Auphere dio de alta a la
    persona con otro: manda el de la membresía."""
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    personal = f"valeria.personal-{uuid.uuid4().hex[:6]}@gmail.com"
    account = await make_console_account(db_session, email=personal)
    db_session.add(
        ClientMembership(
            id=uuid.uuid4(),
            partner_id=w["partner_id"],
            tenant_id=w["tenant_id"],
            user_id=str(account),
            email=email,
            display_name="Valeria Ríos",
            status="active",
        )
    )
    await db_session.commit()
    google["as_"](personal)

    back = await _round_trip(client)

    assert back == {"error": "google_account_mismatch", "state": APP_STATE}


async def test_a_linked_google_account_whose_email_changed_is_refused(
    client, db_session, google, person, email
) -> None:
    db_session.add(
        PrincipalIdentity(
            id=uuid.uuid4(),
            principal_id=person["account"],
            provider="google",
            subject=google["subject"],
            email_at_link=email,
        )
    )
    await db_session.commit()
    google["as_"]("otra-direccion@gmail.com", subject=google["subject"])

    back = await _round_trip(client)

    assert back == {"error": "google_account_mismatch", "state": APP_STATE}


async def test_an_unverified_email_is_refused(client, google, person) -> None:
    google["error"] = google_oidc.EmailNotVerified("sin verificar")

    back = await _round_trip(client)

    assert back == {"error": "email_not_verified", "state": APP_STATE}


async def test_a_partner_member_is_told_the_app_is_not_for_them(
    client, db_session, google, console_world
) -> None:
    email = f"socia-{uuid.uuid4().hex[:8]}@partner.test"
    account = await make_console_account(db_session, email=email)
    db_session.add(
        PartnerMembership(
            id=uuid.uuid4(),
            partner_id=console_world["a"]["partner_id"],
            user_id=str(account),
            email=email,
            display_name="Socia",
            role="owner",
            status="active",
        )
    )
    await db_session.commit()
    google["as_"](email)

    back = await _round_trip(client)

    assert back == {"error": "not_a_client", "state": APP_STATE}


async def test_without_access_the_app_hears_it_and_no_code_is_issued(
    client, db_session, google, person
) -> None:
    await db_session.execute(
        sa.text("UPDATE client_access SET enabled = false WHERE tenant_id = :t"),
        {"t": str(person["world"]["tenant_id"])},
    )
    await db_session.commit()

    back = await _round_trip(client)

    assert back == {"error": "no_access", "state": APP_STATE}
    codes = await db_session.scalar(
        sa.text(
            "SELECT count(*) FROM console_auth.session_codes "
            "WHERE purpose = 'client_phone' AND principal_id = :p"
        ),
        {"p": str(person["account"])},
    )
    assert codes == 0


async def test_cancelling_at_google_goes_back_quietly(client, google) -> None:
    google_query = await _to_google(client)

    back = await _back_from_google(client, error="access_denied", state=google_query["state"][0])

    assert back == {"error": "cancelled", "state": APP_STATE}


async def test_the_same_return_twice_fails_the_second_time(client, google, person) -> None:
    google_query = await _to_google(client)
    state = google_query["state"][0]

    first = await _back_from_google(client, code="codigo-de-google", state=state)
    second = await _back_from_google(client, code="codigo-de-google", state=state)

    assert set(first) == {"code", "state"}
    assert second == {"error": "failed", "state": APP_STATE}


async def test_a_forged_state_never_issues_anything(client, google, person) -> None:
    back = await _back_from_google(client, code="codigo-de-google", state="inventado.de.cero")

    assert back == {"error": "failed"}


async def test_signing_in_with_google_links_it_like_the_web(
    client, db_session, google, person
) -> None:
    back = await _round_trip(client)
    resp = await client.post(REDEEM, json=_redeem_body(back["code"]))
    assert resp.status_code == 201

    link = await db_session.scalar(
        sa.select(PrincipalIdentity.subject).where(
            PrincipalIdentity.principal_id == person["account"],
            PrincipalIdentity.provider == "google",
        )
    )
    assert link == google["subject"]
    phones = await db_session.scalar(sa.select(sa.func.count()).select_from(ClientPhone))
    assert phones == 1
