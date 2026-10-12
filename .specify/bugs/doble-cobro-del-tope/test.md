# Bug Verification: el tope por cliente se descuenta dos veces y el gasto mostrado sale inflado

- **Slug**: doble-cobro-del-tope
- **Tested**: 2026-10-12 (local) · 2026-10-12 (producción, tras el despliegue)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

El bug ya no se reproduce contra la base real: un turno baja el tope una vez,
sin cobro no lo baja, el agente sigue atendiendo con la mitad del tope gastada
y los asientos `:allocation` no cuentan como gasto. La migración `0156`
devuelve lo descontado de más y es idempotente. La verificación completa del
repo pasa sin regresiones. Y en producción, tras el despliegue del
2026-10-12, los topes quedaron como se esperaba y no se han escrito asientos
`:allocation` nuevos.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción (antes del arreglo) | `pytest tests/integration/test_channel_debit_once.py` | fail ×4 | Cada uno por su efecto: tope 6 000 en vez de 8 000; 8 000 sin cobro; 0 con la mitad gastada; gasto 4 000 en vez de 2 000 |
| Reproducción (tras el arreglo) | el mismo | pass | 4 passed |
| Migración de reparación | `pytest tests/integration/test_migration_repair_double_cap_debit.py` | pass | Inutilizada la reparación, falla con `assert 0 == 7000`: la prueba no es vacía |
| Reversibilidad de migraciones | `pytest tests/integration/test_migration_reversibility.py` | pass | |
| Aislamiento del monedero | `pytest tests/isolation/test_24_partner_wallet_rls.py` | pass | La garantía «un cliente no toca el tope de otro» sobre `debit_wallet` |
| Cableado del medidor | worker `pytest tests/unit/test_allocation_debit_wiring.py` | pass | Una sola llamada con `tenant_id`; `debit_allocation` ya no existe |
| Regresión completa | `./scripts/verify.sh` | pass | API 4 800 · worker 438 · canales 61 · MCP 123 · consola 760 · panel 132 · `@nexus/ui` 174 · companion-ui 188 · desktop 949; lint, mypy `--strict` y `next build` en verde |
| Producción tras el despliegue | consulta de solo lectura de los topes (`SET TRANSACTION READ ONLY`) | pass | Cada tope = tope − lo cobrado en la semana; último asiento `:allocation` a las 00:55, antes del despliegue |

## Output Excerpts

```
4800 passed, 373 skipped, 4 xfailed, 152 warnings in 1750.60s (0:29:10)   # API
438 passed, 13 warnings in 11.17s                                         # worker
Todo verde. La tubería debería pasar.
```

Producción, antes y después de `0156` (despliegue `deploy-prod` de `deadd4c1`,
2026-10-12 12:27 UTC):

| Cliente | Antes | Después | Tope − cobrado en la semana |
|---|---|---|---|
| New Air Climatización | **0** (mudo) | 50 000 | 50 000 |
| Barber Supply | 46 347 | 50 000 | 50 000 |
| Amigable Cobro | 1 173 280 | 1 186 640 | 1 186 640 |
| Flor y Encanto | 3 814 680 | 4 225 392 | 4 225 392 |

Los tres avisos de lint del panel (`resume.test.tsx`, `inspector-drawer.tsx`)
son anteriores y no los toca este arreglo.

## Residual Risks

- **La semana de la reparación** se fecha con `included_expires_at - 7 días`.
  Si un partner cambiara su tope o su periodo dentro de la semana, la cuenta
  podría salir distinta. El `GREATEST` evita que eso deje a nadie con menos
  margen; en el peor caso le da más, nunca por encima del tope.
- **El gasto mostrado baja al desplegar**, porque deja de contar lo duplicado.
  Es la cifra correcta, pero un partner atento lo notará.
- **Turnos sin cobro con solo créditos incluidos**: hallazgo relacionado, fuera
  de alcance. New Air vuelve a contestar, pero facelad no tiene créditos
  comprados y esos turnos no se cobran.

## Recommendation

Cerrar el bug: verificado en local y en producción. Queda vigilar una semana
que no aparezcan asientos `:allocation` nuevos (no debería: el código que los
escribía ya no existe) y evaluar aparte los dos hallazgos relacionados.
