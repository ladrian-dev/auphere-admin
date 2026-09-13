# Fase 1 — Modelo de datos: el registro de partners

Dos tablas nuevas. **Ninguna modificación a una tabla existente**, y ninguna
lleva `tenant_id` — son de plataforma e identidad, igual que `partners` y
`console_auth.principals`.

Migración: `0118_signup_and_identities` (la última aplicada en producción es
`0117_billing_events`).

---

## `public.signup_requests`

Un correo que pidió cuenta y todavía no la tiene. **Es lo único que existe antes
de verificar**, y se extingue al completarse el alta o al caducar.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `uuid` PK | |
| `email` | `varchar(255)` | Siempre en minúsculas; lo normaliza el servicio |
| `token_hash` | `char(64)` | **SHA-256 del token.** El claro se enseña una vez, en el enlace, y no se escribe en ningún registro ni traza |
| `status` | `varchar(20)` | `pending` · `consumed` · `expired` · `revoked`. `CHECK` en la base |
| `expires_at` | `timestamptz` | **24 h**, no los 21 días de una invitación — ver abajo |
| `consumed_at` | `timestamptz` NULL | |
| `provider` | `varchar(20)` NULL | `google` cuando la solicitud nace de un alta con Google; `NULL` si es por contraseña. Es la «vía de entrada» que el operador ve (R8.1) |
| `created_ip_hash` | `char(64)` NULL | SHA-256 de la IP. Para investigar abuso sin guardar la IP en claro |
| `created_at` / `updated_at` | `timestamptz` | |

**Índices**

- `uq_signup_requests_token_hash` — único sobre `token_hash`. Buscar una
  solicitud es un índice único sobre 64 caracteres, y un volcado de la tabla no
  permite completar ningún alta. Mismo patrón que `api_keys` y
  `console_auth.principal_sessions`.
- `ix_signup_requests_email_pending` — parcial sobre `lower(email)` donde
  `status = 'pending'`. Es el que hace barata la regla de «una pendiente por
  correo».

**Por qué 24 h y no 21 días.** Una invitación la manda una persona que te
conoce y puede esperar tres semanas. Una solicitud de alta la pide un
desconocido y el correo está en su bandeja ahora mismo. Cuanto más corta la
ventana, menos vale un buzón comprometido.

**Por qué no hay `partner_id`.** No puede haberlo: el partner **no existe**
hasta que alguien completa el alta. Ésa es toda la razón por la que esta tabla
es una tabla y no una columna en otra.

### Ciclo de vida

```
(nada) ──POST /console/signup──► pending
                                   │
                    ┌──────────────┼───────────────┐
                    │              │               │
            complete│      caduca  │      otra solicitud
                    ▼              ▼               ▼
                consumed        expired         revoked
```

`consumed` es terminal y **no deja partner huérfano**: el partner nace en la
misma transacción que consume la fila, o no nace ninguno.

---

## `console_auth.principal_identities`

La relación entre una cuenta de consola y el identificador estable que un
proveedor externo emite para esa persona.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | `uuid` PK | |
| `principal_id` | `uuid` | → `console_auth.principals.id`, `ON DELETE CASCADE` |
| `provider` | `varchar(20)` | `google` hoy. `CHECK` con la lista cerrada |
| `subject` | `varchar(255)` | El `sub` del proveedor. **Opaco y estable** |
| `email_at_link` | `varchar(255)` | El correo que el proveedor afirmaba al vincular. **Instantánea para auditoría, nunca para buscar** |
| `created_at` / `last_used_at` | `timestamptz` | |

**Índices**

- `uq_principal_identities_provider_subject` — único sobre `(provider, subject)`.
  Un identificador de proveedor pertenece a **una sola** cuenta.
- `ix_principal_identities_principal` — para listar los vínculos de una cuenta.

**Por qué el ancla es `subject` y no el correo.** Un correo cambia de dueño: se
libera y se reasigna, y en Workspace eso pasa cada vez que alguien se va de una
empresa. Anclar al correo haría que quien hereda una dirección herede la cuenta.
El `sub` de Google no se reasigna nunca.

`email_at_link` existe **sólo** para poder responder «¿con qué correo se vinculó
esto?» en una auditoría. Ninguna consulta del producto la usa como criterio.

**Por qué una tabla y no dos columnas en `principals`.** La spec exige que
añadir un segundo proveedor no obligue a rehacer el primero (§Fuera de alcance).
Con columnas, el segundo proveedor pide otra columna y el tercero otra.

**Qué NO guarda: ningún token de Google.** El `access_token` no se usa —el
`id_token` ya trae `sub` y `email_verified`— y no se pide `refresh_token`,
porque hoy no hay ámbito que refrescar. La columna se añadirá con la spec que
los necesite. Guardarlos ahora sería una credencial almacenada sin lector, que
es exactamente la figura de `NEXUS_WEBHOOK_HMAC_SECRET` en
`pendientes-tras-el-go-live` §5.

---

## Lo que NO cambia, y conviene decirlo

| Tabla | Por qué se queda igual |
|---|---|
| `partners` | El alta la crea con los valores que ya usa el script de siembra. No hace falta columna de «vía de entrada»: eso vive en `signup_requests.provider` y en la auditoría |
| `partner_memberships` | **Ni una columna.** El alta llega a ella por `PartnerInvitationRepository.accept()`, que es el único camino |
| `partner_invitations` | Igual. El alta emite una y la acepta en la misma transacción |
| `console_auth.principals` | Igual. El principal lo crea `accept()`, como siempre. Una cuenta creada con Google queda **sin contraseña**, que ya es un estado que el modelo admite |
| `partner_subscriptions` | **No se inserta nada.** Un partner sin fila es Free, y la ausencia es un estado válido y diseñado (`db/models/membership.py`) |

---

## Estado efímero en Redis

No es modelo de datos, pero si no se escribe aquí no está en ningún sitio.

| Clave | Contenido | TTL | Por qué no va en Postgres |
|---|---|---|---|
| `oauth:pkce:<nonce>` | El `code_verifier` de PKCE | 10 min | Es de un solo uso y de vida corta. Una tabla para esto sería basura que hay que limpiar |
| `rl:signup:email:<sha256>` | Cubo de ritmo por correo | 60 s | Igual que el del login. El correo va hasheado: una clave de Redis no es sitio para un dato personal |
| `rl:signup:ip:<sha256>` | Cubo de ritmo por IP | 60 s | Ver el aviso de abajo |

> **El cubo por IP sólo significa algo si la IP es la del cliente.** Hoy no lo
> es (research R3): detrás del BFF, la API ve la IP de Vercel para todo el
> mundo. El plan lo arregla con `X-Nexus-Client-IP`, y **hasta que eso esté, el
> cubo por IP no cuenta como contención** — se dice aquí para que nadie lo
> tache de la lista mirando el nombre de la clave.
