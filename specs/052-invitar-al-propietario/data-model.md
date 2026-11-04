# Modelo de datos: Invitar al propietario

## Migración `0217_owner_invitation_sent_at`

`down_revision = "0215_inbox_clear_archive_vocab"`. Una sola cabeza en este árbol.

> Encadena con `0216_out_of_balance_notice_once`, que entró en `develop` en el mismo despliegue, y `0218_test_stop_model_failed` encadena con esta.

| Cambio | Detalle |
|---|---|
| `partner_invitations.last_sent_at` | `TIMESTAMPTZ NULL`. Sin valor por defecto ni relleno: una invitación existente no consta como enviada, y es verdad |
| `console_audit_vocabulary` | Tres filas, categoría `team`: `partner.owner_invited`, `partner.owner_invitation_resent` (`info`) y `partner.owner_invitation_revoked` (`warning`) |

No escribe en ninguna otra fila ni envía nada (R3.11, Historia 4 escenario 5).

## `partner_invitations` (plataforma, sin RLS)

| Columna | Papel aquí |
|---|---|
| `partner_id` | El de la ruta. Toda consulta filtra por él (R7.1) |
| `email` | Recortado y en minúsculas |
| `role` | `owner`, sin que el operador pueda elegir otro (R1.7) |
| `invited_by` | `NULL` en las de Auphere |
| `token_hash` | SHA-256 del token. El token en claro existe solo en el correo y en la respuesta |
| `status`, `expires_at` | Ver estados |
| `last_sent_at` | **Nuevo.** Último envío que el proveedor aceptó (R2.5) |

### Estados, tal como los ve el panel

```text
                  invite / create
                        │
                        ▼
   ┌──────────── pending, expires_at > now ───────────┐   «viva»
   │                    │            │                │
 resend              revoke        accept          vence el plazo
   │                    │            │                │
   ▼                    ▼            ▼                ▼
 revoked ──► nace    revoked      accepted         caducada
 otra fila viva                                 (pending sin marcar,
                                                 o expired ya marcada)
```

«Viva» es `invitation_is_live_clause(now)`: `status = 'pending' AND expires_at > now`. Una `pending` vencida se trata como caducada en toda la pantalla y en toda acción (R3.9). `invite` la marca `expired`; lo demás no escribe.

## `partners` (plataforma, sin RLS)

Al crear desde el panel: `console_enabled = true`, `console_modules` con su valor por defecto, `contact_email` = dirección invitada, `console_v2_enabled_at` como ya hacía `born_on_new_console`.

**Regla del contacto (R1.10)**, al emitir:

| Contacto actual | Invitación sustituida | Resultado |
|---|---|---|
| Vacío | Cualquiera | Pasa a la dirección invitada, y consta en auditoría |
| Igual a la dirección de la sustituida | Última de Auphere, revocada o caducada | Pasa a la dirección invitada, y consta en auditoría |
| Cualquier otro | — | No cambia |

## `audit_log` (fila de plataforma: `tenant_id` nulo)

`actor = operator:<correo>`, `target = partner:<id>`.

| Acción | `after_json` | `before_json` | Cuándo |
|---|---|---|---|
| `partner.create` | Instantánea del partner, con `console_enabled` y `console_modules` | — | Crear (R6.2) |
| `partner.owner_invited` | `email`, `role`, y `contact_email` si cambió | `contact_email` si cambió | Crear e invitar |
| `partner.owner_invitation_resent` | `email`, `role`, y `contact_email` si cambió | `contact_email` si cambió | Reenviar |
| `partner.owner_invitation_revoked` | `email`, `role` | — | Revocar, solo si cambió algo (R5.4) |

Nunca el token ni el enlace (R6.5).

## Eventos de registro

| Evento | Lleva | No lleva |
|---|---|---|
| `email.sent` | tipo, plantilla, destinatario, asunto, `partner_id` | Variables ni enlace |
| `email.send_failed` | Lo anterior, estado y cuerpo del proveedor **sin enlaces** | Enlace |
| `email.suppressed` | Lo anterior y `links` (solo donde se retiene; producción no arranca así, spec 051) | — |
| Línea de acceso, `path` de la petición y span | La ruta con `[token]` en lugar del token | Token (`core/logging_context.safe_path`) |
| `owner_invitation.send_error` | `partner_id`, `invitation_id`, tipo de excepción | Enlace, token, texto de la excepción |
| `owner_invitation.sent_at_not_recorded` | `partner_id`, `invitation_id` | Enlace, token |
