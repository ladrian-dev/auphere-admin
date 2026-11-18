# Contrato — consola (deltas de la 063)

Enmienda `specs/047-la-fabrica-de-agentes/contracts/console-api.md`.

## `GET /console/clients/{ref}/channels/overview`

Cada elemento de `channels[]` gana un campo:

| Campo | Tipo | Significado |
|---|---|---|
| `audience_mode` | `"unset" \| "team_only" \| "everyone"` | A quién responde de verdad el número (audiencia efectiva, `client_overview.channel_audience`). `unset` significa que no responde a nadie (047, 32.9). |

El resto no cambia. La consola lo usa para «No responde a nadie» (2.3).

## `GET /clients/{ref}/channels/{channelId}` (ruta de la consola, no de la API)

Ya existe. La tarjeta de Canales del cliente y el final de la conexión llevan
aquí. La ruta redirige a la configuración dentro del agente que atiende el
número según la regla del principal (`agents.principal_agent_id`, D8): el asignado; si no hay, el vivo por defecto;
y si ninguno lo es, el vivo más antiguo. Es el mismo agente que enseña el número
en su pestaña Canales. Sin agente, la ruta vuelve a la lista. Por eso la tarjeta, sin agentes, ofrece crear uno y no este
enlace (2.5).

## `POST /console/clients/{ref}/agents/draft-jobs` con `start: "template"`

| Caso | Antes | Ahora |
|---|---|---|
| El borrador de la plantilla no se puede sanear | `500 Internal Server Error` | `422` `{"code": "draft_invalid"}` |

La consola pinta «No se pudo crear desde esta plantilla», con «Probar otra
plantilla» y «Empezar en blanco», y conserva lo escrito.

## Trabajo `agent_draft` (sin cambios en la API)

`error_code` sigue siendo `builder_unavailable`. El motivo (`bad_json`, `truncated`,
`invalid_draft`, `provider_failed`, …) y su detalle sin contenido solo van al
registro `jobs.agent_draft.unavailable`.

## Estado visible del agente (requisito 2.6)

El estado `ready_no_channel` puede traer `reason: "unconfigured"` cuando el agente
tiene algún número «Sin configurar». La consola pinta entonces «Listo · número sin
configurar», y si no, «Listo · sin canal». No hay código nuevo, y los recuentos de
`agents_summary` no cambian.

