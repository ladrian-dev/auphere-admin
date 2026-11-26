# Bug Fix: el copiloto cobra el tramo por llamada y no acumula la caché entre turnos

- **Slug**: copiloto-sin-tramos
- **Fixed**: 2026-11-26
- **Assessment**: ./assessment.md
- **Status**: applied (sin commit; guion en `.claude/commits/2026-11-26-080.sh`)

## Summary

Este cambio arregla dos fallos del cobro del copiloto.

1. **El tramo de precio no se aplicaba.** El grafo ya guardaba el consumo de cada llamada, pero hacia la API solo emitía los totales del turno. Ahora emite también la lista de llamadas, y la API cobra cada una con su tramo, igual que el canal:
   - la cuota, con `lanes.for_prompt(prompt)`;
   - el coste, con `pricing.tier_factor`.

   Haiku 5.5 se puede habilitar sin dejar el copiloto fuera del tramo.
2. **La caché se acumulaba entre turnos del mismo hilo.** Al empezar cada turno, la entrada solo ponía a cero la entrada y la salida. La caché, los pasos y las llamadas venían del checkpoint y se sumaban turno a turno. **Esto ya pasaba en prod con Sol:** cada turno cobraba también la caché de los turnos anteriores del hilo. Ahora también se ponen a cero.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/runtime/companion/graph.py` | modificado | `_call_usage(usage)` en los cuatro sitios donde se acumula; `usage_calls` en el estado; `calls` en `cost.updated` |
| `apps/worker/src/nexus_worker/runtime/companion/state.py` | modificado | Campo `usage_calls`. `RUN_SCOPED_DEFAULTS`, que pone a cero el nodo de entrada de cada turno, incluye ahora los seis contadores. Vale para todos los drivers: la consola y las evaluaciones. |
| `apps/api/src/nexus_api/api/companion_streaming.py` | modificado | `calls` entra en el catálogo cerrado de claves de `cost.updated` |
| `apps/api/src/nexus_api/api/console/companion.py` | modificado | El evento guarda `calls` en `handle.extras["usage_calls"]`. `_turn_quota_units` y `_turn_cost_usd` cobran por llamada. Sin llamadas (un run de antes), cobran con los totales como hasta ahora. |
| `apps/api/tests/unit/test_companion_graph.py` | añadidos dos tests | Uno: el evento lleva una entrada por llamada y sus sumas cuadran con los totales. Otro: dos turnos en el mismo hilo informan lo mismo, es decir, cada turno solo cobra lo suyo. |
| `apps/api/tests/unit/test_companion_streaming.py` | añadidos dos tests | Cuota y coste con una llamada por debajo y otra por encima del umbral; dos cortas no pagan tramo |

## Tests

- **En rojo antes del arreglo:**
  - `test_the_cost_event_carries_each_call_for_the_price_tier`
  - `test_the_quota_applies_the_tier_call_by_call`
  - `test_the_cost_applies_the_tier_call_by_call`
- **En verde después** (base propia `nexus_test_080`):
  - API: `test_companion_graph.py`, `test_companion_streaming.py`, `test_model_catalog_prices.py` y `tests/integration/test_companion_endpoints.py`, 75 en total.
  - Worker: `test_platform_default_models.py`, `test_usage_quota_consumer.py`, `test_usage_task_and_line.py` y `test_cache_write_lane.py`, 53 en total.
- **La caché entre turnos** se reprodujo con el grafo de verdad: dos turnos en el mismo hilo, y el 2.º informaba `cache_read` 16.000 en vez de 8.000. Ahora lo cubre `test_each_turn_of_a_thread_bills_only_itself`. Lo cobrado de más en prod no se ha medido.

## Follow-ups

- La puerta por llamada del presupuesto del companion sigue siendo por turno. Ya estaba documentado en `console/companion.py` y no es parte de este bug.
- Lo cobrado de más por la caché acumulada no se ha medido. Hace falta ver cuántos hilos de varios turnos hubo en prod con el copiloto.
