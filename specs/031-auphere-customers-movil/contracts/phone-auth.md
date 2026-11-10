# Contrato: entrar, renovar y salir desde el teléfono

Cubre R1, R2, R7.1, R13 y research §D1 a §D3.

## Las credenciales que guarda el teléfono

Todas las firma la API, con un secreto propio: `customers_app_token_secret`. No
es `device_token_secret`, el de las máquinas de la spec 002: comprometer uno no
abre el otro. Fuera de desarrollo, la API se niega a arrancar con el valor por
defecto (mismo patrón que `device_credential.py:53-61`).

| Credencial | Forma | Vida | Dónde se guarda | Para qué |
|---|---|---|---|---|
| **Acceso** | JWT HS256 `{svc:"customers_phone", sub:<phone_id>, gen, iat, exp, iss, aud}` | 1 h | Almacén seguro, solo la app | Cabecera `Authorization: Bearer` en `/console/lite/*` |
| **Renovación** | 32 bytes aleatorios en base64url, opacos | Mientras el teléfono se use al menos una vez cada 90 días | Almacén seguro, solo la app | `POST /app/phones/refresh` |

**Lo que se comprueba en cada petición** (`require_client_principal`, rama de
teléfono):

1. Firma, `iss`, `aud`, `exp` y que `svc` sea el esperado.
2. Lectura de `client_phones[sub]` **como identidad**, en una transacción corta
   y sin el rol `nexus_app`, igual que `resolve_client_principal` lee la
   membresía (research D3).
3. La fila existe, no está revocada (si lo está: 403 `phone_closed` con
   `reason`) y su generación es `gen` (si no: 401).
4. `resolve_client_principal(row.partner_id, row.principal_id)`: exactamente las
   mismas comprobaciones que hoy hace la BFF. Membresía activa, partner activo,
   tenant sin archivar, acceso activo y módulo.
5. Versión mínima: con `X-App-Platform` y `X-App-Version` por debajo de la
   mínima, 403 `app_update_required` (R13).

**No es reutilizable entre tipos.** Con la credencial de acceso, una ruta de
partner (`/console/*` sin `lite`) o de admin (`/admin/*`) responde 401: la
dependencia de partner rechaza `svc`.

---

## Entrar

**Enmienda del 2026-10-20** (owner): la app tiene **su propia entrada**, con
correo y contraseña o con Google. Nada pasa por la consola de partners. Se
retiran `GET /app-auth` de la consola, `POST /console/lite/phone-codes` y
`POST /app/phones`.

Las dos formas terminan igual: la API crea el teléfono (`client_phones.enroll`)
y devuelve sus credenciales. Lo que se comprueba antes es lo mismo en las dos:

1. La versión mínima (403 `app_update_required` con `minimum_version`).
2. Quién es: una persona de **cliente**. Una de partner recibe 403
   `not_a_client` (R1.5).
3. Que su membresía esté activa y el acceso del cliente encendido, con los
   módulos que sean: si no, 403 `no_access` (R1.6). Es la misma
   `resolve_client_principal` de cada petición.

**Respuesta 201**, en las dos:

```json
{"phone_id": "<uuid>", "access_token": "…", "expires_in": 3600,
 "refresh_token": "…"}
```

La app pide `GET /console/lite/me` justo después, con su credencial: una sola
ruta define la forma de `/me`.

Los errores van **en la raíz** (`{"code": "…"}`), no en `detail`, como el resto
de `/app/*`.

### `POST /app/sign-in/password`

Público. Cuerpo:

```json
{"email": "valeria@flor.test", "password": "…", "platform": "ios",
 "display_name": "iPhone de Valeria", "install_id": "<uuid>",
 "app_version": "1.0.0", "locale": "es"}
```

- La contraseña se comprueba con `console_identity.authenticate`: el mismo
  hash, el mismo bloqueo de la cuenta por intentos fallidos y la misma regla de
  contraseña que la web (R1.2).
- Límite por correo y por IP, en cubos propios (`rl:app:login:*`), con las
  mismas cifras que el login de la consola.
- **401 `invalid_credentials`**, siempre igual: correo desconocido, contraseña
  mala o cuenta bloqueada. No dice cuál.
- **429 `rate_limited`** con `Retry-After`.
- La app nunca guarda la contraseña (R1.8). Los campos llevan los tipos de
  autocompletado del sistema (`username`/`email` y `password`).

### Con Google

```
App                     Ventana del sistema                API                               Google
 │ PKCE S256 (base64url),     │                              │                                  │
 │ state                      │                              │                                  │
 │──openAuthSession(url)─────►│ GET /app/sign-in/google      │                                  │
 │                            │  ?state&code_challenge──────►│ state firmado {s, c} + PKCE      │
 │                            │                              │ propio con Google (verificador   │
 │                            │◄──302 accounts.google.com────│ en Redis, un solo uso)           │
 │                            │──elegir cuenta (select_account)────────────────────────────────►│
 │                            │◄──302 /app/sign-in/google/callback?code&state───────────────────│
 │                            │─────────────────────────────►│ canjea, verifica el id_token,    │
 │                            │                              │ comprueba el correo (abajo) y    │
 │                            │                              │ emite el código de un uso        │
 │                            │◄──302 auphere-customers://auth/callback?code&state ─────────────│
 │◄──callback(code, state)────│                              │                                  │
 │──POST /app/sign-in/google {code, code_verifier, platform, display_name, install_id, app_version, locale}─►│
 │◄──201 {phone_id, access_token, expires_in, refresh_token}───────────────────────────────────│
```

#### `GET /app/sign-in/google`

| Parámetro | Regla |
|---|---|
| `state` | Obligatorio, de 16 a 128 caracteres. Se devuelve tal cual a la app |
| `code_challenge` | Obligatorio. Base64url sin relleno, de 43 caracteres (S256) |

- El `state` y el reto de la app viajan **dentro del `state` firmado** que se
  manda a Google (`oauth_state`, 10 min). Lo que vuelve sin nuestra firma no se
  cree.
- La API usa **su propio PKCE con Google**; el verificador se queda en Redis y
  se consume una vez.
- Sin Google configurado, 302 a la app con `error=google_unavailable`. La app
  ya no enseña el botón: `GET /app/config` dice si Google está disponible.

#### `GET /app/sign-in/google/callback`

La vuelta de Google. Siempre termina en una redirección a
`auphere-customers://auth/callback` (fija, no viene de la petición), con
`code&state` o con `error&state`:

| `error` | Cuándo | Lo que pinta la app |
|---|---|---|
| `google_account_mismatch` | El correo verificado de Google **no es el de la membresía** de la persona en el cliente (también si no hay cuenta, o si la cuenta se encontró por el vínculo de Google y el correo cambió) | R1.3: «Esa cuenta de Google no es la del correo con el que Auphere te dio acceso» y la contraseña |
| `email_not_verified` | Google no respalda el correo | Lo mismo |
| `not_a_client` | La cuenta es de partner | R1.5 |
| `no_access` | Membresía o acceso apagados | R1.6 |
| `cancelled` | La persona canceló en Google (`error=access_denied`) | R1.9, sin alarma |
| `failed` | `state` caducado, manipulado o usado, o el canje con Google falló | R1.9 |

- El vínculo con Google se guarda como en la web (`resolve_provider_identity`):
  el ancla es el `sub`. **La regla nueva es la del correo:** aunque el `sub` ya
  esté vinculado, el correo verificado tiene que ser el de la membresía.
- El código de un uso es el de siempre: `session_codes` con
  `purpose=client_phone`, atado al reto de la app, de 5 minutos.

#### `POST /app/sign-in/google`

Canje del código. Público y con límite por IP.

```json
{"code": "AB12CD34", "code_verifier": "<43-128>", "platform": "ios",
 "display_name": "iPhone de Valeria", "install_id": "<uuid>",
 "app_version": "1.0.0", "locale": "es"}
```

- **422 `invalid_grant`**, siempre igual: el código no existe, caducó, se usó,
  es de otro propósito o el verificador no cuadra.
- **429 `rate_limited`**.

### `POST /app/password-reset`

`{"email": "…"}` → **202 siempre, con el mismo cuerpo** (R1.7). Es el mismo
servicio que `POST /console/auth/password-reset`: mismo límite por dirección,
sin correo si no hay cuenta, y el enlace abre la página de la web.

**Efectos:**

- Si ya había una fila activa con el mismo `install_id`, sea de quien sea y de
  cualquier cliente, se revoca con `signed_out` antes de crear la nueva: una
  sola persona por teléfono. Se hace en la transacción de identidad.
- Se audita `client_phone.signed_in`.

---

## Renovar: `POST /app/phones/refresh`

Es público y tiene límite por IP.

- **Cuerpo:** `{"refresh_token": "…", "app_version": "1.0.3"}`.
- **200:** `{"access_token", "expires_in", "refresh_token"}`. El valor anterior
  pasa a `refresh_prev_hash` y vale **60 s**.
- **Si llega el anterior dentro de esos 60 s:** se rota otra vez y se responde
  200. Cubre la doble petición de una app que se despierta. La app hace una sola
  renovación a la vez.
- **Si llega uno más viejo:** se revoca el teléfono con `refresh_reused` y se
  responde 401 `phone_closed`.
- **Si el teléfono no se usa en 90 días:** al primer intento se revoca con
  `abandoned` y se responde 401 `phone_closed`.
- **Revocado por cualquier otro motivo:** 401 `phone_closed` con `reason`.
- **Ninguna renovación crea sesión web.**

## Salir: `DELETE /console/lite/phones/current`

Lo llama el teléfono con su credencial de acceso. Responde 204.

- Revoca el teléfono con `signed_out`.
- Quita su destino de avisos.
- Audita `client_phone.signed_out`.
- La app borra su almacén seguro.

## Configuración pública: `GET /app/config`

Es público y cacheable 5 minutos.

```json
{"min_version": {"ios": "1.0.0", "android": "1.0.0"},
 "reason": null, "console_url": "https://console.auphere.com",
 "sign_in": {"google": true}}
```

`sign_in.google` es `false` mientras la API no tenga Google configurado; la app
entonces solo enseña correo y contraseña.

La app lo consulta antes de entrar y al volver al primer plano (R13.1). Para
subir la mínima basta con cambiar la configuración de la API, sin publicar una
versión de la app (R13.2).

---

## Archivos de dominio que sirve la consola — diferidos (T041)

No existen en la v1. La vuelta de Google usa el esquema propio, que PKCE y
`state` protegen, y solo después de que la persona elija su cuenta en Google.
Lo que sigue es lo que se servirá si se activa el enlace universal.

- **`/.well-known/apple-app-site-association`:** `applinks` con la ruta
  `/app/customers/*` y `webcredentials` para el App ID de la app. El Team ID es
  el de FACELAD mientras se publique ahí. Hay que cambiarlo al migrar.
- **`/.well-known/assetlinks.json`:** el paquete `com.auphere.customers` con las
  huellas SHA-256 de la firma de Play.
- **`/app/customers/auth` como página:** si se abre en un navegador sin la app
  instalada, explica que es la vuelta de la app y enlaza a las tiendas. No emite
  nada.

## Lo que **no** cambia

- La sesión web: 7 días absolutos, cookie `httpOnly`.
- El canje del escritorio (`/console/auth/session-code/redeem`) sigue con
  `purpose=desktop_session` y `hex`.
- El JWT de 60 s de la BFF y su anti-replay.
