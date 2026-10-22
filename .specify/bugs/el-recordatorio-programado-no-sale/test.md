# Bug Verification: el recordatorio que programa el agente nunca sale

- **Slug**: el-recordatorio-programado-no-sale
- **Tested**: 2026-10-22 (local, base propia `nexus_test_consolas`)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Un recordatorio programado con `notification.schedule_reminder` acababa en
`FAILED` a su hora; ahora sale con la plantilla y los parámetros que eligió el
agente. Las filas antiguas siguen saliendo y conservan su idioma.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción (antes) | `pytest tests/integration/channels/test_reminder_cron.py` | fail ×2 | `payload missing 'template' and/or 'conversation_id'`; idioma `'es' == 'es_CL'` |
| Reproducción (después) | la misma | pass | 5 passed (las 3 de antes y las 2 nuevas) |
| Worker | `pytest apps/worker/tests` | pass | 463 passed |
| Regresión completa | `./scripts/verify.sh` (lint y py repetidos al final) | pass | API 6 024 · worker 463 · canales 61 · MCP 123; ruff y mypy `--strict` en verde; JS entero (consola, panel, `@nexus/ui`, companion-ui, desktop, dos `next build`) en verde. Único rojo: `app · expo-doctor` (parches del SDK 58 publicados por Expo), igual en `develop`; lo arregla la rama 044 |

## Residual Risks

- Los recordatorios que ya fallaron por esto no se reenvían: todos habían
  vencido, y llegar tarde es peor que no llegar.

## Recommendation

Cerrar el bug cuando `verify.sh` pase entero en la rama.
