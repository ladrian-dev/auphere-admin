"""APNs por HTTP/2 con token de proveedor — spec 031, research D8.

El token del proveedor es un JWT ES256 firmado con la clave ``.p8`` del team
(``kid`` = id de la clave, ``iss`` = Team ID). Apple pide reutilizarlo y
rechaza uno con más de una hora, así que se renueva a los 50 minutos.

Respuestas (``developer.apple.com``, «Handling notification responses from
APNs»): 200 envía; 410 y los 400 de destino malo dicen que el destino ya no
sirve; 429 y 5xx son transitorios; ``ExpiredProviderToken`` renueva el token y
se reintenta una vez.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt
import structlog

from nexus_worker.push._result import NOT_CONFIGURED, SendResult

log = structlog.get_logger(__name__)

HOSTS = {"production": "api.push.apple.com", "sandbox": "api.sandbox.push.apple.com"}
TOKEN_TTL = 50 * 60
_GONE = frozenset({"Unregistered", "BadDeviceToken", "DeviceTokenNotForTopic"})


class ApnsClient:
    def __init__(
        self,
        *,
        key_id: str,
        team_id: str,
        key_pem: str,
        topic: str,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.key_id = key_id.strip()
        self.team_id = team_id.strip()
        self._key = key_pem.strip()
        self.topic = topic
        self._clock = clock or time.time
        self._token: tuple[str, float] | None = None
        self._client = httpx.AsyncClient(
            http2=transport is None, transport=transport, timeout=timeout
        )

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.team_id and self._key)

    def _provider_token(self, *, force: bool = False) -> str:
        now = self._clock()
        if not force and self._token is not None and now - self._token[1] < TOKEN_TTL:
            return self._token[0]
        token = jwt.encode(
            {"iss": self.team_id, "iat": int(now)},
            self._key,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )
        self._token = (token, now)
        return token

    async def send(
        self,
        *,
        token: str,
        environment: str | None,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> SendResult:
        if not self.configured:
            return NOT_CONFIGURED
        host = HOSTS.get(environment or "production", HOSTS["production"])
        url = f"https://{host}/3/device/{token}"
        for attempt in (1, 2):
            try:
                resp = await self._client.post(
                    url,
                    json=payload,
                    headers={
                        **headers,
                        "authorization": f"bearer {self._provider_token(force=attempt == 2)}",
                    },
                )
            except httpx.HTTPError as exc:
                log.warning("push.apns.network", error=str(exc))
                return SendResult(outcome="retry", error_code="network")
            if resp.status_code == 200:
                return SendResult(outcome="sent", provider_message_id=resp.headers.get("apns-id"))
            reason = _reason(resp)
            if reason == "ExpiredProviderToken" and attempt == 1:
                continue
            return _classify(resp.status_code, reason)
        return SendResult(outcome="retry", error_code="ExpiredProviderToken")  # pragma: no cover

    async def aclose(self) -> None:
        await self._client.aclose()


def _reason(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("reason") or resp.status_code)
    except ValueError:
        return str(resp.status_code)


def _classify(status: int, reason: str) -> SendResult:
    if status == 410 or reason in _GONE:
        return SendResult(outcome="unregistered", error_code=reason)
    if status == 429 or status >= 500:
        return SendResult(outcome="retry", error_code=reason)
    return SendResult(outcome="failed", error_code=reason)


__all__ = ["HOSTS", "ApnsClient"]
