# Contratos — spec 024

Ningún endpoint nuevo. Tres respuestas cambian de forma y una petición
acepta un bloque más.

## 1 · `GET /console/clients/{ref}/agent/settings` — permiso `agents:read`

```json
{"version": 4, "version_status": "staged", "active_version": 3, "has_draft": true,
 "settings": {"...": "policies.console como hoy"},
 "audience": {"mode": "list",
              "numbers": [{"phone": "+56991919125", "name": "Daniel, ventas"},
                          {"phone": "+34666261967", "name": null}],
              "locked": false}}
```

`audience` se lee de la versión que se edita (borrador si hay, si no la
activa).

## 2 · `PUT /console/clients/{ref}/agent/settings` — permiso `agents:write`

```json
{"settings": {"...": "como hoy"},
 "audience": {"mode": "list",
              "numbers": [{"phone": "+56 9 9191 9125", "name": "Daniel, ventas"},
                          {"phone": "+34 666 261 967"}]}}
```

| Caso | Respuesta |
|---|---|
| ok | 200, `AgentSettingsSaved` con `audience` ya normalizada (`+56991919125`) y `draft_created` |
| `audience` ausente | 200; `admin_access` del borrador no se toca |
| teléfono que no normaliza o con menos de siete cifras | 422 `{"detail": {"code": "audience_invalid_phone", "phone": "<el que falla>"}}` |
| `mode: "list"` sin ningún número útil | 422 `{"detail": {"code": "audience_empty"}}` |
| `mode: "everyone"` en un cliente bloqueado por plantilla | 409 `{"detail": {"code": "audience_locked"}}` |
| más de 50 números | 422 (validación de esquema) |

El cambio queda en el borrador. Publicar (`POST …/agent/versions/{v}/publish`)
lo aplica; el worker lo lee en el siguiente turno.

## 3 · `GET /console/clients` y `GET /console/clients/{ref}` — permiso `clients:read`

Cada cliente gana:

```json
{"audience": {"mode": "list", "count": 5}}
```

Nulo sin versión activa. Leído de la versión activa, no del borrador.

## 4 · `GET /console/clients/{ref}/conversations` y `…/conversations/stats` — permiso `conversations:read`

Cada conversación gana `"unanswered": {"count": 3, "reason": "not_admin"}`
(nulo si cero). Las estadísticas ganan `"unanswered_messages": 3`.

## 5 · Worker (sin contrato HTTP)

Cuando el gate de solo administradores suprime la respuesta, el mensaje
entrante recién persistido queda con `skipped_reason = "not_admin"`. Nada
más cambia: sigue sin saliente, sin acuse de lectura y sin consumo.

## 6 · Lo que no cambia

`PUT /v2/partners/clients/{ref}/admins` sigue igual y escribe el mismo
`admin_access`; `GET …/admins` devuelve lo que la consola guardó, con
`role: "full"` para lo escrito desde la consola.
