"""Wiring de las 6 internal tools agendapro.* + 2 tools operador (bootstrap, health).

Las clases generadas por ``make_subprocess_tool_class`` heredan de
``ToolBase`` igual que cualquier server in-process. Su ``run()`` delega
al server Node vía un ``SubprocessPool`` resuelto al momento del
dispatch (no al import-time, para que tests inyecten un fake transport).

Catalog (tool_status='internal' en la migración 0009):

  agendapro.check_availability       — read-only, cache 5min Redis
  agendapro.create_appointment       — mutativa, screenshot a audit_log
  agendapro.modify_appointment       — mutativa
  agendapro.cancel_appointment       — mutativa
  agendapro.get_today_appointments   — read-only
  agendapro.scrape_no_shows          — cron Bloque H

Tools operador (no en tool_catalog — solo invocables desde endpoints
admin con Bearer auth, vía dispatch_internal con caller_token):

  agendapro._bootstrap_session       — login inicial + captura context_id
  agendapro._health_check            — verifica context, re-login auto si expiró
"""

from __future__ import annotations

from collections.abc import Callable

from nexus_mcp.base import ToolBase
from nexus_mcp.servers.agendapro_browser.schemas import (
    BootstrapSessionInput,
    BootstrapSessionOutput,
    CancelAppointmentInput,
    CancelAppointmentOutput,
    CheckAvailabilityInput,
    CheckAvailabilityOutput,
    CreateAppointmentInput,
    CreateAppointmentOutput,
    GetTodayAppointmentsInput,
    GetTodayAppointmentsOutput,
    HealthCheckInput,
    HealthCheckOutput,
    ModifyAppointmentInput,
    ModifyAppointmentOutput,
    ScrapeNoShowsInput,
    ScrapeNoShowsOutput,
)
from nexus_mcp.servers.agendapro_browser.transport import (
    get_default_transport,
)
from nexus_mcp.subprocess_tool import (
    SubprocessTransport,
    make_subprocess_tool_class,
)

# ── tool definitions ─────────────────────────────────────────────────────────
#
# Tuple of (name, description, side_effects, input_model, output_model,
# timeout_s) — read by both the wiring function below and the catalog seed
# migration 0009.
_TOOL_SPECS: list[tuple[str, str, tuple[str, ...], type, type, float]] = [
    (
        "agendapro.check_availability",
        "List available slots in AgendaPro for the given date and service. "
        "Result is cached server-side for 5 minutes per (barber, date, service).",
        ("external_api", "browser_automation"),
        CheckAvailabilityInput,
        CheckAvailabilityOutput,
        45.0,
    ),
    (
        "agendapro.create_appointment",
        "Create an appointment in AgendaPro. Idempotent via a stable key "
        "derived inside the server from tenant_id + intent_hash. Captures a "
        "screenshot of the confirmation page; URL written to audit_log.",
        ("external_api", "browser_automation", "mutates_external"),
        CreateAppointmentInput,
        CreateAppointmentOutput,
        120.0,
    ),
    (
        "agendapro.modify_appointment",
        "Modify an existing AgendaPro appointment by external_ref. "
        "Captures a screenshot of the modified detail page.",
        ("external_api", "browser_automation", "mutates_external"),
        ModifyAppointmentInput,
        ModifyAppointmentOutput,
        120.0,
    ),
    (
        "agendapro.cancel_appointment",
        "Cancel an AgendaPro appointment by external_ref. Idempotent: "
        "cancelling an already-cancelled appointment is a no-op.",
        ("external_api", "browser_automation", "mutates_external"),
        CancelAppointmentInput,
        CancelAppointmentOutput,
        90.0,
    ),
    (
        "agendapro.get_today_appointments",
        "Read-only list of today's appointments for the tenant from AgendaPro's "
        "calendar view. Used by no-show detection and operator dashboards.",
        ("external_api", "browser_automation"),
        GetTodayAppointmentsInput,
        GetTodayAppointmentsOutput,
        60.0,
    ),
    (
        "agendapro.scrape_no_shows",
        "Detect no-show appointments for the given date (default: today). Cron "
        "invokes 22:00 tenant TZ. Captures a screenshot of the report view.",
        ("external_api", "browser_automation"),
        ScrapeNoShowsInput,
        ScrapeNoShowsOutput,
        90.0,
    ),
]


# Operator-only tools (NOT in tool_catalog, NOT LLM-facing). They live in
# the same internal namespace and are invoked exclusively from admin
# endpoints with Bearer auth.
_OPERATOR_TOOL_SPECS: list[tuple[str, str, tuple[str, ...], type, type, float]] = [
    (
        "agendapro._bootstrap_session",
        "(operator only) Login to AgendaPro with provided credentials, "
        "capture a Browserbase context, persist context_id + encrypted "
        "credentials in tenant_credentials.",
        ("external_api", "browser_automation", "writes_credentials"),
        BootstrapSessionInput,
        BootstrapSessionOutput,
        180.0,
    ),
    (
        "agendapro._health_check",
        "(operator only) Verify the Browserbase context is still logged in. "
        "On expiry, attempt automatic re-login using stored encrypted password. "
        "On re-login failure, set tenant_credentials.needs_reauth=true.",
        ("external_api", "browser_automation"),
        HealthCheckInput,
        HealthCheckOutput,
        180.0,
    ),
]


def get_agendapro_tool_specs() -> list[tuple[str, str, tuple[str, ...], type, type, float]]:
    """Read by the migration generator + tests. Returns only LLM-relevant
    tools (the 6 catalog ones); operator tools live outside the catalog."""
    return list(_TOOL_SPECS)


AGENDAPRO_INTERNAL_TOOL_NAMES: tuple[str, ...] = tuple(spec[0] for spec in _TOOL_SPECS)


def build_agendapro_tools(
    transport_provider: Callable[[], SubprocessTransport] | None = None,
) -> list[ToolBase]:
    """Construye instancias de las 8 tools internas (6 catalog + 2 operator).

    El registry las pasa a ``register_internal``. ``transport_provider``
    es un callable que retorna el ``SubprocessPool`` (o un fake en tests).
    Si se omite, se usa ``get_default_transport`` que lee el transport
    global configurado al startup.
    """
    provider = transport_provider or get_default_transport
    instances: list[ToolBase] = []
    for spec in (*_TOOL_SPECS, *_OPERATOR_TOOL_SPECS):
        name, description, side_effects, input_model, output_model, timeout_s = spec
        cls = make_subprocess_tool_class(
            name=name,
            description=description,
            input_model=input_model,
            output_model=output_model,
            transport_provider=provider,
            side_effects=side_effects,
            timeout_s=timeout_s,
        )
        instances.append(cls())
    return instances
