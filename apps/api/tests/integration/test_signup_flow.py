"""Los tres actos del alta, contra la API — spec 006, Requisitos 1, 2, 3 y 7.

Lo que se fija aquí es sobre todo lo que **no** se puede averiguar desde fuera:

- pedir el alta responde **igual** exista o no el correo (1.2, CE-004);
- los cuatro casos de token muerto dan el **mismo cuerpo** (7.3);
- superar el límite **no manda correo** (1.4) — la mitad que contiene el abuso;
- el registro es abierto de verdad: nadie aprueba nada (1.6, 2.4).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.db.models import AuditLog, Partner, PartnerMembership, SignupRequest, SignupStatus
from nexus_api.repositories.signup import SignupRequestRepository
from tests.conftest import mint_console_token

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _svc() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_console_token(user_id='bff', partner_id=None, service=True)}"
    }


def _svc_ip(ip: str) -> dict[str, str]:
    return {**_svc(), "X-Nexus-Client-IP": ip}


@pytest.fixture(autouse=True)
def _signup_on(monkeypatch: pytest.MonkeyPatch) -> Any:
    """La bandera está apagada por defecto; estas pruebas la encienden."""
    settings = get_settings()
    monkeypatch.setattr(settings, "signup_enabled", True, raising=False)
    yield


def _mail_sink(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Recoge los correos en vez de mandarlos. Devuelve la lista viva."""
    sent: list[dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr("nexus_api.services.email.send_email", _fake)
    return sent


class TestNadieAveriguaQueCorreosExisten:
    async def test_correo_nuevo_y_correo_existente_responden_identico(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nexus_api.services import console_identity

        sent = _mail_sink(monkeypatch)
        ya = f"ya-{uuid.uuid4().hex[:8]}@agencia.com"
        await console_identity.create_account(
            db_session, email=ya, password="una-contrasena-larga", display_name=None
        )
        await db_session.commit()

        nuevo = f"nuevo-{uuid.uuid4().hex[:8]}@agencia.com"
        r_nuevo = await client.post(
            "/console/signup", json={"email": nuevo}, headers=_svc_ip("203.0.113.1")
        )
        r_ya = await client.post(
            "/console/signup", json={"email": ya}, headers=_svc_ip("203.0.113.2")
        )

        assert r_nuevo.status_code == r_ya.status_code == 202
        assert r_nuevo.json() == r_ya.json(), "el cuerpo delata si el correo existe"
        assert r_nuevo.content == r_ya.content, "byte a byte"

        # Dos correos distintos, una sola respuesta: la diferencia sólo la ve
        # quien abre el buzón, que es el dueño de la dirección.
        assert len(sent) == 2
        assert sent[0]["subject"] != sent[1]["subject"]

    async def test_los_cuatro_tokens_muertos_dan_el_mismo_cuerpo(
        self, client: Any, db_session: Any
    ) -> None:
        repo = SignupRequestRepository(db_session)

        # inexistente
        inexistente = await client.get("/console/signup/" + "z" * 40, headers=_svc())
        # caducada
        row, caducado = await repo.create(email=f"c-{uuid.uuid4().hex[:8]}@x.com", ttl_hours=24)
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db_session.commit()
        expirada = await client.get(f"/console/signup/{caducado}", headers=_svc())
        # revocada (pedir otra vez revoca la anterior)
        email = f"r-{uuid.uuid4().hex[:8]}@x.com"
        _r1, primero = await repo.create(email=email, ttl_hours=24)
        await db_session.commit()
        await repo.create(email=email, ttl_hours=24)
        await db_session.commit()
        revocada = await client.get(f"/console/signup/{primero}", headers=_svc())
        # consumida
        r3, usado = await repo.create(email=f"u-{uuid.uuid4().hex[:8]}@x.com", ttl_hours=24)
        r3.status = SignupStatus.CONSUMED.value
        await db_session.commit()
        consumida = await client.get(f"/console/signup/{usado}", headers=_svc())

        respuestas = [inexistente, expirada, revocada, consumida]
        assert {r.status_code for r in respuestas} == {404}
        assert len({r.content for r in respuestas}) == 1, (
            "los cuatro tienen que ser indistinguibles"
        )


class TestElLimiteNoMandaCorreo:
    async def test_al_pasar_el_limite_hay_429_y_cero_correos_nuevos(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Requisito 1.4. Es la mitad que contiene el abuso: un limitador que
        responde 429 *después* de haber mandado el correo pasaría cualquier
        prueba que sólo mire el código de estado."""
        sent = _mail_sink(monkeypatch)
        ip = f"198.51.100.{uuid.uuid4().int % 200 + 1}"
        codigos = []
        for _ in range(8):
            r = await client.post(
                "/console/signup",
                json={"email": f"flood-{uuid.uuid4().hex[:8]}@agencia.com"},
                headers=_svc_ip(ip),
            )
            codigos.append(r.status_code)
            if r.status_code == 429:
                assert r.headers.get("Retry-After"), "el 429 tiene que decir cuándo reintentar"
                break
        assert 429 in codigos, "el cubo por IP no frenó nada"
        enviados_antes = len(sent)
        r = await client.post(
            "/console/signup",
            json={"email": f"flood-{uuid.uuid4().hex[:8]}@agencia.com"},
            headers=_svc_ip(ip),
        )
        assert r.status_code == 429
        assert len(sent) == enviados_antes, "mandó correo pese a estar limitado"


class TestElAltaCompleta:
    async def test_de_punta_a_punta_sin_que_intervenga_nadie(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Requisitos 1.6, 2.4, 3.1, 3.3 — y CE-001/CE-002.

        El registro es **abierto**: no hay cola de aprobación, ni estado
        pendiente de revisión, ni nadie a quien esperar. Es un requisito
        negativo, y por eso se prueba: añadir una puerta más adelante no
        rompería ninguna otra prueba de esta spec.
        """
        _mail_sink(monkeypatch)
        email = f"alta-{uuid.uuid4().hex[:8]}@agencia.com"
        start = await client.post(
            "/console/signup", json={"email": email}, headers=_svc_ip("203.0.113.50")
        )
        assert start.status_code == 202

        row = (
            await db_session.execute(sa.select(SignupRequest).where(SignupRequest.email == email))
        ).scalar_one()
        # El token en claro no está en la base: se re-emite para la prueba.
        repo = SignupRequestRepository(db_session)
        _r, token = await repo.create(email=email, ttl_hours=24)
        await db_session.commit()

        look = await client.get(f"/console/signup/{token}", headers=_svc())
        assert look.status_code == 200 and look.json()["email"] == email

        done = await client.post(
            f"/console/signup/{token}/complete",
            json={"company_name": "Agencia Abierta", "password": "una-contrasena-larga"},
            headers=_svc_ip("203.0.113.50"),
        )
        assert done.status_code == 201, done.text
        body = done.json()
        assert body["role"] == "owner" and body["session_token"]

        partner = (
            await db_session.execute(sa.select(Partner).where(Partner.slug == body["partner_slug"]))
        ).scalar_one()
        assert partner.console_enabled is True
        assert partner.status == "active", "nada quedó esperando a que alguien apruebe"

        membership = (
            await db_session.execute(
                sa.select(PartnerMembership).where(PartnerMembership.partner_id == partner.id)
            )
        ).scalar_one()
        assert membership.role == "owner" and membership.status == "active"

        # Nace en Free: sin fila de suscripción.
        from nexus_api.db.models.membership import PartnerSubscription

        subs = (
            await db_session.execute(
                sa.select(sa.func.count())
                .select_from(PartnerSubscription)
                .where(PartnerSubscription.partner_id == partner.id)
            )
        ).scalar_one()
        assert subs == 0
        assert row is not None

    async def test_la_auditoria_nombra_a_la_persona_y_no_guarda_secretos(
        self, client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Requisitos 3.5 y 7.4."""
        _mail_sink(monkeypatch)
        email = f"audit-{uuid.uuid4().hex[:8]}@agencia.com"
        repo = SignupRequestRepository(db_session)
        _r, token = await repo.create(email=email, ttl_hours=24)
        await db_session.commit()

        password = "otra-contrasena-larga"
        done = await client.post(
            f"/console/signup/{token}/complete",
            json={"company_name": "Con Rastro", "password": password},
            headers=_svc_ip("203.0.113.77"),
        )
        assert done.status_code == 201

        entry = (
            await db_session.execute(
                sa.select(AuditLog)
                .where(AuditLog.action == "partner.signup.completed")
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one()
        assert email in entry.actor, "la auditoría tiene que nombrar a la persona"
        blob = f"{entry.actor}{entry.target}{entry.before_json}{entry.after_json}"
        assert password not in blob
        assert token not in blob
        assert "203.0.113.77" not in blob
        assert entry.after_json is not None and entry.after_json.get("via") == "password"
