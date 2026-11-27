# Bug Fix: un adelanto por lista de espera no respalda la respuesta

- **Slug**: adelanto-por-lista-de-espera-no-respalda
- **Fixed**: 2026-11-27
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

El freno cuenta `waitlist_accepted` como reserva hecha o movida en el ciclo, y el
informe del piloto lo cuenta como movida, salvo cuando acompaña al `created` de un alta
desde la lista (misma reserva, misma hora).

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/worker/src/nexus_worker/runtime/booking_brake.py` | modificado | `_MADE_OR_MOVED` incluye `waitlist_accepted` |
| `apps/api/src/nexus_api/services/client_report.py` | modificado | `WAITLIST_ACCEPTED`; `_agenda` lo lee y `agenda_counts` lo cuenta como `moved` si no hay un `created` de la misma reserva a la misma hora |
| `apps/api/tests/isolation/test_080_booking_brake_customer_cycle.py` | modificado | Prueba del freno con un adelanto por lista de espera en el ciclo, y desde otro negocio |
| `apps/api/tests/unit/test_083_cycles.py` | modificado | Recuento puro: adelanto = movida; alta desde la lista = solo creada |
| `apps/api/tests/integration/console/test_client_report.py` | modificado | Lo mismo por el endpoint del informe, contra la base |
| `docs/agentes.md` | modificado | Los eventos que respaldan, con `waitlist_accepted` |

## Docs

`docs/agentes.md`, el párrafo de la spec 080 sobre el freno: la lista de eventos que
respaldan incluye `waitlist_accepted`.
