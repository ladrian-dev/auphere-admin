# Modelo de datos

Ninguna tabla nueva. Un índice cambia de forma y una clave más en un JSON que
ya existe.

## `channels` · la unicidad del número

| Antes | Después |
|---|---|
| `UNIQUE (type, provider_identifier)` — restricción `uq_channels_type_provider_id` | `UNIQUE INDEX (type, provider_identifier) WHERE status <> 'disconnected'` — índice `uq_channels_live_number` |

**Migración** `0132_channel_number_unique_when_live`. La bajada recrea la
restricción vieja y **falla a propósito** si hay dos filas con el mismo número
(una viva y una desvinculada): mejor un `downgrade` que se niega que uno que
borra.

**RLS**: sin cambio. La política de `channels` sigue siendo por `tenant_id`.

## `channels.config` · lo que queda pendiente en Meta

Clave nueva, opcional:

```json
{ "unlink_pending": ["deregister", "unsubscribe"] }
```

- Solo existe en canales `disconnected`.
- Cada paso desaparece de la lista al terminar; la lista vacía se retira.
- Es lo que la tarjeta lee para decir «queda pendiente en Meta» y ofrecer
  reintentar (R3.2).

**Por qué en `config` y no en columna**: es transitorio, es por canal, y
`config` ya guarda los ids de Meta de ese canal. Una columna sería
formalizar un estado que en el caso bueno no existe.

## Credenciales

Sin cambio de esquema. Cambia **cuándo se borran**:

| Credencial | Se borra cuando |
|---|---|
| `channels.config_encrypted` (por canal) | termina el `deregister` de ese canal |
| `tenant_credentials` (respaldo del tenant) | termina el `unsubscribe`, que solo ocurre con el último número vivo de esa WABA |

## Lo que devuelve la API

`ChannelDetailOut` gana:

- `unlink_pending: list[str]` — vacío en el caso bueno.

Y el 409 del alta gana un código:

- `number_held_by_previous_owner` — Meta retiene el número en otra cuenta.
