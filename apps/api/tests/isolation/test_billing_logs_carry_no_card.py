"""Spec 005 · garantía 6 — ningún registro del cobro lleva tarjeta ni conversación.

Cubre V09, V27 y V55, que el quickstart enuncia por separado porque llegan
desde tres requisitos distintos (R2.2, R4.6 y la garantía 6). Es una sola
comprobación.

Dos mitades, y la segunda es la que se olvida:

1. **Datos de tarjeta.** El proveedor no nos los manda, así que esto no
   protege de él: protege de nosotros, el día que alguien añada el objeto
   entero del aviso a un log «para diagnosticar».
2. **Contenido de conversación.** El camino del dinero pasa junto al del turno
   —el mismo turno que se cobra lleva lo que escribió un cliente final— y un
   campo añadido a un log es como ese texto sale de su tenant (§III). Es
   exactamente lo que ``test_wallet_events_are_logged.py`` ya vigila para el
   libro.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import structlog
import structlog.testing

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

_SRC = Path(__file__).resolve().parents[2] / "src" / "nexus_api"
_BILLING = _SRC / "billing"

#: Claves que no pueden aparecer en un registro del camino del cobro.
_FORBIDDEN_KEYS = (
    "card",
    "pan",
    "cvc",
    "cvv",
    "number",
    "last4",
    "exp_month",
    "exp_year",
    "text",
    "body",
    "content",
    "message",
    "prompt",
    "answer",
    "transcript",
)

#: Un PAN de prueba y uno con forma de tarjeta real.
_PAN = re.compile(r"\b(?:\d[ -]?){13,19}\b")


@pytest.fixture
def captured():
    with structlog.testing.capture_logs() as events:
        yield events


async def test_no_billing_log_call_passes_a_forbidden_key() -> None:
    """Estructural: se mira lo que el código PASA, no lo que se llegó a emitir.

    Un test que solo ejercite un camino deja sin cubrir los demás. Éste lee
    todas las llamadas a logging del paquete de cobro.
    """
    import ast

    offenders: list[str] = []
    for path in _BILLING.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            method = func.attr if isinstance(func, ast.Attribute) else ""
            if method not in {"debug", "info", "warning", "error", "exception", "critical"}:
                continue
            for kw in node.keywords:
                if kw.arg and kw.arg.lower() in _FORBIDDEN_KEYS:
                    offenders.append(f"{path.name}: {method}(..., {kw.arg}=...)")
    assert not offenders, (
        f"registros del cobro con claves prohibidas: {offenders}. El camino del "
        "dinero pasa junto al del contenido, y un campo añadido para "
        "diagnosticar es como el texto de un cliente final sale de su tenant"
    )


async def test_no_stored_event_payload_looks_like_a_card(captured) -> None:
    """Lo que se guarda en ``billing_events.payload`` tampoco.

    La tabla guarda el aviso para poder reprocesarlo. Si el filtro de entrada
    dejara pasar un objeto de método de pago, el dato de tarjeta quedaría en
    nuestra base de datos — que es la frase que la spec promete que no ocurre.
    """
    from nexus_api.billing.events import redact_payload

    dirty = {
        "id": "evt_1",
        "type": "invoice.paid",
        "data": {
            "object": {
                "id": "in_1",
                "amount_paid": 2000,
                "payment_method_details": {
                    "card": {"last4": "4242", "exp_month": 12, "brand": "visa"}
                },
                "customer_details": {"email": "a@b.com"},
            }
        },
    }
    clean = redact_payload(dirty)
    blob = str(clean)
    for key in ("last4", "exp_month", "4242"):
        assert key not in blob, f"«{key}» sobrevivió al filtro: {blob[:400]}"
    assert not _PAN.search(blob), f"algo con forma de tarjeta sobrevivió: {blob[:400]}"
    # Y lo que SÍ tiene que sobrevivir, porque es lo que se necesita para actuar.
    assert clean["id"] == "evt_1"
    assert clean["data"]["object"]["amount_paid"] == 2000
