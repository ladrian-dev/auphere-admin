# Bug Assessment: la suite de un agente no decide, se repite y frena la puerta

- **Slug**: la-suite-no-decide-y-se-repite
- **Created**: 2026-11-04
- **Source**: Luis (sesión del 2026-11-04), consola y logs de staging
- **Verdict**: valid
- **Severity**: high

## Report

«El constructor está poniendo más casos de los que debería: en Más ajustes hay una serie
de cosas larguísima.»

## Symptom

«Ana» (`jemma-s-hair`, `027d068d`) tiene 19 pruebas: 7 del caso y 12 del sector.

- **Se repiten.** 6 de las 7 del caso preguntan lo mismo que una del sector.
- **No deciden.** 11 de las 17 que corren salen «No sé» en cada pasada, y se pagan igual.
- **Frenan.** Una crítica en «No sé» bloquea la puerta (`critical_test_failing`). Las 5
  versiones guardadas se guardaron saltándosela; 10 de 18 trabajos `publish` en 7 días
  terminaron `gate_blocked`.
- **No se enteran.** Con Google Calendar conectado, «Pide cita para mañana» sigue «No
  aplica» y «Pide cita sin agenda», crítica, espera lo contrario.

## Root cause

1. `judge_warnings` da `judge_same_model` y `_decide` no llama al juez: sin variables de
   modelo en el despliegue, agente, cliente simulado y juez son todos `gpt-5.6-sol`. El
   log `tests.judge_warning` salió 20 veces en 7 días. Una prueba sin estado final se
   queda sin nada que la decida.
2. `offline_output` escribe lo común y `add_sector_tests` añade la batería sin mirar.
3. `not_applicable_reason` se calcula una vez, al crear el agente.
4. El mundo simulado solo cuenta como cita lo que pasa por `reservas.*`, así que una cita
   por un conector no cumplía `booking.created`.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/jobs/handlers/agent_tests.py`, `_decide`.
- `apps/worker/src/nexus_worker/platform_models.py`.
- `apps/worker/src/nexus_worker/simulation/world.py`, `final_state`.
- `apps/api/src/nexus_api/services/testing/sector_catalog.py`, `add_sector_tests`.
- `apps/api/src/nexus_api/services/builder/agent_draft.py`, `write_new_agent`.
