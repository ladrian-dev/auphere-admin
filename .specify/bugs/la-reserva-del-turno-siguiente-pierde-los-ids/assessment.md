# Bug Assessment: la reserva del turno siguiente pierde los ids del servicio y de la persona

- **Slug**: la-reserva-del-turno-siguiente-pierde-los-ids
- **Created**: 2026-11-08
- **Source**: conversación real de WhatsApp en staging (2026-11-08), con los registros del turno
- **Verdict**: valid
- **Severity**: high (1 de 3 reservas reales fallidas; el agente dice al cliente que una hora libre está ocupada)

## Report (verbatim or summarized)

Por WhatsApp, reservar casi siempre ocupa varios mensajes: el cliente pregunta por
huecos en uno y elige la hora en el siguiente. En staging, de tres intentos reales:

- dos reservaron bien: en el segundo turno el modelo volvió a llamar a
  `reservas.services` y `reservas.find_slots` (4 llamadas en el turno) y después a
  `reservas.create`;
- uno falló: en el segundo turno el modelo llamó directamente a `reservas.create`
  (1 llamada, 1 iteración) y el agente contestó «Ese horario ya no está disponible»,
  con la hora libre.

## Symptom

`reservas.create` en el turno siguiente no tiene `service_id` ni `staff_id` de verdad.
Según lo que mande el modelo, el turno acaba en uno de estos caminos, y ninguno es
«la hora está ocupada»:

- un `service_id` inventado: `not_offered` (no es un servicio del agente);
- sin `service_id`: `_service` levanta 422 `service_required` y la herramienta
  devuelve `status: error`;
- un `staff_id` inventado: `create_booking` levanta 404 `not_found`, que la
  herramienta traduce a `not_offered`;
- un texto que no es un UUID: la validación del esquema falla y `status: error`.

El modelo lee cualquiera de ellos como «no se pudo» y se lo cuenta al cliente como
una hora tomada. Lo mismo pasa en `reservas.find_slots` (un `staff_id` inventado da
`slots: []`, que se lee como «no hay horas»; sin `service_id` es un `ToolError`), en
`reservas.reschedule` (un `staff_id` que no hace el servicio da `slot_taken`) y en
`reservas.join_waitlist`.

## Reproduction

1. Un negocio en Servicios con «Corte» y «Lucía»; un agente con `reservas.find_slots`
   y `reservas.create`.
2. Turno 1: «¿Tienes hora el jueves para un corte con Lucía?». El modelo llama a
   `reservas.find_slots` con los ids que le dio `reservas.services` y ofrece las horas.
3. Turno 2: «A las 10». El historial del turno solo trae el texto de los mensajes y
   la nota `_tools_already_used` (herramienta, estado y hora; ni argumentos ni
   resultados, a propósito). El modelo no tiene los ids y llama a `reservas.create`
   con lo que tiene: los nombres, o ids inventados.
4. Resultado: error o rechazo, y «Ese horario ya no está disponible».

Reproducido en `apps/api/tests/integration/reservas/test_reserva_por_nombre.py`
(ver `test.md`).

## Suspected Code Paths

- `apps/worker/src/nexus_worker/runtime/pipeline.py` — `_load_history` y
  `_tools_already_used`: entre turnos solo pasa el texto; la nota no lleva argumentos
  ni resultados (decisión deliberada: no se toca).
- `apps/mcp/src/nexus_mcp/servers/reservas/schemas.py` — `FindSlotsInput`,
  `CreateInput`, `RescheduleInput` y `JoinWaitlistInput` solo aceptan ids
  (`extra="forbid"`: un `service_name` es un error de validación).
- `apps/mcp/src/nexus_mcp/servers/reservas/tools.py` — `FindSlots.run`,
  `Create.run`, `Reschedule.run` y `JoinWaitlist.run`: un id que falta o que no
  existe acaba en `ToolError` o en un rechazo que no dice qué pasó.
- `apps/api/src/nexus_api/services/reservations/core.py` — `_service` (422/404) y la
  rama de Servicios de `create_booking` (404 por persona); `move_booking` no comprueba
  que la persona haga el servicio y responde `slot_taken`.

## Root Cause Hypothesis

Las herramientas de escribir dependen de ids que solo existen en el resultado de otra
herramienta de un turno anterior, y ese resultado no llega al turno siguiente. El
modelo sí tiene lo que dijo el cliente («un corte con Lucía»), pero las herramientas no
lo aceptan, y cuando el id falla no le dicen qué hacer: devuelven un error o un código
que el modelo confunde con «ocupado».

Confianza: **alta**. Los registros de staging muestran la diferencia (1 llamada contra
4) y la prueba la reproduce.

## Proposed Remediation

**Preferred**: que las herramientas acepten también el nombre, y que un servicio o una
persona que no se resuelve sea un rechazo con las opciones, no un error.

1. `service_name` y `staff_name` opcionales en `FindSlotsInput`, `CreateInput` y
   `JoinWaitlistInput`, y `staff_name` en `RescheduleInput` (el servicio lo trae la
   reserva). Con el id, todo sigue igual; sin él, el servidor resuelve el nombre:
   - normalizado (minúsculas, sin acentos ni espacios de más): primero igual, luego un
     único prefijo, luego un único «contiene»;
   - el servicio, entre los del catálogo vivo del cliente: si gana uno que **este
     agente** ofrece (`services_for_agent`, «Atiende todos los servicios»), es ese; si
     gana uno de su hermano, `not_offered`, como hoy por id (garantía 9);
   - la persona, entre el equipo activo (no archivado): si gana una que hace el
     servicio, es esa; si no lo hace, `not_offered` (R14.4).
   El negocio sale de la RLS y la persona del turno, como siempre: ningún argumento
   nuevo los nombra.
2. Un id o nombre que no se resuelve no levanta: la salida normal con `refused`
   `unknown_service`, `unknown_staff`, `ambiguous_service` o `ambiguous_staff`, y las
   opciones válidas (`services` / `staff`, con nombre e id), para reintentar en el mismo
   turno. Un id inventado del servicio pasa a `unknown_service` (antes `not_offered`) y
   uno de la persona a `unknown_staff`. `slot_taken` sigue significando solo «la hora
   está ocupada».
3. Las descripciones de las herramientas, que es lo único que el modelo lee de ellas,
   dicen que puede pasar los nombres y que un `unknown_*`/`ambiguous_*` se arregla
   reintentando con una opción, nunca diciendo al cliente que la hora está tomada.
4. La agenda simulada (Playground y pruebas del agente) acepta los mismos nombres y da
   los mismos códigos, con la forma de verdad también en `find_slots` y
   `join_waitlist`.

**Alternative**: meter en la nota `_tools_already_used` los ids del turno anterior.
Descartada: la nota no lleva argumentos ni resultados a propósito (lo que una
herramienta devolvió no se repite como si fuera del sistema), y el modelo puede llamar
a `create` sin `find_slots` en cualquier turno.

## Test plan

- Integración nueva, `apps/api/tests/integration/reservas/test_reserva_por_nombre.py`,
  contra la base y el servidor MCP de verdad:
  - `find_slots` y `create` por nombre: exacto, con acentos y mayúsculas distintos, y
    por prefijo único;
  - el id sigue mandando sobre el nombre;
  - desconocido → `unknown_service` / `unknown_staff` con opciones y sin excepción;
  - ambiguo → `ambiguous_service` / `ambiguous_staff` con las empatadas;
  - una persona que no hace el servicio → `not_offered`;
  - `reschedule` y `join_waitlist` por nombre;
  - el turno de verdad (`process_inbound`): el turno 1 busca huecos, el turno 2 no ve
    los ids y reserva con los nombres.
- Aislamiento: un servicio del hermano por nombre es `not_offered` en `find_slots`,
  `create` y `join_waitlist` (`test_44_agent_within_client.py`), y un servicio de la
  vecina por nombre o por id es igual que uno que no existe, sin sus nombres en las
  opciones (`test_reservas_client_vs_client.py`).
- Freno (spec 056): un `refused` `unknown_service` no respalda
  (`test_booking_brake.py`).
- Agenda simulada: los mismos códigos y la forma de verdad
  (`test_booking_brake_simulation.py`).
