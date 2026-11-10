# Bug Verification: el alta descarta la moneda de la bolsa que se eligió

- **Slug**: el-alta-descarta-la-moneda-de-la-bolsa
- **Tested**: 2026-10-29
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Reproducción | `pytest tests/integration/clients/test_create_three_fields.py -k bag_is_born` antes del arreglo | fail | Sin bolsa tras el alta: la moneda elegida no llegaba a ningún sitio |
| Arreglo | La misma prueba, después | pass | MX→EUR, ES→USD y CL→USD elegidas a mano |
| Sin regresiones | `pytest tests/integration/clients/` | pass | 76 passed |
