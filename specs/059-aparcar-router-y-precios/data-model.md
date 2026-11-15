# Modelo de datos: spec 059

Todo lo de esta spec es **dato de plataforma, sin cliente**, salvo los agentes que
lee el barrido del requisito 1.2. Esos se leen bajo la RLS de cada cliente y solo
salen de ella el recuento y los nombres de los clientes.

## Tablas

### `model_profiles` (existe), con una columna nueva

| Columna | Tipo | Regla |
|---|---|---|
| `status_before_unavailable` | `text NULL` | El estado que tenía el modelo al marcarlo `unavailable`. Se escribe en `mark_unavailable` y se borra en `restore_available` (research D4). `CHECK` con los mismos valores que `status`. |

Se usan, sin cambiar su forma, `quota_weight_input`, `quota_weight_cache_read` y
`quota_weight_output` (`NUMERIC(12,6)`, los tres o ninguno, `CHECK` de la 0120).

### `platform_settings` (nueva, migración `0231_platform_settings`)

| Columna | Tipo | Regla |
|---|---|---|
| `key` | `text PRIMARY KEY` | Por ahora, solo `sale_multiplier` |
| `value` | `jsonb NOT NULL` | Para `sale_multiplier`, un número ≥ 1,5 (lo valida la API) |
| `updated_at` | `timestamptz NOT NULL DEFAULT now()` | |
| `updated_by` | `text NULL` | El actor de la última escritura (`operator:{id}`) |

Siembra: `('sale_multiplier', '2.2'::jsonb, now(), 'migration:0231')`. Sin RLS,
como `model_profiles` y `model_prices`, y con los mismos permisos que esas.

## Estados de un modelo y sus transiciones nuevas

```
active ──Retirar (si no está en uso)──► retiring ──fecha, sin agentes atrapados──► retired
   ▲                                       │  └──fecha, con agentes sin sustituto──► retiring (retirada detenida)
   └──────────Cancelar retirada────────────┘

{active, draft, certifying, retiring, deprecated} ──No disponible (si no está en uso)──► unavailable
unavailable ──Volver a disponible──► status_before_unavailable (o el de la auditoría, o draft)
```

## Objetos de dominio (no persistidos)

- **`ModelUses`**: lo que se sabe del uso de un modelo.
  - `defaults`: lista de `uso` del registro, por ejemplo `respond` o
    `respond_fallback`;
  - `agents`: un entero;
  - `clients`: los nombres visibles de los clientes, sin ids de agentes ni textos
    de configuración;
  - `verified`: un booleano, y `problem` si es falso: `no_heartbeat`,
    `unpublished` o `mismatch`.
- **`SaleLanes`**, por modelo cobrado por tokens:
  - por carril: `cost_per_million`, `weight`, `sale_per_million` (`peso × 10`) y
    `multiplier` (`venta ÷ coste`);
  - para el modelo: `proposed` (los pesos del multiplicador objetivo) y `state`
    (`on_target · drift · below_floor · unweighted · per_minute · no_cost`).

## Auditoría (plataforma)

| Acción | Antes / después |
|---|---|
| `deployment.retirement_cancelled` | `status: retiring → active`, `retire_after`, `reason` |
| `deployment.restored` | `status: unavailable → X`, `reason` |
| `deployment.retirement_blocked` | `agents`, `date`: una vez al día y por modelo |
| `deployment.weights_changed` | Los tres pesos antes y después, `reason` |
| `platform.sale_multiplier_changed` | `multiplier` antes y después, `applied_to` (lista de modelos), `reason` |
| `auphere_channel.*` (existentes) | El actor pasa a ser la persona del panel, con `reason` |
