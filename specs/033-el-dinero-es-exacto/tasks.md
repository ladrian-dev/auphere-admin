# Tasks: el dinero es exacto

- [X] T001 Tests en rojo `apps/api/tests/integration/test_money_is_exact.py`. _Requisitos: 2.2, 2.3, 2.4, 3.1–3.3, 5.1, 6.2_
- [X] T002 Migración `0158_ledger_kind_and_monthly_cap` (tipo, apertura, `period_month`, vocabulario) y modelos. _Requisitos: 2.1, 6.1, 7.3_
- [X] T003 Todo escritor declara el tipo (débito, caducidad del cron, recargas); `_spend_only()` = `kind = debit`. _Requisitos: 2.1, 2.3_
- [X] T004 `add_purchased` atómico e idempotente con gancho de auditoría; `reconcile_purchased`. _Requisitos: 2.2, 2.4, 3.2, 3.3_
- [X] T005 Admin: `POST …/wallet/purchased` en centavos con clave y `X-Operator-Id` (extraído a `api/admin/operator.py`); `GET …/wallet` y `…/ledger` en centavos con tipo y cliente; `GET …/wallet/reconcile`. _Requisitos: 1.1, 1.2, 3.1–3.3, 2.4_
- [X] T006 Worker: compra Stripe por `add_purchased` con `stripe_credit:{sesión}`; un duplicado es `Skip`. _Requisitos: 3.4_
- [X] T007 Débito: solo la clave única cuenta como duplicado; el consumidor relanza el fallo (reintento + DLQ). _Requisitos: 4.1, 4.2_
- [X] T008 Puerta y `quota_state` por saldo recargado; pruebas que esperan un cliente servido le dan saldo recargado (`give_recharged_balance`). _Requisitos: 5.1_
- [X] T009 Barrido de aislamiento: el asiento de una recarga es invisible para otro partner. _Requisitos: 2.2_
- [X] T010 Tope mensual: `replenish_allocations` por `period_month`, llamado en cada tick del cron; prueba con reloj. _Requisitos: 6.1_
- [X] T011 Saldo del cliente acotado por el recargado del partner (consola lite: Panel y Consumo). _Requisitos: 6.2_
- [X] T012 Alertas: % sobre el gasto recargado del mes y el saldo. _Requisitos: 7.1_
- [X] T013 Uso del partner en el admin: gasto del libro en centavos y coste interno en decimal. _Requisitos: 7.2_
- [X] T014 Auditoría `console.allocation.set` en `PUT /console/clients/{ref}/allocation`. _Requisitos: 7.3_
- [X] T015 Panel: pestaña Dinero en US$ (resumen, recarga con confirmación, conciliación, libro con tipos), uso con gasto/coste separados; `lib/money.ts` con pruebas. _Requisitos: 1.1, 1.2, 2.4, 7.2_
- [ ] T016 Suite completa API + worker + panel en verde; `docs/billing.md`; ADR-044.
