# Bug Verification: reinvitar tras una invitación vencida da 409

- **Slug**: reinvitar-tras-vencer-da-409
- **Tested**: 2026-11-03
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Los seis pasos de la reproducción dan ya lo esperado, contra Postgres real y por la API en proceso, también con dos peticiones simultáneas. No aparecen regresiones en los archivos relacionados. No se ha probado en staging, por encargo.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción tras el arreglo | Las 10 pruebas nuevas | pass | Las mismas que estaban en rojo |
| Aislamiento y archivos relacionados | `pytest tests/isolation/test_console_scope.py tests/isolation/test_console_isolation.py` y los archivos de consola, invitaciones, alta y panel | pass | 1706 pasadas, 0 fallos, en 12 min 53 s. Base `nexus_test_invita`, Redis 12 |
| Lint y tipos | `./scripts/verify.sh lint` | pass | «Todo verde»: ruff y `mypy --strict` |
| Suite completa de la API y del worker | No corridas | skipped | Por encargo solo los archivos de lo tocado. No se añade ningún cron, así que no cambia el contrato del worker |
| Staging o producción | No tocados | skipped | Por encargo |

## Output Excerpts

```
1706 passed, 1 warning in 773.40s (0:12:53)
```

## Residual Risks

- Una fila en el instante justo del vencimiento: si una aceptación la leyó aún viva y una reinvitación la retira a la vez, quedan una persona dentro y una invitación pendiente a su nombre, que al aceptarla da `already_member`. Sin consecuencia de seguridad, y la ventana es de milisegundos cada 21 días.
- Las filas vencidas sin reinvitar siguen `pending` en la tabla. Es deliberado: ver el assessment.

## Recommendation

Cerrar el bug tras fusionar. Si se quiere confirmar en staging: una invitación con `expires_at` adelantado a mano no sale en Equipo y se puede volver a enviar.
