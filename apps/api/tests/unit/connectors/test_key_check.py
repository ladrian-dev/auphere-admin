"""El comprobador de la clave de Quédate (spec 061, enmienda del 2026-11-16; T040,
requisitos 1.2-1.5).

``GET /agent/hosts?per_page=1`` con la clave del cliente, en el entorno que eligió:
aceptada, rechazada o sin respuesta. Sin red: un transporte falso dentro del cliente
de Quédate.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from nexus_mcp.servers.quedate import client as qclient

from nexus_api.services.connectors import key_check

pytestmark = [pytest.mark.unit]


def _with(monkeypatch: pytest.MonkeyPatch, status: int, seen: list[httpx.Request]) -> None:
    real_init = qclient.QuedateClient.__init__

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"success": status == 200, "data": {"id": "u"}})

    def init(self: Any, **kw: Any) -> None:
        kw["transport"] = httpx.MockTransport(handler)
        kw["max_retries"] = 0
        real_init(self, **kw)

    monkeypatch.setattr(qclient.QuedateClient, "__init__", init)


@pytest.mark.parametrize(
    ("status", "outcome"), [(200, "ok"), (401, "rejected"), (403, "rejected"), (503, "unavailable")]
)
async def test_the_key_is_checked_against_the_agent_api(
    monkeypatch: pytest.MonkeyPatch, status: int, outcome: str
) -> None:
    seen: list[httpx.Request] = []
    _with(monkeypatch, status, seen)
    assert await key_check.CHECKERS["quedate"]({"api_key": "9|k"}, {}) == outcome
    assert [(r.method, r.url.path) for r in seen] == [("GET", "/api/v1/agent/hosts")]
    assert dict(seen[0].url.params) == {"page": "1", "per_page": "1"}
    assert seen[0].headers["authorization"] == "Bearer 9|k"


@pytest.mark.parametrize(
    ("meta", "host"),
    [
        ({}, "api-v2.quedate.net"),
        ({"_": "console"}, "api-v2.quedate.net"),
        ({"environment": ""}, "api-v2.quedate.net"),
        ({"environment": "produccion"}, "api-v2.quedate.net"),
        ({"environment": "https://evil.example"}, "api-v2.quedate.net"),
        ({"environment": "dev"}, "dev-api.quedate.net"),
        ({"environment": " Desarrollo "}, "dev-api.quedate.net"),
    ],
)
async def test_the_environment_picks_one_of_two_fixed_hosts(
    monkeypatch: pytest.MonkeyPatch, meta: dict[str, Any], host: str
) -> None:
    """1.5 y research D2: nadie escribe una dirección; solo producción o desarrollo."""
    seen: list[httpx.Request] = []
    _with(monkeypatch, 200, seen)
    await key_check.CHECKERS["quedate"]({"api_key": "9|k"}, meta)
    assert seen[0].url.host == host


@pytest.mark.parametrize(
    "exc", [httpx.ConnectError("dns"), httpx.ReadTimeout("slow")], ids=["dns", "timeout"]
)
async def test_a_transport_failure_is_unavailable_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    """Requisito 1.4: sin respuesta de Quédate, la conexión se guarda sin comprobar."""
    real_init = qclient.QuedateClient.__init__

    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    def init(self: Any, **kw: Any) -> None:
        kw["transport"] = httpx.MockTransport(handler)
        kw["max_retries"] = 0
        real_init(self, **kw)

    monkeypatch.setattr(qclient.QuedateClient, "__init__", init)
    assert await key_check.CHECKERS["quedate"]({"api_key": "9|k"}, {}) == "unavailable"


@pytest.mark.parametrize("secrets", [{}, {"api_key": ""}, {"api_key": "   "}, {"token": "x"}])
async def test_a_missing_key_is_rejected_without_calling(
    monkeypatch: pytest.MonkeyPatch, secrets: dict[str, Any]
) -> None:
    seen: list[httpx.Request] = []
    _with(monkeypatch, 200, seen)
    assert await key_check.CHECKERS["quedate"](secrets, {}) == "rejected"
    assert seen == []


def test_only_connectors_with_a_checker_are_checked() -> None:
    assert set(key_check.CHECKERS) == {"quedate"}
