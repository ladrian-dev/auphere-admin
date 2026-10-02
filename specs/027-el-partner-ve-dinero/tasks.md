# Tasks: el partner ve, asigna y gasta dinero

**Input**: `/specs/027-el-partner-ve-dinero/` · **Tests**: no opcionales (§VII). Trabajo en `develop`.

- [ ] T001 Tasa y conversiones únicas en `apps/api/src/nexus_api/billing/pricing.py` (`CREDITS_PER_CENT`, `cents_to_credits`, `credits_to_cents` con redondeo hacia abajo y al más cercano), con tabla de pruebas en `tests/unit/test_billing_pricing.py`; `console_home_blocks` y la compra usan esas. _Req 1_
- [ ] T002 Saldo y reparto en céntimos: `schemas_wallet.py` y `wallet.py` (`WalletOut`, `AllocationOut`, `AllocationIn.cap_cents`, `MoveAllocationIn.amount_cents`, errores en céntimos, sin `pool_size`), tests de integración. _Req 1, 3, 5_
- [ ] T003 Cupo del cliente en céntimos (`ClientQuotaOut`) en detalle y lista de clientes. _Req 2_
- [ ] T004 Inicio en céntimos: `HomeCreditOut`, `CreditRiskOut`, `PortfolioRowOut`, `HomeSpendOut` sin créditos. _Req 2_
- [ ] T005 Companion en dólares: `console.get_wallet`, `console.list_allocations`, `console.propose_allocation(cap_usd)`, propuesta y acción en céntimos, evals sin tokens. _Req 4_
- [ ] T006 Consola: `lib/money.ts` (`formatMoney`, `parseMoney`) con tests; fuera `UNITS_PER_USD`. _Req 1, 3_
- [ ] T007 Consumo: saldo (incluido, comprado, disponible, reserva), tabla de reparto, tope, asignar y mover en dólares. _Req 2, 3, 5_
- [ ] T008 Inicio: crédito disponible, clientes en riesgo y gasto sin créditos. _Req 2_
- [ ] T009 Ficha y lista de clientes en dólares; proyección de gasto en dólares o fuera (bug de mensajes como créditos). _Req 2_
- [ ] T010 Compra: «Recibirás X US$ de saldo», sin unidades. _Req 2_
- [ ] T011 Textos: barrido de «créditos», «unidades», «tokens», «cupo» en lo que ve el partner sobre saldo, con test que lo vigila. _CE-001_
- [ ] T012 e2e y verificación en la consola local, push a `develop`, staging, evidencia, KB.
