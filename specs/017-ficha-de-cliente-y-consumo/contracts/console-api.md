# Contratos de la API de la consola (`/console/*`) — spec 017

Solo lo nuevo o lo que cambia. Todo bajo `require_console_principal`; ningún
endpoint acepta `tenant_id` ni `partner_id` en el body (se resuelven del
principal y del `ref`). Cliente ajeno: 404 opaco, como el resto. Todos los
endpoints nuevos entran en la barrida de `tests/isolation/test_console_scope.py`.

## Ficha y lista

### `GET /console/clients/{ref}` — amplía la respuesta
Permiso `clients:read`. Campos nuevos en negrita:
```json
{ "external_client_ref": "…", "name": "…", "status": "active", "timezone": "…",
  "**sector**": "bakery" | null,
  "**setup**": { "agent": true, "channel": false, "quota": true, "active": true, "next": "channel" },
  "**quota**": { "cap": 5000, "remaining": 3800 } | null,
  "health": { … sin cambios … }, "out_of_quota": false }
```

### `GET /console/clients` — amplía cada fila
Permiso `clients:read`. Cada `items[]` gana `setup` (sin `next`), `quota` y
`conversations_7d`. Coste: tres consultas agrupadas por página, nunca por fila.

## Agente: borrador por pantalla

### `GET /console/clients/{ref}/agent` — amplía
Permiso `agents:read`. Gana `draft_screens: ["settings", "capabilities"]`
(vacío sin borrador).

### `GET /console/clients/{ref}/agent/draft-diff` — nuevo
Permiso `agents:read`. 404 `no_draft` si no hay borrador. Respuesta: `DraftDiffOut`
(ver `data-model.md`). Claves de campo estables; la consola traduce.

### `POST /console/clients/{ref}/agent/versions/{version}/publish` — sin cambios
La barra de borrador lo llama con la misma confirmación y auditoría
(`console.agent.publish`). El `after_json` gana `from: "draft_bar" | "agent_tab"`.

## Capacidades

### `GET /console/clients/{ref}/capabilities` — nuevo
Permiso `agents:read`. Query: `all=true` (incluye otros sectores), `q=` (busca
en nombre de negocio y descripción del idioma del principal).
```json
{ "sector": "bakery", "has_draft": true, "version": 4, "active_version": 3,
  "hidden_by_sector": 31,
  "groups": [ { "function": "orders", "items": [ CapabilityOut… ] }, … ] }
```

### `PUT /console/clients/{ref}/capabilities` — nuevo
Permiso `agents:write`. Body `{ "key": "woo.list_orders", "kind": "tool", "enabled": true }`
o `{ "key": "…", "kind": "tool", "mode": "never" }`. Un cambio por llamada.
Respuesta 200: `{ "item": CapabilityOut, "draft_created": bool, "version": 4 }`.
Errores: 422 `mode_not_supported` (`needs_approval`), 422 `unknown_capability`,
409 `connector_required` (activar algo cuya integración no está conectada:
**no** se activa; la consola ya lo impide, el servidor lo garantiza).
Auditoría `console.capability.update` con `key, kind, enabled|mode`.

### `GET /console/clients/{ref}/tools` y `…/skills` — se conservan
Los siguen usando el Companion y el panel de operador. `PUT …/tools` deja de
aceptar `needs_approval` en `mode` (422), igual que capacidades.

## Consumo

### `GET /console/wallet` — amplía
Gana `equivalence` (ver `data-model.md`). `GET /console/wallet/allocations`
gana `client_name` y `consumed` por fila.

### `GET /console/usage/alerts`, `PUT` — sin cambios
Se consumen desde el panel plegable de Saldo. La página `/usage/alerts`
redirige a `/usage#alerts`.

## Auditoría, notificaciones, facturación, playground

### `GET /console/audit?category=` — amplía
`category` opcional; 422 si no existe. `GET /console/audit/vocabulary` gana
`categories: [{key, label}]`.

### `PUT /console/billing/email` — nuevo
Permiso `billing:manage`. `{ "billing_email": "…" }` → 200 `BillingOut`;
422 `invalid_email`. Auditoría `console.billing.email_update`.

### `POST /console/clients/{ref}/playground/threads` — cambia el título por defecto
Sin `title` → «Conversación del 24 sept 2026» (idioma del principal). Nunca «Untitled».

## Lo que no cambia y la spec usa

`PUT …/allocation`, `POST /wallet/allocations/move`, `GET/PUT …/agent/settings`,
`GET/PUT …/model`, `GET …/knowledge`, `GET /console/onboarding`, `GET /console/home`,
`GET /console/seed-templates`, todos los de canales, conectores y AgendaPro (spec 016).
