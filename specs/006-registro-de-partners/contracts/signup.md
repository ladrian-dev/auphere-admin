# Contrato — `/console/signup/*` y `/console/auth/google/*`

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

## `GET /console/auth/google/start`

```jsonc
// petición
{ "intent": "signup" | "login", "redirect_to": "/" }

// 200
{ "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?…" }
```

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
