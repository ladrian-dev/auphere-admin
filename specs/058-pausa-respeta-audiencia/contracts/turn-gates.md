# Contrato: el orden de las puertas del turno (spec 058)

Sustituye, para la audiencia, la tabla de puertas de
`apps/worker/src/nexus_worker/runtime/dispatcher.py` (docstring del módulo) y
completa `specs/047-la-fabrica-de-agentes/contracts/events.md` §2.

## Orden

La primera que cierra gana. Lo nuevo es la fila 0.

| # | Puerta | `skipped` | Motivo (`waiting_reason`) | Bandeja y avisos |
|---|---|---|---|---|
| **0** | **fuera de la audiencia, en un número que no es solo de envío** | `not_admin` | `out_of_audience` | **No** |
| 1 | cliente en pausa / archivado / en alta | `tenant_inactive` | `paused_client` / `archived_client` / `agent_unpublished` | Sí |
| 2 | canal en pausa | `channel_paused` | `paused_channel` | Sí |
| 3 | canal desconectado | `channel_problem` | `channel_problem` | Sí |
| 4 | número solo de envío | `send_only_channel` | — | No |
| 5 | sin versión publicada | `agent_unpublished` / `no_agent` | `agent_unpublished` | Sí |
| 6 | agente en pausa | `agent_paused` | según su motivo de pausa | Sí |
| 7 | una persona tomó el control | `human_takeover` | `human_takeover` | No (la lleva una persona) |
| — | bolsa vacía, sin modelo, presupuesto | (después, `money_and_model_gate`) | `no_balance`, `no_model`, `turn_limit` | Sí |

La comprobación de audiencia que iba detrás del agente en pausa **se quita**:
con la fila 0 delante, solo podría llegarle un número solo de envío, y a ese ya
lo ha parado la fila 4.

## Un entrante fuera de la audiencia en una conversación que espera

| Estado de la conversación | Resultado |
|---|---|
| `escalated`, motivo de puerta (`GATE_REASONS`), sin asignar | `open`, `waiting_reason = out_of_audience`, evento `released` `{"why": "out_of_audience", "reason": …}`, su aviso `inbox.waiting` pasa a atendido, se publica `conversation.updated` |
| `escalated`, motivo que no es de puerta | sin cambios (motivo incluido) |
| `escalated`, asignada a una persona | sin cambios (motivo incluido) |
| `open` | `waiting_reason = out_of_audience`, como hoy |

## Logs

| Evento | Dónde | Campos |
|---|---|---|
| `pipeline.skipped.not_admin` | runner | los de hoy. Ahora aparece también con el cliente, el canal o el agente en pausa |
| `inbox.audience_cleanup.tenant` | donde se lance el guion | `tenant_id`, `apply`, `released` o `would_release`, `skipped_not_strict` |
| `inbox.audience_cleanup.tenant_failed` | ídem | `tenant_id`, `error` (tipo de excepción, sin datos) |
| `inbox.audience_cleanup.done` | ídem | `apply`, `tenants`, `released` o `would_release`, `failed` |

Ningún log lleva teléfono, nombre del contacto ni texto del mensaje.

## El guion

```
uv run --directory apps/api python scripts/release_out_of_audience_waits.py           # en seco
uv run --directory apps/api python scripts/release_out_of_audience_waits.py --apply   # de verdad
```

Sale con 0 aunque falle un cliente: ese cliente se revierte solo y queda en el
log. Sale con 1 solo si revienta fuera de un cliente.
