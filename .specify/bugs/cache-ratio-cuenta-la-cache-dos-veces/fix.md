# Bug Fix: el aviso `cache_ratio_low` cuenta la caché dos veces

- **Slug**: cache-ratio-cuenta-la-cache-dos-veces
- **Fixed**: 2026-11-25
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

La proporción de lectura de caché del aviso es `cache_read / input`, sin volver a sumar la caché al denominador.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/streams/platform_watcher.py` | modified | `total = input_tok` |
| `infra/observability/grafana/nexus-overview.json` | modified | El panel «LLM cache read ratio (1h)» tenía la misma suma doble |
| `apps/api/src/nexus_api/core/otel_metrics.py` | modified | Solo el docstring que describía la fórmula |
| `apps/worker/tests/unit/test_platform_watcher.py` | added test, fixed data | `test_cache_ratio_counts_the_cache_once`: 109k de caché sobre un prompt de 260k (42 %) no salta. Los datos del test anterior suponían la caché fuera del prompt; ahora el prompt la incluye |

## Local Verification

- El test nuevo, **en rojo** antes del arreglo (la fórmula vieja da 0,295); en verde después.
- `tests/unit/test_platform_watcher.py`: 30 passed (con `--with lupa`).
- `./scripts/verify.sh lint`: todo verde.
