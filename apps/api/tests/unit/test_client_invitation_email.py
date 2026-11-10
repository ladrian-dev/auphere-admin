"""El correo de invitación a la consola de un cliente — spec 030 (R1.4) y
spec 051 (``client_invite``, §2 del catálogo).

Lo que pone el código: el asunto del catálogo en el idioma de la cuenta de la
persona (si ya tiene una), el enlace **absoluto** y el negocio del cliente para
el registro (garantía 6). Y lo que no pone: el nombre del partner, que no le
cambia nada a quien entra en la consola de su negocio.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.services.client_invitation_email import send_client_invitation
from nexus_api.services.email_catalog import CATALOG, EmailKind, console_link, format_day

pytestmark = pytest.mark.asyncio

EXPIRES = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def _fake(kind: EmailKind, **kwargs: Any) -> bool:
        sent.append({"kind": kind, **kwargs})
        return True

    monkeypatch.setattr("nexus_api.services.email.send_template", _fake)
    return sent


async def test_sin_cuenta_sale_en_espanol_con_el_enlace_absoluto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture(monkeypatch)
    tenant_id = uuid.uuid4()
    ok = await send_client_invitation(
        email=f"nadie-{uuid.uuid4().hex[:6]}@cliente.test",
        client_name="Café Norte",
        accept_path="/invite/tok-123",
        expires_at=EXPIRES,
        tenant_id=tenant_id,
    )
    assert ok is True
    [mail] = sent
    assert mail["kind"] is EmailKind.CLIENT_INVITE
    assert mail["locale"] == "es"
    assert mail["subject"] == "Ya puedes acceder a la consola de Café Norte"
    assert mail["variables"] == {
        "CLIENT_NAME": "Café Norte",
        "EXPIRES_ON": format_day(EXPIRES.date(), "es"),
        "ACCEPT_URL": console_link("/invite/tok-123"),
    }
    assert mail["variables"]["EXPIRES_ON"] == "6 de noviembre de 2026"
    assert mail["variables"]["ACCEPT_URL"].startswith(("http://", "https://"))
    # Garantía 6: el correo es del cliente, y su registro lo dice.
    assert CATALOG[EmailKind.CLIENT_INVITE].owner == "client"
    assert mail["tenant_id"] == tenant_id


async def test_con_cuenta_en_ingles_sale_en_ingles(
    monkeypatch: pytest.MonkeyPatch, db_session: Any
) -> None:
    email = f"ana-{uuid.uuid4().hex[:6]}@cliente.test"
    await db_session.execute(
        sa.text(
            "INSERT INTO console_auth.principals (id, email, password_hash, locale) "
            "VALUES (:i, :e, 'scrypt$x', 'en')"
        ),
        {"i": str(uuid.uuid4()), "e": email},
    )
    await db_session.commit()
    sent = _capture(monkeypatch)
    await send_client_invitation(
        email=email,
        client_name="Café Norte",
        accept_path="/invite/tok-456",
        expires_at=EXPIRES,
        tenant_id=uuid.uuid4(),
    )
    [mail] = sent
    assert mail["locale"] == "en"
    assert mail["subject"] == "Your access to the Café Norte console is ready"
    assert mail["variables"]["EXPIRES_ON"] == "November 6, 2026"


async def test_no_nombra_al_partner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec 030: quién vende la consola no le cambia nada a quien entra. El
    servicio ni siquiera recibe el nombre del partner, y no pasa su id."""
    sent = _capture(monkeypatch)
    await send_client_invitation(
        email=f"x-{uuid.uuid4().hex[:6]}@cliente.test",
        client_name="Café Norte",
        accept_path="/invite/t",
        expires_at=EXPIRES,
        tenant_id=uuid.uuid4(),
    )
    [mail] = sent
    assert mail.get("partner_id") is None
    assert set(mail["variables"]) == set(CATALOG[EmailKind.CLIENT_INVITE].variables)
