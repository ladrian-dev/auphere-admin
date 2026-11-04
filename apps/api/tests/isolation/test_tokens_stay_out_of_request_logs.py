"""Spec 052 (R6.5, CE-005): a link with a token does not reach a log by its path.

The token of an invitation travels in the path of ``/console/invitations/{token}``,
so opening the link wrote it in three places that ship off the machine: the
access log, the ``path`` bound to every structlog line of the request, and the
span. Whoever reads those could open the link for up to 21 days and, if the
address has no account yet, choose the password and become the owner.

**The sweep does not list the routes**: every route of the app with a ``{token}``
is exercised, so a new one is covered the moment it is mounted.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any

import httpx
import pytest
import structlog
from fastapi.routing import APIRoute
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from nexus_api.core.logging_context import LoggingContextMiddleware, RedactAccessLog, safe_path
from nexus_api.core.otel import redact_span_path
from nexus_api.main import app

pytestmark = [pytest.mark.isolation]

TOKEN = secrets.token_urlsafe(32)


def _routes_with_a_token() -> list[str]:
    return sorted({r.path for r in app.routes if isinstance(r, APIRoute) and "{token}" in r.path})


def test_the_sweep_finds_the_routes() -> None:
    found = _routes_with_a_token()
    assert "/console/invitations/{token}" in found
    assert "/console/invitations/{token}/accept" in found
    assert any(path.startswith("/console/password-reset/") for path in found)
    assert any(path.startswith("/console/signup/") for path in found)


@pytest.mark.parametrize("path", _routes_with_a_token())
def test_no_route_with_a_token_keeps_it_in_the_path_it_logs(path: str) -> None:
    logged = safe_path(path.replace("{token}", TOKEN))
    assert TOKEN not in logged
    # What is left still says which route it was.
    assert logged == path.replace("{token}", "[token]")


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/console/team/invitations",
        f"/admin/partners/{uuid.uuid4()}/invitations/{uuid.uuid4()}/resend",
        "/console/clients/una-agencia-con-un-identificador",
    ],
)
def test_the_rest_of_the_paths_stay_as_they_are(path: str) -> None:
    assert safe_path(path) == path


@pytest.mark.asyncio
async def test_the_path_bound_to_every_log_line_carries_no_token() -> None:
    seen: dict[str, Any] = {}

    async def endpoint(_: Request) -> PlainTextResponse:
        seen.update(structlog.contextvars.get_contextvars())
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/console/invitations/{token}", endpoint)])
    inner.add_middleware(LoggingContextMiddleware)
    transport = httpx.ASGITransport(app=inner)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(f"/console/invitations/{TOKEN}")
    assert res.status_code == 200
    assert seen["path"] == "/console/invitations/[token]"


def test_the_access_log_carries_no_token() -> None:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("10.0.0.1:5000", "GET", f"/console/invitations/{TOKEN}?x=1", "1.1", 200),
        exc_info=None,
    )
    assert RedactAccessLog().filter(record) is True
    message = record.getMessage()
    assert TOKEN not in message
    assert '"GET /console/invitations/[token]?x=1 HTTP/1.1" 200' in message


def test_the_filter_is_on_the_access_logger() -> None:
    # Importing the app configured logging. Not called again here: it turns on
    # structlog's logger cache, and ``capture_logs`` in later tests would see nothing.
    filters = logging.getLogger("uvicorn.access").filters
    assert any(isinstance(f, RedactAccessLog) for f in filters)


def test_a_record_that_is_not_an_access_line_goes_through_untouched() -> None:
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "started", None, None)
    assert RedactAccessLog().filter(record) is True
    assert record.getMessage() == "started"


class _Span:
    def __init__(self, attributes: dict[str, str]) -> None:
        self.attributes = attributes

    def is_recording(self) -> bool:
        return True

    def set_attribute(self, key: str, value: str) -> None:
        self.attributes[key] = value


def test_the_span_carries_no_token() -> None:
    path = f"/console/invitations/{TOKEN}/accept"
    span = _Span(
        {
            "http.target": path,
            "url.path": path,
            "http.url": f"http://api.test{path}",
            "http.route": "/console/invitations/{token}/accept",
        }
    )
    redact_span_path(span, {"path": path})
    assert TOKEN not in str(span.attributes)
    assert span.attributes["http.url"] == "http://api.test/console/invitations/[token]/accept"
    assert span.attributes["http.route"] == "/console/invitations/{token}/accept"
