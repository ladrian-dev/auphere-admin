"""Spec 076 — lo que ``MetaClient`` hace con la API de conversiones (contracts §4).

- ``token_scopes``: los permisos del token de un número, leídos con el token de
  la app (``GET /debug_token``), de ``data.scopes`` y de
  ``data.granular_scopes[].scope``.
- ``ensure_dataset``: ``POST /{waba_id}/dataset``, que crea u obtiene el conjunto
  de datos de la cuenta de WhatsApp; devuelve su ``id``.
- ``send_conversion_event``: ``POST /{dataset_id}/events`` con un evento en
  ``data``, ``partner_agent`` y, solo si se pasa, ``test_event_code``.

Los errores se clasifican como el resto del cliente.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from nexus_channels.whatsapp_meta.exceptions import (
    MetaAPIError,
    MetaTransientError,
    TokenInvalidatedError,
)
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL, MetaClient

pytestmark = pytest.mark.asyncio

_SECRET = "app-secret"
EVENT = {
    "event_name": "Purchase",
    "event_time": 1764000000,
    "event_id": "reservation:abc:Purchase",
    "action_source": "business_messaging",
    "messaging_channel": "whatsapp",
    "user_data": {"whatsapp_business_account_id": "WABA1", "ctwa_clid": "CLICK"},
    "custom_data": {"currency": "CLP", "value": 15000},
}


async def test_token_scopes_reads_both_shapes() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.get("/debug_token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "scopes": ["whatsapp_business_management"],
                        "granular_scopes": [
                            {"scope": "whatsapp_business_messaging", "target_ids": ["W"]},
                            {"scope": "whatsapp_business_manage_events"},
                        ],
                    }
                },
            )
        )
        async with MetaClient(_SECRET, max_retries=1) as client:
            scopes = await client.token_scopes(input_token="T", app_id="APP")
    assert scopes == {
        "whatsapp_business_management",
        "whatsapp_business_messaging",
        "whatsapp_business_manage_events",
    }
    request = route.calls.last.request
    assert request.url.params["input_token"] == "T"
    # Se lee con el token de la app, no con el del número.
    assert request.headers["Authorization"] == f"Bearer APP|{_SECRET}"


async def test_ensure_dataset_returns_the_id() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.post("/WABA1/dataset").mock(
            return_value=httpx.Response(200, json={"id": "DS9"})
        )
        async with MetaClient(_SECRET, max_retries=1) as client:
            assert await client.ensure_dataset(waba_id="WABA1", access_token="T") == "DS9"
    assert route.calls.last.request.headers["Authorization"] == "Bearer T"


async def test_ensure_dataset_without_id_is_an_error() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/WABA1/dataset").mock(return_value=httpx.Response(200, json={}))
        async with MetaClient(_SECRET, max_retries=1) as client:
            with pytest.raises(MetaAPIError):
                await client.ensure_dataset(waba_id="WABA1", access_token="T")


async def test_send_event_body() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.post("/DS9/events").mock(
            return_value=httpx.Response(200, json={"events_received": 1})
        )
        async with MetaClient(_SECRET, max_retries=1) as client:
            out = await client.send_conversion_event(
                dataset_id="DS9", access_token="T", event=EVENT, partner_agent="auphere"
            )
    assert out == {"events_received": 1}
    body = json.loads(route.calls.last.request.content)
    assert body == {"data": [EVENT], "partner_agent": "auphere"}


async def test_send_event_with_test_code() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.post("/DS9/events").mock(return_value=httpx.Response(200, json={}))
        async with MetaClient(_SECRET, max_retries=1) as client:
            await client.send_conversion_event(
                dataset_id="DS9",
                access_token="T",
                event=EVENT,
                partner_agent="auphere",
                test_event_code="TEST123",
            )
    assert json.loads(route.calls.last.request.content)["test_event_code"] == "TEST123"


@pytest.mark.parametrize(
    ("status", "payload", "error"),
    [
        (500, {"error": {"code": 2, "message": "x"}}, MetaTransientError),
        (400, {"error": {"code": 190, "message": "expired"}}, TokenInvalidatedError),
        (400, {"error": {"code": 100, "message": "bad"}}, MetaAPIError),
    ],
)
async def test_send_event_errors(status: int, payload: dict, error: type[Exception]) -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/DS9/events").mock(return_value=httpx.Response(status, json=payload))
        async with MetaClient(_SECRET, max_retries=1) as client:
            with pytest.raises(error):
                await client.send_conversion_event(
                    dataset_id="DS9", access_token="T", event=EVENT, partner_agent="auphere"
                )
