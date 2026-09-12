"""Spec 005 · el cliente del proveedor: claves de idempotencia y fail-closed.

Unidad y no integración porque lo que se comprueba es **cómo se construye la
llamada**, no qué contesta Stripe. Las claves de idempotencia son el mecanismo
que impide que un reintento nuestro doble un cobro, y su forma tiene una regla
que no es cosmética: **nunca llevan un identificador del proveedor**.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.billing import provider as prov

pytestmark = [pytest.mark.asyncio]

_PID = uuid.UUID("7f3a1c62-0000-4000-8000-000000000001")


async def test_the_key_carries_our_identifier_and_never_theirs() -> None:
    key = prov.idempotency_key("sub", _PID, "create")
    assert str(_PID) in key
    assert not key.startswith("cus_") and "cus_" not in key and "sub_" not in key
    assert key.startswith("billing:sub:"), key


async def test_the_discriminant_makes_a_repeated_action_distinguishable() -> None:
    """Sin discriminante, subir → bajar → volver a subir reutiliza la clave.

    Stripe devolvería la respuesta guardada del primer intento y no haría
    nada — un cambio de plan que el partner pidió y que silenciosamente no
    ocurre.
    """
    first = prov.idempotency_key("sub", _PID, "upgrade", "team", "2026-W37")
    later = prov.idempotency_key("sub", _PID, "upgrade", "team", "2026-W41")
    assert first != later


async def test_the_key_is_stable_for_the_same_action() -> None:
    """Y estable: ése es el sentido de una clave de idempotencia."""
    a = prov.idempotency_key("credit", _PID, "5000", "2026-09-12T10:03:11Z")
    b = prov.idempotency_key("credit", _PID, "5000", "2026-09-12T10:03:11Z")
    assert a == b


async def test_a_key_never_exceeds_the_provider_limit() -> None:
    """Stripe corta las claves de idempotencia en 255 caracteres."""
    key = prov.idempotency_key("sub", _PID, "upgrade", "business", "2026-W37", "x" * 400)
    assert len(key) <= 255


async def test_the_client_refuses_to_exist_without_keys() -> None:
    """Fail-closed: sin llaves no hay cliente, y quien lo pida se entera.

    La alternativa —un cliente a medias que falla en la primera llamada— haría
    que el error apareciese lejos de su causa.
    """
    with pytest.raises(prov.BillingUnavailable):
        prov.get_client(api_key="")
