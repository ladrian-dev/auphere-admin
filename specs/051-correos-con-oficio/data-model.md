# Modelo de datos: Correos con oficio

**Sin tablas ni migraciones.** Lo que esta spec añade son estructuras en memoria y la forma de tres eventos de registro.

## `EmailKind`

`StrEnum` con un miembro por tipo de `contracts/catalogo.md`:

`team_invite` · `client_invite` · `signup_link` · `signup_existing` · `password_reset` · `password_changed` · `receipt` · `charge_confirm` · `client_out_of_quota` · `wallet_low` · `wallet_empty` · `usage_cap_threshold` · `usage_cap_reached` · `inbox_waiting` · `client_balance_low` · `client_balance_out` · `conversation_escalated` · `partner_notice` · `client_notice` · `internal_alert`

## `EmailSpec`

| Campo | Tipo | Regla |
|---|---|---|
| `aliases` | `Mapping[str, str]` | `es` y `en` en todos los tipos externos; `internal_alert`, solo `es`. Formato `auphere-<plantilla>-<idioma>`; únicos en todo el catálogo |
| `sender` | `"billing" \| "notifications"` | `billing` solo en `receipt` y `charge_confirm` (R5.2) |
| `variables` | `frozenset[str]` | Claves `[A-Z0-9_]{1,50}`, ≤ 50, sin las reservadas de Resend (`FIRST_NAME`, `LAST_NAME`, `EMAIL`, `UNSUBSCRIBE_URL`) |
| `link_variables` | `frozenset[str]` | Subconjunto de `variables`. Son las únicas que `email.suppressed` escribe |
| `owner` | `"partner" \| "client" \| "none"` | Decide qué negocio exige la prueba de barrido de aislamiento |
| `links_allowed` | `bool` | `False` solo en `password_changed`: ni `link_variables` ni enlaces en la plantilla salvo `mailto:` |
| `access` | `bool` | `True` solo en los seis correos de acceso: `signup_link`, `signup_existing`, `team_invite`, `client_invite`, `password_reset`, `password_changed`. Son los que salen en modo `access` (staging) |

## `EmailLines`

Subtipo de `str` que devuelve `lines_variable`. Marca un valor **ya escapado** y unido con `<br>`, para que `send_template` no lo escape dos veces. Es la única forma de que un `<` llegue sin escapar a Resend.

## Modo de entrega

| Ajuste | Valores | Resolución |
|---|---|---|
| `email_delivery` (`NEXUS_EMAIL_DELIVERY`) | `auto` · `resend` · `access` · `log` | `auto` → `resend` en producción, `access` en staging, `log` en el resto |

Producción con `log` o `access` → los ajustes no se validan y el proceso no arranca.

## Eventos de registro

Comunes a los tres: `kind`, `template` (alias), `to` (lista), `subject`, `owner`, y `partner_id` y/o `client_ref` cuando existen.

| Evento | Nivel | Cuándo | Además |
|---|---|---|---|
| `email.suppressed` | `info` | modo `log` | `links`: `{VARIABLE: url}`, solo las de `link_variables` |
| `email.sent` | `info` | modo `resend`, 2xx | `message_id` de Resend. **Sin** `links` (R1.5) |
| `email.send_failed` | `error` | modo `resend`, estado ≥ 300 o error de red | `status` y `body` (500 caracteres) o `error` |
| `email.variables_mismatch` | `error` | variables distintas de la ficha | `missing` y `unexpected` |
| `email.not_configured` | `warning` | modo `resend` sin clave real | — |
| `email.notice_without_copy` | `warning` | un aviso sin fila de texto | `notice_kind` |
| `email.delivery_mode` | `info` (staging + `resend`: `warning`) | arranque de la API y del worker | `mode`, `environment` |
