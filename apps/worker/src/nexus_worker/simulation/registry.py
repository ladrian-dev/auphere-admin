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

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import ToolCatalog
from nexus_mcp import MCPRegistry, ToolError, build_default_registry
from nexus_mcp.base import make_envelope
from nexus_mcp.servers.composio_proxy.proxy import ComposioProxyTool
from nexus_mcp.servers.reservas.tools import NOT_ACTIVE

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


__all__ = [
    "EXTRA_BUBBLES",
    "PHRASES",
    "SimulatedRegistry",
    "advance",
    "load_connector_tools",
    "simulated_now",
]
