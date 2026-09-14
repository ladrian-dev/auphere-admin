# Nota sobre la línea base (T001)

**`baseline.txt` está contaminado y no sirve como línea base.** Se lanzó
`./scripts/verify.sh` en segundo plano y **se editó código mientras corría**, así
que su resultado mezcla el estado de `develop` con parte de los cambios de la
007. Es exactamente el modo de fallo que el encargo advertía —«una tarea de
fondo por trabajo, y mátala cuando deje de hacer falta»— y el error fue de
método, no del script.

Salida contaminada: `EXIT=1`, `Fallaron 2: pytest · api, pytest · worker`, con
seis casos en rojo:

    tests/integration/test_migration_reversibility.py::test_the_migrations_go_down_and_come_back_up
    worker/tests/unit/test_allocation_debit_wiring.py::test_channel_turn_debits_wallet_and_allocation
    worker/tests/unit/test_allocation_debit_wiring.py::test_allocation_failure_does_not_hide_a_good_wallet_debit
    worker/tests/unit/test_usage_quota_consumer.py::test_input_billable_is_uncached_and_cache_row_is_tenth
    worker/tests/unit/test_usage_quota_consumer.py::test_summing_input_billable_plus_cache_native_is_not_quota
    worker/tests/unit/test_usage_quota_consumer.py::test_companion_quota_matches_channel_billable_for_the_same_call

## La línea base real de esas tres suites

Se obtuvo con `git stash -u` (árbol en `develop` limpio) y está en
`baseline-limpia.txt`. **Las tres pasan**: 2 casos en la de reversibilidad y 9
en las dos del worker. Ningún fallo es preexistente — los seis son consecuencia
de los cambios de esta spec, y tres de ellos son *esperados*: afirman la fórmula
vieja (el 0,1 global y el peso único) que la 007 sustituye.
