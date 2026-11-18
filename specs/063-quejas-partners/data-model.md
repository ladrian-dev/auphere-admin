# Data model — 063

Sin tablas, columnas ni migraciones nuevas. Cambian dos objetos JSONB que ya
existen, los dos dentro de `agent_configs` (RLS por `tenant_id`), y un objeto de
respuesta.

## `agent_configs.spec.voice` (AgentSpec, «Cómo habla»)

| Campo | Tipo | Antes | Ahora |
|---|---|---|---|
| `languages` | lista de códigos, 1–5, sin repetir | Los idiomas que «habla». El primero es el principal. | Igual. El principal se usa cuando no se sabe el idioma (1.3). |
| `languages_limited` | `bool` u omitido | — | **Nuevo.** `true`: contesta solo en `languages` y, si no, en el principal. Omitido o `false`: contesta en el idioma del cliente (1.6, 1.7). |

Reglas:

- Solo lo cambia una persona. El validador rechaza que el constructor lo cambie
  (`author != "person"`, como `ai_disclosure`; requisito 1.9).
- El constructor no lo escribe nunca: `sanitize` construye `voice` con claves
  conocidas, y esta no está entre ellas.

## `agent_configs.policies.console.languages` (lo que lee el turno)

| Campo | Tipo | Antes | Ahora |
|---|---|---|---|
| `primary` | código | por defecto `es` | Copia de `voice.languages[0]`. |
| `allowed` | lista | por defecto `[primary]` | Copia de `voice.languages`. |
| `limited` | `bool` | — | **Nuevo**, por defecto `false`. Copia de `voice.languages_limited`. |

Cómo se mantiene:

- **Se escribe** en `write_spec`, cada vez que se guarda el AgentSpec en el
  borrador, y publicar lo copia a la versión (D2).
- **No se escribe** desde `PUT …/agent-settings`, que conserva lo guardado, ni desde
  el Companion.
- **Se lee como antes.** Una versión publicada antes de esta spec, sin `limited`,
  se lee sin límite.

## Resumen de canales (`ChannelDetailOut`)

| Campo | Tipo | Ahora |
|---|---|---|
| `audience_mode` | `"unset" \| "team_only" \| "everyone"` | **Nuevo**: la audiencia **efectiva**, con la regla de la tarjeta del agente (`client_overview.channel_audience`). Instagram, Messenger y un número no estricto llevan `unset` guardado y responden con la del agente publicado. |

## `BuilderUnavailable`

Es una excepción, no se persiste. Gana `detail: dict | None`, con `error`, `pos`,
`line`, `col` y `chars` cuando el motivo es `bad_json`. El trabajo guarda solo su
`error_code` (`builder_unavailable`), como hoy. El detalle va solo al registro.
