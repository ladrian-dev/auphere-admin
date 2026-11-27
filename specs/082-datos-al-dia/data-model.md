# Modelo de datos: datos al día en la consola

**Sin migración.** La última sigue siendo la `0243`.

## `customers.preferences` (JSONB que ya existe)

| Clave | Tipo | Quién la escribe | Para qué |
|---|---|---|---|
| `profile_name` | `str` | `upsert_customer(profile_name=…)` con cada entrante de WhatsApp que trae nombre de perfil | Saber si el perfil cambió. Se compara con el último que mandó WhatsApp, no con `name`, para no pisar un nombre que puso una persona |
| `name_by` | `"person"` | `contact_customer(by_person=True)` (alta desde Reservas con el nombre escrito) y `upsert_customer(name=…)` cuando rellena un contacto sin nombre | Si vale `"person"`, el perfil nunca cambia `name` |

Reglas (R5.5):

1. Si llega un entrante con `profile_name` distinto de `preferences.profile_name`, se guarda en `preferences.profile_name`.
2. En ese caso, si `name_by != "person"`, `name = profile_name`.
3. Un contacto nuevo sin `name` toma `profile_name` como nombre.
4. **Los contactos de antes**, sin `profile_name` guardado, comparan con su `name`. Si el perfil es distinto, gana el perfil (spec, Clarificaciones).

`customers.username` (columna, migración 0206) no cambia. Se expone en el detalle lite como `contact.username`.

## Aviso `reservations.changed`

Un hecho sin datos, en el canal `inbox:{tenant_id}`:

```json
{"event": "reservations.changed", "at": "2026-11-26T18:00:00+00:00"}
```

- **Lo emite** `core.add_event` a través de `reservations/live.mark_changed`, una vez por negocio y por transacción confirmada.
- **No sale** si la transacción se deshace, ni por lo registrado en un *savepoint* deshecho.
- **No lleva** id de reserva, nombre, teléfono ni conversación (R1.6).

## Resumen del agente (`conversation_events`)

`summary` del detalle es `payload.customer_summary` del último `escalated` de los 50 eventos más recientes, **solo si**:

- no hay un `resolved` con `created_at` posterior al de ese escalado; y
- `conversation.context_from` es nulo o no es posterior a ese escalado.

## Claves de React Query (consola)

| Clave | Qué lee | Quién la invalida |
|---|---|---|
| `["reservas","screen",urlKey]` | Lo que la página de Reservas lee para esa URL (`ReservasInitial`) | Cada escritura (`ctx.refresh`), `reservations.changed`, el regreso de la línea |
| `["reservas","booking",id]` | La ficha (`BookingDetail`) | Lo mismo, por la raíz `["reservas"]` |
| `["inbox","counts"]` | `{unread, waiting}` | `message.new`, `conversation.updated`, `message.status`, el regreso de la línea, la Bandeja abierta (`setQueryData`) |
| `["agent",ref,id,"knowledge"]` | `AgentKnowledge` del agente | Añadir, quitar, restaurar, enseñar u olvidar; el sondeo de 5 s mientras hay fuentes en `pending` |

## Preferencia del sonido (navegador)

`localStorage["nexus.inbox.sound"]`: `"off"` lo apaga, y cualquier otro valor o su ausencia lo deja encendido. Si el almacenamiento está bloqueado, queda encendido y el interruptor recuerda en memoria.
