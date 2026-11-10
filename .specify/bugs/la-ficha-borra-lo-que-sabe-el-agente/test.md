# Bug Verification: editar la ficha borra lo que sabe el agente

- **Slug**: la-ficha-borra-lo-que-sabe-el-agente
- **Tested**: 2026-10-29
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

La prueba nueva falló antes del arreglo (`'Pedido mínimo' in after` → False) y
pasa después. Las pruebas de recompilación que ya había siguen en verde.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Reproducción | `pytest tests/integration/business/test_recompile_keeps_agent_layer.py` antes del arreglo | fail | El prompt activo perdía la capa del agente tras `PUT /hours` |
| Arreglo | La misma prueba, después | pass | 3 passed |
| Sin regresiones | `pytest tests/integration/business/test_next_message_uses_ficha.py tests/integration/business/test_section_writes.py` | pass | 11 passed en total con la nueva |
