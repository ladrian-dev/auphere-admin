"""Block O — AgendaPro public-link MCP proxy unit tests.

The ``agendapro_public.*`` tools route through ``SubprocessTool`` which
shells out via stdio to the Node binary in production. Here we
substitute a FakeAgendaProPublicTransport so the dispatch path is
covered without needing Browserbase / Node.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

import pytest

from nexus_api.core.tenant_context import tenant_context
from nexus_mcp import build_default_registry, get_internal_caller_token, reset_default_registry
from nexus_mcp.base import ToolError
from nexus_mcp.servers.agendapro_public.transport import (
    set_default_transport,
)

pytestmark = pytest.mark.asyncio


class FakeAgendaProPublicTransport:
    """In-process stand-in for the Node MCP. Records calls and returns
    canned responses so tests can drive the booking facade + cron
    without spawning anything."""

    server_name = "agendapro_public_mcp"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._next_response: dict[str, Any] | None = None
        self._raise: Exception | None = None

    def stage_create_appointment_confirmed(self, external_ref: str) -> None:
        self._next_response = {
            "external_ref": external_ref,
            "confirmation_at_iso": "2026-05-13T12:00:00+00:00",
            "recaptcha_score": 0.92,
            "status": "confirmed",
        }

    def stage_create_appointment_ambiguous(self) -> None:
        self._next_response = {
            "external_ref": None,
            "confirmation_at_iso": "2026-05-13T12:00:00+00:00",
            "recaptcha_score": 0.85,
            "status": "ambiguous",
            "failure_reason": "confirmation marker present but no code",
        }

    def stage_create_appointment_failed(self, reason: str) -> None:
        self._next_response = {
            "external_ref": None,
            "confirmation_at_iso": "2026-05-13T12:00:00+00:00",
            "recaptcha_score": 0.30,
            "status": "failed",
            "failure_reason": reason,
        }

    def stage_check_availability_with_one_slot(self) -> None:
        self._next_response = {
            "slots": [
                {
                    "starts_at_iso": "2026-05-14T15:00:00",
                    "duration_min": 30,
                    "barber_name": "Moisés",
                    "barber_slot_token": "btn-moises-15",
                }
            ],
            "recaptcha_score": 0.95,
        }

    def stage_raise(self, exc: Exception) -> None:
        self._raise = exc

    async def call_tool(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        arguments: Mapping[str, Any],
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
        if self._raise is not None:
            raise self._raise
        if self._next_response is None:
            raise AssertionError(f"FakeAgendaProPublicTransport: no response staged for {name}")
        # MCP wire shape (matches the Node server's reply format).
        return {
            "content": [
                {"type": "text", "text": json.dumps(self._next_response)}
            ]
        }


@pytest.fixture(autouse=True)
def _reset_registry():
    reset_default_registry()
    yield
    reset_default_registry()


@pytest.fixture
def transport() -> FakeAgendaProPublicTransport:
    t = FakeAgendaProPublicTransport()
    set_default_transport(t)
    yield t
    set_default_transport(None)


async def test_dispatch_internal_confirmed_returns_external_ref(transport):
    transport.stage_create_appointment_confirmed("AGPR-1234")

    registry = build_default_registry()
    tenant_id = uuid.uuid4()
    with tenant_context(tenant_id):
        envelope = await registry.dispatch_internal(
            "agendapro_public.create_appointment",
            {
                "public_url": "https://cultorbarber.site.agendapro.com/cl/sucursal/481889",
                "slot": {
                    "starts_at_iso": "2026-05-14T15:00:00",
                    "duration_min": 30,
                    "barber_slot_token": "btn-moises-15",
                },
                "customer": {
                    "name": "Juan Pérez",
                    "phone_e164": "+56911112222",
                    "email": "juan@example.com",
                },
                "service_hint": "Corte clásico",
                "idempotency_key": "test_idem_1",
            },
            caller_token=get_internal_caller_token(),
        )

    assert envelope["result"]["external_ref"] == "AGPR-1234"
    assert envelope["result"]["status"] == "confirmed"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["name"] == "agendapro_public.create_appointment"
    assert call["arguments"]["idempotency_key"] == "test_idem_1"


async def test_check_availability_round_trip(transport):
    transport.stage_check_availability_with_one_slot()

    registry = build_default_registry()
    tenant_id = uuid.uuid4()
    with tenant_context(tenant_id):
        envelope = await registry.dispatch_internal(
            "agendapro_public.check_availability",
            {
                "public_url": "https://cultorbarber.site.agendapro.com/cl/sucursal/481889",
                "on_date": "2026-05-14",
                "service_hint": "Corte clásico",
            },
            caller_token=get_internal_caller_token(),
        )
    slots = envelope["result"]["slots"]
    assert len(slots) == 1
    assert slots[0]["barber_name"] == "Moisés"
    assert slots[0]["barber_slot_token"] == "btn-moises-15"


async def test_transport_error_surfaces_as_tool_error(transport):
    transport.stage_raise(RuntimeError("browserbase down"))
    registry = build_default_registry()
    tenant_id = uuid.uuid4()
    with tenant_context(tenant_id):
        with pytest.raises(ToolError) as info:
            await registry.dispatch_internal(
                "agendapro_public.check_availability",
                {
                    "public_url": "https://x.site.agendapro.com",
                    "on_date": "2026-05-14",
                },
                caller_token=get_internal_caller_token(),
            )
    assert "browserbase down" in str(info.value)


async def test_internal_tools_not_reachable_from_public_dispatch(transport):
    """Defense in depth: even if the LLM hallucinates the tool name and
    the whitelist somehow contains it, ``MCPRegistry.dispatch`` (the
    public path) refuses internal names — they live in ``_internal_tools``
    only.
    """
    transport.stage_create_appointment_confirmed("AGPR-9999")
    registry = build_default_registry()
    tenant_id = uuid.uuid4()
    with tenant_context(tenant_id):
        from nexus_mcp.base import ToolError as _TE

        with pytest.raises(_TE):
            await registry.dispatch(
                "agendapro_public.create_appointment",
                {
                    "public_url": "https://x.site.agendapro.com/cl/sucursal/1",
                    "slot": {
                        "starts_at_iso": "2026-05-14T15:00:00",
                        "duration_min": 30,
                        "barber_slot_token": "x",
                    },
                    "customer": {
                        "name": "X",
                        "phone_e164": "+5611",
                        "email": "x@x.com",
                    },
                    "service_hint": "X",
                    "idempotency_key": "y",
                },
                whitelist=frozenset({"agendapro_public.create_appointment"}),
            )
