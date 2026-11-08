# Bug Verification: el precio leído de la web pierde su moneda

- **Slug**: el-precio-leido-de-la-web-pierde-su-moneda
- **Tested**: 2026-11-08
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Prueba nueva, en rojo antes | `pytest tests/unit/test_reader_structured.py` | 1 failed → 10 passed | `test_a_price_read_from_the_web_carries_the_currency_it_was_read_in` |
| Prueba de aceptación | `pytest tests/integration/clients/test_client_read_job.py` | passed | estaba en rojo en `develop` |
| Lector, ficha y sugerencias | pruebas de `tests/integration/business` y `tests/integration/clients` que nombran lector o sugerencias | 112 passed | |
| Lint | `ruff check`, `ruff format --check`, `mypy --strict` del lector | ok | |
