# Contrato: eventos y registros — la agenda desde el agente

Se añaden a `specs/047-la-fabrica-de-agentes/contracts/events.md` en el mismo commit que el código.

## Motivo de traspaso `agenda_not_ready`

Cuando la agenda de un agente no está lista y el agente **no** tiene `escalate.escalate_to_human`,
el runtime traspasa la conversación por el camino del freno de citas:
`turn_failure = {"kind": "handoff", "reason": "agenda_not_ready"}`. Entra en `_ROUTER_REASONS` y
en `_SILENCES_THE_AGENT` (`dispatcher.py`), como `booking_unbacked`. La línea al cliente es la de
escalado del agente, o la de por defecto.

## Registros (structlog)

| `event` | Dónde | Campos | Cuándo |
|---|---|---|---|
| `agenda.not_ready_turn` | runner | `tenant_id`, `agent_id`, `intent`, `escalated` (bool) | Un turno de un agente con agenda y la agenda no lista |
| `agenda.ready_read_failed` | runner | `tenant_id`, `error` (tipo) | La lectura de `agenda_ready` falló; el turno sigue con las herramientas |
| `reservas.turned_on_from_agent` | api | `tenant_id`, `agent_id`, `mode` | `turn_on_from_agent` encendió el módulo |
| `builder.job` | runner | `kind="agenda_text"`, `status`, `ops`, `fallback` (bool) | Termina la propuesta |

Nunca el texto del agente ni el del cliente.

## Auditoría (`audit_log`)

| `action` | `after_json` |
|---|---|
| `client_access.updated` | `{"modules", "from_agent", "mode", "capacity_kind"}` |
| `console.agenda.update` | `{"agent_id", "enabled", "module_turned_on"}` |
