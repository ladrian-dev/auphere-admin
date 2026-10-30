"""El aviso interno de una consulta de soporte — spec 051, catálogo §20 (T017).

``api/console/support.py`` avisa al equipo de Auphere con la plantilla
``internal_alert``: solo en español, con el asunto ``[Auphere] Consulta …``, el
titular que nombra al partner y una línea por dato. Lleva el negocio (garantía
6) y, como todo correo, escapa el texto que escribió el partner.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.api.console import support
from nexus_api.api.console.schemas_capabilities import SupportTicketIn
from nexus_api.config import get_settings
from nexus_api.services.email_catalog import CATALOG, EmailKind, EmailLines

pytestmark = pytest.mark.asyncio


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def _send(kind: EmailKind, **kw: Any) -> bool:
        calls.append({"kind": kind, **kw})
        return True

    monkeypatch.setattr("nexus_api.services.email.send_template", _send)
    return calls


async def _open(**over: Any) -> None:
    body = SupportTicketIn(
        category="capability",
        topic="connector.shopify",
        client_ref="acme-01",
        need="Quieren que el agente lea los pedidos <de Shopify>",
        checked=["Conectores activos", "Catálogo de herramientas"],
        alternative="Exportar los pedidos a una hoja",
        bridge=True,
    )
    await support._alert_auphere(
        ticket_ref="AU-42",
        body=body,
        topic="connector.shopify",
        sla="48h",
        partner_id=over.get("partner_id", uuid.uuid4()),
        partner_name="Agencia Norte",
        partner_slug="agencia-norte",
        opened_by="maria@agencia.com",
    )


async def test_the_team_gets_an_internal_alert_in_spanish(
    sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "support_alert_email", "soporte@auphere.test")
    partner_id = uuid.uuid4()
    await _open(partner_id=partner_id)

    [mail] = sent
    assert mail["kind"] == EmailKind.INTERNAL_ALERT
    assert mail["to"] == ["soporte@auphere.test"]
    assert mail["locale"] == "es"
    assert mail["partner_id"] == partner_id, "garantía 6: el aviso lleva el negocio"
    assert mail["subject"] == "[Auphere] Consulta AU-42 · capability · connector.shopify"
    variables = mail["variables"]
    assert set(variables) == CATALOG[EmailKind.INTERNAL_ALERT].variables
    assert variables["HEADING"] == "Agencia Norte ha abierto la consulta AU-42"
    assert variables["KIND"] == "support.ticket"

    detail = variables["DETAIL"]
    assert isinstance(detail, EmailLines), "DETAIL va por lines_variable"
    lines = detail.split("<br>")
    assert "Partner: Agencia Norte (agencia-norte)" in lines
    assert "Cliente: acme-01" in lines
    assert "Qué necesita: Quieren que el agente lea los pedidos &lt;de Shopify&gt;" in lines
    assert "· Conectores activos" in lines and "· Catálogo de herramientas" in lines
    assert "Alternativa propuesta (puente): Exportar los pedidos a una hoja" in lines
    assert "SLA: 48h" in lines


async def test_without_a_support_address_only_the_log_line_is_left(
    sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "support_alert_email", "")
    await _open()
    assert sent == []
