"""El registro de herramientas del mundo simulado — spec 047, T085 (requisitos 20.1 y 20.3).

Una vista del registro MCP de siempre (las mismas definiciones, la misma lista
blanca) en la que:

- **Reservas y la agenda** (``reservas.*``, ``booking.*``) operan sobre la agenda
  simulada (``World``): buscan huecos en el horario de la ficha, reservan,
  cancelan y cambian, y el agente ve un resultado de verdad, **con la forma de
  la herramienta de verdad** (sus mismos modelos de salida): lo leen el modelo y
  el freno de citas (spec 056), que en el canal leen lo mismo;
- **pasar a una persona**, **avisos**, **recordatorios** y **pagos** no salen:
  quedan como «Lo que habría hecho» y el agente recibe un «hecho»;
- **los mensajes extra** (``notification.send_text`` y compañía) son burbujas de
  más, que la pantalla señala (20.4);
- **lo demás con efecto** queda bloqueado y anotado, como en el dry-run de hoy;
- **las herramientas de un conector** (Composio, o cualquiera con
  ``connector_id`` en el catálogo) no se ejecutan **nunca**, tampoco las que
  solo leen: traerían datos de verdad de los clientes finales del negocio, que
  el partner no debe ver (C8). El agente recibe un resultado simulado y vacío,
  marcado como tal, y la pantalla «Consultar …» o «Usar …»;
- **«Preguntar antes de escribir»** no pregunta a nadie: queda «Preguntar al
  dueño antes de …» y el turno sigue como si hubiera dicho que sí
  (:meth:`SimulatedRegistry.note_simulated_approval`, desde el grafo);
- **lo interno que solo lee** datos del propio negocio (la ficha, los
  servicios) corre de verdad.

Nada de lo que pasa aquí toca datos del cliente ni sale a un proveedor (20.1).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

import sqlalchemy as sa
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import ToolCatalog
from nexus_mcp import MCPRegistry, ToolError, build_default_registry
from nexus_mcp.base import OutputModel, make_envelope
from nexus_mcp.servers.composio_proxy.proxy import ComposioProxyTool
from nexus_mcp.servers.reservas.schemas import (
    HHMM,
    AnswerOfferOutput,
    BookingBrief,
    CancelOutput,
    ConfirmAttendanceOutput,
    CreateOutput,
    ListMineOutput,
    RescheduleOutput,
)
from nexus_mcp.servers.reservas.tools import NOT_ACTIVE

from nexus_worker.simulation.world import SimBooking, World

#: Lo que el negocio leería de cada herramienta con efecto (20.3).
PHRASES: dict[str, str] = {
    "escalate.escalate_to_human": "Pasar la conversación al equipo",
    "operator.consult_owner": "Consultar al dueño",
    "notification.schedule_reminder": "Programar un recordatorio",
    "notification.cancel_scheduled": "Cancelar un recordatorio",
    "notification.send_template": "Enviar una plantilla de WhatsApp",
    "notification.send_image": "Enviar una imagen",
    "notification.send_document": "Enviar un documento",
    "notification.send_audio": "Enviar un audio",
    "notification.send_video": "Enviar un vídeo",
    "notification.send_location": "Enviar una ubicación",
    "notification.send_reaction": "Reaccionar a un mensaje",
    "payments.request_review": "Pedir al equipo que revise un pago",
    "client.update_preferences": "Guardar las preferencias del cliente",
    "queue.join_queue": "Apuntar al cliente en la cola",
    "queue.check_in": "Registrar la llegada del cliente",
    "queue.remove_from_queue": "Sacar al cliente de la cola",
}
#: La agenda de Reservas: solo con el módulo encendido para el cliente.
AGENDA_PREFIX = "reservas."
#: Herramientas cuyo mensaje es una burbuja más del turno.
EXTRA_BUBBLES = frozenset({"notification.send_text", "response.send_interactive"})


def _ok(result: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "simulated": True, **result}


def _date(raw: Any, world: World) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


async def load_connector_tools(session: Any) -> dict[str, bool]:
    """Las herramientas de conectores del catálogo (``connector_id``) y si solo
    leen: el playground no ejecuta ninguna. Tabla de plataforma."""
    rows = await session.execute(
        sa.select(ToolCatalog.name, ToolCatalog.read_only).where(
            ToolCatalog.connector_id.is_not(None)
        )
    )
    return {str(name): bool(read_only) for name, read_only in rows.tuples().all()}


def _phrase(name: str) -> str:
    return PHRASES.get(name) or f"Usar {name}"


class SimulatedRegistry(MCPRegistry):  # type: ignore[misc]
    """La vista del registro que usan el playground y las pruebas.

    ``connector_tools``: las herramientas de conectores del catálogo y si solo
    leen (:func:`load_connector_tools`). Un proxy de Composio cuenta siempre,
    esté o no en el mapa.

    ``reservas_on``: si el cliente tiene el módulo Reservas encendido. Apagado, la
    agenda simulada responde lo mismo que el servidor de Reservas en el turno
    («no está activo», spec 047, enmienda del 2026-10-29, D67): una prueba no puede
    pasar en verde con una agenda que en el canal no funcionaría.
    """

    def __init__(
        self,
        world: World,
        *,
        base: MCPRegistry | None = None,
        connector_tools: Mapping[str, bool] | None = None,
        reservas_on: bool = True,
    ) -> None:
        super().__init__(dry_run=True)
        source = base or build_default_registry()
        for name in source.names():
            self._tools[name] = source._tools[name]
        for name in source.internal_names():
            self._internal_tools[name] = source._internal_tools[name]
        self.world = world
        self.connector_tools: dict[str, bool] = dict(connector_tools or {})
        self.reservas_on = reservas_on

    def note_simulated_approval(self, name: str, args: dict[str, Any]) -> None:
        """«Preguntar antes de escribir»: lo que habría hecho, sin preguntar."""
        phrase = _phrase(name)
        self.world.did(name, f"Preguntar al dueño antes de {phrase[:1].lower()}{phrase[1:]}", args)

    def simulated_booking_stands(self) -> bool:
        """Una cita en pie en la agenda simulada, de este turno o de los de antes
        de la sesión. Para el freno de citas (spec 056) es la agenda de la
        conversación: sus reservas no llegan a ``reservations``, que es donde mira
        en el canal."""
        return any(b.status == "confirmed" for b in self.world.bookings)

    def _is_connector(self, name: str, tool: Any) -> bool:
        return name in self.connector_tools or isinstance(tool, ComposioProxyTool)

    async def dispatch(self, name: str, args: dict[str, Any], *, whitelist: Iterable[str]) -> Any:
        tenant_id = require_current_tenant()
        if name in set(whitelist):
            if name.startswith(AGENDA_PREFIX) and not self.reservas_on:
                raise ToolError(NOT_ACTIVE)
            handler = _HANDLERS.get(name)
            if handler is not None:
                result = handler(self.world, dict(args))
                return make_envelope(
                    tool=name, tenant_id=tenant_id, args=dict(args), result=result, status="ok"
                )
            tool = self._tools.get(name)
            if name in EXTRA_BUBBLES:
                body = str(args.get("body") or args.get("text") or "").strip()
                if body:
                    self.world.bubbles.append(body)
                return make_envelope(
                    tool=name, tenant_id=tenant_id, args=dict(args), result=_ok({}), status="ok"
                )
            if self._is_connector(name, tool):
                # Un sistema del negocio: ni una lectura sale de aquí (C8).
                reads = self.connector_tools.get(name, False)
                phrase = (
                    f"Consultar {name} (simulado, sin datos reales)" if reads else _phrase(name)
                )
                self.world.did(name, phrase, args)
                return make_envelope(
                    tool=name,
                    tenant_id=tenant_id,
                    args=dict(args),
                    result=_ok(
                        {
                            "data": {},
                            "note": (
                                "Simulado: no se consultó el sistema del negocio; "
                                "no hay datos de verdad."
                                if reads
                                else "Simulado: no se hizo nada de verdad."
                            ),
                        }
                    ),
                    status="ok",
                )
            if tool is not None and tool.side_effects:
                phrase = _phrase(name)
                if name == "escalate.escalate_to_human":
                    self.world.escalated = True
                    reason = str(args.get("reason") or "").strip()
                    if reason:
                        phrase = f"{phrase}: {reason}"
                self.world.did(name, phrase, args)
                return make_envelope(
                    tool=name,
                    tenant_id=tenant_id,
                    args=dict(args),
                    result=_ok({"note": "Simulado: no se hizo nada de verdad."}),
                    status="ok",
                )
        return await super().dispatch(name, args, whitelist=whitelist)


# ── la agenda simulada ───────────────────────────────────────────────────────


def _services(world: World, _args: dict[str, Any]) -> dict[str, Any]:
    return _ok(
        {
            "services": [
                {
                    "id": s.id,
                    "name": s.name,
                    "duration_min": s.duration_min,
                    "bookable": s.bookable,
                    "price": s.price,
                }
                for s in world.services
            ]
        }
    )


def _find(world: World, args: dict[str, Any]) -> dict[str, Any]:
    day = _date(args.get("date") or args.get("on_date"), world)
    if day is None:
        return {"ok": False, "error": "invalid_date"}
    svc = world.service(service_id=args.get("service_id"), name=args.get("service_name"))
    duration = args.get("duration_min") or (svc.duration_min if svc else None)
    slots = world.slots(day, duration)
    return _ok({"date": day.isoformat(), "slots": slots, "closed": not slots})


# Lo que contesta la agenda tiene la forma de la herramienta de verdad, hecha con
# sus mismos modelos de salida (``nexus_mcp.servers.reservas.schemas``): el freno de
# citas (spec 056) decide con ella, y una forma propia de la simulación hacía que
# toda reserva del Playground y de las pruebas pareciera no hecha. Como en la de
# verdad, lo que la agenda rechaza (un hueco ocupado, un día cerrado) es
# ``refused`` con ``status: ok``, y lo que la herramienta no acepta (una fecha que
# no valida, una cita que no es suya) es un ``ToolError``: el grafo lo convierte en
# ``status: error``.


def _real(out: OutputModel) -> dict[str, Any]:
    """La salida de la herramienta de verdad, marcada como simulada."""
    return {**out.model_dump(mode="json"), "simulated": True}


def _start(booking: SimBooking) -> datetime:
    return datetime.fromisoformat(booking.starts_at)


def _brief(world: World, booking: SimBooking) -> BookingBrief:
    """La cita como la cuenta ``reservas`` (``tools._brief``): día y horas locales."""
    local = _start(booking).astimezone(world.tz)
    return BookingBrief(
        id=uuid.UUID(booking.id),
        status=booking.status,
        date=local.date(),
        start=local.strftime("%H:%M"),
        end=(local + timedelta(minutes=booking.duration_min)).strftime("%H:%M"),
        starts_at=_start(booking),
        party_size=1,
        service_name=booking.service_name,
    )


def _requested(world: World, args: dict[str, Any]) -> tuple[date, str]:
    """El día y la hora local que pide la llamada: ``date`` + ``time`` (Reservas) o
    ``starts_at`` (las ``booking.*`` retiradas)."""
    if args.get("starts_at"):
        try:
            at = datetime.fromisoformat(str(args["starts_at"]).replace("Z", "+00:00"))
        except ValueError:
            raise ToolError("invalid_time") from None
        if at.tzinfo is None:
            at = at.replace(tzinfo=world.tz)
        local = at.astimezone(world.tz)
        return local.date(), local.strftime("%H:%M")
    day = _date(args.get("date"), world)
    hhmm = str(args.get("time") or "")
    if day is None or not re.fullmatch(HHMM, hhmm):
        raise ToolError("invalid_time")
    return day, hhmm


def _refusal(world: World, day: date, hhmm: str, free: list[str]) -> tuple[str, str | None]:
    """Por qué la agenda no da ese hueco y el primero que cabe después, con los
    códigos de la de verdad (``services.reservations.core.create_booking``)."""
    if world.week is None and not world.specials:
        return "hours_missing", None
    if datetime.combine(day, time.fromisoformat(hhmm), tzinfo=world.tz) < world.now_at:
        return "too_soon", None
    return "slot_taken", next((t for t in free if t > hhmm), None)


def _own(world: World, args: dict[str, Any]) -> SimBooking:
    booking = world.booking(args.get("booking_id") or args.get("appointment_id"))
    if booking is None:
        raise ToolError("booking not found for this customer")
    return booking


def _create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    day, hhmm = _requested(world, args)
    key = str(args.get("idempotency_key") or "") or None
    prior = next((b for b in world.bookings if key and b.key == key), None)
    if prior is not None:
        # La misma clave devuelve la misma reserva, como en la de verdad.
        return _real(CreateOutput(booking=_brief(world, prior), idempotent_replay=True))
    svc = world.service(service_id=args.get("service_id"), name=args.get("service_name"))
    booking = world.book(day=day, at=hhmm, service=svc, duration_min=args.get("duration_min"))
    if booking is None:
        length = args.get("duration_min") or (svc.duration_min if svc else None)
        refused, first_fit = _refusal(world, day, hhmm, world.slots(day, length))
        return _real(CreateOutput(refused=refused, first_fit=first_fit))
    booking.key = key
    world.did(
        "reservas.create",
        f"Reservar {booking.service_name} el {world.when(booking)}",
        args,
    )
    return _real(CreateOutput(booking=_brief(world, booking)))


def _cancel(world: World, args: dict[str, Any]) -> dict[str, Any]:
    booking = _own(world, args)
    if booking.status != "confirmed":
        raise ToolError(f"booking is {booking.status}")
    booking.status = "cancelled"
    world.did("reservas.cancel", f"Cancelar {booking.service_name} del {world.when(booking)}", args)
    return _real(CancelOutput(booking=_brief(world, booking), offered_to_waitlist=False))


def _reschedule(world: World, args: dict[str, Any]) -> dict[str, Any]:
    booking = _own(world, args)
    if booking.status != "confirmed":
        raise ToolError(f"booking is {booking.status}")
    day, hhmm = _requested(
        world,
        {
            "date": args.get("date"),
            "time": args.get("time"),
            "starts_at": args.get("new_starts_at"),
        },
    )
    if not world.move(booking, day=day, at=hhmm):
        free = world.slots(day, booking.duration_min, ignoring=booking)
        refused, first_fit = _refusal(world, day, hhmm, free)
        return _real(RescheduleOutput(refused=refused, first_fit=first_fit))
    world.did("reservas.reschedule", f"Cambiar la cita a {world.when(booking)}", args)
    return _real(RescheduleOutput(booking=_brief(world, booking)))


def _upcoming(world: World) -> list[SimBooking]:
    return sorted(
        (b for b in world.bookings if b.status == "confirmed" and _start(b) > world.now_at),
        key=_start,
    )


def _mine(world: World, args: dict[str, Any]) -> dict[str, Any]:
    """Las suyas: por defecto, las que vienen y siguen en pie (``only_upcoming``)."""
    rows = (
        _upcoming(world)
        if args.get("only_upcoming", True) is not False
        else sorted(world.bookings, key=_start)
    )
    return _real(ListMineOutput(bookings=[_brief(world, b) for b in rows[:20]]))


def _confirm_attendance(world: World, args: dict[str, Any]) -> dict[str, Any]:
    """Su respuesta a «¿vienes?»: sí la mantiene y no la cancela. Sin cita a la que
    contestar es un error, como en la de verdad."""
    if args.get("booking_id"):
        booking = _own(world, args)
    else:
        upcoming = _upcoming(world)
        if not upcoming:
            raise ToolError("no unconfirmed booking for this customer")
        booking = upcoming[0]
    if args.get("attending") is False:
        if booking.status != "confirmed":
            raise ToolError(f"booking is {booking.status}")
        booking.status = "cancelled"
        phrase = f"Cancelar {booking.service_name} del {world.when(booking)}: no va a venir"
    else:
        phrase = "Confirmar la asistencia"
    world.did("reservas.confirm_attendance", phrase, args)
    return _real(ConfirmAttendanceOutput(booking=_brief(world, booking)))


def _answer_offer(world: World, args: dict[str, Any]) -> dict[str, Any]:
    world.did("reservas.answer_offer", "Responder a una oferta de hueco", args)
    # La agenda simulada no tiene lista de espera: nunca hay una oferta abierta.
    return _real(AnswerOfferOutput(result="no_offer"))


Handler = Callable[[World, dict[str, Any]], dict[str, Any]]


def _retired(handler: Handler) -> Handler:
    """Las ``booking.*`` retiradas fallan con un error, como las de verdad: un
    rechazo con ``status: ok`` respaldaría ante el freno una cita que no se hizo."""

    def run(world: World, args: dict[str, Any]) -> dict[str, Any]:
        out = handler(world, args)
        if out.get("refused"):
            raise ToolError(str(out["refused"]))
        return out

    return run


def _noted(tool: str, phrase: str) -> Handler:
    def handler(world: World, args: dict[str, Any]) -> dict[str, Any]:
        world.did(tool, phrase, args)
        return _ok({})

    return handler


_HANDLERS: dict[str, Handler] = {
    "reservas.services": _services,
    "reservas.find_slots": _find,
    "reservas.create": _create,
    "reservas.cancel": _cancel,
    "reservas.reschedule": _reschedule,
    "reservas.list_mine": _mine,
    "reservas.confirm_attendance": _confirm_attendance,
    "reservas.join_waitlist": _noted("reservas.join_waitlist", "Apuntar en la lista de espera"),
    "reservas.answer_offer": _answer_offer,
    "booking.check_availability": _find,
    "booking.create_appointment": _retired(_create),
    "booking.cancel_appointment": _cancel,
    "booking.modify_appointment": _retired(_reschedule),
    "booking.get_appointments": _mine,
}


def simulated_now(world: World) -> datetime:
    return world.now_at


def advance(world: World, minutes: int) -> None:
    world.set_now(world.now_at + timedelta(minutes=minutes))


__all__ = [
    "EXTRA_BUBBLES",
    "PHRASES",
    "SimulatedRegistry",
    "advance",
    "load_connector_tools",
    "simulated_now",
]
