"""FCM HTTP v1 con la cuenta de servicio — spec 031, research D8.

Sin ``google-auth``: el token de acceso se obtiene con una aserción JWT RS256
firmada con la clave de la cuenta de servicio (``grant_type =
urn:ietf:params:oauth:grant-type:jwt-bearer``), y se reutiliza hasta un minuto
antes de caducar.

Respuestas (``firebase.google.com``, «FCM error codes»): ``UNREGISTERED`` dice
que el destino ya no existe; 429 y 5xx son transitorios; 401 renueva el token y
se reintenta una vez.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt
import structlog

from nexus_worker.push._result import NOT_CONFIGURED, SendResult

log = structlog.get_logger(__name__)

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"


class FcmClient:
    def __init__(
        self,
        *,
        project_id: str,
        service_account_json: str,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.project_id = project_id.strip()
        self._account: dict[str, Any] = {}
        if service_account_json.strip():
            try:
                self._account = json.loads(service_account_json)
            except ValueError:
                log.error("push.fcm.bad_service_account")
        self._clock = clock or time.time
        self._token: tuple[str, float] | None = None
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    @property
    def configured(self) -> bool:
        return bool(
            self.project_id
            and self._account.get("client_email")
            and self._account.get("private_key")
        )

    async def _access_token(self, *, force: bool = False) -> str:
        now = self._clock()
        if not force and self._token is not None and now < self._token[1] - 60:
            return self._token[0]
        token_uri = self._account.get("token_uri") or "https://oauth2.googleapis.com/token"
        assertion = jwt.encode(
            {
                "iss": self._account["client_email"],
                "scope": SCOPE,
                "aud": token_uri,
                "iat": int(now),
                "exp": int(now) + 3600,
            },
            self._account["private_key"],
            algorithm="RS256",
        )
        resp = await self._client.post(
            token_uri, data={"grant_type": _GRANT, "assertion": assertion}
        )
        resp.raise_for_status()
        body = resp.json()
        token = str(body["access_token"])
        self._token = (token, now + float(body.get("expires_in", 3600)))
        return token

    async def send(self, message: dict[str, Any]) -> SendResult:
        if not self.configured:
            return NOT_CONFIGURED
        url = f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"
        for attempt in (1, 2):
            try:
                token = await self._access_token(force=attempt == 2)
                resp = await self._client.post(
                    url, json=message, headers={"Authorization": f"Bearer {token}"}
                )
            except httpx.HTTPError as exc:
                log.warning("push.fcm.network", error=str(exc))
                return SendResult(outcome="retry", error_code="network")
            if resp.status_code == 200:
                return SendResult(outcome="sent", provider_message_id=resp.json().get("name"))
            if resp.status_code == 401 and attempt == 1:
                continue
            return _classify(resp)
        return SendResult(outcome="retry", error_code="UNAUTHENTICATED")  # pragma: no cover

    async def aclose(self) -> None:
        await self._client.aclose()


def _error_code(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error") or {}
    except ValueError:
        return str(resp.status_code)
    for detail in err.get("details") or []:
        code = detail.get("errorCode")
        if code:
            return str(code)
    return str(err.get("status") or resp.status_code)


def _classify(resp: httpx.Response) -> SendResult:
    code = _error_code(resp)
    if code == "UNREGISTERED":
        return SendResult(outcome="unregistered", error_code=code)
    if resp.status_code == 429 or resp.status_code >= 500:
        return SendResult(outcome="retry", error_code=code)
    return SendResult(outcome="failed", error_code=code)


__all__ = ["SCOPE", "FcmClient"]
