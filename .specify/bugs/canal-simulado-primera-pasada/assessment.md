# Bug Assessment: la primera pasada de pruebas de un cliente nuevo falla al crear su canal simulado

- **Slug**: canal-simulado-primera-pasada
- **Created**: 2026-11-03
- **Source**: pasted text — logs de `/nexus/staging/runner`, encontrado al diagnosticar `autprod-staging`
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

`jobs.handler_failed` con `kind=tests` y `UniqueViolationError` en
`uq_channels_live_number`. Aparece dos veces en 14 días de logs de staging, una
por cliente y justo en su primera pasada:

| Tenant | Cliente | Cuándo (UTC) |
|---|---|---|
| `116ca2a6-…` | `meta-review-demo` | 2026-10-30 22:37:40 |
| `6d3e5a76-…` | `jemma-s-hair` | 2026-11-03 19:56:08 |

## Symptom

La primera pasada de pruebas de un cliente termina con el trabajo en `failed`.
Lo esperado es que corra sus pruebas, tenga o no ya el canal simulado.

## Reproduction

1. Tener un cliente sin canal `qa_playground`, es decir, que nunca ha abierto el
   playground ni ha corrido pruebas.
2. Llamar a `open_conversation` dos o más veces a la vez para ese cliente, que es
   lo que hace `run_suite` con varias pruebas.
3. Las llamadas que pierden la carrera lanzan `IntegrityError`.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/simulation/runner.py:106` (`_channel`) — comprueba
  si existe el canal y, si no, lo inserta. Entre las dos cosas no hay nada que
  impida a otra transacción hacer lo mismo.
- `apps/api/src/nexus_api/db/models/channel.py:69` — `uq_channels_live_number` es
  único por `(type, provider_identifier)`, y `provider_identifier` lleva el
  `tenant_id`: solo pueden chocar llamadas del mismo cliente.
- `apps/worker/src/nexus_worker/jobs/handlers/agent_tests.py:313` — `asyncio.gather`
  corre hasta `PARALLEL = 4` pasadas a la vez sin `return_exceptions`, y
  `_attempt` llama a `open_conversation` en la línea 138, fuera de su `try`. La
  excepción sube por `gather` y tumba el trabajo.

## Root Cause Hypothesis

Comprobar y luego insertar, sin defensa ante la concurrencia. Confianza alta en
el mecanismo: el código lo permite, la restricción incumplida solo admite el
mismo cliente, y los dos casos son primeras pasadas. Las pasadas siguientes
encuentran el canal y no pueden fallar por esto.

Confianza media en de qué concurrencia se trató en cada caso. Hubo un solo
`POST …/test-runs` y dos trabajos `tests` en el mismo segundo: uno falló
(`20969182-…`) y otro terminó (`702d794a-…`). No se ha determinado de dónde salió
el segundo. El arreglo no depende de ello, porque cubre las dos variantes.

## Proposed Remediation

**Preferred**: que `_channel` tolere la carrera. Insertar dentro de un savepoint
(`session.begin_nested()`, el mismo patrón de `build_budget.request_more`) y, ante
`IntegrityError`, volver a leer: el índice único espera a que la otra transacción
confirme, así que la fila ganadora ya es visible en `READ COMMITTED`.

**Alternatives**:
- `INSERT … ON CONFLICT DO NOTHING`: repetiría el predicado del índice parcial en
  el código y se rompería en silencio si cambia. El savepoint no depende de él.
- Crear el canal una vez antes de `gather`: arregla una suite, pero no dos trabajos
  a la vez ni el playground abierto durante una pasada.

**Files likely to change**:
- `apps/worker/src/nexus_worker/simulation/runner.py`
- Una prueba de integración nueva junto a las del playground

**Tests to add or update**:
- Con un cliente sin canal, varias `open_conversation` a la vez terminan todas bien
  y comparten un único canal.

## Risks & Considerations

- La relectura debe hacerse tras el rollback del savepoint, no del bloque exterior,
  para no perder lo que la transacción ya llevaba.
- Fuera de alcance: si `gather` falla por otro motivo, las pasadas hermanas siguen
  corriendo con el trabajo ya en `failed` y gastando modelo. Es otro fallo y no se
  ha medido.

## Open Questions

- De dónde salió el segundo trabajo `tests` en el mismo segundo. No bloquea el
  arreglo.
