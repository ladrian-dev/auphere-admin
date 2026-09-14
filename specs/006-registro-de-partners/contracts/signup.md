# Contrato — `/console/signup/*`, `/console/auth/google/*` y `/admin/signups/*`

**Todos estos endpoints van detrás del token de servicio del BFF**
(`svc: "console"`, EdDSA, 60 s, anti-replay por `jti`), igual que
`/console/auth/*` y `/console/invitations/*`.

No es un detalle de implementación: `tests/isolation/test_console_scope.py`
exige 401 sin token en **toda** ruta registrada, y esa suite bloquea el merge.
La anonimidad del registro vive en el borde **navegador ↔ BFF**; el borde
**BFF ↔ API** nunca es anónimo (research R2).

El navegador no llama a ninguno de estos. Los llama el servidor de Next.

## Cabecera obligatoria en los tres del alta

| Cabecera | Contenido |
|---|---|
| `X-Nexus-Client-IP` | La IP del visitante, puesta por el BFF |

Si falta, la petición **no se rechaza**: se cuenta contra un cubo único y
estrecho, y se registra. Fingir que hay límite por IP sería peor que no tenerlo.

---

## `POST /console/signup`

Pide el alta. **No crea ni partner, ni cuenta, ni membresía.**

```jsonc
// petición
{ "email": "maria@agencia.com", "locale": "es" }

// 202 — SIEMPRE la misma respuesta
{ "status": "sent" }
```

**La respuesta es idéntica exista o no el correo** (R1.2, CE-004). Si existe, lo
que cambia es el correo que llega: «ya tienes cuenta, entra por aquí». Nadie
puede averiguar desde fuera si una dirección está registrada.

| Código | Cuándo |
|---|---|
| `202` | Siempre que el correo tenga forma válida, exista o no |
| `422` | El correo no tiene forma de correo |
| `429` | Límite de ritmo, con `Retry-After`. Mismo formato que el login |
| `503` | El alta autónoma está apagada por bandera |

> El `503` lo consume el BFF para **no pintar el formulario**, no para pintar un
> formulario con un error. La ausencia se diseña (constitución §V).

## `GET /console/signup/{token}`

¿Sigue viva la solicitud? Lo usa la página del enlace para decidir qué pintar.

```jsonc
// 200
{ "email": "maria@agencia.com", "provider": null, "expires_at": "2026-09-14T19:22:00Z" }
```

| Código | Cuándo |
|---|---|
| `200` | Pendiente y no caducada |
| `404` | No existe, caducada, ya usada o revocada — **los cuatro dan el mismo cuerpo**, byte a byte |

## `POST /console/signup/{token}/complete`

Nace el partner. **Una transacción o ninguna.**

```jsonc
// petición
{ "company_name": "Agencia Bonita", "password": "…", "display_name": "María" }

// 201
{ "session_token": "…", "partner_slug": "agencia-bonita", "role": "owner" }
```

`password` se omite cuando la solicitud vino con `provider: "google"`: esa cuenta
nace sin contraseña.

| Código | Cuándo |
|---|---|
| `201` | Partner, cuenta y membresía `owner` creados; sesión iniciada |
| `404` | Token muerto. Mismo cuerpo que el `404` de arriba |
| `409` | `already_member` — ese correo ya pertenece a un partner |
| `422` | Nombre de empresa vacío o contraseña que no cumple la política |

**Lo que el servidor hace en esa transacción**, en orden:

1. `partners` — con `console_enabled = true` y `status = 'active'`
2. `partner_invitations` — de `owner`, para el correo ya verificado
3. `PartnerInvitationRepository.accept()` — crea el principal si no existe, crea
   la membresía, marca la invitación
4. `signup_requests.status = 'consumed'`
5. `audit_log` — nombrando a la persona y la vía de entrada

**No se inserta nada en `partner_subscriptions`**: un partner sin fila es Free.

---

## `GET /console/auth/google/available`

```jsonc
// 200 — siempre 200, nunca 503
{ "available": true }
```

**Una pregunta, no un efecto.** La consola lo usa para decidir si pinta el
botón, y lo resuelve en el servidor al renderizar la página. Existe porque
preguntarlo con `/start` acuñaba un PKCE que nadie consumiría: cada visita a
`/login` —pública— dejaba una clave de diez minutos en Redis.

`false` cuando falta cualquiera de los tres ajustes de Google: con dos de tres
el canje fallaría con un error del proveedor que no se parece a la causa. Que
no haya Google **no es un error** — el alta con contraseña sigue funcionando
(CE-006) y la consola necesita distinguir «no hay» de «no se pudo preguntar».

## `POST /console/auth/google/start`

```jsonc
// petición
{ "intent": "signup" | "login" }

// 200
{ "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?…" }
```

**`POST` y no `GET` a propósito**: esta llamada *escribe* — acuña el par PKCE y
guarda el verificador en Redis. Un `GET` con efectos invita a que alguien lo
use como sonda, que es exactamente el fallo que costó el endpoint de arriba.

La URL lleva `state` firmado (HMAC-SHA256 sobre JSON canónico, nonce, TTL 10
min — el patrón de `services/tiktok_oauth_state.py`) y el `code_challenge` de
PKCE. El `code_verifier` se queda en Redis bajo el nonce y **no viaja al
navegador**.

## `POST /console/auth/google/callback`

```jsonc
// petición
{ "code": "4/0A…", "state": "eyJ…" }

// 200 — la persona ya tiene partner
{ "outcome": "session", "session_token": "…" }

// 200 — cuenta nueva: falta nombrar la empresa
{ "outcome": "signup_pending", "signup_token": "…" }
```

| Código | Cuándo |
|---|---|
| `200` | Vinculado o creado |
| `400` | `state` ausente, caducado, ya usado o que no casa; o `code` inválido |
| `403` | **El proveedor devolvió `email_verified: false`.** No se crea cuenta, no se vincula nada, no se concede sesión |

**Reglas que el contrato fija, no el código:**

- El vínculo se ancla a `(provider, sub)`. El correo **no es identidad**.
- Correo verificado que ya tiene cuenta → se vincula a **esa** cuenta. Nunca una
  segunda cuenta ni una segunda membresía.
- La sesión que sale por aquí es **la misma clase** que la del login con
  contraseña, y pasa por la misma revalidación de pertenencia en cada llamada.
- No se guarda ningún token del proveedor.

---

## Lo que ninguno de estos endpoints hace

- **No acepta `partner_id` ni `tenant_id`** en ninguna parte — ni ruta, ni
  query, ni cabecera, ni cuerpo. Lo comprueba `test_console_scope.py` sobre el
  OpenAPI, estructuralmente.
- **No devuelve nada que permita enumerar correos.** Ni en el cuerpo, ni en el
  código, ni en el tiempo de respuesta.
- **No escribe en ningún registro** la contraseña, el token en claro, el
  `code`, el `id_token` ni el `code_verifier`.

---

## `GET /admin/signups`

```jsonc
// 200 — de la más reciente a la más vieja
[
  {
    "id": "…",
    "email": "maria@agencia.com",
    "status": "pending" | "consumed" | "expired" | "revoked",
    "provider": "password" | "google",   // nunca null
    "created_at": "…", "expires_at": "…", "consumed_at": null,
    "partner": null | { "id": "…", "name": "…", "slug": "…", "status": "active", "tier": "free" }
  }
]
```

`partner` en `null` **es** la señal de que el registro está a medias. No es un
dato que falte: es el estado, y es lo que R8.1 pide distinguir.

## `POST /admin/signups/{id}/resend`

```jsonc
// 200 — la solicitud NUEVA (la anterior queda revocada)
{ "id": "…", "status": "pending", "partner": null, … }
```

| Código | Cuándo |
|---|---|
| `200` | Reemitida y enviada |
| `404` | No existe |
| `409` | Existe pero no está viva: consumida o caducada |
| `401` | Sin token de operador |

**409 y no 404**: aquí no hay nada que ocultar. Quien pregunta es un operador
autenticado, no un desconocido sondeando qué correos existen — que es lo que sí
obliga a `/console/signup/*` a responder siempre igual.
