# T061 — `/cso --diff` sobre bugs + 045 + 043

2026-10-22, modo diario (umbral 8/10), solo lectura, sobre todo lo no confirmado
contra `develop` (813e73cb). Fases 0, 1, 2, 3, 6, 7, 9, 10 y 11. Superficie:
37 rutas nuevas en `/console/lite/reservas` (18 con id, 24 escrituras), 8 rutas
cambiadas, 23 acciones de servidor, 9 herramientas `reservas.*`, 4 crons nuevos,
5 migraciones (13 tablas de cliente). Sin dependencias ni lockfiles nuevos.

Sin hallazgos críticos ni altos. Lo comprobado y limpio: RLS FORCE con `WITH
CHECK` y FK compuestas en las 13 tablas; ninguna ruta ni herramienta acepta
cliente, partner ni `ref`; 404 opaco con el id de la vecina; `as_tenant` vuelve
con `RESET ROLE` en `finally`; todo `sa.text` con parámetros; hacia Google solo
«Ocupado»; push sin nombre del cliente final; candados contra la doble reserva.

## Hallazgos y qué se hizo

| # | Sev. | Qué | Resuelto |
|---|---|---|---|
| CSO-001 | Media | `reservas.create`: el modelo elige la clave de idempotencia y no conoce el id de la conversación; dos personas con la misma clave → la segunda recibía la reserva de la primera | La herramienta guarda `agent:` + sha256(cliente + clave); `create_booking` responde 409 `idempotency_conflict` si la clave es de otra persona. Pruebas en `tests/isolation/test_reservas_customer_axis.py` |
| CSO-002 | Baja | La ruta del adjunto (`/inbox/messages/{id}/media`) no aplicaba la regla de la Bandeja de la 045, y el stream publicaba el id de los entrantes silenciados | La ruta exige `_in_inbox()` y `_shown_message()`; el despachador solo publica `message.new` de lo atendido. Pruebas en `test_lite_inbox_attended_only.py` y `test_dispatcher_attended.py` |

Del apéndice (bajo el umbral), lo que cabía en este cambio:

- El calendario de una persona tiene que ser de la cuenta conectada (422
  `unknown_calendar`).
- Lo nuestro en Google se reconoce por el id del evento guardado, no por la
  marca del texto (una invitación con `auphere:reserva:` liberaba el hueco).
- La siembra de demo exige una base local, no solo «no producción».
- Los crons no escriben en el log ni en `last_error` el texto de un error de
  SQLAlchemy (lleva teléfono y nombre): solo los tipos (`automation.error_text`).
- Un `service_id` o `staff_id` ajeno al apuntar en la lista de espera es 404, no 500.

Fuera de este cambio, para después: `notification.schedule_reminder` (herramienta
anterior, que el bug del recordatorio hace funcionar) no tiene tope de cantidad
ni de plantillas; el mismo defecto de clave de CSO-001 existe en
`booking.create_appointment`.

Esta herramienta no sustituye una auditoría de seguridad profesional.
