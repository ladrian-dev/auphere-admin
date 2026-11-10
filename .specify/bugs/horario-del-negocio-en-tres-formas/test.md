# Bug Verification: el horario del negocio se guarda en tres formas y el agente no entiende la del admin

- **Slug**: horario-del-negocio-en-tres-formas
- **Tested**: 2026-10-22 (local, base propia `nexus_test_consolas`)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Antes del arreglo, las cuatro pruebas de integración de la herramienta fallaban
(`AttributeError` con el horario del admin; 10–19 con el de la semilla). Después
pasan, igual que las unitarias del lector, las del endpoint del admin, la de la
migración y las del selector. Las suites del worker y del MCP siguen en verde.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción (antes) | `pytest tests/integration/mcp/test_availability_business_hours.py` | fail ×4 | `ToolError: tool 'booking.check_availability' failed: 'list' object has no attribute 'get'` (y `'str'` con el del admin) |
| Lector (antes) | `pytest tests/unit/test_business_hours.py` | error | El módulo no existía |
| Reproducción (después) | las mismas + `test_endpoint_tenants.py` + `test_servers_happy_path.py` | pass | 79 passed |
| Migración | `pytest tests/integration/test_migration_0170_canonical_business_hours.py` | pass | Escrita junto con la migración: no se vio en rojo antes |
| Selector del admin | `pnpm --dir apps/admin exec vitest run src/components/forms` | pass | 3 passed; `pnpm typecheck` en verde |
| Worker | `pytest apps/worker/tests` | pass | 463 passed |
| MCP | `pytest apps/mcp/tests` | pass | 123 passed |
| Regresión completa | `./scripts/verify.sh` (lint y py repetidos al final) | pass | API 6 024 · worker 463 · canales 61 · MCP 123; ruff y mypy `--strict` en verde; JS entero (consola, panel, `@nexus/ui`, companion-ui, desktop, dos `next build`) en verde. Único rojo: `app · expo-doctor` (parches del SDK 58 publicados por Expo), igual en `develop`; lo arregla la rama 044 |

## Residual Risks

- Producción: no se ha medido cuántos tenants tienen cada forma. La migración es
  tolerante (lo que no entiende lo deja), así que no depende de ese dato.
- Los tenants con horario dejarán de recibir huecos fuera de él: es lo que el
  arreglo pretende, pero el agente cambia de comportamiento para ellos.

## Recommendation

Cerrar el bug cuando `verify.sh` pase entero en la rama.
