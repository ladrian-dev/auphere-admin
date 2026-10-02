# Tasks: el partner ve, asigna y gasta dinero

**Input**: `/specs/027-el-partner-ve-dinero/` · **Tests**: no opcionales (§VII). Trabajo en `develop`.

- [X] T001 Tasa y conversiones únicas en `apps/api/src/nexus_api/billing/pricing.py` (`CREDITS_PER_CENT`, `cents_to_credits`, `credits_to_cents` con redondeo hacia abajo y al más cercano), con tabla de pruebas en `tests/unit/test_billing_pricing.py`; `console_home_blocks` y la compra usan esas. _Req 1_
- [X] T002 Saldo y reparto en céntimos: `schemas_wallet.py` y `wallet.py` (`WalletOut`, `AllocationOut`, `AllocationIn.cap_cents`, `MoveAllocationIn.amount_cents`, errores en céntimos, sin `pool_size`), tests de integración. _Req 1, 3, 5_
- [X] T003 Cupo del cliente en céntimos (`ClientQuotaOut`) en detalle y lista de clientes. _Req 2_
- [X] T004 Inicio en céntimos: `HomeCreditOut`, `CreditRiskOut`, `PortfolioRowOut`, `HomeSpendOut` sin créditos. _Req 2_
- [X] T005 Companion en dólares: `console.get_wallet`, `console.list_allocations`, `console.propose_allocation(cap_usd)`, propuesta y acción en céntimos, evals sin tokens. _Req 4_
- [X] T006 Consola: `lib/money.ts` (`formatMoney`, `parseMoney`) con tests; fuera `UNITS_PER_USD`. _Req 1, 3_
- [X] T007 Consumo: saldo (incluido, comprado, disponible, reserva), tabla de reparto, tope, asignar y mover en dólares. _Req 2, 3, 5_
- [X] T008 Inicio: crédito disponible, clientes en riesgo y gasto sin créditos. _Req 2_
- [X] T009 Ficha y lista de clientes en dólares; proyección de gasto en dólares o fuera (bug de mensajes como créditos). _Req 2_
- [X] T010 Compra: «Recibirás X US$ de saldo», sin unidades. _Req 2_
- [X] T011 Textos: barrido de «créditos», «unidades», «tokens», «cupo» en lo que ve el partner sobre saldo, con test que lo vigila. _CE-001_
- [ ] T012 e2e y verificación en la consola local, push a `develop`, staging, evidencia, KB.

## Notas de entrega (2026-10-02)

- Contrato de consola en céntimos (`*_cents`, `currency: "USD"`); la API rechaza `cap` y `qty` en créditos (422).
- Redondeo: saldos y restantes hacia abajo, gasto al céntimo más cercano. CE-002 probado: lo que se escribe es lo que se lee.
- `pool_size` deja de viajar; el incluido se ve en dólares con su porcentaje como dato secundario.
- El Companion propone `cap_usd` como texto («40», «25.50»), sin floats.
- La proyección de la ficha (mensajes con la etiqueta «créditos») se quitó: no hay todavía una proyección de gasto por cliente fiable.
- En la tabla de topes el botón de guardar solo aparece en la fila cambiada (regla de los tres puntos).
- Fuera de esta entrega: el detalle técnico de Consumo por medidor (mensajes, tokens, multimedia) sigue en sus unidades; pasarlo a dinero por medidor es otra iteración. El panel de Auphere sigue en créditos.
