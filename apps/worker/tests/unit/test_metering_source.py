"""El origen del consumo sobrevive al viaje por el stream (0079).

El colector etiqueta el turno; el consumidor tiene que poner esa etiqueta
en la fila y —esto es lo que más importa— **no alimentar el contador de
presupuesto con las pruebas del operador**. El contador de WP-20 degrada o
corta el servicio del cliente; dispararlo con turnos de QA apagaría el
grader de un cliente en producción porque alguien estaba revisando su
agente.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest

from nexus_worker.metering import consumer

pytestmark = pytest.mark.asyncio


def _entry(source: str | None, *, tenant_id: uuid.UUID) -> dict[str, str]:
    fields = {
        "tenant_id": str(tenant_id),
        "turn_id": "t1",
        "events": json.dumps(
            [
                {
                    "meter": "llm.input_tokens",
                    "quantity": 100,
                    "idempotency_key": "t1:1:llm.input_tokens",
                    "occurred_at": "2026-08-14T10:00:00+00:00",
                    "provider": "anthropic",
                    "model": "anthropic/claude-sonnet-4-6",
                }
            ]
        ),
    }
    if source is not None:
        fields["source"] = source
    return fields


async def test_source_reaches_the_row() -> None:
    tenant_id = uuid.uuid4()
    _, rows = consumer.rows_from_entry(_entry("qa", tenant_id=tenant_id))
    assert [r["source"] for r in rows] == ["qa"]


async def test_an_entry_without_source_is_channel() -> None:
    """Compatibilidad hacia atrás: lo que quedó en el stream antes del
    despliegue de la 0079 es, todo, tráfico de canal. Sin este defecto, un
    reproceso tras el corte tumbaría el ``INSERT`` contra el CHECK."""
    _, rows = consumer.rows_from_entry(_entry(None, tenant_id=uuid.uuid4()))
    assert [r["source"] for r in rows] == ["channel"]


async def test_an_unknown_source_dead_letters_the_entry() -> None:
    """Se rechaza aquí, no en la base. El CHECK de la tabla tumbaría el
    ``INSERT`` del lote ENTERO —incluidas las filas sanas de otros
    turnos— y el PEL se atascaría. Lanzando en el parseo, la entrada
    envenenada se va sola al DLQ y el resto entra."""
    with pytest.raises(ValueError, match="source"):
        consumer.rows_from_entry(_entry("cortesia-de-la-casa", tenant_id=uuid.uuid4()))


async def test_qa_spend_does_not_touch_the_budget_counter(monkeypatch) -> None:
    """El fallo que esto evita no es contable, es operativo: un operador
    probando a fondo dejaría al cliente sin grader en producción."""
    calls: list[tuple[str, Decimal]] = []

    async def _fake_add_spend(_redis, *, scope, scope_id, amount):
        calls.append((scope, amount))

    async def _no_partner(_tenant_id):
        return None

    monkeypatch.setattr(consumer, "add_spend", _fake_add_spend)
    monkeypatch.setattr(consumer, "_partner_for", _no_partner)

    rows = [
        {"cost_usd": Decimal("1.00"), "source": "channel"},
        {"cost_usd": Decimal("9.00"), "source": "qa"},
    ]
    await consumer._bump_budget(uuid.uuid4(), rows)

    assert [c[0] for c in calls] == ["tenant"]
    assert calls[0][1] == Decimal("1.00"), "los 9 USD del Playground no son del cliente"


async def test_a_turn_of_pure_qa_spend_bumps_nothing(monkeypatch) -> None:
    calls: list[str] = []

    async def _fake_add_spend(_redis, *, scope, scope_id, amount):
        calls.append(scope)

    monkeypatch.setattr(consumer, "add_spend", _fake_add_spend)

    await consumer._bump_budget(uuid.uuid4(), [{"cost_usd": Decimal("5.00"), "source": "qa"}])
    assert calls == []
