# Bug Verification: el gasto del mes del cliente se queda a cero con bolsas

- **Slug**: gasto-del-mes-a-cero-con-bolsas
- **Tested**: 2026-11-08
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Reproducción (API) | `pytest tests/integration/wallet/test_client_month_spend_from_bag.py` antes del arreglo | fail | Con 0,85 € cobrados por `charge_turn`, el Panel del partner daba `bag.spent` 85 000 EUR y `month.spent` 0 USD; la lite, `spend_month.total_cents` 0 y el reparto a cero, `/usage/summary` 0 sin proyección y `/usage/spend` 0 en USD, con el saldo bien (19,40 €). La bolsa sin tocar este mes enseñaba 50 000 del mes pasado |
| Reproducción (consola) | `vitest run lite-spend-card.test.tsx lite-usage.test.tsx` antes del arreglo | fail | La tarjeta y Consumo pintaban US$ con la bolsa en EUR |
| Arreglo (API) | La misma prueba, después | pass | 2 passed: el total y el reparto por agente cuadran entre `/console/lite/home`, `/console/lite/usage/summary`, `/console/lite/usage/spend` (también con `?agent=`) y `/console/clients/{ref}/panel`, en EUR |
| Arreglo (consola) | Las mismas pruebas, después | pass | La tarjeta, el saldo, las cifras, la gráfica y el detalle de Consumo en EUR; sin moneda, US$ |
| Sin regresiones (API) | `pytest tests/integration/wallet/ tests/integration/clients/test_client_panel.py tests/integration/clients/test_clients_list.py tests/integration/clients/test_partner_panel.py tests/unit/test_lite_home.py tests/unit/test_lite_usage.py tests/unit/test_lite_by_agent.py tests/integration/test_lite_phone_figures_match_web.py` | pass | 103 passed (sin bolsas, el camino del libro no cambia) |
| Aislamiento | `pytest tests/isolation/test_console_scope.py tests/isolation/test_lite_*.py` | pass | 2268 passed; las rutas tocadas siguen cubiertas por el barrido de `/console/*` |
| Tras el último retoque | `pytest` de la prueba nueva, `test_client_panel.py`, `test_lite_home.py`, `test_lite_usage.py`, `test_lite_by_agent.py` y `test_lite_phone_figures_match_web.py` | pass | 36 passed |
| Consola | `vitest run src/components/lite src/app/(console)/usage src/lib src/i18n` | pass | 30 archivos, 278 pruebas (incluida la que prohíbe `;` en los textos) |
| Tipos y estilo | `pnpm --dir apps/console exec tsc --noEmit`; `eslint` de los archivos tocados; `ruff check`, `ruff format --check` y `mypy --strict src/nexus_api` | pass | Sin errores |
