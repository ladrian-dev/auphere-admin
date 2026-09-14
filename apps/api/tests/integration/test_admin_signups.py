"""Lo que ve el operador del alta autónoma — spec 006, Requisito 8.

**El requisito no es «una lista»: es no perder el gobierno al abrir la puerta.**
De ahí las tres cosas que se fijan aquí:

1. Un partner que nació solo se distingue de uno que creó el equipo, y trae su
   **fecha**, su **vía de entrada** y su **nivel** (8.1). Sin la vía de entrada,
   el panel enseña partners y no dice cuáles llegaron sin que nadie mirara.
2. Un registro **a medias** —correo verificado, empresa sin nombrar— no se
   parece a un partner activo (8.1). Son dos situaciones distintas y piden
   cosas distintas del operador.
3. Reenviar el enlace y suspender se hacen **sin ejecutar nada dentro de la
   VPC** (8.2). Suspender ya existía (`PATCH /admin/partners/{id}` con
   `status`); reenviar no, y ésa era la mitad que obligaba a abrir una consola.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nexus_api.config import get_settings
from nexus_api.db.models import SignupStatus
from nexus_api.repositories.signup import SignupRequestRepository
from nexus_api.services.signup import complete_signup

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _signup_on(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(get_settings(), "signup_enabled", True, raising=False)
    yield


def _mail_sink(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr("nexus_api.services.email.send_email", _fake)
    return sent


async def _pending(db_session: Any, *, provider: str | None = None) -> Any:
    email = f"pide-{uuid.uuid4().hex[:8]}@agencia.com"
    row, _plaintext = await SignupRequestRepository(db_session).create(
        email=email, ttl_hours=24, provider=provider, ip=None
    )
    await db_session.commit()
    return row


async def _born(db_session: Any, *, provider: str | None = None) -> tuple[Any, Any]:
    """Una solicitud llevada hasta el final: partner vivo y solicitud consumida."""
    row = await _pending(db_session, provider=provider)
    outcome = await complete_signup(
        db_session,
        signup=row,
        company_name=f"Agencia {uuid.uuid4().hex[:6]}",
        user_id=f"user_{uuid.uuid4().hex[:8]}",
        display_name=None,
    )
    await db_session.commit()
    return row, outcome


class TestElOperadorVeQuienEntroSolo:
    async def test_trae_fecha_via_de_entrada_y_nivel(
        self, client: Any, db_session: Any, admin_headers: dict[str, str]
    ) -> None:
        _row, outcome = await _born(db_session, provider="google")

        r = await client.get("/admin/signups", headers=admin_headers)
        assert r.status_code == 200

        fila = next(
            f for f in r.json() if (f.get("partner") or {}).get("id") == str(outcome.partner.id)
        )
        assert fila["status"] == SignupStatus.CONSUMED.value
        assert fila["provider"] == "google", "sin la vía de entrada, el panel no dice cómo llegó"
        assert fila["created_at"], "la fecha es parte del requisito, no un extra"
        assert fila["partner"]["tier"] == "free", "sin fila en partner_subscriptions ES Free"
        assert fila["partner"]["status"] == "active"

    async def test_la_via_de_entrada_por_contrasena_se_nombra_y_no_es_null(
        self, client: Any, db_session: Any, admin_headers: dict[str, str]
    ) -> None:
        """`null` obligaría a quien lee el panel a saber que `null` significa
        «con contraseña». Se nombra."""
        _row, outcome = await _born(db_session, provider=None)

        r = await client.get("/admin/signups", headers=admin_headers)
        fila = next(
            f for f in r.json() if (f.get("partner") or {}).get("id") == str(outcome.partner.id)
        )
        assert fila["provider"] == "password"

    async def test_un_registro_a_medias_no_se_parece_a_un_partner_activo(
        self, client: Any, db_session: Any, admin_headers: dict[str, str]
    ) -> None:
        row = await _pending(db_session)

        r = await client.get("/admin/signups", headers=admin_headers)
        fila = next(f for f in r.json() if f["id"] == str(row.id))
        assert fila["status"] == SignupStatus.PENDING.value
        assert fila["partner"] is None, "a medias no tiene empresa: no puede parecer que la tiene"
        assert fila["expires_at"], "lo que caduca se enseña con su caducidad"


class TestReenviarSinEntrarEnLaVpc:
    async def test_reenviar_manda_correo_y_deja_muerto_el_enlace_anterior(
        self,
        client: Any,
        db_session: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """**El enlace viejo tiene que morir.** Si convivieran dos vivos, el
        reenvío duplicaría la superficie en vez de reemplazarla."""
        sent = _mail_sink(monkeypatch)
        row = await _pending(db_session)
        hash_viejo = row.token_hash

        r = await client.post(f"/admin/signups/{row.id}/resend", headers=admin_headers)
        assert r.status_code == 200
        assert len(sent) == 1, "reenviar sin mandar el correo no es reenviar"

        await db_session.refresh(row)
        assert row.status == SignupStatus.REVOKED.value
        # Y hay una nueva, viva, para el mismo correo.
        nueva = await SignupRequestRepository(db_session).get_pending_by_email(row.email)
        assert nueva is not None and nueva.token_hash != hash_viejo

    async def test_no_se_reenvia_una_solicitud_ya_consumida(
        self,
        client: Any,
        db_session: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ya tiene cuenta: reenviarle un alta le mandaría a rehacer lo hecho."""
        sent = _mail_sink(monkeypatch)
        row, _outcome = await _born(db_session)

        r = await client.post(f"/admin/signups/{row.id}/resend", headers=admin_headers)
        assert r.status_code == 409
        assert sent == [], "una solicitud muerta no manda correo"

    async def test_no_se_reenvia_una_caducada_sin_resucitarla(
        self,
        client: Any,
        db_session: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent = _mail_sink(monkeypatch)
        row = await _pending(db_session)
        row.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db_session.commit()

        r = await client.post(f"/admin/signups/{row.id}/resend", headers=admin_headers)
        assert r.status_code == 409
        assert sent == []

    async def test_reenviar_deja_rastro_en_auditoria(
        self,
        client: Any,
        db_session: Any,
        admin_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Una acción de operador que manda un correo a un desconocido no puede
        no dejar rastro."""
        import sqlalchemy as sa

        from nexus_api.db.models import AuditLog

        _mail_sink(monkeypatch)
        row = await _pending(db_session)
        await client.post(f"/admin/signups/{row.id}/resend", headers=admin_headers)

        n = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "signup.resend", AuditLog.target == f"signup:{row.id}")
        )
        assert n == 1


class TestSigueDetrasDelTokenDeOperador:
    async def test_listar_sin_token_401(self, client: Any) -> None:
        assert (await client.get("/admin/signups")).status_code == 401

    async def test_reenviar_sin_token_401(self, client: Any) -> None:
        r = await client.post(f"/admin/signups/{uuid.uuid4()}/resend")
        assert r.status_code == 401
