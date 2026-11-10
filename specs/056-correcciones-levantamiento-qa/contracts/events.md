# Contrato de eventos: spec 056

Lo que se añade a `specs/047-la-fabrica-de-agentes/contracts/events.md`. Ese archivo se actualiza en la misma tarea que lo implementa.

## §2 · Motivos de espera

| Código | Texto (es) | Texto (en) | ¿Lo libera la siguiente respuesta del agente? |
|---|---|---|---|
| `booking_unbacked` | El agente dio por hecha una cita que no existe | The agent confirmed a booking that does not exist | No |
| `out_of_audience` (ya existía, faltaba en la tabla de la consola) | Fuera de su audiencia | Outside its audience | Como hoy |

## §4 · Auditoría

| Acción | Objetivo | `after` | Quién |
|---|---|---|---|
| `agent.booking_brake` | `conversation:{id}` | `{agent_id, turn_id, outcome: "retried"\|"handed_off"\|"grader_fallback"}`, nunca el texto. Solo en turnos de canal: el Playground y las pruebas del agente dejan solo el log | `system:worker` |
| `client_access.updated`, `client_member.invited`, `client_member.resent`, `client_member.revoked` (ya existían) | el cliente | los de hoy | `operator:<correo>` o, desde ahora, `console:<correo>` |
| `correction.batch_accepted`, `correction.batch_discarded` | `correction_batch:{id}` | `{agents: [...], skipped: [...]}` | `console:<correo>` |

## §5 · Eventos de log

| Evento | Campos | Nunca |
|---|---|---|
| `booking.brake` | `tenant_id`, `conversation_id`, `turn_id`, `agent_id`, `outcome` (`retried`, `handed_off`, `grader_fallback`, `classifier_failed_closed`) | el texto, un campo llamado `result` (`test_49`) |
| `console.request_error` (consola, `instrumentation.ts`) | `digest`, `route`, `route_type`, `cause_code` | `error.message`, cabeceras, cookies |

## Avisos (push y campana)

- `agents.state` (push): enlaza a `auphere-customers://home`, no a `agents/<id>`.
- `LITE_LINKS` pierde `agent.*` y `channel.*`.
- `inbox.waiting`: gana `handled`. Un aviso atendido no cuenta en el número de la campana.
