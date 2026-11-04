# Bug Fix: no había dos trabajos `tests`: las pasadas de uno siguen corriendo cuando ya falló

- **Slug**: pasadas-huerfanas-tras-fallar-el-trabajo
- **Fixed**: 2026-11-03
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Ninguna pasada sobrevive a su trabajo, y la fila se cierra. Todo lo que lanza una suite
pasa por el mismo bloqueo y pregunta lo mismo. Además, el aviso de un trabajo ya no sale
antes de que su fila exista, que era lo único parecido a «dos trabajos seguidos» en los
logs.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/jobs/handlers/agent_tests.py` | modified | `_all_or_none`: cancela y espera. `_close_unfinished`: la pasada queda `failed` con `stopped` |
| `apps/api/src/nexus_api/services/testing/runs.py` | modified | `lock_agent`; `live_run` ve también la suite de `publish` |
| `apps/api/src/nexus_api/services/business/writes.py` | modified | `mark_tests_stale` bajo el bloqueo y con `live_run`. `after_commit` espera a la transacción de fuera |
| `apps/worker/src/nexus_worker/jobs/handlers/agent_publish.py` | modified | `suite_running` con otra pasada viva |
| `apps/api/src/nexus_api/api/console/agent_tests.py` | modified | `409 suite_running` con la suite de «Guardar» en marcha |
| `apps/console/src/components/builder/{quality-model.ts,test-list.tsx,tests-box.tsx,publish-bar.tsx}`, `i18n/lanes/builder-quality.ts` | modified | Dicen `suite_running` |
| `docs/agentes.md`, `specs/047-la-fabrica-de-agentes/contracts/console-api.md` | modified | Lo que describen |
| `.specify/bugs/canal-simulado-primera-pasada/fix.md` | modified | Cierra lo que dejaba abierto |

## Tests Added or Updated

- `apps/api/tests/integration/builder/test_one_suite_at_a_time.py::test_when_a_pass_blows_up_the_others_die_with_the_job`: el trabajo termina `failed`, ninguna pasada sigue, la fila queda cerrada y «Reintentar» es otro trabajo.
- Mismo archivo: un cambio de la ficha se junta con la que no ha empezado; cuatro a la vez encolan una; una fila muerta no se traga el cambio; con una en marcha encola una más y solo una; «Guardar» y «Probar» se ven; y el bloqueo choca con `start_run` sin frenar las inserciones con FK.
- `apps/api/tests/integration/business/test_after_commit_is_the_outer_one.py`: soltar un savepoint no lo dispara; deshacer el de fuera lo tira; deshacer un savepoint tira solo lo suyo.
- `apps/worker/tests/unit/test_suite_passes_end_together.py`: un fallo, el plazo agotado y el camino sano.

## Local Verification

En `./test.md`.

## Deviations from Assessment

**Corrige la evaluación, que no se toca:**

- Las pasadas huérfanas corrieron de 22:37:41.732 a 22:37:58.791 (51) y de 19:56:09.920 a 19:56:27.926 (49), no hasta las horas redondas de su tabla. Todas después de `jobs.finished`.
- Dice que los 4 `jobs.not_startable` son reclamaciones. Son 3: el cuarto, `a024f2f8` el 2026-10-31 a las 21:26:35.884, tiene `status: null`, así que su fila no se veía.

**Amplía el alcance, por ese cuarto caso:**

- SQLAlchemy dispara `after_commit` también al soltar un *savepoint*, y `section_write` escribe en uno. El aviso de `a024f2f8` salió desde `mark_tests_stale`, dentro del `client_read` `d552ebf9` que seguía corriendo (terminó a las 21:26:37.268). El consumidor no vio la fila y acusó el aviso.
- Si esa transacción confirmó después, el trabajo se quedó en cola sin nadie que lo corriera. Sin acceso a la base no se ha comprobado qué pasó con esa fila. Mientras no caduque, `live_run` la da por viva: 10 minutos en que «Probar» devuelve un trabajo que nunca va a empezar.
- El arreglo cambia cuándo corren **todos** los `after_commit` de la ficha, no solo este. Se pasaron los archivos de prueba que los usan.
- También se corrige el caso contrario: deshacer un savepoint tiraba lo que la transacción ya había dejado antes.

## Follow-ups

- Sin desplegar. La migración 0216 sale de `0215`: si otra rama añade otra antes, hay que encadenarla.
- `api/console/agent_quality.py` sigue sin comprobar si hay una pasada viva. Hoy responde siempre `409` (requisito 64): al reactivarlo, hay que pasarla por `lock_agent` y `live_run`.
- Una pasada de `scope = one` en cola no absorbe un cambio de la ficha: puede haber esa y otra de las afectadas, las dos vivas.
- Visto de paso y sin tocar:
  - El `POST …/decide` del 2026-10-31 a las 21:26:35 respondió `500` por un `DeadlockDetectedError` en `bump_content_rev`, contra otra transacción de la ficha. Al reintentar, `200`.
  - `finish_run` sobrescribe `run.summary` y pierde `sections`, así que `agent.tests.failing` sale con `sections: []`. Leído en el código, sin prueba.
