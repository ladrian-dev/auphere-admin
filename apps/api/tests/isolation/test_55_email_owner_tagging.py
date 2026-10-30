"""Garantía 6 — el registro de cada correo dice de qué negocio es (spec 051, R1.6).

Todo log lleva el negocio al que pertenece (``architecture/agent-isolation.md``
§6). Un correo es un log más: en staging, ``email.suppressed`` lleva destinatario
y enlaces de un solo uso, y sin el partner o el cliente no se puede filtrar por
negocio ni demostrar que un negocio no ve lo de otro.

**El barrido no enumera los sitios que envían.** Recorre el código de la API, de
sus scripts y del worker, encuentra cada llamada a ``send_template`` o
``send_localized`` y le pregunta al catálogo de quién es ese tipo de correo. Un
sitio nuevo que envíe un correo de partner sin decir de qué partner aparece
aquí solo, sin que nadie se acuerde de añadirlo.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any

import pytest
import structlog

from nexus_api.config import get_settings
from nexus_api.services.email import send_template
from nexus_api.services.email_catalog import CATALOG, EmailKind

pytestmark = pytest.mark.isolation

_REPO = pathlib.Path(__file__).resolve().parents[4]
_ROOTS = (
    _REPO / "apps" / "api" / "src",
    _REPO / "apps" / "api" / "scripts",
    _REPO / "apps" / "worker" / "src",
)
_SENDERS = {"send_template", "send_localized"}
_NEEDS = {"partner": {"partner_id"}, "client": {"tenant_id", "client_ref"}}


def _imports_email(tree: ast.Module) -> bool:
    """El módulo importa el envío de correo. WhatsApp también tiene un
    ``send_template`` (las plantillas de Meta), y no es esto."""
    return any(
        isinstance(node, ast.ImportFrom) and node.module == "nexus_api.services.email"
        for node in ast.walk(tree)
    )


def _calls() -> list[tuple[str, int, str, set[str]]]:
    """(fichero, línea, tipo, keywords) de cada envío por catálogo."""
    found: list[tuple[str, int, str, set[str]]] = []
    for root in _ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            if not _imports_email(tree):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                # La función importada (``send_template(...)``) o el módulo
                # (``email.send_template(...)``). ``adapter.send_template`` es
                # WhatsApp, aunque viva en el mismo fichero.
                if isinstance(func, ast.Name):
                    name = func.id
                elif (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "email"
                ):
                    name = func.attr
                else:
                    continue
                if name not in _SENDERS:
                    continue
                if path.name == "email.py" and path.parent.name == "services":
                    continue  # send_localized llamando a send_template
                kind = node.args[0] if node.args else None
                label = kind.attr if isinstance(kind, ast.Attribute) else ast.unparse(kind or node)
                keywords = {k.arg for k in node.keywords if k.arg}
                found.append((str(path.relative_to(_REPO)), node.lineno, label, keywords))
    return found


def test_hay_envios_que_barrer() -> None:
    """Si el barrido no encuentra nada, no está barriendo: está roto."""
    assert len(_calls()) >= 15


@pytest.mark.parametrize("call", _calls(), ids=lambda c: f"{c[0]}:{c[1]}")
def test_cada_envio_dice_de_que_negocio_es(call: tuple[str, int, str, set[str]]) -> None:
    path, line, label, keywords = call
    assert label in EmailKind.__members__, (
        f"{path}:{line} envía {label!r}, que no es un EmailKind: el barrido no puede saber de quién es"
    )
    owner = CATALOG[EmailKind[label]].owner
    if owner == "none":
        return
    assert keywords & _NEEDS[owner], (
        f"{path}:{line} envía {label} (de un {owner}) sin decir de qué {owner}: "
        f"le falta {' o '.join(sorted(_NEEDS[owner]))}"
    )


@pytest.mark.asyncio
async def test_el_registro_lleva_el_negocio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "email_delivery", "log", raising=False)
    with structlog.testing.capture_logs() as logs:
        await send_template(
            EmailKind.WALLET_EMPTY,
            to="ops@a.com",
            subject="s",
            variables={"PARTNER_NAME": "A", "PERIOD": "p", "BILLING_URL": "u"},
            partner_id="partner-a",
        )
        await send_template(
            EmailKind.CLIENT_BALANCE_OUT,
            to="ana@cliente.com",
            subject="s",
            variables={"CLIENT_NAME": "C", "CONSOLE_URL": "u"},
            partner_id="partner-a",
            client_ref="cliente-c",
        )
    events: list[dict[str, Any]] = [e for e in logs if e["event"] == "email.suppressed"]
    assert [(e["owner"], e.get("partner_id"), e.get("client_ref")) for e in events] == [
        ("partner", "partner-a", None),
        ("client", "partner-a", "cliente-c"),
    ]
