"""Spec 005 · el mapeo de estados es exhaustivo, y un desconocido falla.

Es el test que más barato sale escribir y más caro sale no tener: el día que
el proveedor añada un estado, la alternativa a fallar es concederle el nivel a
alguien que no lo tiene, en silencio.
"""

from __future__ import annotations

import pytest

from nexus_api.billing.ladder import (
    UnknownProviderState,
    known_provider_states,
    pool_refills_in,
    state_from_provider,
)
from nexus_api.db.models.membership import (
    STATE_CANCELED,
    STATE_CURRENT,
    STATE_PAYMENT_FAILED,
    STATE_UNPAID,
    SUBSCRIPTION_STATES,
)

pytestmark = [pytest.mark.asyncio]

#: Los ocho estados de suscripción de Stripe, verificados el 2026-09-12.
_PROVIDER_STATES = (
    "trialing",
    "active",
    "incomplete",
    "incomplete_expired",
    "past_due",
    "unpaid",
    "canceled",
    "paused",
)


async def test_every_provider_state_is_mapped() -> None:
    """Exhaustivo: los ocho, sin agujeros."""
    missing = [s for s in _PROVIDER_STATES if s not in known_provider_states()]
    assert not missing, f"estados del proveedor sin mapear: {missing}"


async def test_every_mapping_lands_on_one_of_our_four() -> None:
    for provider_state in _PROVIDER_STATES:
        assert state_from_provider(provider_state) in SUBSCRIPTION_STATES


async def test_an_unknown_state_raises_instead_of_guessing() -> None:
    with pytest.raises(UnknownProviderState):
        state_from_provider("subscription_on_the_moon")


async def test_the_ladder_lands_where_adr037_says() -> None:
    assert state_from_provider("active") == STATE_CURRENT
    assert state_from_provider("trialing") == STATE_CURRENT
    assert state_from_provider("past_due") == STATE_PAYMENT_FAILED
    assert state_from_provider("unpaid") == STATE_UNPAID
    assert state_from_provider("canceled") == STATE_CANCELED
    assert state_from_provider("incomplete_expired") == STATE_CANCELED


async def test_paused_does_not_read_as_healthy() -> None:
    """No lo usamos, pero el mapeo no puede tener agujeros.

    Si ``paused`` cayera en «al corriente», una suscripción que dejó de
    facturar seguiría reponiendo pool gratis.
    """
    assert state_from_provider("paused") != STATE_CURRENT


async def test_only_the_healthy_state_refills_the_pool() -> None:
    assert pool_refills_in(STATE_CURRENT) is True
    for state in (STATE_PAYMENT_FAILED, STATE_UNPAID, STATE_CANCELED):
        assert pool_refills_in(state) is False, f"{state} repone pool"
