# Modelo de datos — spec 023

Sin migración. Nada nuevo en base de datos: las filas de `tool_catalog` de
los tres conectores las crea la sincronización que ya existe, solo que
ahora **filtrada**. Lo que se añade vive en código (listas, nombres,
categorías, plantillas) y en un campo de salida de la API.

## 1 · La lista cerrada (`services/connectors/toolkits.py`)

```python
class ToolHint(TypedDict):
    read_only: bool
    destructive: bool

TOOLKIT_ALLOWLISTS: dict[str, dict[str, ToolHint]]
#  "stripe"   → 12 slugs (8 lectura · 4 escritura)
#  "calendly" → 10 slugs (7 · 3)
#  "hubspot"  → 11 slugs (6 · 5)
```

Reglas fijadas por test:

- Cada slug empieza por `<TOOLKIT>_` en mayúsculas (el toolkit en minúsculas
  es la clave; el prefijo es el slug del proveedor).
- `read_only` y `destructive` nunca son los dos `True`.
- Un slug con `read_only=False` tiene `destructive=True` (escribir nace
  bloqueado; no hay tercer estado).
- Cada slug tiene entrada en `CAPABILITY_NAMES` con nombre y descripción en
  `es` y `en` (Requisito 3.2).

## 2 · Filas de `tool_catalog` (sin cambio de esquema)

Las crea `sync_tools_for`, como hoy, con estos valores para un slug de la lista:

| Columna | Valor |
|---|---|
| `name` | el slug (`STRIPE_LIST_PAYMENT_LINKS`) |
| `mcp_server` | `composio:<toolkit>` |
| `connector_id` | el conector proyectado |
| `read_only` / `destructive` | de `TOOLKIT_ALLOWLISTS`, no de la heurística |
| `default_mode` | `always` si lee · `blocked` si escribe (`auto_enable_destructive=False` para los dinámicos) |
| `side_effects` | `["destructive"]` si escribe |
| `capability_tags` | `[connector.category]` → `billing` / `booking` / `crm` |
| `status` | `active`; pasa a `deprecated` si el proveedor deja de devolverlo o si sale de la lista |

Un slug fuera de la lista **no tiene fila**. Si la tenía de una
sincronización anterior (Calendly ya existía con las 53), el bucle de
deprecación de hoy la marca `deprecated` en la primera sincronización con
lista, y Capacidades deja de enseñarla (ya filtra `DEPRECATED`).

## 3 · Categoría del conector (`catalog.py`)

```python
_CATEGORY_BY_TOOLKIT: dict[str, str] = {"stripe": "billing", "calendly": "booking", "hubspot": "crm"}
```

Consultado antes que la metadata del proveedor en `_project_dynamic`. Valores
posibles siguen siendo los de la consola: `booking · calendar · billing ·
catalog · ecommerce · messaging · docs · crm · otros`.

## 4 · Plantilla de sector (`SeedTemplate`)

```yaml
# seeds/<sector>_v1.yaml
connectors:
  recommended: [agendapro, calendly]   # opcional; slugs de conector
```

```python
@dataclass(frozen=True)
class SeedTemplate:
    ...
    connectors_recommended: list[str]   # [] si el YAML no lo trae
```

Validación en `load_seed_template`: lista de cadenas no vacías; no se
comprueba que el slug exista (el catálogo es dinámico y un conector puede
no estar hoy en el proveedor: entonces simplemente no hay tarjeta que marcar).

## 5 · Salida de la API (`ConnectorOut`)

```python
class ConnectorOut(BaseModel):
    ...
    recommended: bool = False   # spec 023: la plantilla del sector lo recomienda
```

`True` cuando `slug ∈ SeedTemplate(sector).connectors_recommended`. Sin
sector o sin plantilla cargable → `False` para todos.

## 6 · Auditoría `connector.tools.synced` (vocabulario existente)

`after` gana dos claves; no hace falta fila nueva de vocabulario porque la
acción ya existe y el texto no cambia:

```json
{"added": [...], "deprecated": [...], "unchanged_count": 7,
 "missing": ["STRIPE_SEND_INVOICE"], "dropped_count": 414}
```

`missing` y `dropped_count` solo aparecen cuando el toolkit tiene lista.

## 7 · Consola

- `Connector` (`lib/backend/…`) gana `recommended: boolean`.
- Claves i18n nuevas: `connectors.desc.stripe`, `connectors.desc.calendly`,
  `connectors.desc.hubspot`, `connectors.badge.recommended`. Todas usadas
  (guarda `no-orphan-keys`).
