# Contrato: la línea en vivo con Reservas (spec 082)

Amplía `specs/030-*/contracts/realtime.md` (D17) y el §8 del contrato de la app (spec 044, `contracts/app-needs.md`).

## `GET /console/lite/inbox/stream`

| | Antes | Desde la 082 |
|---|---|---|
| Quién entra | Persona de cliente con `inbox` | Persona de cliente con `inbox` **o** `reservas`. Sin ninguno de los dos, 403 |
| Canal | `inbox:{tenant de la sesión}` | Igual |
| `conversation.updated`, `message.new`, `message.status` | A todos | Solo si la persona tiene `inbox` |
| `reservations.changed` | No existía | Solo si la persona tiene `reservas` |
| `ready`, `ping` | A todos | Igual |
| Teléfono (spec 031) | Se corta a los 300 s | Igual |

Trama de `reservations.changed`:

```
event: reservations.changed
data: {"event":"reservations.changed","at":"2026-11-26T18:00:00+00:00"}
```

Sin cuerpo: la consola y la app releen por sus rutas con RLS.

## `GET /api/lite/inbox/stream` (BFF de la consola)

- Admite a la persona de cliente con `inbox` o `reservas`, y en otro caso responde 403.
- `export const maxDuration = 300`: la plataforma corta limpio y `EventSource` reconecta con un token de 60 s nuevo.

## Detalle lite de una conversación

`GET /console/lite/inbox/conversations/{id}` → `contact.username: string | null` (nuevo, opcional).

`summary` es `null` cuando la conversación se resolvió después de su último escalado o cuando ese escalado es anterior a `context_from`.
