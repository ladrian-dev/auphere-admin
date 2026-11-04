# Bug Verification: no había dos trabajos `tests`: las pasadas de uno siguen corriendo cuando ya falló

- **Slug**: pasadas-huerfanas-tras-fallar-el-trabajo
- **Tested**: 2026-11-03
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

La reproducción de la evaluación (una pasada que lanza fuera de su `try`, con otras a
medias) se ejecutó con `PARALLEL` real, en rojo con el `gather` de antes y en verde
después. Lo demostrado es local: la rama no está desplegada. Que no vuelvan a salir
`jobs.tests.attempt_failed` tras un `jobs.finished` se tendrá que ver en staging.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Causa, en los logs | Logs Insights de `/nexus/staging/api` y `/nexus/staging/runner`, 30 días, solo lectura | pass | 12 trabajos `tests`: ninguno se solapa y ninguno empieza a menos de 5 s de otro. 49 y 51 pasadas después de `jobs.finished` |
| Reproducción, antes | `pytest tests/integration/builder/test_one_suite_at_a_time.py::test_when_a_pass_blows_up_the_others_die_with_the_job` | fail | `ninguna sigue viva`: 0 canceladas, y una quinta empezó con el trabajo ya `failed` |
| Productores y `after_commit`, antes | `test_one_suite_at_a_time.py`, `test_after_commit_is_the_outer_one.py` | fail | 9 failed, 3 passed. `['dentro'] == []` al soltar el savepoint; 2 trabajos con 4 cambios a la vez |
| Lo mismo, después | Los mismos dos archivos | pass | 12 passed |
| Plazo agotado y camino sano | `apps/worker/tests/unit/test_suite_passes_end_together.py` | pass | Parte de los 48 del worker. Se escribió junto a `_all_or_none`: su rojo es el de la integración |
| Regresión | 22 archivos de la API, con los que usan `after_commit` y `tests/isolation/test_console_scope.py` | pass | 1731 passed |
| Lint | `./scripts/verify.sh lint` | pass | «Todo verde.» |
| Staging | | not-run | Sin desplegar |
| La fila de `a024f2f8` | | not-run | Sin acceso de lectura a la base: no se sabe si llegó a confirmarse |

## Output Excerpts

```
E   AssertionError: ninguna sigue viva
E   assert 0 == 4
E   assert ['dentro'] == []
E   assert 2 == 1
9 failed, 3 passed, 2 warnings in 20.55s
12 passed, 1 warning in 28.23s
```

## Residual Risks

- `test_two_changes_at_once_queue_one` depende de que cuatro transacciones coincidan. Con el arreglo siempre pasa; sin él se vio en rojo una vez, y antes de forzar que las pruebas ya estuvieran desactualizadas pasaba: no prueba la carrera en todos los órdenes.
- Una caducidad perezosa, porque la réplica murió, sigue dejando la fila de la pasada en `running`. Nada la lee para decidir: `live_run` mira el trabajo.

## Recommendation

Cerrar al desplegar, tras una pasada real en staging. Un fallo a mitad de pasada no debe
dejar `jobs.tests.attempt_failed` después de su `jobs.finished`.
