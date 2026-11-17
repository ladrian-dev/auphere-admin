"""Cliente REST de Quédate (spec 061, enmienda del 2026-11-16).

Quédate tiene dos APIs bajo la misma base:

- la **del agente** (``/api/v1/agent/*``), con la clave que el cliente generó en su
  panel (alcance ``agent:onboarding``). Aísla por clave: solo ve los anfitriones y
  anuncios que esa clave creó, y no tiene ``DELETE``.
- la **general** (``/api/v1/*``), de la que el conector usa solo las rutas públicas,
  sin clave.

**El entorno es una elección cerrada** (research D2): producción o desarrollo, con
sus direcciones fijas en el código. Nadie escribe una dirección.

**Errores**: el ``StandardError`` de Quédate (``success``, ``error_code``,
``message``, ``errors``). Se propaga su ``message`` o el primero de ``errors``,
nunca el cuerpo crudo.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx

from nexus_mcp.http import BaseHTTPConnectorClient, HTTPConnectorError
from nexus_mcp.servers.quedate.errors import (
    QuedateAuthError,
    QuedateConflict,
    QuedateError,
    QuedateForbidden,
    QuedateNotFound,
    QuedateRateLimited,
    QuedateUnavailable,
    QuedateValidationError,
)

Environment = Literal["production", "development"]

BASES: dict[Environment, str] = {
    "production": "https://api-v2.quedate.net/api/v1",
    "development": "https://dev-api.quedate.net/api/v1",
}

_DEV_WORDS = frozenset({"dev", "development", "desarrollo"})


def environment_of(value: object) -> Environment:
    """Lo que el cliente escribió en «entorno»: ``dev`` y sus sinónimos son
    desarrollo; cualquier otra cosa, también vacío, es producción (research D2)."""
    if isinstance(value, str) and value.strip().lower() in _DEV_WORDS:
        return "development"
    return "production"


ListingStatus = Literal["pending_approval", "hidden"]


class QuedateClient(BaseHTTPConnectorClient):
    """Una llamada, un cliente. ``token`` es la clave del cliente, o ``None`` para
    las rutas públicas de la API general."""

    def __init__(
        self,
        *,
        environment: Environment = "production",
        token: str | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url=BASES[environment],
            timeout_s=timeout_s,
            max_retries=max_retries,
            transport=transport,
        )
        self.environment = environment
        self._token = token

    def __repr__(self) -> str:  # nunca la clave
        return f"QuedateClient({self.environment}, authenticated={self._token is not None})"

    # ── overrides ────────────────────────────────────────────────────────

    def _default_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: dict[str, Any] | None = None,
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    ) -> tuple[httpx.Response, dict[str, Any] | list[Any] | None]:
        """Un fallo de transporte del cliente base pasa a ser «Quédate no responde»."""
        try:
            return await super().request(
                method, path, params=params, json=json, data=data, files=files
            )
        except QuedateError:
            raise
        except HTTPConnectorError as exc:
            raise QuedateUnavailable(str(exc), status_code=exc.status_code) from exc

    @staticmethod
    def _error_parts(response: httpx.Response) -> tuple[str | None, str, str | None]:
        try:
            body = response.json()
        except (ValueError, UnicodeDecodeError):
            return None, f"HTTP {response.status_code}", None
        if not isinstance(body, dict):
            return None, f"HTTP {response.status_code}", None
        code = body.get("error_code")
        message = body.get("message") if isinstance(body.get("message"), str) else None
        field: str | None = None
        errors = body.get("errors")
        if isinstance(errors, dict) and errors:
            field = str(next(iter(errors)))
            first = errors[field]
            detail = first[0] if isinstance(first, list) and first else first
            if isinstance(detail, str) and detail:
                message = detail
        return (
            code if isinstance(code, str) else None,
            (message or f"HTTP {response.status_code}")[:300],
            field,
        )

    def _extract_error_message(self, response: httpx.Response) -> str:
        return self._error_parts(response)[1]

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        _code, message, field = self._error_parts(response)
        if status == 401:
            raise QuedateAuthError(message, status_code=status)
        if status == 403:
            raise QuedateForbidden(message, status_code=status)
        if status == 404:
            raise QuedateNotFound(message, status_code=status)
        if status == 409:
            raise QuedateConflict(message, status_code=status)
        if status == 429:
            raise QuedateRateLimited(message, status_code=status)
        if 400 <= status < 500:
            raise QuedateValidationError(message, status_code=status, field=field)
        raise QuedateUnavailable(message, status_code=status)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        _, body = await self.get(path, params=params)
        return body

    # ── API del agente ───────────────────────────────────────────────────

    async def catalogs(self) -> Any:
        return await self._get("/agent/catalogs")

    async def list_hosts(self, *, page: int = 1, per_page: int = 10) -> Any:
        return await self._get("/agent/hosts", {"page": page, "per_page": per_page})

    async def get_host(self, host_id: str) -> Any:
        return await self._get(f"/agent/hosts/{_ref(host_id)}")

    async def create_host(self, payload: dict[str, Any]) -> Any:
        _, body = await self.post("/agent/hosts", json=payload)
        return body

    async def kyc_link(self, host_id: str) -> Any:
        return await self._get(f"/agent/hosts/{_ref(host_id)}/kyc-link")

    async def upload_kyc(
        self,
        host_id: str,
        *,
        document: tuple[str, bytes, str],
        selfie: tuple[str, bytes, str] | None,
    ) -> Any:
        files = [("document_image", document)]
        if selfie is not None:
            files.append(("selfie_image", selfie))
        _, body = await self.request("POST", f"/agent/hosts/{_ref(host_id)}/kyc", files=files)
        return body

    async def list_listings(self, *, page: int = 1, per_page: int = 10) -> Any:
        return await self._get("/agent/listings", {"page": page, "per_page": per_page})

    async def get_listing_managed(self, listing_id: str) -> Any:
        return await self._get(f"/agent/listings/{_ref(listing_id)}")

    async def create_listing(self, payload: dict[str, Any]) -> Any:
        _, body = await self.post("/agent/listings", json=payload)
        return body

    async def upload_media(self, listing_id: str, photos: list[tuple[str, bytes, str]]) -> Any:
        files = [("files[]", p) for p in photos]
        _, body = await self.request(
            "POST", f"/agent/listings/{_ref(listing_id)}/media", files=files
        )
        return body

    async def set_status(self, listing_id: str, status: ListingStatus) -> Any:
        # El agente nunca publica: solo a revisión o a oculto (Luis, 2026-11-16).
        if status not in ("pending_approval", "hidden"):
            raise QuedateValidationError("estado no permitido", field="status")
        _, body = await self.request(
            "PATCH", f"/agent/listings/{_ref(listing_id)}/status", json={"status": status}
        )
        return body

    # ── API general, rutas públicas ──────────────────────────────────────

    async def search_listings(self, params: dict[str, Any]) -> Any:
        return await self._get("/search/listings", params)

    async def public_listing(self, ref: str) -> Any:
        return await self._get(f"/listings/{_ref(ref)}")

    async def quote(self, *, listing_id: str, check_in: str, check_out: str, guests: int) -> Any:
        _, body = await self.post(
            "/checkout/quote",
            json={
                "listing_id": listing_id,
                "check_in_date": check_in,
                "check_out_date": check_out,
                "guests_count": guests,
            },
        )
        return body

    async def public_settings(self) -> Any:
        return await self._get("/settings/public")


def _ref(value: str) -> str:
    """Un id o slug de Quédate: letras, dígitos y guiones. Nada más llega a la ruta."""
    v = value.strip()
    if not v or len(v) > 120 or not all(c.isalnum() or c == "-" for c in v) or not v[0].isalnum():
        raise QuedateValidationError("identificador no válido", field="id")
    return v


__all__ = ["BASES", "Environment", "ListingStatus", "QuedateClient", "environment_of"]
