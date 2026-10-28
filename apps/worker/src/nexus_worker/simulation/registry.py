"""El registro de herramientas del mundo simulado — spec 047, T085 (requisitos 20.1 y 20.3).

Una vista del registro MCP de siempre (las mismas definiciones, la misma lista
blanca) en la que:

- **Reservas y la agenda** (``reservas.*``, ``booking.*``) operan sobre la agenda
  simulada (``World``): buscan huecos en el horario de la ficha, reservan,
  cancelan y cambian, y el agente ve un resultado de verdad;
- **pasar a una persona**, **avisos**, **recordatorios** y **pagos** no salen:
  quedan como «Lo que habría hecho» y el agente recibe un «hecho»;
- **los mensajes extra** (``notification.send_text`` y compañía) son burbujas de
  más, que la pantalla señala (20.4);
- **lo demás con efecto** queda bloqueado y anotado, como en el dry-run de hoy;
- **lo que solo lee** (el catálogo, por ejemplo) corre de verdad.

Nada de lo que pasa aquí toca datos del cliente ni sale a un proveedor (20.1).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

from nexus_api.core.tenant_context import require_current_tenant
from nexus_mcp import MCPRegistry, build_default_registry
from nexus_mcp.base import make_envelope

from nexus_worker.simulation.world import World

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
#: Herramientas cuyo mensaje es una burbuja más del turno.
EXTRA_BUBBLES = frozenset({"notification.send_text", "response.send_interactive"})


def _ok(result: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "simulated": True, **result}


def _date(raw: Any, world: World) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


class SimulatedRegistry(MCPRegistry):  # type: ignore[misc]
    """La vista del registro que usan el playground y las pruebas."""

    def __init__(self, world: World, *, base: MCPRegistry | None = None) -> None:
        super().__init__(dry_run=True)
        source = base or build_default_registry()
        for name in source.names():
            self._tools[name] = source._tools[name]
        for name in source.internal_names():
            self._internal_tools[name] = source._internal_tools[name]
        self.world = world

    async def dispatch(self, name: str, args: dict[str, Any], *, whitelist: Iterable[str]) -> Any:
        tenant_id = require_current_tenant()
        if name in set(whitelist):
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
            if tool is not None and tool.side_effects:
                phrase = PHRASES.get(name) or f"Usar {name}"
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


def _create(world: World, args: dict[str, Any]) -> dict[str, Any]:
    day: date | None
    if args.get("starts_at"):
        try:
            at = datetime.fromisoformat(str(args["starts_at"]).replace("Z", "+00:00"))
        except ValueError:
            return {"ok": False, "error": "invalid_time"}
        if at.tzinfo is None:
            at = at.replace(tzinfo=world.tz)
        local = at.astimezone(world.tz)
        day, hhmm = local.date(), local.strftime("%H:%M")
    else:
        day = _date(args.get("date"), world)
        hhmm = str(args.get("time") or "")[:5]
        if day is None or not hhmm:
            return {"ok": False, "error": "invalid_time"}
    svc = world.service(service_id=args.get("service_id"), name=args.get("service_name"))
    booking = world.book(day=day, at=hhmm, service=svc, duration_min=args.get("duration_min"))
    if booking is None:
        return {
            "ok": False,
            "error": "slot_unavailable",
            "alternatives": world.slots(day, None)[:3],
        }
    world.did(
        "reservas.create",
        f"Reservar {booking.service_name} el {world.when(booking)}",
        args,
    )
    return _ok(
        {"booking_id": booking.id, "when": world.when(booking), "service": booking.service_name}
    )


def _cancel(world: World, args: dict[str, Any]) -> dict[str, Any]:
    booking = world.booking(args.get("booking_id") or args.get("appointment_id"))
    if booking is None or booking.status != "confirmed":
        return {"ok": False, "error": "not_found"}
    booking.status = "cancelled"
    world.did("reservas.cancel", f"Cancelar {booking.service_name} del {world.when(booking)}", args)
    return _ok({"booking_id": booking.id, "status": "cancelled"})


def _reschedule(world: World, args: dict[str, Any]) -> dict[str, Any]:
    booking = world.booking(args.get("booking_id") or args.get("appointment_id"))
    if booking is None or booking.status != "confirmed":
        return {"ok": False, "error": "not_found"}
    booking.status = "cancelled"
    new_args = {
        "date": args.get("date"),
        "time": args.get("time"),
        "starts_at": args.get("new_starts_at"),
        "service_id": booking.service_id,
        "service_name": booking.service_name,
        "duration_min": booking.duration_min,
    }
    created = _create(world, {k: v for k, v in new_args.items() if v})
    if not created.get("ok"):
        booking.status = "confirmed"
        return created
    world.actions[-1].phrase = "Cambiar la cita a " + str(created["when"])
    return created


def _mine(world: World, _args: dict[str, Any]) -> dict[str, Any]:
    return _ok({"bookings": world.agenda()})


def _noted(tool: str, phrase: str) -> Any:
    def handler(world: World, args: dict[str, Any]) -> dict[str, Any]:
        world.did(tool, phrase, args)
        return _ok({})

    return handler


_HANDLERS: dict[str, Any] = {
    "reservas.services": _services,
    "reservas.find_slots": _find,
    "reservas.create": _create,
    "reservas.cancel": _cancel,
    "reservas.reschedule": _reschedule,
    "reservas.list_mine": _mine,
    "reservas.confirm_attendance": _noted("reservas.confirm_attendance", "Confirmar la asistencia"),
    "reservas.join_waitlist": _noted("reservas.join_waitlist", "Apuntar en la lista de espera"),
    "reservas.answer_offer": _noted("reservas.answer_offer", "Responder a una oferta de hueco"),
    "booking.check_availability": _find,
    "booking.create_appointment": _create,
    "booking.cancel_appointment": _cancel,
    "booking.modify_appointment": _reschedule,
    "booking.get_appointments": _mine,
}


def simulated_now(world: World) -> datetime:
    return world.now_at


def advance(world: World, minutes: int) -> None:
    world.set_now(world.now_at + timedelta(minutes=minutes))


__all__ = ["EXTRA_BUBBLES", "PHRASES", "SimulatedRegistry", "advance", "simulated_now"]
