"""Identidad del panel de operador en la API — ``/admin/auth/*`` (ADR-034).

El panel dejó de tener base de datos porque no podía tenerla: vive en
Vercel y la Aurora de producción es privada. Lo que este archivo fija es el
comportamiento del que depende que esa mudanza no sea un retroceso de
seguridad:

1. **contraseña mala, usuario inexistente y cuenta bloqueada devuelven
   exactamente la misma respuesta** — nada permite enumerar correos;
2. una sesión válida resuelve al operador, una caducada no, y el logout es
   idempotente;
3. diez fallos bloquean la cuenta, y el bloqueo tampoco se nota;
4. una cuenta deshabilitada **entra** y sale con ``access="disabled"``:
   distinguirla en el login sería otra forma de enumerar;
5. **un principal de la consola NO resuelve aquí** — son dos esquemas, no
   dos filas con un flag;
6. el ``role`` que gatea el QA Playground viaja en la respuesta, con
   ``qa_operator`` por defecto y sin admitir valores inventados;
7. ni ``password`` ni ``password_hash`` ni el hash del token aparecen jamás
   en una respuesta.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import ConsoleAccount, OperatorAccount, OperatorSession
from nexus_api.services import console_identity, operator_identity

pytestmark = pytest.mark.asyncio

PASSWORD = "operator-password-1"
EMAIL = "ops@auphere.test"


async def _make_operator(
    db_session, *, email: str = EMAIL, disabled: bool = False, role: str = "qa_operator"
):
    async with db_session.begin():
        account = await operator_identity.create_account(
            db_session, email=email, password=PASSWORD, display_name="Ops", role=role
        )
        if disabled:
            account.disabled_at = datetime.now(UTC) - timedelta(minutes=1)
    return account


async def _login(client, admin_headers, *, email: str = EMAIL, password: str = PASSWORD):
    return await client.post(
        "/admin/auth/login",
        headers=admin_headers,
        json={"email": email, "password": password},
    )


# ── login ─────────────────────────────────────────────────────────────


async def test_login_returns_an_opaque_token_and_the_operator(
    client, admin_headers, db_session
) -> None:
    account = await _make_operator(db_session)

    r = await _login(client, admin_headers)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["operator"]["id"] == str(account.id)
    assert body["operator"]["email"] == EMAIL
    assert body["operator"]["access"] == "ok"
    # El token es opaco: ni es el hash guardado ni se parece a él.
    assert len(body["token"]) >= 32
    async with db_session.begin():
        stored = (await db_session.execute(sa.select(OperatorSession.token_hash))).scalars().all()
    assert body["token"] not in stored


async def test_login_without_the_service_token_is_401(client, db_session) -> None:
    await _make_operator(db_session)
    r = await client.post("/admin/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 401


async def test_bad_password_and_unknown_email_are_indistinguishable(
    client, admin_headers, db_session
) -> None:
    """El corazón del endpoint. Si estas dos respuestas se diferencian en
    algo —código, cuerpo, cabeceras— el login se convierte en un oráculo
    de qué correos existen."""
    await _make_operator(db_session)

    bad_password = await _login(client, admin_headers, password="wrong-password-x")
    unknown = await _login(client, admin_headers, email="nadie@auphere.test")

    assert bad_password.status_code == unknown.status_code == 401
    assert bad_password.json() == unknown.json()
    assert bad_password.json()["detail"] == "Invalid e-mail or password"


async def test_lockout_after_ten_failures_looks_exactly_like_a_bad_password(
    client, admin_headers, db_session
) -> None:
    """Los diez fallos se gastan por el SERVICIO, no por HTTP, y no es un
    atajo: el limitador corta a los 10 intentos por minuto, exactamente el
    mismo número que dispara el bloqueo, así que por HTTP el 11.º siempre
    sería un 429 y el bloqueo no llegaría a verse dentro del minuto. Lo que
    esta prueba fija es que, una vez bloqueada, **ni la contraseña buena
    abre**, y que la respuesta es indistinguible de una contraseña mala.
    """
    account = await _make_operator(db_session)

    async with db_session.begin():
        for _ in range(operator_identity.MAX_FAILED_ATTEMPTS):
            assert (
                await operator_identity.authenticate(
                    db_session, email=EMAIL, password="nope-nope-nope"
                )
            ) is None
        refreshed = await db_session.get(OperatorAccount, account.id)
        assert refreshed is not None
        assert refreshed.locked_until is not None

    blocked = await _login(client, admin_headers)
    assert blocked.status_code == 401
    assert blocked.json()["detail"] == "Invalid e-mail or password"


async def test_the_rate_limiter_answers_429_with_retry_after(
    client, admin_headers, db_session
) -> None:
    """Antes de que el bloqueo entre en juego, el limitador ya frena. Es una
    respuesta DISTINTA del 401 a propósito: no dice nada de la cuenta, dice
    algo del que llama."""
    await _make_operator(db_session)

    codes = [
        (await _login(client, admin_headers, password="nope-nope-nope")).status_code
        for _ in range(operator_identity.MAX_FAILED_ATTEMPTS + 1)
    ]

    assert codes[-1] == 429
    limited = await _login(client, admin_headers, password="nope-nope-nope")
    assert limited.headers["Retry-After"] == "60"


async def test_a_disabled_account_logs_in_but_has_no_access(
    client, admin_headers, db_session
) -> None:
    """Deshabilitada no es lo mismo que inexistente, y el login no lo
    revela: entra igual y es el panel quien pinta "sin acceso"."""
    await _make_operator(db_session, email="fuera@auphere.test", disabled=True)

    r = await _login(client, admin_headers, email="fuera@auphere.test")

    assert r.status_code == 200, r.text
    assert r.json()["operator"]["access"] == "disabled"


# ── sesión ────────────────────────────────────────────────────────────


async def test_session_resolves_then_logout_makes_it_useless(
    client, admin_headers, db_session
) -> None:
    await _make_operator(db_session)
    token = (await _login(client, admin_headers)).json()["token"]

    ok = await client.post("/admin/auth/session", headers=admin_headers, json={"token": token})
    assert ok.status_code == 200
    assert ok.json()["operator"]["email"] == EMAIL

    out = await client.post("/admin/auth/logout", headers=admin_headers, json={"token": token})
    assert out.status_code == 204

    gone = await client.post("/admin/auth/session", headers=admin_headers, json={"token": token})
    assert gone.status_code == 200
    assert gone.json()["operator"] is None

    # Idempotente: cerrar dos veces no es un error.
    assert (
        await client.post("/admin/auth/logout", headers=admin_headers, json={"token": token})
    ).status_code == 204


async def test_an_expired_session_resolves_to_nobody(client, admin_headers, db_session) -> None:
    await _make_operator(db_session)
    token = (await _login(client, admin_headers)).json()["token"]

    async with db_session.begin():
        await db_session.execute(
            sa.update(OperatorSession)
            .where(OperatorSession.token_hash == operator_identity.hash_session_token(token))
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    r = await client.post("/admin/auth/session", headers=admin_headers, json={"token": token})
    assert r.status_code == 200
    assert r.json()["operator"] is None


async def test_an_unknown_token_is_not_an_error(client, admin_headers) -> None:
    """Para el BFF "no hay sesión" es una respuesta normal —enseña el
    login—, no un fallo de su credencial. Por eso 200 y no 401."""
    r = await client.post("/admin/auth/session", headers=admin_headers, json={"token": "x" * 40})
    assert r.status_code == 200
    assert r.json()["operator"] is None


# ── la frontera entre las dos identidades ─────────────────────────────


async def test_a_console_principal_cannot_log_into_the_admin_panel(
    client, admin_headers, db_session
) -> None:
    """La razón de que ``operator_auth`` sea un esquema aparte y no un flag
    en ``console_auth``: una cuenta de partner no puede resolver aquí ni
    aunque comparta correo y contraseña."""
    shared_email = "socio@partner.test"
    async with db_session.begin():
        await console_identity.create_account(
            db_session, email=shared_email, password=PASSWORD, display_name="Partner"
        )

    r = await _login(client, admin_headers, email=shared_email)

    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid e-mail or password"

    # Y al revés: la cuenta sigue existiendo, pero en su propio esquema.
    async with db_session.begin():
        assert (
            await db_session.scalar(
                sa.select(sa.func.count())
                .select_from(ConsoleAccount)
                .where(ConsoleAccount.email == shared_email)
            )
        ) == 1
        assert (
            await db_session.scalar(
                sa.select(sa.func.count())
                .select_from(OperatorAccount)
                .where(OperatorAccount.email == shared_email)
            )
        ) == 0


# ── nada de secretos en las respuestas ────────────────────────────────


async def test_no_response_ever_carries_a_secret(client, admin_headers, db_session) -> None:
    await _make_operator(db_session)
    login = await _login(client, admin_headers)
    token = login.json()["token"]
    session = await client.post("/admin/auth/session", headers=admin_headers, json={"token": token})

    for response in (login, session):
        raw = response.text
        assert "password" not in raw
        assert "scrypt$" not in raw
        assert operator_identity.hash_session_token(token) not in raw


# ── el rol, portado de better-auth ────────────────────────────────────


async def test_the_role_travels_and_defaults_to_qa_operator(
    client, admin_headers, db_session
) -> None:
    """El rol NO es una rejilla nueva: es la que ``auth.user.role`` ya tenía
    y que ``qa-access.ts`` usa para dejar entrar al Playground. Si dejara de
    viajar, el panel abriría el Playground a todo el mundo."""
    await _make_operator(db_session)
    assert (await _login(client, admin_headers)).json()["operator"]["role"] == "qa_operator"

    await _make_operator(db_session, email="jefe@auphere.test", role="admin")
    r = await _login(client, admin_headers, email="jefe@auphere.test")
    assert r.json()["operator"]["role"] == "admin"


async def test_an_invented_role_never_reaches_the_table(client, admin_headers, db_session) -> None:
    """La CHECK es la red: sin ella, un typo en un script de alta crea una
    cuenta con un rol que ``qa-access.ts`` no reconoce y que se comporta
    como ``viewer`` sin que nadie lo haya decidido."""
    with pytest.raises(Exception) as exc:
        await _make_operator(db_session, email="raro@auphere.test", role="superadmin")
    assert "ck_operator_principals_role" in str(exc.value)
