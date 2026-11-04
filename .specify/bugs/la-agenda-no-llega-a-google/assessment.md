# Bug Assessment: la agenda no llega a Google Calendar y nadie se entera

- **Slug**: la-agenda-no-llega-a-google
- **Created**: 2026-11-04
- **Source**: auditoría de un compañero sobre la spec 043 (R10) y logs de staging
- **Verdict**: valid
- **Severity**: high — R10 promete una sincronización que nunca ha corrido para nadie

## Report (summarized)

`reservation-calendar-cron` arrancó 48 veces en 7 días en staging, con cero
`.tenant` y cero fallos: nada está asociado porque ninguna pantalla deja asociar un
calendario. Además, el camino que no ha corrido tiene seis defectos.

## Symptom

Nadie puede asociar un calendario. Si pudiera, Google quedaría desfasado de la agenda:
una reserva movida sigue bloqueando su hora antigua, los «Ocupado» se repiten cada dos
minutos, y un calendario que deja de sincronizarse sigue bloqueando huecos sin que
nadie lo sepa. Lo esperado es R10: asociar, leer el ocupado, escribir las reservas y
moverlas o borrarlas con ellas.

## Reproduction

Con el doble de la puerta, antes del arreglo: 31 de 36 pruebas de
`test_la_agenda_llega_a_google.py` en rojo. Las pruebas de la pantalla, 19 de 19.
No se ha reproducido con una cuenta de Google de verdad.

## Comprobación de cada hallazgo

| # | Hallazgo | Veredicto | Evidencia |
|---|---|---|---|
| 1 | El nombre de la acción de listar | **Confirmado contra la documentación, no contra el proveedor** | `docs.composio.dev/toolkits/googlecalendar` (2026-11-04) tiene `GOOGLECALENDAR_EVENTS_LIST`, con `calendarId`, `timeMin`, `timeMax`, `singleEvents`, `pageToken`; `GOOGLECALENDAR_LIST_EVENTS` no aparece. `toolkits.py` no lista Google Calendar: `sync_tools_for` guarda lo que el proveedor devuelva. El nombre viejo solo está en dobles de prueba y en `service.py:192` |
| 1 | Una lectura fallida se salta las escrituras | Confirmado | El `continue` de `calendar_sync.py:207` |
| 2 | Mover no mueve el evento | Confirmado | `move_booking` no toca `external_event_id` y solo se escriben los nulos. Prueba en rojo |
| 3 | «Ocupado» duplicados | Confirmado | Crear y borrar sin `try`, en una transacción por cliente: un fallo se lleva los ids de lo ya creado |
| 4 | Fallos silenciosos | Confirmado | `last_error` sin registro ni pantalla, `status` fijo en `connected`, y `needs_reauth` sale sin tocar el ocupado |
| 5 | Todo el día y páginas | Confirmado | Solo se leía `dateTime`, sin `pageToken` |
| 5 | El SDK para el bucle de eventos | Confirmado | `tools.execute` es síncrono (`composio/core/models/tools.py:653`) y `_maybe_async` lo llama en el bucle |
| 6 | Sin pantalla | Confirmado, con un matiz | Las rutas existen y nadie las llama. **El matiz:** no se puede enlazar a donde se conecta, porque la persona de un cliente no tiene esa pantalla; `/clients/[ref]/integrations` es solo del partner |

## Encontrado además, al confirmar los argumentos

- `send_updates: False`: la acción pide un texto (`all`, `externalOnly`, `none`).
- `start_datetime` iba con desfase: la acción lo pide sin él, con `timezone` aparte.
- Una respuesta sin `items` se leía como calendario vacío, y borraba el ocupado de verdad.
- Un evento de duración cero viola `ck_reservation_busy_span` y tumba la pasada entera.
- Crear sin id en la respuesta guardaba `""`: el evento quedaba suelto.
- Una reserva movida a otra persona: su evento pasaba a contar como ocupado ajeno de la
  primera, y se buscaba en el calendario de la segunda.
- Cambiar o soltar un calendario dejaba los eventos en el antiguo para siempre.
- Se ofrecían calendarios de solo lectura: cada escritura fallaría siempre.
- `last_error` guardaba el texto crudo del proveedor.
- `read_calendar` pintaba un proveedor caído como una cuenta sin calendarios.

## Root Cause Hypothesis

Confianza alta. Sin pantalla el código no corrió nunca fuera de las pruebas, y las
pruebas usan un doble de la puerta: nada contrasta los nombres con el proveedor, y el
caso de mover no estaba cubierto. `docs/reservas.md` ya pedía verificarlo en staging.

## Proposed Remediation

**Preferred**: los seis puntos en orden, sin migración. `external_event_id` guarda
`<calendario> <evento>` y un prefijo `moved `. Cada escritura se apunta en su propia
transacción. Con datos viejos no se bloquea.

**Alternatives**:

- Columnas nuevas en `reservations` para el calendario y «pendiente»: más limpio de
  leer, pero una migración en un árbol con otras en curso, por dos valores que siempre
  van juntos con el id. Se descarta por ahora; pasar a columnas es una migración de datos
  sencilla si hace falta consultarlas.
- Parchear el evento en vez de borrarlo y crearlo: no sirve si cambia de calendario, y
  serían dos caminos. Borrar y crear es uno.
- Comparar las horas con la lectura de Google para detectar el cambio: haría depender
  las escrituras de la lectura, justo lo que este bug separa.
- Mantener el ocupado viejo hasta que vuelva la conexión: protege de una reserva doble
  a cambio de cerrar huecos reales sin aviso. Decidido lo contrario, y la pantalla lo dice.

**Files likely to change**: `services/reservations/{calendar_sync,calendar,core}.py`,
`services/connectors/composio_client.py`, `api/console/lite/{reservas,reservas_schemas}.py`,
`streams/reservation_calendar_cron.py`, `apps/console` (`settings/`, acciones, cliente,
textos, arnés), `docs/reservas.md`.

**Tests to add or update**: `test_la_agenda_llega_a_google.py`, el doble de
`test_calendar_sync.py`, `staff-calendars.test.tsx`, `actions.test.ts`.

## Risks & Considerations

- **Garantía 1 (RLS).** Las escrituras van en una segunda sesión, con
  `tenant_scoped_session`, y varias sentencias no filtran por cliente porque lo hace la
  RLS. No la debilita. Ningún dato de cliente entra desde quien llama.
- **Garantía 6 (logs).** Los registros nuevos llevan `tenant_id`.
- Las dos primeras: `test_a_client_only_touches_what_is_its_own` y el barrido de
  `tests/isolation/test_reservas_client_vs_client.py`.
- Liberar el ocupado puede ofrecer un hueco que en Google está tomado. Se elige a
  conciencia, y sale como choque en cuanto vuelve la lectura.
- La pasada sigue reteniendo una conexión a la base durante las llamadas a Google, como
  antes, y ahora usa una segunda para cada escritura. El pool es de 10 + 20.

## Open Questions

- **R10.5 frente a `booking_skills.py`, para Luis.** La prueba de
  `test_calendar_sync.py:202` pasa, pero solo fija el modo con el que nace la herramienta:
  conectar la cuenta pone `GOOGLECALENDAR_CREATE_EVENT` en el borrador del agente (owner,
  2026-11-03), y R10.5 dice que deben seguir bloqueadas. Qué calendario usa un agente para
  reservar es la decisión pendiente; este bug no la toca.
- ¿Debe poder conectar Google Calendar la persona del cliente? Hoy tiene que pedírselo a
  quien gestiona sus agentes, y es lo que dice la pantalla.
