"""Identidad de la consola en la API — ``/console/auth/*`` (ADR-032).

La consola dejó de tener base de datos: usuarios, contraseñas y sesiones
viven aquí. Lo que este archivo fija es el comportamiento del que depende
que eso no sea un retroceso de seguridad:

1. el hash es scrypt con sal, verificable, y dos hashes de la misma
   contraseña son distintos;
2. **contraseña mala y usuario inexistente devuelven exactamente la misma
   respuesta** (mismo código y mismo cuerpo) — nada permite enumerar
   correos;
3. una sesión válida resuelve el principal, una caducada da 401 y el
   logout es idempotente;
4. diez fallos bloquean la cuenta, y el bloqueo tampoco se nota;
5. aceptar una invitación crea principal + membresía + sesión, y el
   segundo intento con el mismo enlace da 404;
6. la política de 12 caracteres se aplica al crear la cuenta;
7. **ni ``password`` ni ``password_hash`` ni el hash del token aparecen
   jamás en una respuesta**.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    ConsoleAccount,
    ConsoleSession,
    MembershipStatus,
    Partner,
    PartnerMembership,
)
from nexus_api.services import console_identity
from tests.conftest import mint_console_token

pytestmark = pytest.mark.asyncio

PASSWORD = "console-dev-2026!!"


def _svc_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_console_token(user_id='bff', partner_id=None, service=True)}"
    }


def _email(prefix: str = "owner") -> str:
    """Correo único por test: las filas de ``console_auth.principals`` no se
    borran entre tests (como el resto de la suite) y el índice único sobre
    ``lower(email)`` es global."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


async def _make_account(
    db_session,
    *,
    email: str,
    password: str = PASSWORD,
    display_name: str | None = "Owner",
) -> ConsoleAccount:
    account = await console_identity.create_account(
        db_session, email=email, password=password, display_name=display_name
    )
    await db_session.commit()
    return account


async def _link_membership(db_session, account: ConsoleAccount, partner_id: uuid.UUID) -> None:
    """Reapunta la membresía del partner al principal recién creado."""
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.partner_id == partner_id)
        .values(user_id=str(account.id), email=account.email)
    )
    await db_session.commit()


# ── hashing ────────────────────────────────────────────────────────────


def test_hash_and_verify_roundtrip() -> None:
    stored = console_identity.hash_password(PASSWORD)
    assert stored.startswith("scrypt$")
    assert console_identity.verify_password(PASSWORD, stored) is True
    assert console_identity.verify_password(PASSWORD + "x", stored) is False
    # Sal aleatoria: el mismo secreto NO produce la misma fila.
    assert stored != console_identity.hash_password(PASSWORD)
    assert console_identity.needs_rehash(stored) is False


def test_hash_never_contains_the_password_and_survives_garbage() -> None:
    stored = console_identity.hash_password(PASSWORD)
    assert PASSWORD not in stored
    # Una fila corrupta es False, no una excepción (y por tanto no un 500
    # que distinga esa cuenta del resto).
    for junk in ("", "not-a-hash", "scrypt$x$y$z$a$b", "bcrypt$1$2$3$4$5"):
        assert console_identity.verify_password(PASSWORD, junk) is False
    assert console_identity.needs_rehash("bcrypt$1$2$3$4$5") is True


def test_password_policy_is_twelve_characters() -> None:
    with pytest.raises(console_identity.PasswordPolicyError):
        console_identity.validate_password("a" * 11)
    console_identity.validate_password("a" * 12)
    with pytest.raises(console_identity.PasswordPolicyError):
        console_identity.validate_password("a" * 257)


# ── login ──────────────────────────────────────────────────────────────


async def test_login_returns_principal_with_permissions(client, console_world, db_session) -> None:
    a = console_world["a"]
    account = await _make_account(db_session, email=_email())
    await _link_membership(db_session, account, a["partner_id"])

    r = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": account.email.upper(), "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    principal = payload["principal"]
    assert principal["access"] == "ok"
    assert principal["role"] == "owner"
    assert principal["console_enabled"] is True
    assert principal["partner_slug"] == a["slug"]
    assert principal["user_id"] == str(account.id)
    assert "clients:write" in principal["permissions"]
    assert payload["token"] and payload["expires_at"]
    # Nada de secretos en la respuesta.
    assert "password" not in r.text and "password_hash" not in r.text
    assert console_identity.hash_session_token(payload["token"]) not in r.text


async def test_wrong_password_and_unknown_user_are_the_same_answer(
    client, console_world, db_session
) -> None:
    account = await _make_account(db_session, email=_email())

    wrong = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": account.email, "password": "totally-wrong-1234"},
    )
    unknown = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": "nobody@example.com", "password": "totally-wrong-1234"},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid e-mail or password"}


async def test_login_works_without_membership_but_says_no_access(
    client, console_world, db_session
) -> None:
    """Regla replicada del BFF: entrar SÍ, ver el panel no. La consola
    enseña su página "sin acceso" con estos datos."""
    account = await _make_account(db_session, email=_email("orphan"), display_name="Orphan")
    r = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": account.email, "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    principal = r.json()["principal"]
    assert principal["access"] == "no_membership"
    assert principal["role"] is None
    assert principal["permissions"] == []
    assert principal["console_enabled"] is False
    assert principal["email"] == account.email


async def test_console_disabled_partner_is_access_disabled(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    account = await _make_account(db_session, email=_email())
    await _link_membership(db_session, account, a["partner_id"])
    await db_session.execute(
        sa.update(Partner).where(Partner.id == a["partner_id"]).values(console_enabled=False)
    )
    await db_session.commit()

    r = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": account.email, "password": PASSWORD},
    )
    assert r.status_code == 200
    principal = r.json()["principal"]
    assert principal["access"] == "disabled"
    assert principal["partner_name"] == "Console Partner A"
    assert principal["console_enabled"] is False


async def test_suspended_membership_is_access_suspended(client, console_world, db_session) -> None:
    a = console_world["a"]
    account = await _make_account(db_session, email=_email())
    await _link_membership(db_session, account, a["partner_id"])
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.partner_id == a["partner_id"])
        .values(status=MembershipStatus.SUSPENDED.value)
    )
    await db_session.commit()

    r = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": account.email, "password": PASSWORD},
    )
    assert r.status_code == 200 and r.json()["principal"]["access"] == "suspended"


async def test_login_needs_the_service_token(client, console_world, db_session) -> None:
    account = await _make_account(db_session, email=_email())
    anonymous = await client.post(
        "/console/auth/login", json={"email": account.email, "password": PASSWORD}
    )
    assert anonymous.status_code == 401
    # Un token de principal tampoco vale: estos endpoints son de servicio.
    principal_token = {
        "Authorization": (
            f"Bearer {mint_console_token(user_id='x', partner_id=console_world['a']['partner_id'])}"
        )
    }
    assert (
        await client.post(
            "/console/auth/login",
            headers=principal_token,
            json={"email": account.email, "password": PASSWORD},
        )
    ).status_code == 403


# ── bloqueo por intentos ───────────────────────────────────────────────


async def test_ten_failures_lock_the_account_without_saying_so(
    client, console_world, db_session, monkeypatch
) -> None:
    """El límite de peticiones se sube para poder llegar a los diez fallos:
    lo que se mide aquí es el BLOQUEO, no el rate limit."""
    from nexus_api.api.console import auth as auth_router

    monkeypatch.setattr(auth_router, "LOGIN_ATTEMPTS_PER_MINUTE", 1000)
    account = await _make_account(db_session, email=_email("locked"))

    for _ in range(console_identity.MAX_FAILED_ATTEMPTS):
        r = await client.post(
            "/console/auth/login",
            headers=_svc_headers(),
            json={"email": account.email, "password": "wrong-password-here"},
        )
        assert r.status_code == 401

    await db_session.refresh(account)
    assert account.failed_attempts == console_identity.MAX_FAILED_ATTEMPTS
    assert account.locked_until is not None

    # Ahora la contraseña BUENA tampoco entra, y la respuesta es la misma.
    blocked = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": account.email, "password": PASSWORD},
    )
    assert blocked.status_code == 401
    assert blocked.json() == {"detail": "Invalid e-mail or password"}

    # Pasado el bloqueo, la cuenta vuelve y el contador se pone a cero.
    await db_session.execute(
        sa.update(ConsoleAccount)
        .where(ConsoleAccount.id == account.id)
        .values(locked_until=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()
    ok = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": account.email, "password": PASSWORD},
    )
    assert ok.status_code == 200
    await db_session.refresh(account)
    assert account.failed_attempts == 0 and account.locked_until is None


async def test_rate_limit_answers_429_with_retry_after(
    client, console_world, db_session, monkeypatch
) -> None:
    from nexus_api.api.console import auth as auth_router

    monkeypatch.setattr(auth_router, "LOGIN_ATTEMPTS_PER_MINUTE", 2)
    account = await _make_account(db_session, email=_email("hammered"))

    codes = []
    for _ in range(5):
        r = await client.post(
            "/console/auth/login",
            headers=_svc_headers(),
            json={"email": account.email, "password": "wrong-password-here"},
        )
        codes.append(r.status_code)
        if r.status_code == 429:
            assert r.headers["Retry-After"] == "60"
    assert 429 in codes


# ── sesiones ───────────────────────────────────────────────────────────


async def test_session_resolves_expires_and_logout_is_idempotent(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    account = await _make_account(db_session, email=_email())
    await _link_membership(db_session, account, a["partner_id"])

    login = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": account.email, "password": PASSWORD},
    )
    token = login.json()["token"]

    resolved = await client.post(
        "/console/auth/session", headers=_svc_headers(), json={"token": token}
    )
    assert resolved.status_code == 200
    assert resolved.json()["principal"]["role"] == "owner"

    # El token en claro NO está en la base: solo su SHA-256.
    stored = await db_session.scalar(
        sa.select(ConsoleSession).where(
            ConsoleSession.token_hash == console_identity.hash_session_token(token)
        )
    )
    assert stored is not None
    assert (
        await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(ConsoleSession)
            .where(ConsoleSession.token_hash == token)
        )
        == 0
    )

    # Caducada → 401 (y la fila se limpia sola).
    await db_session.execute(
        sa.update(ConsoleSession)
        .where(ConsoleSession.token_hash == stored.token_hash)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.commit()
    expired = await client.post(
        "/console/auth/session", headers=_svc_headers(), json={"token": token}
    )
    assert expired.status_code == 401

    # Logout de una sesión que ya no existe: 204 igualmente.
    for _ in range(2):
        out = await client.post(
            "/console/auth/logout", headers=_svc_headers(), json={"token": token}
        )
        assert out.status_code == 204


async def test_unknown_session_token_is_401(client, console_world) -> None:
    r = await client.post("/console/auth/session", headers=_svc_headers(), json={"token": "n" * 43})
    assert r.status_code == 401


async def test_logout_kills_the_session(client, console_world, db_session) -> None:
    a = console_world["a"]
    account = await _make_account(db_session, email=_email())
    await _link_membership(db_session, account, a["partner_id"])
    token = (
        await client.post(
            "/console/auth/login",
            headers=_svc_headers(),
            json={"email": account.email, "password": PASSWORD},
        )
    ).json()["token"]

    assert (
        await client.post("/console/auth/logout", headers=_svc_headers(), json={"token": token})
    ).status_code == 204
    assert (
        await client.post("/console/auth/session", headers=_svc_headers(), json={"token": token})
    ).status_code == 401


# ── invitación → cuenta + membresía + sesión ───────────────────────────


async def test_accept_invitation_creates_principal_membership_and_session(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    joiner = _email("joiner")
    inv = await client.post(
        "/console/team/invitations",
        headers=a["headers"](),
        json={"email": joiner, "role": "builder"},
    )
    assert inv.status_code == 201, inv.text
    token = inv.json()["accept_path"].removeprefix("/invite/")

    accepted = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc_headers(),
        json={"password": PASSWORD, "display_name": "Joiner"},
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["role"] == "builder"
    assert "password" not in accepted.text and "password_hash" not in accepted.text

    # 1. el principal existe; 2. la membresía apunta a su id;
    # 3. la sesión devuelta ya resuelve.
    account = await console_identity.get_by_email(db_session, joiner)
    assert account is not None
    membership = await db_session.scalar(
        sa.select(PartnerMembership).where(PartnerMembership.email == joiner)
    )
    assert membership is not None and membership.user_id == str(account.id)

    session_resp = await client.post(
        "/console/auth/session", headers=_svc_headers(), json={"token": body["token"]}
    )
    assert session_resp.status_code == 200
    assert session_resp.json()["principal"]["role"] == "builder"

    # El enlace es de un solo uso: el segundo intento es un 404 opaco.
    again = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc_headers(),
        json={"password": PASSWORD},
    )
    assert again.status_code == 404


async def test_accept_with_short_password_creates_nothing(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    invited = _email("short")
    inv = await client.post(
        "/console/team/invitations",
        headers=a["headers"](),
        json={"email": invited, "role": "analyst"},
    )
    token = inv.json()["accept_path"].removeprefix("/invite/")
    r = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc_headers(),
        json={"password": "a" * 11},
    )
    assert r.status_code == 422
    assert await console_identity.get_by_email(db_session, invited) is None
    # El enlace sigue vivo.
    assert (
        await client.get(f"/console/invitations/{token}", headers=_svc_headers())
    ).status_code == 200


async def test_accept_with_an_existing_account_requires_its_password(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    account = await _make_account(db_session, email=_email("already"), display_name="Already")
    inv = await client.post(
        "/console/team/invitations",
        headers=a["headers"](),
        json={"email": account.email, "role": "analyst"},
    )
    token = inv.json()["accept_path"].removeprefix("/invite/")

    wrong = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc_headers(),
        json={"password": "some-other-password"},
    )
    assert wrong.status_code == 409
    assert wrong.json()["detail"].startswith("account_exists")

    right = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc_headers(),
        json={"password": PASSWORD},
    )
    assert right.status_code == 200 and right.json()["role"] == "analyst"


# ── ninguna respuesta filtra secretos ──────────────────────────────────


async def test_no_console_auth_response_contains_a_secret_field(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    account = await _make_account(db_session, email=_email())
    await _link_membership(db_session, account, a["partner_id"])
    login = await client.post(
        "/console/auth/login",
        headers=_svc_headers(),
        json={"email": account.email, "password": PASSWORD},
    )
    session_resp = await client.post(
        "/console/auth/session",
        headers=_svc_headers(),
        json={"token": login.json()["token"]},
    )
    for resp in (login, session_resp):
        payload = resp.json()
        flat = str(payload)
        assert "password" not in flat
        assert "password_hash" not in flat
        assert "token_hash" not in flat
    # ``token`` sí sale (es lo que la consola guarda en la cookie), pero
    # solo en el login: la lectura de sesión no lo repite.
    assert "token" not in session_resp.json()["principal"]
