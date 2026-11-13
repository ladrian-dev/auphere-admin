# Contrato: API del panel para el acceso a conectores por partner

Todas las rutas van bajo `/admin`, con `require_operator`, como el resto del panel. Ninguna está en `/console`: ningún partner lee ni cambia estas decisiones (requisito 1.7).

Estados de un conector para un partner:

- `enabled` / `disabled`: decisión propia del partner.
- `default`: sin decisión propia; hereda el valor por defecto del conector.

`effective` es el resultado de la regla: `true` o `false`.

## `GET /admin/partners/{partner_id}/connectors`

Vista por partner (requisito 2.1). Lista el catálogo completo del panel (`audience=OPERATOR`), sin canales ni conectores de sistema.

```json
{
  "partner": {"id": "…", "name": "Amacrux"},
  "items": [
    {
      "slug": "quedate",
      "display_name": "Quédate",
      "category": "real_estate",
      "auth_kind": "api_key",
      "default_enabled": false,
      "partner_state": "enabled",
      "effective": true,
      "connected_clients": 1,
      "set_by": "operator:…",
      "set_at": "2026-11-13T…",
      "reason": "Conector propio de Amacrux"
    }
  ]
}
```

Si Composio no responde, el catálogo trae solo los conectores sembrados, igual que `GET /admin/connectors`. Quedan fuera los canales y los deprecados.

Errores:
- `404 partner_not_found`.

## `PUT /admin/connectors/{slug}/partners/{partner_id}`

Habilitar, deshabilitar o volver al valor por defecto para un partner. La usan las dos vistas (requisito 3.3).

```json
{"state": "enabled" | "disabled" | "default", "reason": "…", "confirm": false}
```

- `200` devuelve el ítem como en el `GET` de la vista por partner.
- `409 confirm_required`: el cambio quita el acceso a clientes con conexión y no se mandó `confirm: true`. No guarda nada (requisito 4.1).

  ```json
  {
    "code": "confirm_required",
    "affected": [
      {
        "partner_id": "…",
        "partner_name": "…",
        "clients": [{"tenant_id": "…", "name": "…", "connection_status": "connected", "agents": 2}]
      }
    ],
    "totals": {"clients": 1, "agents": 2}
  }
  ```

- `409 partner_default_connector`: el slug es el `default_connector_slug` del partner y el cambio le quita el acceso. Se rechaza aunque venga `confirm` (requisito 4.3).

  ```json
  {"code": "partner_default_connector", "partners": [{"id": "…", "name": "…"}]}
  ```

- `422 reason_required`: el motivo falta o está vacío (requisito 2.4).
- `422 connector_not_managed`: es un canal o un conector de sistema (research D12).
- `404 connector_not_found`: el slug no está en el catálogo. `404 partner_not_found`: el partner no existe.

Si nada cambia (mismo estado), responde `200` sin auditar.

## `GET /admin/connectors/{slug}/access`

Vista por conector (requisito 3.1).

```json
{
  "slug": "quedate",
  "default_enabled": false,
  "default_reason": "…",
  "default_updated_by": "…",
  "default_updated_at": "…",
  "partners": [
    {"partner_id": "…", "name": "Amacrux", "state": "enabled", "effective": true, "connected_clients": 1, "set_by": "…", "set_at": "…", "reason": "…"}
  ],
  "partners_without_decision": 7,
  "clients_without_partner_connected": 0
}
```

`partners` solo trae los partners con decisión propia. El selector para añadir uno usa la lista de partners que ya consume el panel.

## `PUT /admin/connectors/{slug}/access/default`

```json
{"enabled": false, "reason": "…", "confirm": false}
```

- Pasar a `false` afecta a todo partner sin decisión propia y a los clientes sin partner. Usa los mismos `409 confirm_required` y `409 partner_default_connector`, calculados sobre todos ellos (requisito 4.1).
- Pasar a `true` nunca quita acceso: no pide confirmación.
- Mismos `422` y `404` que la ruta anterior.

## Cambios en respuestas existentes

- `GET /admin/connectors` y `GET /admin/connectors/{slug}`: cada conector añade `access: {"default_enabled": bool, "partner_decisions": int}` (requisito 3.4).
- La lista de conectores de un cliente en el panel (`GET /admin/tenants/{id}/connectors`): cada conexión añade `available_for_partner: bool` (requisito 3.5).

## Consola (sin rutas nuevas)

Las rutas de la consola no cambian de forma. Cambia lo que devuelven:

- `GET /console/clients/{ref}/connectors`, `…/agents/{id}/integrations`, `…/integrations/{slug}/tools` y `…/capabilities`: no incluyen conectores ni herramientas no disponibles (requisito 5.1). Pedir el detalle de uno no disponible da el mismo `404` que un slug que no existe (sin oráculo).
- `POST …/connectors/{slug}/consent`, `…/api-key`, `…/connections` y `PUT/DELETE …/activations/{slug}`, con un conector no disponible: el mismo `404` que un slug que no existe, con el mismo cuerpo (requisito 5.2, research D13).
