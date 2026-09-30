# Contratos — spec 023

Ningún endpoint nuevo. Cambia la **forma** de dos respuestas que ya existen y
el **contenido** de una tercera.

## 1 · `GET /console/clients/{ref}/connectors` — permiso `tools:read`

`ConnectorOut` gana un campo:

```json
{
  "slug": "stripe",
  "display_name": "Stripe",
  "category": "billing",
  "auth_kind": "oauth_composio",
  "installed": false,
  "status": null,
  "tools_total": 0,
  "tools_enabled": 0,
  "recommended": true
}
```

| Campo | Regla |
|---|---|
| `category` | `billing` para `stripe`, `booking` para `calendly`, `crm` para `hubspot`, digan lo que digan las etiquetas del proveedor |
| `recommended` | `true` si la plantilla del sector del cliente lo lista en `connectors.recommended`; `false` sin sector, sin plantilla o sin bloque |
| `tools_total` | tras conectar y sincronizar: **12 / 10 / 11**, nunca 426 |

Si el proveedor no tiene *auth config* para uno de los tres, ese slug no
aparece en la lista (Requisito 1.3). Si el proveedor no responde, la
respuesta es la de hoy (los dinámicos faltan y la consola lo dice).

## 2 · `GET /console/clients/{ref}/capabilities` — permiso `tools:read`

Sin cambio de forma. Para un cliente con Stripe conectado, cada elemento de
la lista cerrada llega así:

```json
{
  "kind": "tool",
  "key": "STRIPE_SEARCH_PAYMENT_INTENTS",
  "name": "Ver el estado de un cobro",
  "description": "Busca los cobros de un cliente y dice si cada uno está pagado, pendiente o fallido.",
  "function": "orders",
  "sectors": [],
  "mode": "always",
  "enabled": true,
  "connector_slug": "stripe",
  "connector_status": "connected",
  "usable": true
}
```

| Regla | Prueba |
|---|---|
| `name` nunca es igual a `key` para un slug de la lista cerrada | CE-002 |
| las de lectura llegan `mode=always` y, tras conectar, `enabled=true` | CE-001, Requisito 2.1 |
| las de escritura llegan `mode=blocked`, `enabled=false` | CE-003, Requisito 2.2 |
| ningún slug fuera de la lista aparece, ni siquiera `deprecated` | Historia 1, escenario 3 |

## 3 · Sincronización (`sync_tools_for`) — sin endpoint propio; la dispara
`POST …/connectors/{slug}/sync` y el retorno del consentimiento

Comportamiento con lista:

| Entrada del proveedor | Resultado |
|---|---|
| slug en la lista | fila creada o actualizada con las anotaciones de la lista |
| slug fuera de la lista | no se crea fila; cuenta en `dropped_count`; registro `connector.sync.allowlist_dropped` |
| slug de la lista que el proveedor no devuelve | no se inventa; va en `missing`; registro `connector.sync.allowlist_missing`; si tenía fila, pasa a `deprecated` |
| toolkit sin lista | exactamente lo de hoy |

Auditoría `connector.tools.synced.after`:

```json
{"added": ["STRIPE_SEARCH_CUSTOMERS", "..."], "deprecated": [], "unchanged_count": 0,
 "missing": [], "dropped_count": 414}
```

## 4 · Plantilla de sector — contrato del YAML

```yaml
connectors:
  recommended: [agendapro, calendly]
```

Opcional. Lista de slugs de conector. Un YAML sin el bloque carga igual que
hoy (`connectors_recommended == []`). Un valor que no sea lista de cadenas
hace fallar `load_seed_template` con el mismo error de esquema que el resto
de campos.
