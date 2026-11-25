# Contrato: API de admin de la spec 077

Todas las rutas van bajo `/admin`, con `Authorization: Bearer <admin token>`. Las que escriben exigen además `X-Operator-Id` (operador habilitado) y dejan auditoría `operator:<email>`. Los errores llevan `detail.code` (cadena cerrada) para que el panel los traduzca.

## Solo envío

`POST /admin/tenants` acepta `"send_only": bool` (por defecto `false`). `TenantOut` devuelve `send_only`.

`PATCH /admin/tenants/{id}/send-only` · cuerpo `{"send_only": bool}` → `TenantOut`.

`GET /admin/tenants/{id}/send-readiness` →
```json
{
  "channel": {"ok": true, "active_numbers": 1},
  "template": {"ok": false, "approved": 0, "pending": 1, "unknown": false},
  "membership": {"ok": false, "status": "pending"} ,
  "keys": {"ok": true, "active": 1}
}
```
`membership` es `null` si el cliente no tiene membresía. `template` cuenta solo plantillas de categoría `AUTHENTICATION`; `template.unknown` es `true` si Meta no respondió (el paso se pinta como «no se pudo comprobar»).

## Claves del cliente

`GET /admin/tenants/{id}/api-keys` → `ApiKeyOut[]` (todas las ligadas a este cliente, de cualquier partner), con `created_by` (el correo del operador que la emitió o rotó; `null` si se emitió fuera del panel).

`ApiKeyOut`: `id, partner_id, tenant_id, type, prefix_snippet, scopes, created_at, last_used_at, revoked_at, grace_expires_at, expires_at`.

`POST /admin/tenants/{id}/api-keys` · `{}` → `201 {"key": ApiKeyOut, "plaintext": "ak_live_…"}`. Scope `messages_send`, partner = el del cliente o el contenedor `auphere-direct`.

`POST /admin/tenants/{id}/api-keys/{key_id}/rotate` · `{"grace_hours": 0..336}` → `{"key": ApiKeyOut, "plaintext": "…"}`. La nueva conserva `tenant_id`.

`POST /admin/tenants/{id}/api-keys/{key_id}/revoke` → `ApiKeyOut`.

Errores: `404 key_not_found` (la clave no es de este cliente).

## Últimos envíos

`GET /admin/tenants/{id}/template-messages?limit=50` →
```json
[{"id": "…", "created_at": "…", "to_masked": "+5691***5678", "template": "tecfin_codigo",
  "status": "delivered", "failure_code": null}]
```

## Membresía

`MembershipOut`:
```json
{
  "tenant_id": "…", "payer": "stripe", "amount_cents": 4000, "pending_amount_cents": null,
  "status": "pending", "active": false, "current_period_end": null,
  "billing_email": "facturacion@…", "checkout_url": "https://checkout.stripe.com/…",
  "checkout_expires_at": "…", "last_synced_at": null, "last_failure": null,
  "partner_id": null, "partner_name": null, "has_subscription": false
}
```

`GET /admin/tenants/{id}/membership` → `MembershipOut` · `404 no_membership`.

`PUT /admin/tenants/{id}/membership` · `{"payer": "stripe"|"partner_wallet", "amount_cents": 4000, "billing_email": "…"?}` → `MembershipOut`.
- Primera vez: `pending` (Stripe) o se cobra en el acto a la bolsa (`active` o `past_due`).
- Errores: `422 no_partner` (bolsa sin partner) · `409 subscription_in_progress` (cambiar importe o quién paga con una suscripción de Stripe viva) · `422 invalid_amount` · `409 checkout_already_paid` (el enlace abierto ya se pagó sin aviso: se aplica el pago y no se cambia nada) · `503 billing_unavailable` (Stripe no pudo caducar el enlace abierto: no se guarda nada). Un cambio de importe o de quién paga, archivar y cancelar caducan antes el enlace abierto.

`POST /admin/tenants/{id}/membership/archive` → `204`. Archiva la fila (no la borra) y el cliente deja de tener membresía exigida · `409 membership_active` si está activa o tiene una suscripción viva (antes hay que cancelarla).

`POST /admin/tenants/{id}/membership/checkout` → `{"url": "…", "expires_at": "…"}`. Con una suscripción impagada, `url` es la página de su factura pendiente y `expires_at` es `null`: no se abre otra suscripción · `409 not_stripe` · `409 already_active` · `409 subscription_in_progress` (impagada sin factura abierta) · `409 checkout_already_paid` (el enlace anterior ya se pagó sin aviso: se aplica ese pago y no se abre otro) · `503 billing_unavailable`.

`POST /admin/tenants/{id}/membership/refresh` → `MembershipOut` · `409 not_stripe` · `503 billing_unavailable`.

`POST /admin/tenants/{id}/membership/charge` → `MembershipOut` (cobra ahora a la bolsa si no está activa) · `409 not_wallet`.

`POST /admin/tenants/{id}/membership/cancel` → `MembershipOut` (`canceled`).

`GET /admin/tenants/{id}/membership/charges` →
```json
[{"period_start": "…", "period_end": "…", "amount_cents": 4000, "status": "paid",
  "url": "https://invoice.stripe.com/…"}]
```
`status`: `paid`, `open`, `failed`, `void` (Stripe) o `paid` (bolsa). `url` es `null` para la bolsa.

## API pública (cambio)

`POST /v1/messages/template` acepta `"code": "482913"` (1–15 caracteres) para plantillas `AUTHENTICATION`.

Errores nuevos:
- `402 membership_inactive`
- `422 code_required`
- `422 code_not_allowed`
- `422 invalid_code`
- `422 variables_not_allowed`

Las difusiones también responden `402 membership_inactive`.

## Cambios de la revisión de seguridad (2026-11-24)

- `POST /admin/tenants` y `PUT /admin/tenants/{id}/billing` aceptan `X-Operator-Id`. Si llega, la auditoría nombra al operador, y si no es un operador habilitado, `400`. El cambio de facturación ahora queda siempre en la auditoría (`tenant.billing_updated`).
- Una rotación desde la consola de partners conserva el `tenant_id` de la clave.
