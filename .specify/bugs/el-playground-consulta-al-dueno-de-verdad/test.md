# Bug Verification: el playground y las pruebas consultan al dueño de verdad

- **Slug**: el-playground-consulta-al-dueno-de-verdad
- **Tested**: 2026-10-29
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Reproducido con un turno del playground (`run_turn`, el grafo del canal con el
registro simulado): un agente con una integración en «Preguntar antes de escribir»
creaba una fila real en `owner_consultations` y ejecutaba la lectura de la tienda
del negocio. Después del arreglo, ninguna consulta, ninguna lectura ni escritura
de verdad, y el turno cuenta lo que habría hecho. El canal sigue preguntando.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Playground, antes (consulta) | `pytest tests/integration/connectors/test_playground_never_reaches_the_business.py` con el código anterior de `pipeline.py`, `simulation/registry.py` y `nexus_mcp/registry.py` (el runner, con el agente en el estado) | fail | `the playground asked the real owner`: una `OwnerConsultation` de la conversación simulada |
| Playground, antes (lectura) | lo mismo, sin la comprobación de la consulta | fail | `the playground read the business's real shop`: `_ShopRead.runs == 1` |
| Playground, después | `pytest tests/integration/connectors/test_playground_never_reaches_the_business.py` | pass | 2 passed: sin consulta, sin lectura ni escritura; «Preguntar al dueño antes de usar …», «Usar …» y «Consultar … (simulado, sin datos reales)»; y el canal (`_approval_envelope` fuera del dry run) sigue en `approval_requested` |
| Registro simulado, antes | `pytest apps/worker/tests/unit/test_simulated_registry_connectors.py` | fail | 6 en rojo: el registro no sabía de conectores (`TypeError` en `connector_tools`) |
| Registro simulado, después | lo mismo | pass | 6 passed: lectura de conector y proxy de Composio sin ejecutar, escritura anotada, lectura interna del negocio sí, la consulta anotada, la vista por turno conserva el mundo |
| Vista de Composio | `pytest apps/worker/tests/unit/test_pipeline_composio_view_dry_run.py` | pass | sigue heredando `dry_run` y su auditoría |
| Sin regresiones | `pytest tests/integration/connectors/ tests/integration/builder/test_playground_draft.py tests/integration/builder/test_agent_suite.py tests/integration/builder/test_publish_gate.py` | pass | 84 passed (con el agente ya en el estado del turno simulado) |

## Not run

- El playground de antes (`/console/clients/{ref}/playground`, `qa.py`) no tiene
  prueba propia nueva: comparte la rama del grafo (`dry_run` → sin consulta), que
  la prueba del playground cubre.
