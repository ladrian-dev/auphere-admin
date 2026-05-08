"""Pydantic schemas para las 6 internal tools agendapro.*.

Estos schemas definen el contract estable entre booking-server (Python) y
el server subprocess Node. El payload se serializa via
``model_dump(mode='json')`` y vuelve parseado por ``model_validate``.
Los Zod schemas del lado Node deben matchear estos exactamente — los
tests del adapter validan que round-trip funcione.

Idempotency: el server Node compone la idempotency key dentro de su
proceso (forma ``auphere_<tenant_id>_<intent_hash>``); NUNCA la acepta
del Python adapter ni del LLM. Esto evita que un caller pueda forzar
re-bookings inadvertidos.
"""

from __future__ import annotations

from datetime import date as Date  # noqa: N812
from datetime import datetime
from typing import Literal

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel

# ── shared types ─────────────────────────────────────────────────────────────


class SessionRef(InputModel):
    """Marker mixin para inputs de tools business: el adapter Python siempre
    pasa el ``context_id`` activo (leído de ``tenant_credentials``). El
    server Node lo cachea entre calls del mismo proceso para no re-attach
    al Browserbase context en cada llamada.
    """

    context_id: str | None = Field(
        default=None,
        description=(
            "Browserbase context_id del tenant. El adapter Python lo lee de "
            "``tenant_credentials.encrypted_payload`` y lo pasa en cada call. "
            "Si el server ya tiene una sesión attach'd al mismo context_id, "
            "la reusa; si difiere, re-attach."
        ),
    )


class AgendaProSlot(OutputModel):
    starts_at: datetime
    ends_at: datetime
    barber_external_id: str | None = Field(
        default=None,
        description="ID del profesional en AgendaPro (no nuestro barber_id local).",
    )


class AgendaProAppointment(OutputModel):
    """Vista canónica de una cita en AgendaPro.

    ``external_ref`` es el id de AgendaPro — se persiste en
    ``appointments.external_ref`` desde la fachada booking.create_appointment.
    """

    external_ref: str
    starts_at: datetime
    ends_at: datetime
    service_name: str
    barber_external_id: str | None
    customer_name: str | None
    customer_phone: str | None
    status: Literal["booked", "confirmed", "cancelled", "completed", "no_show"]
    management_url: str | None = Field(
        default=None,
        description=(
            "URL de gestión que AgendaPro envía al cliente final, si está "
            "disponible. Bloque E lo captura para futura modificación/cancelación "
            "sin re-login."
        ),
    )


class ScreenshotMeta(OutputModel):
    """Devuelta por toda acción mutativa para que el adapter Python
    persista la URL en ``audit_log.after_json``."""

    screenshot_url: str | None = Field(
        default=None,
        description=(
            "URI del screenshot capturado. Phase 1: ``file://...`` cuando "
            "el ScreenshotStore es LocalDisk. Bloque G/H lo migra a R2 sin "
            "cambiar este shape."
        ),
    )
    screenshot_failed: bool = False
    screenshot_error: str | None = None


class SessionStatus(OutputModel):
    """Devuelta por TODA tool: indica si el server detectó que el context
    está expirado. El adapter Python, si ve ``needs_reauth=True``, dispara
    un ``_health_check`` y reintenta una vez antes de propagar.
    """

    needs_reauth: bool = Field(
        default=False,
        description=(
            "True si el server intentó usar el context_id pero AgendaPro "
            "respondió con la pantalla de login (sesión expirada). El "
            "adapter Python flippea ``tenant_credentials.needs_reauth`` y "
            "dispara escalate.escalate_to_human si re-login auto también falla."
        ),
    )


# ── check_availability ───────────────────────────────────────────────────────


class CheckAvailabilityInput(SessionRef):
    on_date: Date
    service_name: str = Field(min_length=1, max_length=120)
    barber_external_id: str | None = Field(
        default=None,
        description=(
            "ID del profesional en AgendaPro. El adapter Python lo resuelve "
            "desde ``kg_nodes.properties.agendapro_id`` antes de invocar."
        ),
    )
    duration_min: int = Field(default=30, ge=5, le=480)


class CheckAvailabilityOutput(OutputModel):
    on_date: Date
    service_name: str
    slots: list[AgendaProSlot]
    cached: bool = Field(
        default=False,
        description="True si el resultado vino del cache Redis 5min del lado Node.",
    )
    session: SessionStatus = Field(default_factory=SessionStatus)


# ── create_appointment ───────────────────────────────────────────────────────


class CreateAppointmentInput(SessionRef):
    """Sin idempotency_key — la compone el server Node internamente."""

    intent_hash: str = Field(
        min_length=8,
        max_length=64,
        description=(
            "Hash determinístico del turn (conv id + user message). El server "
            "Node compone ``auphere_<tenant_id>_<intent_hash>`` y lo usa como "
            "idempotency key contra AgendaPro. Sirve para que retries del "
            "webhook YCloud no doble-booken."
        ),
    )
    starts_at: datetime
    duration_min: int = Field(ge=5, le=480, default=30)
    service_name: str = Field(min_length=1, max_length=120)
    barber_external_id: str | None = None
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str = Field(min_length=4, max_length=40)
    customer_email: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class CreateAppointmentOutput(OutputModel):
    appointment: AgendaProAppointment
    idempotent_replay: bool
    screenshot: ScreenshotMeta
    session: SessionStatus = Field(default_factory=SessionStatus)


# ── modify_appointment ───────────────────────────────────────────────────────


class ModifyAppointmentInput(SessionRef):
    external_ref: str = Field(min_length=1, max_length=255)
    new_starts_at: datetime | None = None
    new_duration_min: int | None = Field(default=None, ge=5, le=480)
    new_barber_external_id: str | None = None
    new_service_name: str | None = Field(default=None, min_length=1, max_length=120)


class ModifyAppointmentOutput(OutputModel):
    appointment: AgendaProAppointment
    status: Literal["modified", "no_changes"]
    screenshot: ScreenshotMeta
    session: SessionStatus = Field(default_factory=SessionStatus)


# ── cancel_appointment ───────────────────────────────────────────────────────


class CancelAppointmentInput(SessionRef):
    external_ref: str = Field(min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=500)


class CancelAppointmentOutput(OutputModel):
    external_ref: str
    status: Literal["cancelled"]
    screenshot: ScreenshotMeta
    session: SessionStatus = Field(default_factory=SessionStatus)


# ── get_today_appointments ───────────────────────────────────────────────────


class GetTodayAppointmentsInput(SessionRef):
    # Solo context_id (heredado de SessionRef). No otros params — el
    # subprocess sabe la fecha actual del tenant TZ.
    pass


class GetTodayAppointmentsOutput(OutputModel):
    appointments: list[AgendaProAppointment]
    fetched_at: datetime
    session: SessionStatus = Field(default_factory=SessionStatus)


# ── scrape_no_shows ──────────────────────────────────────────────────────────


class NoShowEntry(OutputModel):
    external_ref: str
    starts_at: datetime
    service_name: str
    customer_name: str | None
    customer_phone: str | None
    barber_external_id: str | None


class ScrapeNoShowsInput(SessionRef):
    on_date: Date | None = Field(
        default=None,
        description=(
            "Si se omite, scrape de la fecha actual del tenant. El cron "
            "Bloque H corre 22:00 tenant TZ y omite el campo."
        ),
    )


class ScrapeNoShowsOutput(OutputModel):
    on_date: Date
    no_shows: list[NoShowEntry]
    screenshot: ScreenshotMeta
    session: SessionStatus = Field(default_factory=SessionStatus)


# ── _bootstrap_session (no LLM-facing, operator-invocable) ──────────────────


class BootstrapSessionInput(InputModel):
    """Tool interna invocable solo desde el endpoint admin operador.

    El password va en plaintext SOLO acá — el server Node lo encripta
    con la Fernet key del proceso y lo persiste en
    ``tenant_credentials.encrypted_payload``. Se usa para re-login auto
    cuando el context Browserbase expira.
    """

    login: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)
    business_url: str | None = Field(
        default=None,
        max_length=500,
        description="URL del backend de AgendaPro del tenant (si difiere del default).",
    )


class BootstrapSessionOutput(OutputModel):
    context_id: str = Field(
        description="Browserbase context_id capturado. Persistido en tenant_credentials."
    )
    bootstrap_at: datetime
    screenshot: ScreenshotMeta


# ── _health_check (no LLM-facing, operator-invocable) ───────────────────────


class HealthCheckInput(InputModel):
    context_id: str = Field(
        min_length=1,
        max_length=255,
        description="context_id actual a verificar.",
    )
    login_for_relogin: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Si se proporciona y el context está expirado, el server intenta "
            "re-login con estos credentials y devuelve el nuevo context_id."
        ),
    )
    password_for_relogin: str | None = Field(default=None, max_length=200)
    business_url: str | None = Field(default=None, max_length=500)


class HealthCheckOutput(OutputModel):
    healthy: bool
    relogin_attempted: bool = False
    relogin_succeeded: bool = False
    needs_reauth: bool = Field(
        description=(
            "True si el re-login automático falló y el operador debe "
            "re-bootstrap. Coincide con la columna ``tenant_credentials.needs_reauth``."
        ),
    )
    checked_at: datetime
    notes: str | None = None
    new_context_id: str | None = Field(
        default=None,
        description=(
            "Si el re-login generó un context_id nuevo, viene acá. El adapter "
            "Python lo persiste en ``tenant_credentials.encrypted_payload``."
        ),
    )
