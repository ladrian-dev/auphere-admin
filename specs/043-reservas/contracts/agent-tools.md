# Contrato 043: herramientas del agente `reservas.*`

**Estado: congelado el 2026-10-22.**

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

| Herramienta | `side_effects` | Entrada | Salida |
|---|---|---|---|
| `reservas.services` | — | `{}` | Servicios: `{services: [{id, name, duration_minutes, price: {amount_minor, currency}\|null, staff: [{id, name}]}]}`. Aforo: `{mode: "capacity", max_party, unit}` |
| `reservas.find_slots` | — | `{date, service_id?, staff_id?, party_size?}` | `{date, closed, why_closed?, slots: [{time, staff: [{id, name}]?, left?}], first_fit?}`. Respeta antelación mínima y máxima del agente, horario, guardadas (Aforo), bloqueos, ofertas en curso |
| `reservas.create` | `mutates_db` | `{date, time, service_id?, staff_id?, any_staff?, party_size?, note?, join_waitlist?, idempotency_key}` | `{booking: BookingBrief, idempotent_replay}` o `{refused: "slot_taken\|too_large\|too_soon\|too_far\|closed\|hours_missing", first_fit?}` |
| `reservas.list_mine` | — | `{only_upcoming?: true}` | `{bookings: [BookingBrief]}` |
| `reservas.reschedule` | `mutates_db` | `{booking_id, date, time, staff_id?}` | `{booking}` o `{refused}` |
| `reservas.cancel` | `mutates_db` | `{booking_id}` | `{booking, offered_to_waitlist: bool}` |
| `reservas.confirm_attendance` | `mutates_db` | `{attending: bool, booking_id?}` | `{booking}`. Sin `booking_id`, la próxima `pending` de la persona. `attending=false` cancela (`cancelled_by = customer`) |
| `reservas.join_waitlist` | `mutates_db` | Aforo `{date, time, party_size}` · Servicios `{service_id, staff_id?, date?, until?, booking_id?}` | `{entry_id, status: "waiting"}` |
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
