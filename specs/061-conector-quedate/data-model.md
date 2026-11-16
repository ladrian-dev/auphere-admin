# Modelo de datos: Conector de Quédate

## Tabla nueva: `customer_connector_accounts` (con RLS)

El vínculo entre un cliente final de un tenant y su cuenta en un sistema externo. Para Quédate, el anfitrión que creó para esa persona la clave del cliente.

**No guarda credenciales** (enmienda del 2026-11-16): la credencial es la clave del cliente, en `tenant_credentials`.

| Columna | Tipo | Reglas |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | NOT NULL. FK a `tenants (id)` `ON DELETE CASCADE`. RLS por `app.tenant_id` |
| `customer_id` | uuid | NOT NULL. FK compuesta `(tenant_id, customer_id) → customers (tenant_id, id)` `ON DELETE CASCADE` |
| `connector_slug` | text | NOT NULL, en minúsculas (CHECK) |
| `external_user_id` | text | NOT NULL. El id del anfitrión en Quédate |
| `state` | jsonb | NOT NULL, `{}` por defecto. Para Quédate: `verification_link` (`{url, expires_at}`) |
| `needs_review` | boolean | NOT NULL, `false` por defecto. Se marca si Quédate responde 403 sobre ese anfitrión |
| `created_at`, `updated_at` | timestamptz | `now()` |

**Restricciones**: `UNIQUE (tenant_id, customer_id, connector_slug)`; `UNIQUE (tenant_id, connector_slug, external_user_id)`, un anfitrión para una sola persona del negocio (/cso del 2026-11-16); `ENABLE` y `FORCE ROW LEVEL SECURITY`; política de tenant con `USING` y `WITH CHECK`; `GRANT` a `nexus_app`.

**Ciclo de vida**

```text
(sin fila) ──register_me (201, o correo ya de la clave)──▶ vinculado ──403 sobre el anfitrión──▶ needs_review
                                                                ▲                                     │
                                                                └──── register_me (sustituye) ◀───────┘
se borra el cliente final o el tenant ──▶ (sin fila)
```

## Filas nuevas en tablas existentes

- **`connectors`**: `slug='quedate'`, Quédate, Amacrux, categoría `lodging`, `api_key`, `mcp_server_ref='internal:quedate'`, `auto_enable_on_connect=false`. Su `credentials_form` tiene dos campos:
  - `api_key`, secreto y obligatorio;
  - `environment`, no secreto y opcional (va a `endpoint_meta`).
- **`tool_catalog`**: las 27 herramientas de [contracts/tools.md](contracts/tools.md), con `requires_consent=true` y `default_mode='always'`. Ninguna es `destructive`.
- **`connector_access_defaults`**: `('quedate', enabled=false, 'Conector de Amacrux (spec 061)', 'migration:0233')`.
- **Vocabulario de auditoría**:
  - `connector.customer_account_linked`;
  - `connector.customer_account_link_failed`;
  - `connector.external_write_unconfirmed` (un anuncio o unas fotos sin respuesta).

## Auditoría

`AuditLog` con `actor='customer:{customer_id}'` y `target='connector:quedate'`. `after_json` lleva solo `customer_id` y, si aplica, la operación. Sin nombre, correo, documento, ids externos ni clave.
