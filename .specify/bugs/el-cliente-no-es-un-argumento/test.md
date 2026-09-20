# Bug Verification: el cliente del turno viajaba como argumento

- **Slug**: el-cliente-no-es-un-argumento
- **Tested**: 2026-09-20
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: **verified**

## El test se escribió primero y se vio en rojo

`apps/api/tests/isolation/test_35_customer_scope_within_tenant.py`, siete casos,
antes de tocar una línea de `src/`:

```
7 failed, 1 warning in 3.87s
```

El fallo que más dice, con **ningún** cliente en contexto:

```
>           assert out.appointments == []
E           AssertionError: assert [AppointmentB...rrency='CLP')] == []
E             Left contains 2 more items, first extra item: AppointmentBrief(
E             … service_name='Endodoncia' …)
```

«Endodoncia» es la cita del *otro* cliente.

Después del arreglo, los mismos siete: `7 passed in 3.86s`.

## Checks Performed

| Check | Command | Result | Notes |
|---|---|---|---|
| Reproducción (rojo primero) | `pytest tests/isolation/test_35_*` | **pass** | 7 rojos antes, 7 verdes después |
| Suite de aislamiento entera | `pytest tests/isolation/ -q` | **pass** | 905 |
| Suite MCP | `pytest tests/ -q` en `apps/mcp` | **pass** | 100 |
| Suite del worker | `pytest tests/ -q` en `apps/worker` | **pass** | 419 — el olvido histórico del repo |
| Integración MCP | `pytest tests/integration/mcp/ -q` | **pass** | 15, tras adaptarlas al contrato nuevo |
| `ruff` + `mypy --strict` | `./scripts/verify.sh lint` | **pass** | «Todo verde». Cazó un `no-any-return` en `_customer.py` |
| Suite completa de la API | `pytest tests/ -q -p no:randomly` | **pass** | 3584 pasados, 313 skip, 4 xfail, en 10 m 35 s |

## Los cuatro tests que el arreglo tumbó, y por qué importan

Al correr la suite completa cayeron cuatro que no tocaban la agenda de frente:

```
FAILED tests/integration/test_agent_promote_no_redeploy.py
FAILED tests/integration/test_evals_real_pipeline.py
FAILED tests/integration/test_react_loop.py
FAILED tests/isolation/test_2_tool_whitelist_runtime.py
```

Los cuatro guionizaban una llamada del modelo **con el `customer_id` correcto puesto
a mano**:

```python
arguments={"customer_id": str(cust.id), "limit": 5},
```

Eso es precisamente lo que escondía el defecto: en producción el modelo no tiene ese
id, así que la llamada real nunca se parecía a la del test. Ahora los cuatro piden
`{"limit": 5}` y el servidor resuelve a la persona. **Que estos tests fallaran es
parte de la verificación, no un daño colateral**: confirma que el contrato viejo
estaba escrito en las pruebas y no en el runtime.

## Lo que este test NO cubre

- **Ninguna llamada a un LLM real.** No sabemos qué hacía el modelo al recibir el
  error engañoso de FK: si inventaba un UUID, lo pedía por chat o se rendía. La
  pregunta deja de importar para el arreglo —el campo ya no existe— pero sigue
  abierta para los evals multi-turno de la futura spec 016.
- **Producción.** Si alguien llegó a leer una cita ajena no se responde aquí; se
  responde con la consulta de `appointments` por tenant que quedó pendiente en la
  ola 0, y ese resultado va a la KB privada.
