# Contrato: `/admin/partners`, invitación de propietario

Todas exigen `Authorization: Bearer <NEXUS_ADMIN_TOKEN>`. Las de escritura exigen además `X-Operator-Id` con un operador habilitado.

| Falta | Respuesta |
|---|---|
| Token ausente o inválido, también una credencial de consola, de clave de partner o de dispositivo | `401` |
| `X-Operator-Id` ausente, mal formado, de nadie o de una cuenta deshabilitada | `400` |

Ninguna acepta `tenant_id` ni `partner_id` en la petición, salvo el partner de la ruta. Los cuerpos son `extra="forbid"`.

Las negativas son `{"detail": {"code": "<código>"}}`.

## Tipos

```jsonc
// OwnerInvitationResultOut
{
  "id": "uuid",
  "email": "persona@negocio.com",
  "role": "owner",
  "status": "pending",
  "expires_at": "2026-11-24T19:00:00Z",
  "created_at": "2026-11-03T19:00:00Z",
  "last_sent_at": "2026-11-03T19:00:01Z", // null si no salió
  "email_sent": true,                     // lo que dijo el proveedor
  "accept_url": "https://console…/invite/<token>" // absoluto. Solo en esta respuesta
}
```

## `POST /admin/partners` → `201`

Cuerpo: `{"name": "…", "slug": "…", "owner_email": "…"}`. `contact_email` deja de aceptarse: 422.

Respuesta: `PartnerOut` con `invitation: OwnerInvitationResultOut`.

| Código | HTTP | Cuándo |
|---|---|---|
| — | `422` | `owner_email` falta o no tiene forma de correo |
| `slug_taken` | `409` | Identificador usado |
| `address_has_own_console` | `409` | Es de una persona de otro partner o de un cliente, activa o no |

Si responde error, no queda partner, ni invitación, ni correo.

## `POST /admin/partners/{partner_id}/invitations` → `201`

Cuerpo: `{"email": "…"}`. Respuesta: `OwnerInvitationResultOut`.

| Código | HTTP | Cuándo |
|---|---|---|
| `partner_not_found` | `404` | |
| `partner_suspended` | `409` | R3.7 |
| `console_off` | `409` | R3.6 |
| `has_active_owner` | `409` | R3.4 |
| `invitation_pending` | `409` | Ya hay una de Auphere viva, a esa dirección o a otra (R3.5) |
| `already_in_team` | `409` | Es de una persona de este partner (R3.8) |
| `address_has_own_console` | `409` | R1.5 |
| `address_already_invited` | `409` | Otra invitación viva de este partner a esa dirección, que no es de Auphere |

## `POST /admin/partners/{partner_id}/invitations/{invitation_id}/resend` → `201`

Sin cuerpo útil (`{}`). Respuesta: `OwnerInvitationResultOut` de la invitación **nueva**, con otro `id`.

| Código | HTTP | Cuándo |
|---|---|---|
| `partner_not_found` | `404` | |
| `invitation_not_found` | `404` | No existe, es de otro partner o no es de Auphere. **Mismo cuerpo, byte a byte** (R7.2) |
| `invitation_accepted`, `invitation_revoked`, `invitation_expired` | `409` | R4.5. Se comprueba antes que lo siguiente |
| `has_active_owner`, `partner_suspended`, `console_off` | `409` | R4.4. No toca el enlace que hay |
| `already_in_team`, `address_has_own_console` | `409` | La dirección pasó a vivir en otro sitio: el enlace fallaría al aceptarlo (R1.5). No toca el enlace que hay |

## `POST /admin/partners/{partner_id}/invitations/{invitation_id}/revoke` → `200`

Sin cuerpo útil (`{}`). Respuesta: `{"id": "uuid", "email": "…", "status": "revoked", "changed": true}`. No envía correo (R5.6).

`changed` es lo que permite no mentir: con un `id` antiguo, porque otro operador ya reenvió, la respuesta es éxito con `changed: false`, y el panel no dice que el enlace del partner haya muerto, porque puede haber otro vivo.

| Caso | Respuesta |
|---|---|
| Viva | Pasa a `revoked` y audita |
| Ya revocada o caducada | `200` con su `status` y `changed: false`, sin cambio ni auditoría (R5.4) |
| Aceptada | `409 invitation_accepted` (R5.5) |
| No existe, de otro partner o no de Auphere | `404 invitation_not_found`, mismo cuerpo (R7.2) |
| Partner inexistente | `404 partner_not_found` |

No depende del estado del partner, de su consola ni de sus personas (R5.1).

## `GET /admin/partners/{partner_id}/members` → `200` (extendida)

```jsonc
{
  "members": [ /* como hoy */ ],
  "invitations": [                  // solo vivas (R3.9). Nunca un token ni su hash
    {
      "id": "uuid", "email": "…", "role": "owner",
      "expires_at": "…", "created_at": "…",
      "last_sent_at": null,         // nuevo
      "from_auphere": true          // nuevo: solo estas tienen acciones
    }
  ],
  "owner": {                        // nuevo
    "has_active_owner": false,
    "can_invite": true,             // R3.1
    "can_resend": false,            // R4.1, R4.4
    "block": null,                  // "suspended" | "console_off" | null
    "expired_email": null,          // R3.10, solo sin propietario activo
    "expired_at": null,
    "suggested_email": "…"          // R3.2, R3.10. Nunca se envía sola
  }
}
```

## `GET /admin/partners/{partner_id}/audit-log?limit=100` → `200` (nueva)

Filas de plataforma de este partner, de la más reciente a la más antigua. `limit` entre 1 y 200. No exige `X-Operator-Id`: es lectura, como el resto de la ficha.

```jsonc
[{ "id": "uuid", "action": "partner.owner_invited", "actor": "ana@auphere.com",
   "summary": "ana@auphere.com invitó a x@y.com como propietario de Acme.",
   "created_at": "…" }]
```

El operador sale por su correo. Una persona del partner, también por el suyo, y lo demás, como lo dice la consola.

## Consola (sin cambios de contrato)

`GET /console/invitations/{token}` y `POST …/accept` siguen iguales. Un enlace revocado o sustituido responde igual que uno inexistente (R5.3). En `/console/audit` el actor sale como «Auphere» (R6.4).
