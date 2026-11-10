# Bug Verification: la clave de idempotencia de una cita entregaba la cita de otro cliente

- **Slug**: la-clave-de-la-cita-no-es-de-otro
- **Tested**: 2026-10-22
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Las dos pruebas nuevas de `test_35` se escribieron antes del arreglo y se vieron en
rojo por la razón del bug; con el arreglo, verdes. La suite de aislamiento entera, la
del MCP y las de la API que ejercitan `booking.*` siguen en verde.

Base propia para no pisar a otras sesiones: `nexus_test_booking_idem` en
`nexus-postgres` (Redis db 12). Una suite a la vez.

## El test se escribió primero y se vio en rojo

`apps/api/tests/isolation/test_35_customer_scope_within_tenant.py`, antes de tocar
`src/`:

```
FAILED ...::test_the_same_idempotency_key_never_hands_over_another_persons_appointment
FAILED ...::test_a_row_with_this_persons_key_but_another_owner_is_refused
2 failed, 7 passed in 6.83s
```

El fallo que cuenta el bug: con la misma clave, Bruno recibe la cita de Ana.

```
>       assert mine.idempotent_replay is False, "recibí la cita de otra persona"
E       AssertionError: recibí la cita de otra persona
E       assert True is False
E        +  where True = CreateAppointmentOutput(appointment=AppointmentBrief(...),
E           idempotent_replay=True, booking_status='confirmed').idempotent_replay
```

El segundo (`DID NOT RAISE <class 'nexus_mcp.base.ToolError'>`): sin defensa en el
replay, una fila ajena con la clave de esta persona no se rechazaba.

Después del arreglo, el fichero entero: `9 passed in 5.77s`.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción (rojo primero) | `pytest tests/isolation/test_35_customer_scope_within_tenant.py` | pass | 2 rojos antes; 9/9 después |
| Suite de aislamiento + API de `booking.*` | `pytest tests/isolation tests/integration/mcp tests/integration/test_mcp_dry_run_per_server.py tests/integration/test_react_loop.py tests/integration/test_qa_endpoints.py tests/integration/test_console_capabilities.py tests/unit/test_booking_async_facade.py tests/unit/test_agendapro_public_proxy.py tests/unit/test_repo_tool_catalog.py tests/unit/test_capability_names.py -q` | pass | 1748 pasados, 1 skip en 4 min. El skip es el de `test_37` para un vertical de operador, previo y deliberado |
| Replay existente | incluido arriba: `test_booking_create_appointment_idempotent_on_replay` | pass | Misma persona, misma clave → misma cita, sin cambios en la prueba |
| Suite MCP | `pytest apps/mcp/tests -q` | pass | 123 |
| `ruff check` + `ruff format --check` | `apps/mcp/src`, `apps/mcp/tests` y el fichero de prueba | pass | |
| `mypy --strict` | `mypy --strict apps/mcp/src/nexus_mcp` | pass | 66 ficheros, sin errores |

## Residual Risks

- Sin LLM real: no se ha medido qué clave construye el modelo con la descripción
  nueva. No afecta al aislamiento (la clave es por persona sea cual sea), solo a la
  calidad de la deduplicación de reintentos.
- Filas anteriores al despliegue con clave cruda: un reintento que cruce el despliegue
  puede duplicar una cita (ver `fix.md`).
- No se corrió la suite completa de la API (6 000+) ni la del worker: el cambio es de
  una herramienta del MCP, y el worker solo lee la clave de la fila.

## Recommendation

Cerrar el bug: el caso de dos personas con la misma clave queda cubierto en la suite
de aislamiento, que bloquea el merge. Al fusionar con la 043, reunir las dos
`_agent_key` en `nexus_mcp/_customer.py`.
