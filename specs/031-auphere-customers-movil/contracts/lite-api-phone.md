# Contrato: la API lite vista desde el teléfono

Las rutas son las de la spec 030
([lite-api.md](../../030-consola-lite-del-cliente/contracts/lite-api.md)), sin
copia aquí. Este documento solo dice qué cambia para que un teléfono las use.
Cubre R3 a R6, R12 y R14.

## Autenticación

- **Toda ruta `/console/lite/*` acepta las dos credenciales:** el JWT de 60 s de
  la BFF, igual que hoy, y la credencial de acceso del teléfono
  ([phone-auth.md](phone-auth.md)). Las dos se resuelven al **mismo**
  `ClientPrincipal`, así que la autorización por módulo, la RLS y los 403 y 404
  no cambian.
- **Cabeceras del teléfono en cada petición:** `X-App-Platform` (`ios` |
  `android`) y `X-App-Version` (semver). Sin ellas, la credencial de teléfono
  responde 400.
- **Solo las acepta la credencial de teléfono:** `/console/lite/phones/current*`.
  La BFF recibe 403.
- **Solo las acepta la BFF:** `/console/lite/phone-codes`. El teléfono recibe
  403.

## `GET /console/lite/me`: lo que cambia

Hay un campo nuevo, **`nav`**: los módulos del cliente ya ordenados. Es la
**única** fuente del orden para la web y para la app (R3.2).

```json
{"user": {…}, "client": {"name": "…", "modules": ["panel","inbox","usage"]},
 "nav": ["panel", "inbox", "usage"],
 "balance_contact": {…}, "agents": […], "channels": […]}
```

- **De dónde sale:** `ClientAccess.ordered_modules()`, la tupla que ya existe en
  la API.
- **En la consola:** `liteNav()` deja de tener su `ORDER` y pinta `nav` tal cual.
  `CLIENT_MODULES` se queda solo para validar.
- **En la app:**
  - Pinta las pestañas en el orden de `nav`.
  - **Ignora los módulos que no conoce** (R3.6).
  - Con un solo módulo conocido, no pinta barra (R3.4).
  - Sin ninguno, aplica R1.5.
- **Cuándo se refresca:** cada vez que la app vuelve al primer plano y cuando
  cualquier respuesta trae un 403 de módulo (R3.3 y R3.5).

## Envío idempotente

`POST /console/lite/inbox/conversations/{id}/messages` y `POST …/attachments`
aceptan la cabecera **`Idempotency-Key`**: un UUID v4, uno por mensaje que la
persona compone. La app lo crea al pulsar «Enviar» y lo **reutiliza en cada
reintento** de ese mensaje.

| Caso | Respuesta |
|---|---|
| Primera vez | 201 con `SentOut`, como hoy. Se guarda en `messages.idempotency_key` |
| La misma clave otra vez, mensaje no fallido | **200** con el **mismo** `SentOut`, sin enviar nada |
| La misma clave, mensaje `failed` | Se vuelve a intentar sobre la **misma** fila y responde 200 (el precedente es `direct_messages.py:164-184`) |
| Dos peticiones a la vez con la misma clave | La segunda captura la violación de unicidad y responde como un replay. Nunca 500 |
| Clave de más de 80 caracteres o que no es UUID | 400 |

- **Sin cabecera:** igual que hoy. La web puede seguir sin ella, aunque se le
  añade por coherencia.
- **El orden de las comprobaciones.** El replay de un envío que ya existe y no
  falló va **primero**: no envía nada, así que responde 200 con el original
  aunque la ventana de 24 h se haya cerrado o la persona haya perdido el control
  después. Si el envío anterior falló, el reintento sí envía, así que se
  comprueban antes las precondiciones (`not_assigned_to_you`, `window_closed`,
  `channel_disconnected`).
- **La misma clave en otra conversación** es un error de la app: 422
  `idempotency_key_reused`, y no se envía nada.

## Tiempo real

- `GET /console/lite/inbox/stream` acepta la credencial del teléfono. Los eventos
  son los de
  [realtime.md](../../030-consola-lite-del-cliente/contracts/realtime.md).
- **La app abre la SSE solo en primer plano**, la cierra al pasar a segundo plano
  y, al volver, pide de nuevo la lista y el hilo abierto antes de dejar actuar
  (R5.4 y R5.5).
- Con la línea caída, la Bandeja pinta «Reconectando…», como la web.

## Medios

- **Leer:** `GET /console/lite/inbox/messages/{id}/media` con la credencial en la
  cabecera. La app nunca recibe un enlace de almacenamiento.
- **Subir:** `POST …/attachments` en multipart, con los límites de hoy (JPEG y
  PNG hasta 5 MB, PDF hasta 16 MB). La app comprueba tipo y tamaño **antes** de
  subir y dice el límite.

## Teléfonos (R7.3 a R7.5)

| Ruta | Quién | Qué |
|---|---|---|
| `GET /console/lite/phones` | Las dos credenciales | Los teléfonos activos de **la persona que pide**: `[{id, display_name, platform, app_version, last_seen_at, enrolled_at, current}]`. `current` es `true` para el que llama |
| `DELETE /console/lite/phones/{id}` | Las dos credenciales | Cierra un teléfono **de la persona que pide** (`closed_by_person`). El de otra persona da 404 opaco |
| `PUT /console/lite/phones/current/push` | Teléfono | `{provider, token, apns_environment?}`. Registra o cambia el destino de avisos de este teléfono |
| `PUT /console/lite/phones/current/notices` | Teléfono | `{"kinds": ["inbox.waiting", …]}`. Los interruptores de R11.2 |
| `DELETE /console/lite/phones/current` | Teléfono | Salir ([phone-auth.md](phone-auth.md)) |
| `POST /console/lite/account/deletion-request` | Las dos credenciales | 202. Audita `client_account.deletion_requested` y envía un correo a Auphere (R11.4). Repetirla en 24 h no envía otro correo |

En la consola web, la lista vive en una página de cuenta nueva para la persona
de cliente: `/account/phones`.

## Admin

Se protege con `require_admin_token` y exige `X-Operator-Id`, el patrón de
`api/admin/client_access.py`.

| Ruta | Qué |
|---|---|
| `GET /admin/tenants/{id}/client-members/{member_id}/phones` | Los teléfonos activos y revocados de esa persona |
| `DELETE /admin/tenants/{id}/client-members/{member_id}/phones/{phone_id}` | Cierra el teléfono (`closed_by_auphere`) y lo audita con `operator:<correo>` |

En el admin se pintan dentro de `members-list.tsx`, en la pestaña «Acceso».

## Revocaciones que ya existen y ahora también cierran teléfonos

| Disparador | Dónde | Motivo |
|---|---|---|
| Se apaga el acceso del cliente | `client_access.set_access` → `_end_sessions` | `access_disabled` (todos los teléfonos del cliente) |
| Se quita a una persona | `client_access.revoke` | `member_removed` |
| Se restablece la contraseña | `principal_access.revoke_all_access` | `password_reset` |

Quitar un **módulo** no cierra nada: la pestaña desaparece (R3.3).
