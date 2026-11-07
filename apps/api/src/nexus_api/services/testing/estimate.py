"""What running an agent's suite will cost, before running it — spec 047, amendment
of 2026-10-29 (requirement 61.8; research D52), recalibrated on 2026-11-04.

A pass is a conversation: :data:`AGENT_CALLS` calls of the agent (its tool loop
included), :data:`CLASSIFY_CALLS` to the classifier, :data:`CUSTOMER_CALLS` messages of
the simulated customer and :data:`JUDGE_CALLS` to the judge, three passes per test. The
sizes are the ones measured in staging (2026-10-30 to 2026-11-05): the agent resends a
prompt of up to 6,000 tokens, most of it from the cache. A suite of 17 tests with tools
cost $1.63 to $2.91 and one of 8 without them, $0.52. Counting that prompt as fresh, with
four turns on the agent's model for everyone, said $10.97.

The estimate multiplies that by each model's current price (the catalog's,
``model_prices``), at the partner's price (the same multiplier as «Construcción y
pruebas»). A price that is not known is never a zero cost: the estimate is ``None`` and
says which model is missing.

It is an estimate, not a quote: the real cost is measured per call in «Construcción y
pruebas» (``usage_records``, ``source = tests``). The console only asks when it does not
fit in what is left of that budget (requirement 66.5).
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

AGENT_CALLS: Final = 2
CLASSIFY_CALLS: Final = 2
CUSTOMER_CALLS: Final = 2
JUDGE_CALLS: Final = 1
#: Size of each call, as measured: the agent resends its prompt, tools and history,
#: most of it from the cache, and writes little.
AGENT_CALL: Final = TokenEstimate(input_tokens=1_500, cache_read_tokens=4_500, output_tokens=45)
CLASSIFY_CALL: Final = TokenEstimate(input_tokens=140, output_tokens=35)
CUSTOMER_CALL: Final = TokenEstimate(input_tokens=400, output_tokens=60)
#: With the business data to check against (66.9).
JUDGE_CALL: Final = TokenEstimate(input_tokens=800, output_tokens=120)
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
    classify_model: str | None = None,
    customer_model: str | None,
    judge_model: str | None,
) -> SuiteEstimate:
    """The estimate for ``tests`` tests (pure)."""
    passes = max(0, tests) * RUNS
    plan = [
        ("agent", agent_model, passes * AGENT_CALLS, AGENT_CALL),
        ("classify", classify_model, passes * CLASSIFY_CALLS if classify_model else 0,
         CLASSIFY_CALL),
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
        models={
            "agent": agent_model,
            "classify": classify_model,
            "customer_sim": customer_model,
            "judge": judge_model,
        },
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
    classify_model = get_worker_settings().llm_classify_model
    models = {agent_model, classify_model, platform_model("customer_sim"), platform_model("judge")}
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
        classify_model=classify_model,
        customer_model=platform_model("customer_sim"),
        judge_model=platform_model("judge"),
    )


__all__ = [
    "AGENT_CALLS",
    "CLASSIFY_CALLS",
    "CUSTOMER_CALLS",
    "JUDGE_CALLS",
    "SuiteEstimate",
    "estimate_for_agent",
    "estimate_suite",
]
