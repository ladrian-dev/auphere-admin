"""Spec 065, T022 (requisitos 1.5 y 1.6): lo que costaría una respuesta del agente con cada modelo.

research.md §D14, «Estimación del selector»: de los últimos 7 días del agente (solo tráfico
del canal) salen, por respuesta, el contexto, lo leído de caché y la salida de la
conversación, y lo que costó clasificar. Cada modelo se calcula con su caché: lo leído a su
tarifa de lectura, lo no leído a la de escritura si el modelo la tiene (Anthropic y GPT-5.6)
o a la de entrada si no, por los pesos de venta, el precio de venta (10 USD por millón de
unidades) y el ``estimate_factor`` de su perfil. Sin consumo, un turno típico.

Importes en cien milésimas de dólar. Los esperados están calculados a mano aquí, con los
pesos que siembran las migraciones (multiplicador 2,2), no copiados del resultado.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

from nexus_api.core import respond_catalog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.usage_record import UsageRecord

from .test_agent_model_console import agent_of, url

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

RESPONSES = 10
#: Por respuesta: la conversación con Sol (como Jemma, la mitad desde caché) y la clasificación.
CONVERSATION = {"llm.input_tokens": 20_000, "llm.cache_read": 10_000, "llm.output_tokens": 110}
CLASSIFY = {"llm.input_tokens": 1_600, "llm.cache_read": 400, "llm.output_tokens": 32}

#: Pesos sembrados (tarifa por 2,2 entre 10): entrada, lectura, escritura, salida.
WEIGHTS = {
    "openai/gpt-5.6-sol": ("0.88", "0.088", "1.10", "4.4"),
    "openai/gpt-5.6-terra": ("0.44", "0.044", "0.55", "2.64"),
    "openai/gpt-5.6-luna": ("0.044", "0.0044", "0.055", "0.264"),
    "anthropic/claude-haiku-5-5": ("0.022", "0.0022", "0.0275", "0.11"),
}


def by_hand(model_id: str, tokens: dict[str, int]) -> Decimal:
    """Dólares de venta por respuesta de ``tokens`` con ``model_id``, según §D14."""
    w_in, w_read, w_write, w_out = (Decimal(w) for w in WEIGHTS[model_id])
    unread = Decimal(tokens["llm.input_tokens"] - tokens["llm.cache_read"])
    units = (
        unread * (w_write if w_write > 0 else w_in)
        + Decimal(tokens["llm.cache_read"]) * w_read
        + Decimal(tokens["llm.output_tokens"]) * w_out
    )
    return units / Decimal(1_000_000) * Decimal(10)


def micros(usd: Decimal) -> int:
    return int((usd * 100_000).quantize(Decimal(1)))


@pytest_asyncio.fixture(autouse=True)
async def _catalog() -> AsyncIterator[None]:
    async with get_sessionmaker()() as session:
        await respond_catalog.refresh_from_db(session)
    yield
    respond_catalog.reset()


async def spend(tenant_id: uuid.UUID, partner_id: uuid.UUID, agent_id: uuid.UUID) -> None:
    when = datetime.now(UTC) - timedelta(days=1)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        for n in range(RESPONSES):
            for task, model, tokens in (
                ("tool_turn", "openai/gpt-5.6-sol", CONVERSATION),
                ("classify", "anthropic/claude-haiku-5-5", CLASSIFY),
            ):
                for meter, qty in tokens.items():
                    session.add(
                        UsageRecord(
                            occurred_at=when,
                            tenant_id=tenant_id,
                            partner_id=partner_id,
                            meter=meter,
                            quantity=Decimal(qty),
                            billable_qty=Decimal(0),
                            provider=model.split("/")[0],
                            model=model,
                            agent_id=agent_id,
                            task=task,
                            source="channel",
                            idempotency_key=f"{agent_id}:{n}:{task}:{meter}",
                        )
                    )
        # Lo que no es del canal (pruebas, Playground) no cuenta.
        session.add(
            UsageRecord(
                occurred_at=when,
                tenant_id=tenant_id,
                partner_id=partner_id,
                meter="llm.output_tokens",
                quantity=Decimal(50_000),
                billable_qty=Decimal(0),
                model="openai/gpt-5.6-sol",
                agent_id=agent_id,
                task="tool_turn",
                source="tests",
                idempotency_key=f"{agent_id}:tests",
            )
        )
        await session.commit()


async def test_each_option_is_priced_with_its_own_cache_rules(client, console_world) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    await spend(a["tenant_id"], a["partner_id"], agent)

    body = (await client.get(url(a["ref"], agent), headers=a["headers"]())).json()
    classify = by_hand("anthropic/claude-haiku-5-5", CLASSIFY)
    expected = {
        model_id: micros(by_hand(model_id, CONVERSATION) + classify)
        for model_id in ("openai/gpt-5.6-sol", "openai/gpt-5.6-terra", "openai/gpt-5.6-luna")
    }
    got = {o["model_id"]: o["estimate"] for o in body["options"]}
    assert {m: e["amount_micros"] for m, e in got.items()} == expected
    assert {e["basis"] for e in got.values()} == {"agent_7d"}
    assert {e["currency"] for e in got.values()} == {"USD"}
    assert [o["model_id"] for o in body["options"]] == sorted(expected, key=expected.__getitem__)
    assert body["effective"]["estimate"]["amount_micros"] == expected["openai/gpt-5.6-sol"]


async def test_without_spend_a_typical_turn(client, console_world) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    body = (await client.get(url(a["ref"], agent), headers=a["headers"]())).json()
    estimates = [o["estimate"] for o in body["options"]]
    assert {e["basis"] for e in estimates} == {"nominal"}
    assert all(e["amount_micros"] > 0 for e in estimates)
    prices = [e["amount_micros"] for e in estimates]
    assert prices == sorted(prices)
