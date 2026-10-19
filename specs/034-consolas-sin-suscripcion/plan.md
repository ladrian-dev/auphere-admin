# Implementation Plan: las consolas son gratis mientras el Teammate se termina

**Branch**: `034-consolas-sin-suscripcion` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

## Summary

Un interruptor de configuración, `membership_enabled` (apagado por defecto), decide si
los niveles de la spec 005 atan algo. Apagado: los dos topes (`assert_can_add_teammate`,
`assert_can_add_member`) vuelven sin comprobar, `_pool_refills_for` responde que sí, los
cuatro endpoints de planes responden 404 **después** de resolver la persona (los
barridos de aislamiento siguen viendo 401/403), `GET /console/billing` lleva
`memberships_enabled` y la pantalla pinta compra de crédito y recibos. En el worker,
`apply_credit_purchase` exige `mode=payment` y `metadata.kind=credit` siempre, y los
avisos `customer.subscription.*` e `invoice.*` se ignoran con el interruptor apagado.

## Technical Context

Python 3.14 (API, worker) · Next 16 (consola). Sin dependencias nuevas, sin migraciones.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | El 404 va dentro del cuerpo, tras la persona: `tests/isolation/test_console_scope.py` y `test_lite_route_scope.py` siguen viendo 401/403 |
| II | Superficie | ☑ | `0`; se cierran puertas |
| III | Lo leído es dato | ☑ | El aviso del proveedor no abona saldo si la sesión no es de crédito |
| IV | Auditoría | ☑ | Sin escrituras nuevas |
| V | La ausencia se diseña | ☑ | Sin planes no hay pantalla de planes ni botón gris; 404 en la API |
| VI | Por API | ☑ | N/A |
| VII | Test primero | ☑ | `test_consoles_without_membership.py`, `test_billing_worker_apply.py` |
| VIII | Licencias | ☑ | Ninguna dependencia |
| IX | KB | ☑ | `[[ADR-043-consolas-sin-suscripcion]]` |

| Puerta | Respuesta | Tarea |
|---|---|---|
| Aislamiento | Ninguna garantía tocada; los barridos se conservan | T003 |
| Licencias | Ninguna | — |
| Medidor | Sin cambio | — |
