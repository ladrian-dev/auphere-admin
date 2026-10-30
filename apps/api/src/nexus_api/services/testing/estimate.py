"""What running an agent's suite will cost, before running it — spec 047, amendment
of 2026-10-29 (requirement 61.8; research D52).

Since the amendment a pass is a conversation, not one turn: on average
:data:`AGENT_TURNS` turns of the agent, :data:`CUSTOMER_CALLS` messages of the
simulated customer and :data:`JUDGE_CALLS` call to the judge, three passes per
test. The estimate multiplies that by each model's current price (the catalog's,
``model_prices``) with a nominal token size per call, at the partner's price (the
same multiplier as «Construcción y pruebas»). A price that is not known is never
a zero cost: the estimate is ``None`` and says which model is missing.

It is an estimate, not a quote: the real cost is measured per call in
«Construcción y pruebas» (``usage_records``, ``source = tests``).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.services.router_catalog import Price, TokenEstimate, estimate_cost_micros
from nexus_api.services.testing.runs import RUNS

AGENT_TURNS: Final = 4
CUSTOMER_CALLS: Final = 4
JUDGE_CALLS: Final = 1
#: Nominal size of each call: the agent resends its prompt, tools and history.
AGENT_CALL: Final = TokenEstimate(input_tokens=3_000, output_tokens=250)
CUSTOMER_CALL: Final = TokenEstimate(input_tokens=900, output_tokens=80)
JUDGE_CALL: Final = TokenEstimate(input_tokens=1_500, output_tokens=150)
#: The partner's price over the provider's cost, as in «Construcción y pruebas».
PRICE_MULTIPLIER: Final = Decimal("2.2")


@dataclass
class SuiteEstimate:
    amount_micros: int | None
    currency: str = "USD"
    calls: dict[str, int] = field(default_factory=dict)
    models: dict[str, str | None] = field(default_factory=dict)
    unknown: list[str] = field(default_factory=list)

    def out(self) -> dict[str, Any]:
        return {
            "estimate": {"amount_micros": self.amount_micros, "currency": self.currency}
            if self.amount_micros is not None
            else None,
            "calls": dict(self.calls),
            "unknown_prices": list(self.unknown),
        }


def estimate_suite(
    *,
    tests: int,
    prices: Mapping[str, Price | None],
    agent_model: str,
    customer_model: str | None,
    judge_model: str | None,
) -> SuiteEstimate:
    """The estimate for ``tests`` tests (pure)."""
    passes = max(0, tests) * RUNS
    plan = [
        ("agent", agent_model, passes * AGENT_TURNS, AGENT_CALL),
        ("customer_sim", customer_model, passes * CUSTOMER_CALLS if customer_model else 0,
         CUSTOMER_CALL),
        ("judge", judge_model, passes * JUDGE_CALLS if judge_model else 0, JUDGE_CALL),
    ]  # fmt: skip
    total = Decimal(0)
    unknown: list[str] = []
    calls: dict[str, int] = {}
    for name, model, count, size in plan:
        calls[name] = count
        if not count or model is None:
            continue
        price = prices.get(model)
        cost = estimate_cost_micros(price, size) if price is not None else None
        if cost is None:
            if model not in unknown:
                unknown.append(model)
            continue
        total += Decimal(cost) * count
    amount = None if unknown else int((total * PRICE_MULTIPLIER).to_integral_value())
    return SuiteEstimate(
        amount_micros=amount,
        calls=calls,
        models={"agent": agent_model, "customer_sim": customer_model, "judge": judge_model},
        unknown=unknown,
    )


async def estimate_for_agent(
    session: AsyncSession, agent_id: uuid.UUID, *, tests: int
) -> SuiteEstimate:
    """The estimate for this agent, inside its client's scope: its pinned model if
    it has one in the catalog (else the platform's answering model), and the
    platform's simulated customer and judge (64.2)."""
    from nexus_worker.config import get_worker_settings
    from nexus_worker.platform_models import platform_model

    from nexus_api.services.router_catalog import load_snapshot
    from nexus_api.services.testing.runs import target_version

    snapshot = await load_snapshot(session, refresh_hop=False)
    version = await target_version(session, agent_id)
    policy = dict(
        ((version.policies or {}) if version is not None else {}).get("model_policy") or {}
    )
    pinned = str(policy.get("deployment") or "") if policy.get("kind") == "pinned" else ""
    agent_model = (
        pinned if pinned in snapshot.deployments else get_worker_settings().llm_respond_model
    )
    models = {agent_model, platform_model("customer_sim"), platform_model("judge")}
    prices: dict[str, Price | None] = {
        model: (
            snapshot.deployments[model].current_price() if model in snapshot.deployments else None
        )
        for model in models
    }
    return estimate_suite(
        tests=tests,
        prices=prices,
        agent_model=agent_model,
        customer_model=platform_model("customer_sim"),
        judge_model=platform_model("judge"),
    )


__all__ = [
    "AGENT_TURNS",
    "CUSTOMER_CALLS",
    "JUDGE_CALLS",
    "SuiteEstimate",
    "estimate_for_agent",
    "estimate_suite",
]
