# Modelo de datos: Acceso a conectores por partner

Dos tablas de plataforma nuevas, sin `tenant_id` y sin RLS (research D3). Una migración, la siguiente a `0231_platform_settings`.

## `connector_access_defaults`

El valor por defecto de un conector para los partners. **Sin fila significa habilitado**, así que al desplegar no cambia nada (requisito 1.1).

| Columna | Tipo | Notas |
|---|---|---|
| `connector_slug` | `text` PK | Minúsculas. Es el mismo slug de `connectors.slug` y de los conectores dinámicos de Composio (D1). |
| `enabled` | `boolean NOT NULL` | `false` = deshabilitado para todo partner sin decisión propia y para los clientes sin partner. |
| `reason` | `text NOT NULL` | Motivo del último cambio. |
| `updated_by` | `text NOT NULL` | `operator_actor(...)`. |
| `updated_at` | `timestamptz NOT NULL DEFAULT now()` | |

`CHECK (connector_slug = lower(connector_slug))`.

## `connector_partner_access`

La decisión propia de un partner sobre un conector. Las dos vistas del panel escriben aquí.

| Columna | Tipo | Notas |
|---|---|---|
| `connector_slug` | `text` | PK compuesta con `partner_id`. |
| `partner_id` | `uuid` | FK `partners(id) ON DELETE CASCADE`: desaparece con el partner. |
| `enabled` | `boolean NOT NULL` | |
| `reason` | `text NOT NULL` | |
| `set_by` | `text NOT NULL` | |
| `set_at` | `timestamptz NOT NULL DEFAULT now()` | |

Índice por `partner_id`, para la vista por partner. «Como el valor por defecto» borra la fila. Es una decisión de configuración, no un dato de un cliente, y la auditoría guarda el antes y el después (constitución §IV: lo que no se borra son los datos de clientes).

`CHECK (connector_slug = lower(connector_slug))`.

## Permisos

`GRANT SELECT, INSERT, UPDATE, DELETE ON connector_access_defaults, connector_partner_access TO nexus_app`, como `platform_settings` (0231).

## La regla

Para un cliente `t`, con `p = tenants.partner_id` (puede ser `NULL`):

```
no_disponibles(t) =
    { s | fila (s, p) en connector_partner_access con enabled = false }
  ∪ { s | connector_access_defaults(s).enabled = false
          y no hay fila (s, p) en connector_partner_access }
  − canales − conectores de sistema
```

Si `p` es `NULL`, no puede haber fila de partner y solo cuenta el valor por defecto (requisito 1.4).

Es una sola consulta por turno, sobre dos tablas pequeñas (decenas de filas).

## Lo que no cambia

`connectors`, `tenant_connectors`, `tenant_credentials`, `agent_connector_activations`, `tenant_connector_tool_overrides` y `tool_catalog` no se tocan (requisito 5.5). Quitar el acceso no escribe en ninguna de ellas.

## Auditoría

`audit_log` con `tenant_id = NULL`. `action` es una de las dos siguientes:

- `connector_access.default_changed`: `target = "connector:<slug>"`.
- `connector_access.partner_changed`: `target = "connector:<slug>/partner:<id>"`.

En los dos casos, `before_json` y `after_json` llevan `{"enabled": …}`, o `null` para «como el valor por defecto», y `after_json.reason`.

Las dos frases van a `console_audit_vocabulary`, sembradas en la misma migración.
