# Investigación: el informe del piloto

Todo validado contra `main` `44a43298` (el mismo código que `develop` `dc6a271d`). Las rutas son relativas a `apps/api/src/nexus_api` salvo que digan otra cosa.

## R1. De dónde sale un ciclo

- Una fila de `conversations` por contacto y número; el worker reabre la última si estaba `CLOSED` (`apps/worker/.../persistence/messages.py:116-146`, `upsert_conversation_for_customer`).
- `inbox_lifecycle.resolve` pone `CLOSED` y escribe `resolved` con el actor que resuelve; el cierre por inactividad lo hace con `system` y `{"reason": "inactivity"}` (spec 064).
- `inbox_lifecycle.reopen` escribe `reopened` con el actor que reabre. `_is_person(actor)` (hay `:` en el actor) distingue a una persona, que **deshace** la resolución (spec 064, 4.4), del contacto o un aviso, que empiezan de cero.
- `archive` («Eliminar el chat») también pasa por `resolve`.

**Decisión.** Un ciclo empieza en `conversations.created_at` o en un `reopened` cuyo actor no es una persona. Acaba en el siguiente `resolved`. Un `reopened` de persona reabre el último ciclo cerrado (le quita el final). Un `resolved` con el ciclo ya cerrado se ignora. Es una función pura sobre `(created_at, eventos ordenados)`: se prueba sin base.

## R2. Los mensajes del contacto, del agente y de una persona

- El entrante lo guarda el worker al ingerirlo (`persist_inbound_message`), antes de la agrupación de 3 s del turno. `origin` queda `NULL` (no lo rellena). La importación del historial guarda `origin = 'history_import'`.
- El saliente del agente lleva `actor_kind = 'agent'` (`persist_outbound_message`, `_ORIGIN_BY_ACTOR`). La Bandeja escribe `actor_kind = 'member'`; el panel de operador, `'operator'`; el eco de la app de WhatsApp Business, `origin = 'business_app_echo'`.
- `latency_ms` **sí** se escribe en los salientes que pasan por el despachador: `msg.latency_ms = msg.latency_ms or _ms_since(msg.created_at)` (`apps/worker/.../streams/outbound.py:855`). Es el tiempo de entrega (fila creada → proveedor la acepta), no el de respuesta.
- No hay columna `sent_at` en `messages`. `delivered_at` depende del teléfono del cliente.

**Decisión.**

| Qué | Filtro |
|---|---|
| Escribió el contacto | `direction = inbound` y `origin IS NULL OR origin = 'customer'` |
| Envió el agente | `direction = outbound`, `actor_kind = 'agent'`, `status IN (sent, delivered, read)` |
| Escribió una persona | `direction = outbound` y (`actor_kind IN (member, operator, owner)` o `origin IN (business_person, business_app_echo)`) |

El primer envío del agente es `created_at + latency_ms` (o `created_at` sin él). La primera respuesta va desde el `created_at` del primer entrante del ciclo: incluye la agrupación y no la cola del webhook al worker, que es de menos de un segundo.

El encargo proponía `turn_id` (el id del primer entrante del turno). No hace falta: las horas bastan, y valen para los mensajes de antes de la migración 0176, que no tienen `turn_id`.

## R3. Las señales de persona

| Señal | Dónde se escribe | Qué deja |
|---|---|---|
| Escalado del agente | `inbox_lifecycle.mark_waiting` | `conversation_events` `escalated`, actor `agent`, `payload.reason` = **texto libre** del modelo |
| Escalado de una puerta | `inbox_lifecycle.mark_waiting_reason` | `escalated`, actor `system`, `payload.reason` = código de `WAITING_REASONS` |
| Takeover desde la Bandeja | `api/console/lite/inbox.py:720-722` | evento `takeover` **y** auditoría `inbox.takeover` del mismo acto |
| Takeover desde el panel | `api/admin/conversations.py:225` | solo auditoría `conversation.takeover` |
| Persona que escribe | Bandeja, panel, eco de coexistencia | un saliente de persona (R2); el eco no deja evento |
| Freno de reservas | `apps/worker/.../runtime/booking_brake.record_brake` | auditoría `agent.booking_brake`, `target = conversation:<id>`, `after.outcome` ∈ `retried`, `handed_off`, `grader_fallback` |

- Un freno `handed_off` acaba en `turn_failure` con `booking_unbacked`, que el despachador convierte en `mark_waiting_reason("booking_unbacked")` (`dispatcher.py:513-526`, `879`): deja **además** un `escalated` de sistema. Es una incidencia, no dos (D6).
- La auditoría del freno es best-effort (su propia sesión) y solo en turnos de canal. El Playground no la escribe.
- La auditoría vive en `audit_log` con `tenant_id` y RLS. `target` es texto: se filtra por `action` (indexada) y por la lista de `conversation:<id>` de las conversaciones del periodo.

**Decisión.** Un ciclo es «con persona» si alguna señal cae entre su principio y su final (o ahora). Para Rendimiento y su lista, la misma regla sobre toda la vida de la fila es una expresión SQL (`EXISTS`) que sustituye a la de hoy: `handed_to_person()` la siguen importando `services/improvement/suggestions.py` y el propio archivo.

## R4. El motivo

`payload.reason` del escalado del agente puede repetir al cliente. La prueba de alcance (`tests/isolation/test_console_scope.py`) rechaza cualquier propiedad `reason` en una respuesta de `/console/*` salvo enums, y C8 prohíbe las palabras del cliente final. **Decisión**: un vocabulario cerrado, `cause`, con **los mismos códigos** que ya pinta la consola (`apps/console/src/lib/waiting-reasons.ts`, `WAITING_REASONS` de la API) más uno nuevo, `booking_brake`. Un flujo por concepto: la Bandeja, Rendimiento y el informe dicen lo mismo con las mismas palabras.

| `cause` | De dónde |
|---|---|
| `escalated` | escalado del agente, o de sistema con `reason = escalated` (un turno enrutado que acabó en escalado) |
| `booking_unbacked` | el freno pasó la conversación |
| `booking_brake` | el freno paró una respuesta y el agente la rehízo (`retried`, `grader_fallback`) |
| el código de la puerta | `no_balance`, `agent_cap`, `paused_agent`, `paused_channel`, `paused_client`, `archived_client`, `channel_problem`, `agent_unpublished`, `no_model`, `provider_failure`, `turn_limit`, `reception_loop`, `agenda_not_ready` |
| `other` | un código que este informe no conoce (futuro) |

## R5. La agenda

- `reservation_events.kind` ∈ `created`, `moved`, `cancelled`… con `actor_kind` ∈ `agent`, `person`, `system`, `customer` (`db/models/reservation.py`).
- `system` cancela al liberar las reservas sin confirmar (`automation.release_unconfirmed`, `cause = release_unconfirmed`) y crea al importar «Paso a Reservas» (`passing.py:715`, `IMPORTER`).
- `customer` cancela en dos sitios de `apps/mcp/.../servers/reservas/tools.py`: `reservas.cancel` (línea 696, la del agente: lo arregla la 080) y `reservas.confirm_attendance` con `attending = false` (líneas 753-755), que escribe **antes** `replied_no` en la misma transacción. `created_at` es `now()` de la transacción: los dos eventos llevan la misma hora.

**Decisión.** Cancelación de `customer` con un `replied_no` de la misma reserva entre 60 s antes y la misma hora → del cliente. Sin él → del agente. Tras la 080, la cancelación del agente ya es `agent` y la regla sigue dando lo mismo.

El cliente «tiene Reservas» si tiene fila en `reservation_settings` (la misma condición que `reservations.core.load_ctx`).

## R6. Los recordatorios

`reservation_outbox` nace cuando el aviso toca (`automation.request_confirmations` y los recordatorios, con `enqueue_once`), no al reservar. Su estado final se escribe al procesarlo (`mark_sent`, `mark_skipped`, o `failed` tras los reintentos), y `updated_at` es esa hora. `skipped` con `skip_reason = stale` no es un fallo: el aviso dejó de aplicar (la cita se canceló o se movió) y no deja evento.

**Decisión**: se cuentan por `updated_at` dentro del periodo, por `kind` (`reminder`, `ask_confirmation`) y estado final: enviados (`sent`), fallidos (`failed`) y omitidos (`skipped` salvo `stale`). `sent` es que el canal lo aceptó.

## R7. El gasto

`services/wallet/usage_lines.spend` es la única función de Consumo (requisito 46.7). La fila de un cliente en Consumo suma `("conversations", "client_tests")`. Abre sus propias sesiones de partner y de cliente y, al final, `reporting_transaction(reporting)`, que hace `reporting.begin()`: con la sesión de `client_scope` (ya en una transacción) fallaría. **Decisión**: se le da una sesión propia, y se le piden `conversations`, `client_tests` y `meta` del periodo exacto (de medianoche local a medianoche local, o ahora). Sus celdas van por día UTC: el informe usa solo el total.

Si la lectura falla, la respuesta lleva `spend: null` (estado parcial) y el resto del informe.

## R8. La zona horaria

`tenants.timezone` es la que escriben todos los que escriben la zona (`services/business/hours.load_hours`) y la que usan la agenda y los horarios. Un nombre inválido cae a UTC, como `reservations.core._zone`. En SQL, el día local es `timezone(<zona>, columna)::date` con el nombre validado antes por `ZoneInfo`.

## R9. Rendimiento hoy

`agent_performance` cuenta filas creadas en el periodo (no ciclos), mira el estado actual (`handed_to_person`) y agrupa en UTC (`_utc_day`, `performance.py:93-94`). `agent_conversations` da el resultado por estado actual y el motivo de `waiting_reason`. Las pruebas que lo fijan están en `tests/integration/improvement/test_suggestions.py` y siembran estado, no historial: hay que sembrar el historial.

## R10. Dónde va la página

- La consola nueva (v2) es la de todos los partners desde la migración 0204 (`console-version.ts`).
- La cabecera del cliente pinta sus pestañas desde `TABS` en `components/clients/v2/client-header-v2.tsx`, con las URL de `components/shell/routes-v2.ts`. «Anuncios» (spec 076) es una pestaña con informe y periodo.
- `nav.ts` alimenta la barra lateral, la paleta y la prueba de paridad con la app de escritorio; el design system fija la barra en cuatro entradas.

**Decisión**: pestaña «Informe» (D1).

## R11. Imprimir

- El marco v2 (`components/shell/console-shell-v2.tsx`) mide `h-svh` con `overflow-hidden` y desplaza el contenido dentro de `shell-canvas`: impreso, cortaría el informe en la primera página. Hace falta `print:` en el marco (ocultar barra lateral, cabecera y barra inferior; soltar alto y desbordamiento).
- El tema oscuro es `data-theme="dark"` en `<html>` (`tokens.css`). **Decisión**: el informe cambia a claro en `beforeprint` y lo devuelve en `afterprint`, sin tocar la preferencia guardada.
- Las barras de `BlockChart` son fondos (`bg-series-*`): sin `print-color-adjust: exact` el navegador no los imprime. Se pone en el contenedor del informe (la propiedad se hereda).
- No hay CSS de impresión en la consola hoy (solo `print:hidden` en el lanzador del Companion).

## R12. Volumen

Un cliente como Jemma tiene cientos de conversaciones al mes. Para 92 días de un cliente grande, la lectura trae, por conversación del periodo: sus eventos de resolución y reapertura, las horas de los mensajes del contacto del periodo, el último mensaje del contacto anterior al periodo, los envíos del agente y las señales de persona. Seis consultas indexadas por `conversation_id` (`ix_conversation_events_conversation`, `messages.conversation_id`) y el cálculo en Python. Objetivo: menos de 2 s para 2 000 conversaciones (CE-006).
