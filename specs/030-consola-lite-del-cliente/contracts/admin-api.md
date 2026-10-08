# Contrato: acceso del cliente en el admin

Autenticación: `Authorization: Bearer <NEXUS_ADMIN_TOKEN>` **y**
`X-Operator-Id` de la sesión del operador (ADR-034). Sin operador identificado,
400 (como la suplantación): estas acciones se auditan como `operator:<correo>`, nunca con el prefijo
del token.

## `GET /admin/tenants/{tenant_id}/client-access`

```json
{
  "eligible": true,
  "ineligible_reason": null,
  "partner": {"id": "…", "name": "Amacrux"},
  "whatsapp_connected": true,
  "enabled": true,
  "modules": ["panel", "inbox", "usage"],
  "members": [
    {"id": "…", "kind": "member", "email": "valeria@minegocio.com", "name": "Valeria Ríos", "status": "active", "since": "…"},
    {"id": "…", "kind": "invitation", "email": "luis@minegocio.com", "status": "pending", "expires_at": "…"}
  ]
}
```

`ineligible_reason`: `no_partner` (el tenant no está en `partner_tenants`) |
`archived`. `status` de una persona: `active` | `revoked`; de una invitación:
`pending` | `expired` | `revoked`.

## `PUT /admin/tenants/{tenant_id}/client-access`

```json
{"enabled": true, "modules": ["panel", "usage"]}
```

422 `no_modules` (activo sin módulos) · 422 `inbox_requires_whatsapp` · 409
`no_partner`. Apagar el acceso cierra las sesiones de todas sus personas.

## `POST /admin/tenants/{tenant_id}/client-members`

```json
{"email": "valeria@minegocio.com", "name": "Valeria Ríos"}
```

201 con la invitación; envía el correo. 409 `account_is_partner_member` · 409
`account_is_other_client` · 409 `already_member` · 409 `access_disabled`.

## `POST /admin/tenants/{tenant_id}/client-members/{id}/resend`

Revoca la invitación viva y emite otra (nuevo enlace). 409 si `{id}` es una
persona activa.

## `POST /admin/tenants/{tenant_id}/client-members/{id}/revoke`

Invitación → `revoked`. Persona → `revoked` y cierre de sesiones. Idempotente.
