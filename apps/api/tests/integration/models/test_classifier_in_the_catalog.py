"""Requisito 69.4: el modelo del clasificador se puede llamar y se puede cobrar.

Sin fila activa en el catálogo, el transporte rechaza cada intento antes de salir y el
turno cae en la reserva sin que se note. Con la fila y sin pesos, el turno no se cobra.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.config import WorkerSettings

from nexus_api.core.respond_catalog import require_hop_model
from nexus_api.metering.pricing_policy import weights_for
from nexus_api.services.router_catalog import TokenEstimate, estimate_cost_micros, load_snapshot

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MODEL = WorkerSettings.model_fields["llm_classify_model"].default


async def test_the_classifier_can_be_called_priced_and_charged(db_session: Any) -> None:
    assert MODEL == "anthropic/claude-haiku-5-5"
    snapshot = await load_snapshot(db_session)

    assert require_hop_model(MODEL) == MODEL, "lee la lista ejecutable que sale de la base"

    deployment = snapshot.deployments[MODEL]
    price = deployment.current_price()
    assert price is not None
    # 140 de entrada y 35 de salida: lo medido en una clasificación.
    cost = estimate_cost_micros(price, TokenEstimate(input_tokens=140, output_tokens=35))
    assert cost == pytest.approx(14 + 17.5, abs=1)

    row = (
        await db_session.execute(
            sa.text(
                "SELECT quota_weight_input AS input, quota_weight_cache_read AS cache_read, "
                "quota_weight_output AS output FROM model_profiles WHERE model_id = :m"
            ),
            {"m": MODEL},
        )
    ).one()
    await db_session.rollback()
    lanes = weights_for(MODEL, {MODEL: dict(row._mapping)})
    assert lanes is not None
    assert Decimal(str(row.output)) == Decimal("0.11"), "2,2 sobre 10 USD por millón de unidades"
