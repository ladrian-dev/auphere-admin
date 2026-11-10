"""Spec 031 · R8.8 a R8.10, R9.1 — enviar a Apple y a Google (T086).

Los dos clientes hablan directo con los proveedores, sin el servicio de push de
Expo (research D8): APNs por HTTP/2 con un token de proveedor ES256, y FCM HTTP
v1 con una aserción RS256 de la cuenta de servicio. Aquí se fija, contra
transportes falsos, lo que cada uno manda y cómo traduce cada respuesta:

- ``sent`` con el id del proveedor;
- ``unregistered`` cuando el destino ya no existe (el reparto se lo quita al
  teléfono);
- ``retry`` para lo transitorio (429, 5xx);
- ``failed`` para lo demás, y ``provider_not_configured`` sin credenciales.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from nexus_worker.push.apns import ApnsClient
from nexus_worker.push.fcm import FcmClient

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _ec_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _service_account() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {
            "type": "service_account",
            "client_email": "push@auphere-test.iam.gserviceaccount.com",
            "private_key": pem,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


# ── APNs ───────────────────────────────────────────────────────────────


def _apns(handler: Any, *, clock: Any = None) -> ApnsClient:
    return ApnsClient(
        key_id="ABC123DEFG",
        team_id="CBSWMG766P",
        key_pem=_ec_pem(),
        topic="com.auphere.customers",
        transport=httpx.MockTransport(handler),
        clock=clock,
    )


async def test_apns_sends_to_the_right_host_with_a_provider_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"apns-id": "id-1"})

    client = _apns(handler)
    out = await client.send(
        token="a" * 64,
        environment="sandbox",
        headers={"apns-push-type": "alert", "apns-topic": "com.auphere.customers"},
        payload={"aps": {"alert": {"title": "t", "body": "b"}}},
    )

    assert out.outcome == "sent" and out.provider_message_id == "id-1"
    (req,) = seen
    assert req.url.host == "api.sandbox.push.apple.com"
    assert req.url.path == "/3/device/" + "a" * 64
    assert req.headers["apns-push-type"] == "alert"
    bearer = req.headers["authorization"].removeprefix("bearer ")
    header = jwt.get_unverified_header(bearer)
    claims = jwt.decode(bearer, options={"verify_signature": False})
    assert header["alg"] == "ES256" and header["kid"] == "ABC123DEFG"
    assert claims["iss"] == "CBSWMG766P"
    assert json.loads(req.content) == {"aps": {"alert": {"title": "t", "body": "b"}}}


async def test_apns_production_host() -> None:
    hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200, headers={"apns-id": "x"})

    await _apns(handler).send(token="a" * 64, environment="production", headers={}, payload={})
    assert hosts == ["api.push.apple.com"]


async def test_apns_reuses_its_token_for_fifty_minutes() -> None:
    tokens: list[str] = []
    now = [1_000_000.0]

    def handler(request: httpx.Request) -> httpx.Response:
        tokens.append(request.headers["authorization"])
        return httpx.Response(200, headers={"apns-id": "x"})

    client = _apns(handler, clock=lambda: now[0])
    await client.send(token="a" * 64, environment="sandbox", headers={}, payload={})
    now[0] += 49 * 60
    await client.send(token="a" * 64, environment="sandbox", headers={}, payload={})
    now[0] += 2 * 60
    await client.send(token="a" * 64, environment="sandbox", headers={}, payload={})
    assert tokens[0] == tokens[1] != tokens[2]


@pytest.mark.parametrize(
    ("status", "reason", "outcome"),
    [
        (410, "Unregistered", "unregistered"),
        (400, "BadDeviceToken", "unregistered"),
        (400, "DeviceTokenNotForTopic", "unregistered"),
        (429, "TooManyRequests", "retry"),
        (500, "InternalServerError", "retry"),
        (503, "ServiceUnavailable", "retry"),
        (400, "PayloadTooLarge", "failed"),
    ],
)
async def test_apns_maps_each_answer(status: int, reason: str, outcome: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"reason": reason})

    out = await _apns(handler).send(token="a" * 64, environment="sandbox", headers={}, payload={})
    assert out.outcome == outcome
    assert out.error_code == reason


async def test_apns_without_credentials_is_not_configured() -> None:
    client = ApnsClient(key_id="", team_id="", key_pem="", topic="x")
    out = await client.send(token="a" * 64, environment="sandbox", headers={}, payload={})
    assert out.outcome == "failed" and out.error_code == "provider_not_configured"


async def test_a_network_error_is_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    out = await _apns(handler).send(token="a" * 64, environment="sandbox", headers={}, payload={})
    assert out.outcome == "retry"


# ── FCM ────────────────────────────────────────────────────────────────


def _fcm(send: Any, *, token_calls: list[Any] | None = None) -> FcmClient:
    calls = token_calls if token_calls is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            calls.append(request)
            return httpx.Response(
                200, json={"access_token": f"ya29.{len(calls)}", "expires_in": 3600}
            )
        return send(request)

    return FcmClient(
        project_id="auphere-test",
        service_account_json=_service_account(),
        transport=httpx.MockTransport(handler),
    )


async def test_fcm_exchanges_an_assertion_and_sends_v1() -> None:
    sent: list[httpx.Request] = []
    token_calls: list[httpx.Request] = []

    def send(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"name": "projects/auphere-test/messages/1"})

    client = _fcm(send, token_calls=token_calls)
    message = {"message": {"token": "t", "data": {"title": "x"}}}
    out1 = await client.send(message)
    out2 = await client.send(message)

    assert out1.outcome == out2.outcome == "sent"
    assert out1.provider_message_id == "projects/auphere-test/messages/1"
    assert len(token_calls) == 1  # el token de acceso se reutiliza
    form = dict(httpx.QueryParams(token_calls[0].content.decode()))
    assert form["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    claims = jwt.decode(form["assertion"], options={"verify_signature": False})
    assert claims["scope"] == "https://www.googleapis.com/auth/firebase.messaging"
    assert claims["iss"] == "push@auphere-test.iam.gserviceaccount.com"
    assert sent[0].url.path == "/v1/projects/auphere-test/messages:send"
    assert sent[0].headers["authorization"] == "Bearer ya29.1"


@pytest.mark.parametrize(
    ("status", "body", "outcome", "code"),
    [
        (
            404,
            {"error": {"status": "NOT_FOUND", "details": [{"errorCode": "UNREGISTERED"}]}},
            "unregistered",
            "UNREGISTERED",
        ),
        (
            400,
            {
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "details": [{"errorCode": "INVALID_ARGUMENT"}],
                }
            },
            "failed",
            "INVALID_ARGUMENT",
        ),
        (429, {"error": {"status": "RESOURCE_EXHAUSTED"}}, "retry", "RESOURCE_EXHAUSTED"),
        (503, {"error": {"status": "UNAVAILABLE"}}, "retry", "UNAVAILABLE"),
    ],
)
async def test_fcm_maps_each_answer(status: int, body: dict, outcome: str, code: str) -> None:
    out = await _fcm(lambda r: httpx.Response(status, json=body)).send({"message": {}})
    assert out.outcome == outcome
    assert out.error_code == code


async def test_fcm_without_credentials_is_not_configured() -> None:
    client = FcmClient(project_id="", service_account_json="")
    out = await client.send({"message": {}})
    assert out.outcome == "failed" and out.error_code == "provider_not_configured"
