# Bug Assessment: no había dos trabajos `tests`: las pasadas de uno siguen corriendo cuando ya falló

- **Slug**: pasadas-huerfanas-tras-fallar-el-trabajo
- **Created**: 2026-11-03
- **Source**: pasted text (Luis, sesión del 2026-11-03), `.specify/bugs/canal-simulado-primera-pasada/` y logs de staging
- **Verdict**: valid, con la premisa corregida
- **Severity**: medium

## Report (verbatim or summarized)

> Dos trabajos `tests` del mismo cliente en el mismo segundo. Si se lanzan dos pasadas,
> se paga dos veces el modelo. Encuentra quién encola, demuestra la causa y hazlo
> idempotente en el origen.

Casos: tenant `116ca2a6` el 2026-10-30 22:37:40 UTC y tenant `6d3e5a76` el 2026-11-03
19:56:08 UTC.

## Symptom

**La premisa no se sostiene.** No hubo dos trabajos en el mismo segundo. Hubo un
trabajo que falló en 283 ms y cuyas pasadas siguieron corriendo en segundo plano.

Lo que sí es cierto: una pasada puede seguir gastando modelo con su trabajo ya
`failed`, y al volver a pulsar se suma otra encima. Esa es la forma real de pagar dos
veces. Lo esperado es que ninguna pasada sobreviva a su trabajo.

## Reproduction

Lo que dicen los logs (`/nexus/staging/api` y `/nexus/staging/runner`, 30 días, solo
lectura):

| Hora (UTC) | Qué | Fuente |
|---|---|---|
| 10-30 22:37:39.599 | `POST …/test-runs` 202, una sola | api |
| 10-30 22:37:40.385 | `347e1301` `failed/internal`, 283 ms | runner |
| 10-30 22:37:40 → 22:37:46 | 51 `jobs.tests.attempt_failed` **después de terminar** | runner |
| 11-03 19:56:07.267 | `POST …/test-runs` 202 | api |
| 11-03 19:56:08.450 | `20969182` `failed/internal`, 282 ms | runner |
| 11-03 19:56:08 → 19:56:30 | 49 `jobs.tests.attempt_failed` **después de terminar** | runner |
| 11-03 19:58:12.465 | `POST …/test-runs` 202, otra persona pulsando otra vez | api |
| 11-03 19:58:12 → 19:58:31 | `702d794a` `done`, 19 s | runner |

La nota anterior decía «un solo `POST` y dos trabajos en el mismo segundo». No es así:
hay dos `POST` con dos minutos de diferencia, y `702d794a` empieza con el segundo.

En 30 días: 12 trabajos `tests` terminados y 12 `POST` (11 con `202` y uno con `402`).
Once salen de un `POST` con la misma hora; el otro (`ef1ea4a8`, 10-31 21:26:23) no
tiene `POST`, así que es de `mark_tests_stale`. **Ningún par se solapa y ninguno empieza
a menos de 5 s de otro.** Un trabajo cuyo proceso murió sin escribir `jobs.finished` no
saldría en este recuento.

Para reproducirlo: una suite con varias pruebas, que una pasada lance algo fuera de su
`try`. El trabajo queda `failed` y las demás pasadas siguen.

## Suspected Code Paths

Los productores de `kind="tests"`, todos los que hay (`create_job`, único sitio que crea
`Job(`):

| Productor | ¿Idempotente hoy? |
|---|---|
| `api/console/agent_tests.py::start_run` | Sí: bloquea la fila del agente y devuelve la viva (T217) |
| `services/business/writes.py::mark_tests_stale` | **No**: sin bloqueo, y solo se junta con una `business_change` en cola |
| `api/console/agent_quality.py` | Suspendido: `refuse_model_policy_change()` responde siempre `409` |

Y uno que no es de ese `kind` pero corre la misma suite y paga lo mismo:

| `jobs/handlers/agent_publish.py::_needs_run` | **No**: no mira si hay otra viva, y `live_run` no lo ve a él |

La reentrega no es otra fuente: `start_job` es `UPDATE … WHERE status = 'queued'`. Los 4
`jobs.not_startable` del periodo son reclamaciones de trabajos que ya estaban corriendo.

El defecto en sí:

- `apps/worker/src/nexus_worker/jobs/handlers/agent_tests.py:313` — `asyncio.gather` sin
  `return_exceptions`: al fallar una pasada, `gather` propaga la excepción y **no cancela
  a las demás**. Siguen, con su `usage_turn`, hasta acabar la suite.
- Mismo archivo, `run_suite`: si falla, la fila de la pasada se queda en `running` para
  siempre.
- `apps/api/src/nexus_api/services/business/writes.py:522` — `pending` con `FOR UPDATE` no
  bloquea nada si no hay filas (dos escrituras a la vez encolan dos), y mira
  `AgentTestRun.status = 'queued'` sin mirar el trabajo: si ese trabajo caducó, la fila
  sigue `queued` y **se traga todos los cambios siguientes**.

## Root Cause Hypothesis

Confianza alta en el mecanismo: lo reproducen la prueba y los logs, y cuadra el recuento
(`20969182`: 17 pruebas × 3 = 51 pasadas, menos las 2 que lanzaron, son las 49 del log).

La carrera de `uq_channels_live_number` fue el disparador en estos dos casos y ya está
arreglada, pero cualquier otra excepción (el juez, la base) deja a las pasadas igual de
huérfanas.

En estos dos casos no se pagó nada, porque el partner no tenía clave
(`missing partner virtual key`). Con clave, se habría pagado.

## Proposed Remediation

**Preferred**:

1. `run_suite` cancela las pasadas hermanas al primer fallo y espera a que terminen antes
   de propagarlo. Ninguna sobrevive a su trabajo, así que «Reintentar» no se suma a nada.
2. La pasada se cierra como `failed` con `stopped` cuando no termina. Una fila no se
   queda `running` para siempre.
3. `mark_tests_stale`, bajo el bloqueo de la fila del agente, y preguntando a `live_run`
   y no a la columna `status`: una viva **en cola** de `all` o `affected` recoge el cambio,
   porque aún no ha empezado.
4. `live_run` ve también la suite de un trabajo `publish`. Pedir otra con esa en marcha es
   `409 suite_running`; publicar con otra en marcha falla con `suite_running`.

**Alternatives**:

- `asyncio.TaskGroup`: hace lo mismo, pero `str(ExceptionGroup)` se come el error que
  escribe `jobs.handler_failed`.
- Un índice único parcial por agente en `agent_test_runs`: la fila no refleja la caducidad
  del trabajo, y una fila muerta bloquearía al agente para siempre.
- Que `publish` espere a la pasada viva: más cómodo, pero añade un bucle de espera dentro
  de un trabajo con plazo.

**Una excepción que se mantiene a propósito**: con una pasada **en marcha**, un cambio de
la ficha sí encola otra. La que corre empezó antes del cambio y no lo cubre. La siguiente
se junta en esa misma cola.

**Files likely to change**: `jobs/handlers/{agent_tests,agent_publish}.py`,
`services/testing/runs.py`, `services/business/writes.py`, `api/console/agent_tests.py`,
`docs/agentes.md`.

**Tests to add or update**: integración con `PARALLEL` real.

## Risks & Considerations

- El bloqueo de `mark_tests_stale` es `FOR NO KEY UPDATE`: choca con el de `start_run` pero
  no bloquea las inserciones que validan la FK de `agents`.
- `mark_tests_stale` corre dentro de una escritura de la ficha. Toma el bloqueo después de
  tocar las pruebas, y `start_run` no escribe pruebas: no hay ciclo.

## Open Questions

- Ninguna.
