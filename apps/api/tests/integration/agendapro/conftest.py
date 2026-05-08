"""Fixtures para los tests de integración Bloque E (AgendaPro browser MCP).

``FakeAgendaProTransport`` matchea el ``SubprocessTransport`` Protocol —
no spawnea Stagehand ni Browserbase. Las respuestas se scriptean por
test (set_response) o quedan en defaults razonables. Los tests Python
no requieren el server Node corriendo.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest_asyncio
from nexus_mcp.registry import reset_default_registry
from nexus_mcp.servers.agendapro_browser.transport import set_default_transport

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Tenant, TenantPlan
from nexus_api.services.agendapro_credentials import (
    upsert_agendapro_credentials,
)


@pytest_asyncio.fixture
async def two_tenants(db_session) -> dict[str, uuid.UUID]:
    """Mismo shape que el fixture de tests/integration/mcp/."""
    a_id = uuid.uuid4()
    b_id = uuid.uuid4()
    db_session.add_all(
        [
            Tenant(id=a_id, name="AP A", slug=f"ap-a-{a_id.hex[:6]}", plan=TenantPlan.PRO),
            Tenant(id=b_id, name="AP B", slug=f"ap-b-{b_id.hex[:6]}", plan=TenantPlan.PRO),
        ]
    )
    await db_session.commit()
    return {"a": a_id, "b": b_id}


class FakeAgendaProTransport:
    """In-process fake del SubprocessTransport. Devuelve dicts scripted
    (``set_response("agendapro.<name>", {...})``) o un default vacío."""

    server_name = "agendapro_browser_mcp"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
        self._default_response = lambda args: {
            "content": [{"type": "text", "text": "{}"}],
        }

    def set_response(
        self, name: str, payload: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]
    ) -> None:
        """Si ``payload`` es dict, devuelve siempre ese. Si es callable,
        se invoca con los args para producir la respuesta dinámica."""
        import json as _json

        if callable(payload):
            handler = payload
        else:
            payload_dict = payload

            def handler(_args: dict[str, Any]) -> dict[str, Any]:
                return payload_dict

        self._responses[name] = lambda args: {
            "content": [
                {"type": "text", "text": _json.dumps(handler(args))},
            ],
        }

    def set_response_raw(self, name: str, mcp_response: dict[str, Any]) -> None:
        """Set the raw MCP response (no auto-wrap)."""
        self._responses[name] = lambda args: mcp_response

    async def call_tool(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        arguments: dict[str, Any],
        timeout: float = 90.0,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "tenant_id": str(tenant_id),
                "name": name,
                "arguments": dict(arguments),
                "timeout": timeout,
            }
        )
        handler = self._responses.get(name, self._default_response)
        return handler(dict(arguments))


@pytest_asyncio.fixture
async def fake_agendapro() -> AsyncIterator[FakeAgendaProTransport]:
    """Inyecta el fake como default transport para las internal tools y
    resetea el registry para que las tools nuevas se construyan con el
    fake. Limpieza al teardown."""
    reset_default_registry()
    fake = FakeAgendaProTransport()
    set_default_transport(fake)
    try:
        yield fake
    finally:
        set_default_transport(None)
        reset_default_registry()


@pytest_asyncio.fixture
async def tenant_with_agendapro(
    db_session,
) -> AsyncIterator[uuid.UUID]:
    """Crea un tenant y le mete credenciales AgendaPro válidas
    (needs_reauth=False) directo via servicio."""
    tid = uuid.uuid4()
    db_session.add(
        Tenant(id=tid, name=f"AP {tid.hex[:6]}", slug=f"ap-{tid.hex[:6]}", plan=TenantPlan.PRO)
    )
    await db_session.commit()
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tid):
        await upsert_agendapro_credentials(
            s,
            login="owner@cultor.cl",
            password="secret",
            context_id="ctx-test-12345",
            business_url=None,
        )
    yield tid
