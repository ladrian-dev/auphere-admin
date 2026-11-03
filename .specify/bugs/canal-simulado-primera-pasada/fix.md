# Bug Fix: la primera pasada de pruebas de un cliente nuevo falla al crear su canal simulado

- **Slug**: canal-simulado-primera-pasada
- **Fixed**: 2026-11-03
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`_channel` crea el canal simulado dentro de un savepoint y, si otra conversación se
le adelanta, relee el que ganó. La primera pasada de un cliente ya no termina en
`failed` por abrir conversaciones en paralelo.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/simulation/runner.py` | modified | Savepoint y relectura ante `IntegrityError` |
| `apps/api/tests/integration/builder/test_playground_channel_race.py` | added test | `PARALLEL` conversaciones a la vez en un cliente sin canal |

## Tests Added or Updated

- `test_playground_channel_race.py::test_first_conversations_at_once_share_one_channel` — todas terminan bien, comparten un canal y solo existe uno.

## Local Verification

- Antes del arreglo: `pytest tests/integration/builder/test_playground_channel_race.py` → rojo con `UniqueViolationError` en `uq_channels_live_number`, el mismo error que en staging.
- Después: la misma prueba, tres veces seguidas → verde.
- `pytest tests/integration/builder/test_playground_draft.py tests/integration/connectors/test_playground_never_reaches_the_business.py` → 7 verdes.

## Deviations from Assessment

Ninguna.

## Follow-ups

- Sin desplegar hasta que la rama llegue a `develop`.
- Sigue abierto de dónde salió el segundo trabajo `tests` del mismo segundo.
- Fuera de alcance: si `gather` falla por otro motivo, las pasadas hermanas siguen corriendo con el trabajo ya en `failed`.
