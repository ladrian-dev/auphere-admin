"""Spec 005 · las llaves del cobro, y qué pasa cuando no están.

El contrato (`contracts/webhook.md`) dice que la aplicación **arranca igual**
sin ellas y que lo que queda cerrado es el paquete de cobro. Es deliberado:
arrancar sin cobro es un estado honesto (§V); arrancar con un secreto de
mentira acepta avisos falsos.
"""

from __future__ import annotations

import pytest

from nexus_api.config import Settings

pytestmark = [pytest.mark.asyncio]


def _settings(**over: str) -> Settings:
    base = {
        "billing_api_key": "",
        "billing_public_key": "",
        "billing_webhook_secret": "",
    }
    return Settings(**{**base, **over})  # type: ignore[arg-type]


async def test_the_three_keys_have_no_default() -> None:
    """Ni ``change-me`` ni nada que parezca una llave.

    Un valor de fábrica en un secreto de firma es peor que no tenerlo: el
    webhook aceptaría lo que firme cualquiera que lea el repositorio.
    """
    s = Settings()  # type: ignore[call-arg]
    for name in ("billing_api_key", "billing_public_key", "billing_webhook_secret"):
        value = getattr(s, name)
        assert value == "", f"{name} trae un valor por defecto: {value!r}"


async def test_billing_is_closed_when_any_key_is_missing() -> None:
    assert _settings().billing_enabled is False
    assert _settings(billing_api_key="sk_test_x").billing_enabled is False
    assert (
        _settings(billing_api_key="sk_test_x", billing_public_key="pk_x").billing_enabled is False
    )


async def test_billing_is_open_only_with_all_three() -> None:
    s = _settings(
        billing_api_key="sk_test_x",
        billing_public_key="pk_test_x",
        billing_webhook_secret="whsec_x",
    )
    assert s.billing_enabled is True


async def test_whitespace_is_not_a_key() -> None:
    """Una variable de entorno puesta a un espacio es un despiste, no una llave."""
    s = _settings(billing_api_key="   ", billing_public_key="  ", billing_webhook_secret=" ")
    assert s.billing_enabled is False
