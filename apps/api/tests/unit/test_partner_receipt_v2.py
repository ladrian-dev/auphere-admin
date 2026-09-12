"""Spec 005 · R8 — el recibo deja de ser la factura.

El cambio no es de formato, es de **papel**. Hasta ahora el recibo era el
documento que se pagaba: llevaba «total a pagar» y una fecha de vencimiento.
Desde que el proveedor emite factura, esa factura es el documento fiscal, y el
recibo pasa a ser **lo que el proveedor no sabe**: qué cliente consumió qué, y
cómo se convirtieron las comisiones desde pesos chilenos.

Dos documentos con el mismo importe y dos papeles distintos. Dejar «total a
pagar» en los dos es pedirle a alguien que pague dos veces — y aunque no lo
haga, le obliga a averiguar cuál de los dos era el bueno.
"""

from __future__ import annotations

import pytest

from nexus_api.services.partner_receipt import ReceiptLine, receipt_kind

pytestmark = [pytest.mark.asyncio]


def _line(model: str, cents: int = 0, **over) -> ReceiptLine:
    import uuid

    base: dict = {
        "tenant_id": uuid.uuid4(),
        "tenant_slug": "cliente-uno",
        "tenant_name": "Cliente Uno",
        "model": model,
        "description": "línea",
        "amount_cents": cents,
    }
    base.update(over)
    return ReceiptLine(**base)


async def test_the_receipt_is_a_statement_not_an_invoice() -> None:
    """R8.2: el papel del documento, declarado en el propio módulo."""
    assert receipt_kind() == "statement"


async def test_membership_is_one_of_the_line_models() -> None:
    """R8.1: la línea de membresía existe como modelo, no como texto suelto."""
    from nexus_api.services.partner_receipt import LINE_MODELS

    assert "membership" in LINE_MODELS


async def test_consumption_is_one_of_the_line_models() -> None:
    from nexus_api.services.partner_receipt import LINE_MODELS

    assert "consumption" in LINE_MODELS


async def test_the_old_models_survive() -> None:
    """Lo que ya facturaba sigue facturando: esto añade, no sustituye."""
    from nexus_api.services.partner_receipt import LINE_MODELS

    for model in ("commission", "subscription", "inactive"):
        assert model in LINE_MODELS


async def test_the_currency_detail_is_what_the_provider_does_not_know() -> None:
    """R8.3. La conversión desde CLP no está en ninguna factura de Stripe."""
    from decimal import Decimal

    line = _line("commission", 5_000, commission_clp=Decimal("4500"))
    assert line.commission_clp == Decimal("4500")
