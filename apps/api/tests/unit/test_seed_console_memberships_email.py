"""La invitación del script de alta de pilotos — spec 051 (``team_invite``).

``scripts/seed_console_memberships.py --email`` mandaba su propio HTML, y sin
``--console-origin`` el enlace era una ruta relativa que ningún cliente de
correo sabe abrir. Ahora es el mismo correo que la invitación desde Equipo, con
el enlace absoluto de ``console_link`` salvo que se pida otro origen.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from nexus_api.services.email_catalog import EmailKind, console_link

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_console_memberships.py"
EXPIRES = datetime(2026, 11, 6, 9, 30, tzinfo=UTC)


def _script() -> ModuleType:
    name = "seed_console_memberships_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def _fake(kind: EmailKind, **kwargs: Any) -> bool:
        sent.append({"kind": kind, **kwargs})
        return True

    monkeypatch.setattr("nexus_api.services.email.send_template", _fake)
    return sent


def test_sin_origen_el_enlace_es_el_de_la_consola_del_entorno() -> None:
    script = _script()
    assert script.invitation_link("tok-1", "") == console_link("/invite/tok-1")
    assert script.invitation_link("tok-1", "").startswith(("http://", "https://"))


def test_con_origen_el_enlace_usa_ese_origen() -> None:
    script = _script()
    assert (
        script.invitation_link("tok-1", "https://console.auphere.com/")
        == "https://console.auphere.com/invite/tok-1"
    )


@pytest.mark.asyncio
async def test_el_correo_es_la_invitacion_de_equipo(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture(monkeypatch)
    partner = SimpleNamespace(id=uuid.uuid4(), name="Facelad")
    ok = await _script().email_invitation(
        email="maria@facelad.com",
        partner=partner,
        role="owner",
        accept_url="https://console.auphere.com/invite/tok-1",
        expires_at=EXPIRES,
        locale="es",
    )
    assert ok is True
    [mail] = sent
    assert mail["kind"] is EmailKind.TEAM_INVITE
    assert mail["to"] == "maria@facelad.com"
    assert mail["locale"] == "es"
    # Garantía 6: la invitación es del partner, y su registro lo dice.
    assert mail["partner_id"] == partner.id
    assert mail["subject"] == "Te han invitado a unirte a Facelad en Auphere"
    assert mail["variables"] == {
        "INVITER": "Auphere",
        "PARTNER_NAME": "Facelad",
        "ROLE_LABEL": "Propietario",
        "EXPIRES_ON": "6 de noviembre de 2026",
        "ACCEPT_URL": "https://console.auphere.com/invite/tok-1",
    }


@pytest.mark.asyncio
async def test_en_ingles(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture(monkeypatch)
    await _script().email_invitation(
        email="maria@facelad.com",
        partner=SimpleNamespace(id=uuid.uuid4(), name="Facelad"),
        role="billing",
        accept_url="https://console.auphere.com/invite/tok-1",
        expires_at=EXPIRES,
        locale="en",
    )
    [mail] = sent
    assert mail["locale"] == "en"
    assert mail["subject"] == "You're invited to join Facelad on Auphere"
    assert mail["variables"]["INVITER"] == "Auphere"
    assert mail["variables"]["ROLE_LABEL"] == "Billing"
    assert mail["variables"]["EXPIRES_ON"] == "November 6, 2026"
