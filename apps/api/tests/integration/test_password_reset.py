"""El circuito de recuperar la contraseña — spec 011, Requisitos 1, 2 y 5.

Lo que se fija aquí es, sobre todo, **lo que no se puede averiguar desde
fuera**. Un test que sólo mire el código de estado no ve la diferencia que
importa: dos respuestas pueden ser las dos `202` y delatar en el cuerpo si la
dirección tiene cuenta. Por eso la comparación es **carácter a carácter**, y
cubre los cuatro caminos que tienen que ser el mismo camino: con cuenta, sin
cuenta, **con el envío caído** y **en el tope**.

``send_email`` **no lanza: devuelve ``False``**. Ese es justo el caso (c): un
fallo de envío es un problema de Auphere, visible en sus registros y no en la
pantalla de quien pregunta — decir «no pudimos enviarlo» revelaría que la
cuenta existe.

La atomicidad (R3.3) y el alcance (R3.5) **no se prueban aquí por el camino
feliz**: viven en ``TestLaTransaccion`` de este mismo fichero —que rompe algo a
propósito— y en ``tests/isolation/test_42_reset_scope.py``, que necesita dos
personas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.db.models import PasswordResetRequest
from nexus_api.db.models.console_identity import ConsoleAccount
from nexus_api.services import console_identity
from tests.conftest import mint_console_token

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PASSWORD = "una-contrasena-larga"
NUEVA = "otra-contrasena-mas-larga"


def _svc() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_console_token(user_id='bff', partner_id=None, service=True)}"
    }


async def _account(db_session: Any, prefix: str = "quien") -> ConsoleAccount:
    account = await console_identity.create_account(
        db_session,
        email=f"{prefix}-{uuid.uuid4().hex[:8]}@agencia.com",
        password=PASSWORD,
        display_name="Quien sea",
    )
    await db_session.commit()
    return account


def _mail_sink(monkeypatch: pytest.MonkeyPatch, *, works: bool = True) -> list[dict[str, Any]]:
    """Recoge los correos en vez de mandarlos.

    Con ``works=False`` devuelve ``False``, que es **exactamente** lo que hace
    ``send_email`` cuando el proveedor rechaza o no está configurado: no lanza.
    """
    sent: list[dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return works

    monkeypatch.setattr("nexus_api.services.email.send_email", _fake)
    return sent


def _link_token(sent: list[dict[str, Any]]) -> str:
    """El token que viajó dentro del enlace del último correo."""
    html = sent[-1]["html"]
    marker = "/reset/"
    start = html.index(marker) + len(marker)
    end = min(
        (i for i in (html.find('"', start), html.find("<", start), html.find(">", start)) if i > 0),
        default=len(html),
    )
    return html[start:end]


async def _ask(client: Any, email: str) -> Any:
    return await client.post("/console/password-reset", json={"email": email}, headers=_svc())


# ── T006: el no-oráculo, carácter a carácter ───────────────────────────────


class TestNadieAveriguaQueCuentasExisten:
    """R1.3 y R1.5. Cuatro caminos, una sola respuesta."""

    async def test_con_cuenta_y_sin_cuenta_responden_identico(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mail_sink(monkeypatch)
        account = await _account(db_session)

        con = await _ask(client, account.email)
        sin = await _ask(client, f"nadie-{uuid.uuid4().hex[:8]}@agencia.com")

        assert con.status_code == sin.status_code == 202
        assert con.json() == sin.json(), "el cuerpo delata si la cuenta existe"
        assert con.content == sin.content, "byte a byte"

    async def test_el_envio_caido_responde_igual_que_el_envio_bueno(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``send_email`` devuelve ``False``; la pantalla no se entera.

        Decir «no pudimos enviarlo» revelaría que la cuenta existe: el correo
        sólo se intenta cuando la hay.
        """
        buena = await _account(db_session, "buena")
        _mail_sink(monkeypatch, works=True)
        ok = await _ask(client, buena.email)

        caida = await _account(db_session, "caida")
        _mail_sink(monkeypatch, works=False)
        roto = await _ask(client, caida.email)

        assert ok.status_code == roto.status_code == 202
        assert ok.content == roto.content, "un envío caído no puede verse desde fuera"

    async def test_el_tope_responde_igual_que_una_peticion_normal(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R1.5: el techo no puede convertirse en un oráculo.

        Se agota el tope de una dirección **con** cuenta y se compara con la
        primera respuesta de una dirección **sin** cuenta. Si el tope
        contestara `429` —o cualquier otro cuerpo— bastaría con gastarlo para
        saber qué direcciones están registradas.
        """
        sent = _mail_sink(monkeypatch)
        account = await _account(db_session)

        primera = await _ask(client, account.email)
        for _ in range(6):
            topada = await _ask(client, account.email)

        assert primera.status_code == topada.status_code == 202
        assert primera.content == topada.content, "el tope delata"
        # Y contiene el abuso de verdad: pasado el techo no sale ningún correo.
        assert len(sent) <= console_identity_reset_cap(), (
            "el tope documenta el abuso en vez de contenerlo"
        )

    async def test_una_direccion_que_no_es_correo_no_es_un_camino_distinto(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validación de formato: 422, y el mismo 422 para cualquiera.

        No es el oráculo —no depende de si la cuenta existe— pero conviene
        fijarlo: el día que alguien conteste «esa dirección no está registrada»
        aquí, el test de arriba no lo vería.
        """
        _mail_sink(monkeypatch)
        uno = await client.post("/console/password-reset", json={"email": "no-es"}, headers=_svc())
        otro = await client.post("/console/password-reset", json={"email": "@@"}, headers=_svc())
        assert uno.status_code == otro.status_code == 422


def console_identity_reset_cap() -> int:
    from nexus_api.services.password_reset import REQUESTS_PER_WINDOW

    return REQUESTS_PER_WINDOW


# ── T007: sirve una vez ────────────────────────────────────────────────────


class TestElEnlaceSirveUnaVez:
    async def test_el_segundo_canje_dice_que_ya_no_vale(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R2.3, R5.1 y R5.3."""
        sent = _mail_sink(monkeypatch)
        account = await _account(db_session)
        await _ask(client, account.email)
        token = _link_token(sent)

        primero = await client.post(
            f"/console/password-reset/{token}", json={"password": NUEVA}, headers=_svc()
        )
        segundo = await client.post(
            f"/console/password-reset/{token}", json={"password": NUEVA}, headers=_svc()
        )

        assert primero.status_code == 200
        assert segundo.status_code == 404

    async def test_usado_caducado_e_inexistente_dan_el_mismo_cuerpo(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R5.3: no valer, haber caducado y no existir son indistinguibles —
        y ninguno dice de quién era el enlace."""
        sent = _mail_sink(monkeypatch)

        gastada = await _account(db_session, "gastada")
        await _ask(client, gastada.email)
        usado = _link_token(sent)
        await client.post(
            f"/console/password-reset/{usado}", json={"password": NUEVA}, headers=_svc()
        )

        caducada = await _account(db_session, "caducada")
        await _ask(client, caducada.email)
        vencido = _link_token(sent)
        await db_session.execute(
            sa.update(PasswordResetRequest)
            .where(PasswordResetRequest.account_id == caducada.id)
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await db_session.commit()

        inexistente = "no-existe-" + uuid.uuid4().hex

        cuerpos = []
        for token in (usado, vencido, inexistente):
            r = await client.post(
                f"/console/password-reset/{token}", json={"password": NUEVA}, headers=_svc()
            )
            assert r.status_code == 404
            cuerpos.append(r.content)
        assert cuerpos[0] == cuerpos[1] == cuerpos[2], "los tres casos muertos tienen que ser uno"
        for cuerpo in cuerpos:
            assert gastada.email.encode() not in cuerpo
            assert caducada.email.encode() not in cuerpo


# ── T008: pedir uno nuevo invalida los anteriores ──────────────────────────


class TestPedirOtroInvalidaElAnterior:
    async def test_tres_peticiones_no_dejan_tres_llaves_buenas(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R1.6. Sin esto, el motivo habitual para pedir otro enlace —sospechar
        del primero— no serviría de nada."""
        sent = _mail_sink(monkeypatch)
        account = await _account(db_session)

        await _ask(client, account.email)
        primero = _link_token(sent)
        await _ask(client, account.email)
        segundo = _link_token(sent)
        assert primero != segundo

        viejo = await client.post(
            f"/console/password-reset/{primero}", json={"password": NUEVA}, headers=_svc()
        )
        assert viejo.status_code == 404, "el enlace anterior seguía abriendo la cuenta"

        nuevo = await client.post(
            f"/console/password-reset/{segundo}", json={"password": NUEVA}, headers=_svc()
        )
        assert nuevo.status_code == 200


# ── T009: la contraseña cambia de verdad ───────────────────────────────────


class TestLaContrasenaCambia:
    async def test_la_anterior_no_sirve_y_la_nueva_si(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R2.1 y R2.2."""
        sent = _mail_sink(monkeypatch)
        account = await _account(db_session)
        # La dirección, como cadena, ANTES de expirar: leer un atributo de un
        # objeto expirado desde código async dispara IO sin await.
        email = account.email
        await _ask(client, email)

        r = await client.post(
            f"/console/password-reset/{_link_token(sent)}",
            json={"password": NUEVA},
            headers=_svc(),
        )
        assert r.status_code == 200

        # La contraseña la cambió OTRA sesión: sin expirar, el mapa de
        # identidad de ésta seguiría devolviendo el hash viejo.
        db_session.expire_all()
        assert (
            await console_identity.authenticate(db_session, email=email, password=PASSWORD) is None
        ), "la contraseña anterior seguía sirviendo"
        assert (
            await console_identity.authenticate(db_session, email=email, password=NUEVA) is not None
        )

    async def test_restablecer_desbloquea_a_quien_estaba_bloqueado(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R2.4: si no, se arregla la contraseña y se sigue sin poder entrar."""
        sent = _mail_sink(monkeypatch)
        account = await _account(db_session)
        email = account.email
        await db_session.execute(
            sa.update(ConsoleAccount)
            .where(ConsoleAccount.id == account.id)
            .values(failed_attempts=10, locked_until=datetime.now(UTC) + timedelta(minutes=15))
        )
        await db_session.commit()

        await _ask(client, email)
        r = await client.post(
            f"/console/password-reset/{_link_token(sent)}",
            json={"password": NUEVA},
            headers=_svc(),
        )
        assert r.status_code == 200

        db_session.expire_all()
        assert (
            await console_identity.authenticate(db_session, email=email, password=NUEVA) is not None
        ), "restablecer no levantó el bloqueo"

    async def test_una_contrasena_que_no_cumple_la_politica_no_gasta_el_enlace(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R2.1: «las mismas reglas de validez que el alta».

        Y el enlace sigue vivo: equivocarse escribiendo la contraseña nueva no
        puede obligar a pedir otro correo.
        """
        sent = _mail_sink(monkeypatch)
        account = await _account(db_session)
        await _ask(client, account.email)
        token = _link_token(sent)

        corta = await client.post(
            f"/console/password-reset/{token}", json={"password": "corta"}, headers=_svc()
        )
        assert corta.status_code == 422

        buena = await client.post(
            f"/console/password-reset/{token}", json={"password": NUEVA}, headers=_svc()
        )
        assert buena.status_code == 200, "una contraseña rechazada quemó el enlace"


# ── T010: en reposo sólo vive el hash ──────────────────────────────────────


class TestLoGuardadoNoAbreNada:
    async def test_el_valor_en_claro_no_aparece_en_la_fila(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R1.4 y R5.2. Un volcado de la tabla no restablece nada."""
        sent = _mail_sink(monkeypatch)
        account = await _account(db_session)
        await _ask(client, account.email)
        token = _link_token(sent)

        row = (
            await db_session.execute(
                sa.select(PasswordResetRequest).where(PasswordResetRequest.account_id == account.id)
            )
        ).scalar_one()

        assert row.token_hash != token
        assert len(row.token_hash) == 64
        volcado = " ".join(str(v) for v in row.__dict__.values())
        assert token not in volcado, "el enlace en claro estaba en la fila"


# ── US2 · T019 y T020: restablecer retira todo el acceso ───────────────────


async def _with_sessions_and_machines(
    db_session: Any, console_world: dict[str, Any], *, label: str = "yo"
) -> dict[str, Any]:
    """Una persona con dos sesiones abiertas y dos máquinas dadas de alta."""
    from nexus_api.db.models import PartnerDevice, PartnerMembership

    partner_id = console_world["a"]["partner_id"]
    account = await _account(db_session, label)
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.partner_id == partner_id)
        .values(user_id=str(account.id), email=account.email)
    )
    machines = [
        PartnerDevice(
            id=uuid.uuid4(),
            partner_id=partner_id,
            principal_id=str(account.id),
            display_name=f"mac-{label}-{i}",
            hostname=f"mac-{label}-{i}.local",
            platform="macos",
        )
        for i in range(2)
    ]
    db_session.add_all(machines)
    await db_session.commit()

    tokens = []
    for _ in range(2):
        token, _expires = await console_identity.start_session(db_session, account)
        tokens.append(token)
    await db_session.commit()
    return {"account": account, "tokens": tokens, "machines": machines}


class TestRestablecerDejaFueraAQuienEntro:
    async def test_la_otra_sesion_deja_de_valer_y_las_maquinas_quedan_archivadas(
        self, client: Any, db_session: Any, console_world: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R3.1 y R3.2. La mitad de los motivos para recuperar una contraseña
        no son «se me olvidó» sino «creo que alguien entró»."""
        sent = _mail_sink(monkeypatch)
        w = await _with_sessions_and_machines(db_session, console_world)
        await _ask(client, w["account"].email)

        r = await client.post(
            f"/console/password-reset/{_link_token(sent)}",
            json={"password": NUEVA},
            headers=_svc(),
        )
        assert r.status_code == 200

        db_session.expire_all()
        for token in w["tokens"]:
            assert await console_identity.resolve_session(db_session, token) is None, (
                "una sesión abierta en otro sitio sobrevivió al restablecimiento"
            )
        for machine in w["machines"]:
            await db_session.refresh(machine)
            assert machine.revoked_at is not None
            assert machine.revoked_reason == "archivada_consola", (
                "el motivo de archivado no es el vocabulario que sembró la 012"
            )

    async def test_queda_asiento_de_la_retirada_con_la_persona_y_el_motivo(
        self, client: Any, db_session: Any, console_world: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R3.4."""
        from nexus_api.db.models import AuditLog

        sent = _mail_sink(monkeypatch)
        w = await _with_sessions_and_machines(db_session, console_world)
        await _ask(client, w["account"].email)
        await client.post(
            f"/console/password-reset/{_link_token(sent)}",
            json={"password": NUEVA},
            headers=_svc(),
        )

        rows = (
            (
                await db_session.execute(
                    sa.select(AuditLog).where(AuditLog.action == "principal.access_revoked")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        row = rows[0]
        assert str(w["account"].id) in row.target
        assert row.after_json["reason"], "el asiento no dice por qué se retiró el acceso"
        assert row.after_json["sessions_closed"] == 2
        assert row.after_json["machines_archived"] == 2


# ── US2 · T017: la atomicidad, que sólo se ve cuando algo se rompe ─────────


class TestLaTransaccion:
    async def test_un_fallo_a_mitad_no_deja_la_contrasena_cambiada_con_las_sesiones_vivas(
        self, client: Any, db_session: Any, console_world: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R3.3: o las tres cosas, o ninguna.

        **Esto no se ve por el camino feliz.** Se rompe a propósito la segunda
        mitad de la retirada de acceso —archivar las máquinas— con las sesiones
        ya cerradas dentro de la misma transacción. Si el canje fueran dos
        operaciones seguidas en vez de una, quedaría una contraseña nueva con
        las máquinas vivas: alguien que cree haber echado al intruso y le ha
        dejado la ejecución local.

        Que la persona siga con su contraseña **vieja** tras un fallo es
        incómodo y honesto. Lo otro es peor, porque quien lo pidió cree que
        terminó.
        """
        from nexus_api.repositories import local_workstation

        sent = _mail_sink(monkeypatch)
        w = await _with_sessions_and_machines(db_session, console_world)
        email = w["account"].email
        await _ask(client, email)
        token = _link_token(sent)

        async def _boom(*_args: object, **_kwargs: object) -> int:
            raise RuntimeError("la mitad de las máquinas se cayó")

        monkeypatch.setattr(
            local_workstation.PartnerDeviceRepository, "archive_all_for_principal", _boom
        )

        with pytest.raises(RuntimeError):
            await client.post(
                f"/console/password-reset/{token}", json={"password": NUEVA}, headers=_svc()
            )

        monkeypatch.undo()
        db_session.expire_all()

        # Ninguna de las tres mitades quedó aplicada.
        assert (
            await console_identity.authenticate(db_session, email=email, password=PASSWORD)
            is not None
        ), "la contraseña cambió pese a que la transacción falló"
        for session_token in w["tokens"]:
            assert await console_identity.resolve_session(db_session, session_token) is not None
        for machine in w["machines"]:
            await db_session.refresh(machine)
            assert machine.revoked_at is None

        # **Soltar la transacción de la prueba antes de volver a canjear.**
        # ``authenticate`` acaba de escribir ``last_login_at`` en la fila de
        # esta persona y esta sesión no ha hecho commit: sin esto, el `UPDATE`
        # del canje se queda esperando ese cerrojo para siempre. Es artefacto
        # de tener dos sesiones contra la misma fila, no del producto — en
        # producción cada petición abre y cierra la suya.
        await db_session.rollback()

        # Y el enlace sigue vivo: un fallo de Auphere no puede costarle a la
        # persona el correo que ya recibió.
        otra_vez = await client.post(
            f"/console/password-reset/{token}", json={"password": NUEVA}, headers=_svc()
        )
        assert otra_vez.status_code == 200


# ── US3 · T023 y T024: el aviso de que cambió ──────────────────────────────


class TestElAvisoDeQueCambio:
    """R4. Es lo que convierte un secuestro silencioso en uno que la víctima ve.

    Los dos tests de aquí miran cosas distintas y ninguna es «sale un correo»:
    el primero mira **qué no lleva** el aviso, y el segundo mira que el aviso
    sea lo último y no pueda deshacer nada.
    """

    async def test_un_restablecimiento_con_exito_avisa_a_la_direccion_de_la_cuenta(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R4.1 y R4.2."""
        monkeypatch.setattr(
            get_settings(), "security_contact_email", "seguridad@ejemplo.com", raising=False
        )
        sent = _mail_sink(monkeypatch)
        account = await _account(db_session)
        email = account.email
        await _ask(client, email)

        r = await client.post(
            f"/console/password-reset/{_link_token(sent)}",
            json={"password": NUEVA},
            headers=_svc(),
        )
        assert r.status_code == 200

        assert len(sent) == 2, "el enlace salió pero el aviso no"
        aviso = sent[-1]
        assert aviso["to"] == email
        # Cuándo ocurrió: el año y la hora, que es lo que deja a alguien decir
        # «yo a esa hora no estaba».
        assert str(datetime.now(UTC).year) in aviso["html"]
        assert "UTC" in aviso["html"]
        # Y a quién escribir si no fue la persona.
        assert "seguridad@ejemplo.com" in aviso["html"]

    async def test_el_aviso_no_lleva_contrasena_ni_enlace_que_sirva_para_entrar(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R4.3, y es el requisito con más filo de los cuatro.

        Un aviso de «tu contraseña ha cambiado» que trae un enlace es un aviso
        que entrena a la gente a pulsar enlaces dentro de correos sobre su
        contraseña — que es exactamente el gesto que un suplantador necesita.
        Por eso la comprobación no es «no lleva el enlace de restablecer» sino
        **no lleva ningún `href` que apunte a ninguna parte**, salvo `mailto:`.
        """
        monkeypatch.setattr(
            get_settings(), "security_contact_email", "seguridad@ejemplo.com", raising=False
        )
        sent = _mail_sink(monkeypatch)
        account = await _account(db_session)
        await _ask(client, account.email)
        token = _link_token(sent)

        await client.post(
            f"/console/password-reset/{token}", json={"password": NUEVA}, headers=_svc()
        )

        html = sent[-1]["html"]
        assert NUEVA not in html, "el aviso llevaba la contraseña"
        assert PASSWORD not in html
        assert token not in html, "el aviso llevaba el enlace de restablecer"
        for prefijo in ('href="http', "href='http", "http://", "https://"):
            assert prefijo not in html, f"el aviso lleva un enlace ({prefijo})"
        # El único destino admitido es escribir a alguien.
        assert "mailto:" in html

    async def test_si_el_aviso_no_sale_el_restablecimiento_no_se_deshace(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R4.4. El aviso va **después** de la transacción y a propósito.

        Deshacer un restablecimiento porque no se pudo avisar de él sería lo
        peor de los dos mundos: la persona se queda sin entrar Y sin enterarse.
        El fallo es de Auphere y vive en sus registros.
        """
        import structlog

        account = await _account(db_session)
        email = account.email

        # El enlace sale bien; el aviso, no. Dos comportamientos del mismo
        # doble, porque es lo que pasa de verdad cuando el proveedor empieza a
        # rechazar a mitad de un día.
        llamadas: list[dict[str, Any]] = []

        async def _fake(**kwargs: Any) -> bool:
            llamadas.append(kwargs)
            return len(llamadas) == 1

        monkeypatch.setattr("nexus_api.services.email.send_email", _fake)

        await _ask(client, email)
        token = _link_token(llamadas)

        with structlog.testing.capture_logs() as eventos:
            r = await client.post(
                f"/console/password-reset/{token}", json={"password": NUEVA}, headers=_svc()
            )

        assert r.status_code == 200, "el fallo del aviso tumbó el restablecimiento"
        assert len(llamadas) == 2, "no se intentó avisar"

        db_session.expire_all()
        assert (
            await console_identity.authenticate(db_session, email=email, password=NUEVA) is not None
        ), "el restablecimiento ya ocurrido se deshizo"

        assert any(e.get("event") == "password_reset.notice_not_sent" for e in eventos), (
            "el fallo del aviso no quedó en los registros"
        )
