# Contratos de la API de la consola (`/console/*`) — spec 016

Solo lo nuevo o lo que cambia. Todo bajo `require_console_principal`; ningún
endpoint acepta `tenant_id` ni `partner_id` en el body (se resuelven del
principal y del `ref`). Errores de cliente ajeno: 404 opaco, como el resto.

## Canales

### `POST /console/clients/{ref}/channels/whatsapp/signup` — cambia la respuesta
Permiso `channels:write`. Body sin cambios (`code, waba_id, phone_number_id?, business_id?, mode`).

Respuesta 200 (campos nuevos en negrita):
```json
{ "status": "active", "channel_id": "…", "display_phone_number": "+34…", "mode": "cloud_api",
  "used_channels": 1, "max_channels": 1,
  "**client_status**": "active", "**health**": { "ready": true, "missing": [] } }
```
Errores: 409 `channel_quota` (ya existía) · **409 `number_in_use`** (el número pertenece a otro cliente; ningún cambio) · 400/502 de Meta (ya existían).

## Cupo

### `POST /console/wallet/allocations/move` — nuevo
Permiso `usage:write`.
```json
{ "from_ref": "panaderia-la-espiga", "to_ref": "clinica-boreal", "qty": 20000 }
```
Respuesta 200:
```json
{ "from": { "client_ref": "…", "cap": 30000, "remaining": 30000 },
  "to":   { "client_ref": "…", "cap": 70000, "remaining": 70000 } }
```
Errores: 422 `same_client` · 422 `insufficient_cap` (`{"cap": 30000, "qty": 40000}`) · 422 `qty` (≤ 0) · 404 opaco si un ref no es del partner. Atómico: en cualquier error ningún tope cambia. Auditoría `console.allocation.move`.

### `GET /console/clients` y `GET /console/clients/{ref}` — cambia `health`
`health.missing` puede contener `"quota"` (después de `"whatsapp"`, antes de `"activation"`). `health.ready` sigue significando agente ∧ canal ∧ activo; `quota` no lo bloquea (un cliente listo puede quedarse sin cupo).

### `GET /console/home` — cambia `incidents`
`issues` de un cliente puede contener `"out_of_quota"`.

## Modelo

### `GET /console/models` — cambia la respuesta
```json
[ { "model_id": "openai/gpt-5.6-sol", "display_name": "Sol", "relative_cost": 4, "weights": { "input": 4, "cache_read": 0.4, "output": 20 } }, … ]
```
`relative_cost` = peso de salida normalizado al menor de la lista (entero, «×N»).

### `GET /console/clients/{ref}/model` — cambia la respuesta
```json
{ "model_id": "…", "display_name": "…", "is_bound": true, "allowed": true }
```

### `PUT /console/clients/{ref}/model` — cambia el efecto
Sin cambios de body ni de códigos. Escribe auditoría `console.model.update`.

## AgendaPro

### `PUT /console/clients/{ref}/integrations/agendapro/public-url` — nuevo
Permiso `agents:write`.
```json
{ "public_url": "https://cultorbarber.site.agendapro.com/cl/sucursal" }
```
`""` o `null` desenlaza. Respuesta 200 `{ "integration": "agendapro", "public_url": "…", "updated_at": "…" }`. Errores: 422 si la URL no es `https` ni del dominio de AgendaPro. Auditoría `console.integration.agendapro_url`.

### `GET /console/clients/{ref}/connectors` — cambia el elemento de AgendaPro
`auth_kind: "public_url"` (derivado para la consola; el seed no cambia), `public_url: "…" | null`, `status: connected` cuando hay URL. `credentials_form` vacío.

## Conectores por clave

### `POST /console/clients/{ref}/connectors/{slug}/api-key` — cambia el efecto y la respuesta
Guarda la clave **y sincroniza**. Respuesta 200 = `ConnectorOut` con:
```json
{ "…": "…", "last_sync": { "status": "ok" | "error", "added": 12, "deprecated": 0, "reason": null | "auth_expired" | "provider_unavailable", "at": "…" } }
```
Si la sincronización falla, la clave queda guardada, `status` = `connected`, `last_sync.status` = `error`. Auditoría `console.connector.connect` con `{slug, sync_status}`.

### `POST /console/clients/{ref}/connectors/{slug}/sync` — sin cambios
Es el «Reintentar» de R7.3.

## Avisos

### `GET /console/notifications` — tipos nuevos
- `client.out_of_quota` — `severity: warning`, `data: { external_client_ref, remaining: 0 }`, `external_client_ref` relleno. Máximo uno por cliente y día.
- `client.model_reset` — `severity: info`, `data: { external_client_ref, from_model, to_model }`.

## Auditoría (vocabulario, migración de datos)

| Acción | ES | EN |
|---|---|---|
| `console.allocation.move` | `{actor} movió {qty} créditos de {from} a {to}` | `{actor} moved {qty} credits from {from} to {to}` |
| `console.model.update` | `{actor} cambió el modelo de {client} a {model}` | `{actor} changed {client}'s model to {model}` |
| `console.integration.agendapro_url` | `{actor} enlazó la agenda de AgendaPro de {client}` / `…desenlazó…` | `{actor} linked {client}'s AgendaPro booking page` |
| `console.connector.connect` | `{actor} conectó {connector} en {client}` | `{actor} connected {connector} on {client}` |
