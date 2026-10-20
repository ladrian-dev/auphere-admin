# Implementation Plan: el dinero es exacto

**Branch**: `033-el-dinero-es-exacto` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

## Summary

El libro (`usage_ledger`) gana un **tipo** por asiento y deja de deducirse de la clave.
El gasto es `kind = debit` y nada más. Toda recarga (admin o Stripe) pasa por una sola
función, `add_purchased(..., kind, idempotency_key, audit)`, que bloquea la fila del
saldo, comprueba la clave, escribe asiento y saldo y — en el admin — la auditoría con el
operador, todo en una transacción. La conciliación compara el saldo recargado guardado
con el libro; la migración escribe un asiento de **apertura** por partner con la
diferencia histórica, de modo que el libro cuadra desde esta revisión. La puerta de los
turnos y el estado «sin cupo» miran el saldo recargado; el tope por cliente se repone
una vez por mes de calendario (`partner_allocations.period_month`); el saldo de un
cliente nunca supera el recargado de su partner; el consumidor no se traga un débito
fallido.

## Technical Context

Python 3.14 (API, worker) · Next 16 (panel). Migración **0158**. Sin dependencias nuevas.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | Toda lectura y escritura del libro fija `app.partner_id` (`apply_partner_to_session`); la migración rellena partner a partner con el GUC. Barrido nuevo en `tests/isolation/test_24_partner_wallet_rls.py` (`test_a_topup_writes_its_entry_under_its_own_partner`) |
| II | Superficie | ☑ | `0` |
| III | Lo leído es dato | ☑ | El aviso de Stripe solo abona con la clave de su sesión; una segunda notificación no abona |
| IV | Auditoría con persona | ☑ | Recarga: `X-Operator-Id`, actor `operator:<correo>`, misma transacción que el dinero. Tope por cliente: `console.allocation.set` con la persona |
| V | Estados honestos | ☑ | Saldo ilegible = «—», nunca cero; la conciliación dice «no cuadra» con la diferencia exacta |
| VI | Por API | ☑ | N/A |
| VII | Test primero | ☑ | `tests/integration/test_money_is_exact.py` (recarga ×5 = 1 abono, recarga no es gasto, libro cuadra tras 60 movimientos aleatorios con reintentos, edición a mano detectada, puerta por saldo recargado, saldo del cliente acotado), `test_allocation_on_purchased.py` (reloj que avanza al día 1), worker `test_allocation_debit_wiring.py` (débito fallido no se acusa) |
| VIII | Licencias | ☑ | Ninguna |
| IX | KB | ☑ | `[[ADR-044-el-dinero-es-exacto]]` |

| Puerta | Respuesta | Tarea |
|---|---|---|
| Aislamiento | Garantía 1 (RLS FORCE del libro) | T009 |
| Licencias | Ninguna | — |
| Medidor | Es el medidor; no gasta nada nuevo | — |

## Decisiones

- **Conciliar solo el saldo recargado.** El pool incluido es una asignación semanal que se
  repone entera; no es dinero.
- **Asiento de apertura en la migración**, no un ajuste silencioso: la diferencia histórica
  (saldos escritos a mano antes del 2026-09-08) queda nombrada en el libro.
- **La clave de idempotencia la genera el formulario**, una por intento confirmado; un
  error deja la misma clave para el reintento.
- **Mover tope entre clientes no cambia de semántica**: el tope es un límite, no dinero.
- `move_allocation` y `set_allocation` siguen igual; solo se audita el `PUT`.

## Migración 0158

`usage_ledger.kind` (relleno por prefijo de clave, sin valor por defecto después, CHECK),
índice `(partner_id, kind)`, asientos `opening_credit|opening_debit`, vocabulario
`console.allocation.set`, `partner_allocations.period_month`. `downgrade()` borra las
aperturas y el vocabulario y suelta las columnas.
