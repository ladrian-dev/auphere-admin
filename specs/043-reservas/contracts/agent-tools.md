# Contrato 043: herramientas del agente `reservas.*`

**Estado: congelado el 2026-10-22.** Enmienda del 2026-11-08: el servicio y la persona
también por nombre (fallo `la-reserva-del-turno-siguiente-pierde-los-ids`).

Servidor MCP `reservas-server` (`apps/mcp/src/nexus_mcp/servers/reservas/`).
Reglas para todas:

- **Ninguna acepta cliente** (spec 014): ni `customer_id`, ni teléfono, ni
  nombre de otra persona. La persona es la del turno (`current_customer_or_refuse`).
  `test_37` lo barre.
- **Sin el módulo activo** → `ToolError("Reservas no está activo para este negocio")`.
- Una reserva de otra persona se lee **igual que una inexistente**.
- Horas en la zona del negocio (`date` + `time` locales); la salida trae también
  el instante UTC.
- Las escrituras revalidan con candado (`data-model.md`).
- **El servicio y la persona, por id o por nombre** (enmienda del 2026-11-08). Entre
  turnos el agente solo conserva el texto: los ids que dio `services` o `find_slots`
  en un turno no llegan al siguiente, donde el cliente suele elegir la hora.
  `service_name` y `staff_name` son opcionales en `find_slots`, `create` y
  `join_waitlist`, y `staff_name` en `reschedule` (el servicio lo trae la reserva):
  - **el id manda**; un nombre se usa sin id, o con un id que no existe;
  - se compara normalizado (sin mayúsculas, acentos ni espacios de más): primero el
    nombre igual, luego un único prefijo, luego un único «contiene»;
  - el servicio, contra el catálogo vivo del cliente: uno que **este agente** ofrece
    es ese; uno de su hermano, `not_offered` (garantía 9);
  - la persona, contra el equipo activo: una que hace el servicio es esa; una que no
    lo hace, `not_offered` (R14.4) con `staff` = quienes sí.
- **Lo que no se resuelve no es un error** (enmienda del 2026-11-08): la salida normal
  con `refused` y las opciones para reintentar en el mismo turno, `services:
  [{id, name}]` o `staff: [{id, name}]`:
  - `unknown_service`: sin servicio, o un id o nombre que no está (inventado,
    archivado o de la vecina, que se lee igual que uno que no existe). Opciones: los
    reservables del agente;
  - `unknown_staff`: una persona que no está en el equipo activo. Opciones: quienes
    hacen el servicio;
  - `ambiguous_service` / `ambiguous_staff`: el nombre encaja con varios. Opciones:
    los empatados (de este agente).

  `slot_taken` sigue significando solo «la hora está ocupada». La descripción de cada
  herramienta, que es lo único que lee el modelo, lo dice: reintentar con una opción o
  preguntar, y nunca decirle al cliente que la hora está tomada por esto.

| Herramienta | `side_effects` | Entrada | Salida |
|---|---|---|---|
| `reservas.services` | — | `{}` | Servicios: `{services: [{id, name, bookable, why_not?, duration_minutes, price: {amount_minor, currency}\|null, staff: [{id, name}]}]}`. `why_not: no_staff`: nadie lo hace ahora (R14.1). Aforo: `{mode: "capacity", max_party, unit}` |
| `reservas.find_slots` | — | `{date, service_id?, service_name?, staff_id?, staff_name?, party_size?}` | `{date, closed, why_closed?, slots: [{time, staff: [{id, name}]?, left?}], first_fit?}`, o `{closed: false, slots: [], refused: "unknown_service\|unknown_staff\|ambiguous_service\|ambiguous_staff", services, staff}`. Un servicio del hermano o una persona que no lo hace: `closed, why_closed: "not_offered"`. Respeta antelación mínima y máxima del agente, horario, guardadas (Aforo), bloqueos, ofertas en curso |
| `reservas.create` | `mutates_db` | `{date, time, service_id?, service_name?, staff_id?, staff_name?, any_staff?, party_size?, note?, join_waitlist?, idempotency_key}` | `{booking: BookingBrief, idempotent_replay}` o `{refused: "slot_taken\|too_large\|too_soon\|too_far\|closed\|hours_missing\|not_bookable\|not_offered\|no_staff\|unknown_service\|unknown_staff\|ambiguous_service\|ambiguous_staff", first_fit?, services, staff}` |
| `reservas.list_mine` | — | `{only_upcoming?: true}` | `{bookings: [BookingBrief]}` |
| `reservas.reschedule` | `mutates_db` | `{booking_id, date, time, staff_id?, staff_name?}` | `{booking}` o `{refused, staff}`. `not_offered`: esa persona no hace el servicio de la reserva |
| `reservas.cancel` | `mutates_db` | `{booking_id}` | `{booking, offered_to_waitlist: bool}` |
| `reservas.confirm_attendance` | `mutates_db` | `{attending: bool, booking_id?}` | `{booking}`. Sin `booking_id`, la próxima `pending` de la persona. `attending=false` cancela (`cancelled_by = customer`) |
| `reservas.join_waitlist` | `mutates_db` | Aforo `{date, time, party_size}` · Servicios `{service_id \| service_name, staff_id? \| staff_name?, date?, until?, booking_id?}` (con `booking_id` y sin servicio, el de la reserva) | `{entry_id, status: "waiting"}` o `{refused: "not_offered\|unknown_*\|ambiguous_*", services, staff}` (antes `not_offered` era un `ToolError`) |
| `reservas.answer_offer` | `mutates_db` | `{accept: bool}` | `{result: "booked\|late_taken\|declined\|no_offer", booking?}`. Resuelve **la oferta abierta de la persona del turno** |

`BookingBrief`: `{id, status, local: {date, start, end}, starts_at, party_size,
service_name, staff_name, note}`.

- `reservas.create` desde el agente: origen `agent`, canal `whatsapp`,
  `conversation_id` y `agent_id` del turno, `contact` = nombre y teléfono del
  contacto. Estado `pending` si el negocio pide confirmación, si no
  `confirmed`. Encola el push `reservas.agent_change`.
- `idempotency_key` es **de la persona del turno**: la herramienta guarda
  `agent:` + sha256(cliente + clave), así que dos personas que manden la misma
  clave reservan cada una lo suyo; y el dominio nunca devuelve por clave la
  reserva de otra persona (409 `idempotency_conflict`). Enmienda del 2026-10-22,
  hallazgo CSO-001 de `/cso`.
- `too_large`: el grupo pasa del máximo por reserva → el agente escala con
  `escalate.escalate_to_human` (lo dice la descripción de la herramienta).
- Registro: catálogo en `0173_reservations_tools` (snapshot
  `alembic/data/0173_reservations_tools.json`), `capability_names.py` (grupo
  «Citas»), `_INTENT_CATEGORIES["book"]` e `["info"]` (lectura) del pipeline.
- `side_effects` vacío en las de lectura: el administrador de solo lectura (spec
  024) puede consultarlas.
