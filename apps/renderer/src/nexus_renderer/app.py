"""``POST /render`` and ``GET /health``.

The only caller is the runner (its security group is the only one let in),
and it presents ``NEXUS_RENDERER_TOKEN`` as a bearer token, compared in
constant time **before** the body is read. No docs, no schema, no other route.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nexus_renderer.browser import MAX_URL_CHARS, RenderError, RenderResult
from nexus_renderer.config import Settings

log = logging.getLogger(__name__)

#: Each render failure, as the HTTP status the client sees.
STATUS_FOR: Final = {
    "bad_url": 400,
    "forbidden_address": 422,
    "too_large": 413,
    "unreachable": 502,
    "timeout": 504,
}


class Renderer(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def render(self, url: str) -> RenderResult: ...


class RenderIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(min_length=1, max_length=MAX_URL_CHARS)


def _error(code: str, status: int) -> JSONResponse:
    return JSONResponse({"error": code}, status_code=status)


def create_app(settings: Settings, renderer: Renderer) -> FastAPI:
    expected = settings.token.encode()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await renderer.start()
        try:
            yield
        finally:
            await renderer.close()

    app = FastAPI(
        title="nexus-renderer",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    def require_token(authorization: str | None = Header(default=None)) -> None:
        scheme, _, presented = (authorization or "").partition(" ")
        token = presented.strip().encode() if scheme.lower() == "bearer" else b""
        if not token or not hmac.compare_digest(token, expected):
            raise HTTPException(
                status_code=401, detail="unauthorized", headers={"WWW-Authenticate": "Bearer"}
            )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/render", dependencies=[Depends(require_token)])
    async def render(request: Request) -> JSONResponse:
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > settings.max_body_bytes:
                return _error("bad_request", 413)
        try:
            payload = RenderIn.model_validate_json(bytes(body))
        except ValidationError:
            return _error("bad_request", 400)
        try:
            result = await renderer.render(payload.url)
        except RenderError as exc:
            return _error(exc.code, STATUS_FOR[exc.code])
        except Exception:
            log.exception("renderer.unexpected")
            return _error("internal", 500)
        return JSONResponse(
            {"final_url": result.final_url, "status": result.status, "html": result.html}
        )

    return app


__all__ = ["STATUS_FOR", "RenderIn", "Renderer", "create_app"]
