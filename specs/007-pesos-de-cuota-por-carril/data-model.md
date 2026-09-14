# Fase 1 — modelo de datos

**Spec**: [spec.md](./spec.md) · **Investigación**: [research.md](./research.md)

Dos tablas tocadas, **sólo por adición**. Ninguna columna se borra y ninguna
cambia de significado, por lo que el `downgrade()` devuelve el esquema exacto.

---

## `model_profiles` — el catálogo de plataforma

**Tenant**: ninguno. Es catálogo de plataforma, **no lleva `tenant_id` y no lleva
RLS**. La garantía no es una política: es que no hay columna por la que un
cliente final pudiera alcanzarlo. `tests/isolation/test_pool_not_exposed_to_tenant.py`
es lo que impide que alguien abra esa puerta, y su lista `FORBIDDEN` **debe
crecer con los tres nombres nuevos**.

| Columna | Tipo | Nulo | Qué es |
|---|---|---|---|
| `quota_weight_input` | `NUMERIC(12,6)` | sí | unidades de cuota por token de entrada no cacheada |
| `quota_weight_cache_read` | `NUMERIC(12,6)` | sí | unidades de cuota por token leído de caché |
| `quota_weight_output` | `NUMERIC(12,6)` | sí | unidades de cuota por token de salida |
| `quota_weight` | `NUMERIC(6,3)` | sí | **deprecada**. Se conserva para que el `downgrade()` sea real; la borra una migración posterior |

**Reglas**:

- `NULL` en los tres significa **«este modelo no se sirve por el carril de cuota
  de LLM»** — el mismo idioma que la tabla ya habla con las tarifas, y el que
  deja a `openai/whisper-1` funcionando por minutos. No significa «peso 1».
- **Los tres o ninguno.** Un modelo con dos pesos y uno nulo es un error de
  configuración, no un modelo medio servible: se rechaza igual que uno sin
  ninguno. `CHECK` que exige que los tres sean nulos o los tres no nulos.
- `CHECK` de positividad en cada uno, como el que ya tiene `quota_weight`.
- **Valor sembrado**: `2,2 × price_<carril>_per_mtok ÷ 10`, redondeado a la escala
  de la columna. Se siembra en la migración desde las tarifas **que haya en la
  fila**, no desde una lista escrita a mano: una lista se desincroniza del
  catálogo el día que alguien añada un modelo.
- No se siembra `quota_weight_cache_write`. La escritura en caché no entra en la
  cuota y no gana un cuarto peso (R1.5).

### Invariante

Para todo modelo con los tres pesos, y para cada carril *c*:

```
quota_weight_c × CREDIT_USD_PER_MILLION ÷ price_c_per_mtok  ≥  1,50
```

comprobado **sobre el valor almacenado**, después del redondeo de la columna
(R2.2). Con el catálogo de hoy el cociente es 2,20x en los dieciocho carriles.

---

## `companion.runs` — un turno del Companion

**Tenant**: ninguno; es del partner, y la fila la alcanza `principal_id` +
el esquema `companion`. No cambia con esta spec.

| Columna | Tipo | Nulo | Qué es |
|---|---|---|---|
| `uncached_input_tokens` | `integer` | sí | **nueva** — entrada no cacheada, **nativa y sin ponderar** |
| `input_tokens` | `integer` | sí | **deprecada**. Sigue siendo la cuota ponderada de la `0093` para las filas ya escritas. Deja de escribirse |
| `output_tokens` · `cache_read` · `cache_write` | `integer` | sí | nativos, sin cambio |

**Por qué una columna nueva y no reinterpretar la que hay** (D4): reinterpretarla
dejaría filas cuya lectura depende de su fecha, y un `downgrade()` incapaz de
devolver los datos. Con la columna nueva, una fila vieja se lee con la regla
vieja y una nueva con la nueva, sin ambigüedad y sin backfill.

**Backfill**: ninguno, a propósito. `uncached_input_tokens` queda `NULL` en las
filas históricas y eso es la verdad — el nativo no se puede recuperar de la cuota
sin asumir que el factor fue 0,1, que es exactamente la suposición de la que esta
spec sale. Un `NULL` declarado vale más que un número reconstruido.

---

## Lo que **no** cambia

- `usage_records` y su `billable_qty`: el desglose por medidor nativo sigue igual;
  lo que cambia es el factor de cada carril.
- `usage_ledger`, `partner_wallets`, `partner_allocations`: la unidad de cuota
  sigue siendo una sola unidad comparable. **Ningún saldo se revalora** (D5).
- `membership_tiers`: los tamaños de bolsa son decisión comercial, fuera de
  alcance.
- `qa.runs`: no debita y su cifra es nativa bruta. Fuera de alcance.
