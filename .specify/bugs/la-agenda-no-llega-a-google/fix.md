# Bug Fix: la agenda no llega a Google Calendar y nadie se entera

- **Slug**: la-agenda-no-llega-a-google
- **Fixed**: 2026-11-04
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Ya se puede asociar un calendario a cada persona desde Ajustes, y la pasada habla con los
nombres documentados de Composio. Mover una reserva mueve su evento, sin duplicados aunque
algo falle. Un calendario que no se puede leer deja de bloquear con datos viejos, y la
pantalla dice por qué. **Sin probar contra una cuenta de Google de verdad.**

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/api/src/nexus_api/services/reservations/calendar_sync.py` | modified | Acción y argumentos de Composio, páginas, todo el día, respuestas no reconocidas; tres partes independientes; cada escritura en su transacción; códigos de error; `connection_state`, `connection_lost`, `has_work` |
| `apps/api/src/nexus_api/services/reservations/core.py` | modified | `move_booking` marca el evento con `EVENT_MOVED` si cambia la hora o la persona |
| `apps/api/src/nexus_api/services/reservations/calendar.py` | modified | `staff_calendar_status` deriva `status` y `last_error` |
| `apps/api/src/nexus_api/services/connectors/composio_client.py` | modified | `execute_tool` llama al SDK en un hilo. Vale para todas las herramientas, no solo las de Reservas |
| `apps/api/src/nexus_api/api/console/lite/reservas_schemas.py` | modified | `CalendarStatus`: `needs_reauth`, `error`, `last_error`. `CalendarOut`: `connection`, `unavailable` |
| `apps/api/src/nexus_api/api/console/lite/reservas.py` | modified | Solo `read_calendar` |
| `apps/worker/src/nexus_worker/streams/reservation_calendar_cron.py` | modified | Conexión perdida y eventos pendientes de un calendario sin nadie asociado |
| `apps/console/src/components/reservas/settings/staff-calendars.tsx` | added | La pantalla, con los cinco estados |
| `apps/console/src/components/reservas/settings/services-settings.tsx` | modified | La monta y quita la pista «Más adelante» |
| `apps/console/src/lib/backend/reservas.ts`, `app/(console)/reservas/actions.ts`, `i18n/lanes/reservas.ts` | modified | Rutas, acciones y textos en es y en |
| `apps/console/src/components/reservas/__tests__/harness.tsx` | modified | Las dos acciones nuevas |
| `docs/reservas.md` | modified | Lo que describe |

## Decisión: el ocupado viejo

Se favorece no bloquear disponibilidad real con datos viejos. Sin conexión sana, permiso
rechazado o calendario desaparecido, el ocupado se quita en la pasada siguiente, porque no
se arregla solo. Una lectura que falla por otra causa conserva el ocupado 30 minutos
(`BUSY_STALE_AFTER`): un corte breve no libera huecos de golpe. La tabla, con lo que dice
la pantalla en cada caso, está en `docs/reservas.md`.

## Tests Added or Updated

- `apps/api/tests/integration/reservas/test_la_agenda_llega_a_google.py`: added, por punto.
- `apps/api/tests/integration/reservas/test_calendar_sync.py`: el doble acepta `tz`. El
  docstring de la prueba de R10.5 dice lo que fija y lo que no.
- `apps/console/src/components/reservas/settings/__tests__/staff-calendars.test.tsx`: added.
- `apps/console/src/app/(console)/reservas/__tests__/actions.test.ts`: las dos acciones.

## Local Verification

En `./test.md`.

## Deviations from Assessment

- **Fuera de la primera lista de archivos, con permiso del coordinador:**
  `reservas_schemas.py`, `read_calendar` y `harness.tsx`.
- **Sin enlace a donde se conecta**, que era lo pedido. La persona de un cliente no tiene
  esa pantalla y `/clients/[ref]/integrations` la devolvería a su primer módulo: la pantalla
  dice que lo pida a quien gestiona sus agentes.
- **Sin `calendar_id` en la respuesta de la persona.** El selector no preselecciona: enseña
  el nombre actual y ofrece cambiarlo.

## Follow-ups

- **Verificar en staging con una cuenta real**, antes de encenderlo para un cliente: que
  lista, crea, borra y reconoce un 404, y la forma de la respuesta.
- `services/connectors/service.py:192`: `_TOOL_SLUG_ANNOTATIONS` tiene
  `GOOGLECALENDAR_LIST_EVENTS`. El nombre documentado no está en la tabla y, si el proveedor
  no manda la marca de solo lectura, nace como destructiva y bloqueada. Sin tocar: lo edita
  otra sesión y afecta a lo que recibe el agente.
- **La app móvil** copia el contrato en `apps/mobile/src/api/{openapi.json,schema.gen.ts}`,
  sin regenerar. `api/reservas.ts:230` solo reconoce `connected`: una persona con el
  calendario en `needs_reauth` o `error` sale como «sin calendario».
- `specs/043-reservas/contracts/lite-api.md` (§3 y §8) y `data-model.md` siguen con el contrato
  antiguo: fuera de la lista de este arreglo.
- **Invitaciones rechazadas:** un evento que la persona rechazó sigue contando como ocupado.
  Google lo devuelve, y distinguirlo exige leer `attendees`, algo que R10.2 quiere evitar.
- Las demás llamadas al SDK de `composio_client.py` (`_maybe_async`) siguen en el bucle de
  eventos: no están en este camino.
- Si una reserva termina con un evento sin borrar por un fallo permanente, se deja de
  intentar a los 7 días (`REMOVAL_WINDOW`) y el evento se queda en Google.
