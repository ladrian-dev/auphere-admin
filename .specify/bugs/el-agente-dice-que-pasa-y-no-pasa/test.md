# Bug Verification: el agente dice que pasa la conversación y no la pasa

- **Slug**: el-agente-dice-que-pasa-y-no-pasa
- **Tested**: 2026-11-08
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified en local; falta repetirlo en staging

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Prueba nueva, en rojo antes | `test_intent_tool_filter.py::TestHandOffOnEveryIntent` | 1 failed → 16 passed | |
| Worker entero | `pytest apps/worker/tests` (entorno de la API) | 928 passed | |
| Lista blanca y bucle | `test_45_tools_only_from_activations`, `test_2_tool_whitelist_*`, `test_react_loop`, `test_booking_brake_turn` | 87 passed | |
| Lint | ruff, format, `mypy --strict` del worker | ok | |
| Staging | repetir la petición a nombre de otra persona | pendiente | debe quedar «Necesita humano» y aviso en la campana |
