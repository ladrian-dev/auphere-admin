# Bug Fix: el gasto del mes del cliente se queda a cero con bolsas

- **Slug**: gasto-del-mes-a-cero-con-bolsas
- **Fixed**: 2026-11-08
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Con bolsas, el gasto del cliente se lee de su bolsa, como su saldo. Una sola
lectura (`bags.bag_spend`) da a la consola lite (Panel, Consumo y su gráfica) y
al Panel del cliente del partner el mismo total y el mismo reparto por agente,
en la moneda de la bolsa; sin bolsas, todo sigue leyendo el libro de la cuenta.
La consola formatea cada importe del cliente con la moneda que llega.

Decisiones tomadas sin el owner, para revisar:

- **El total del mes es `month_spent_micros`** de la bolsa, la cifra que ya
  enseñaba la bolsa del partner, con UTC como mes (el de la bolsa y el del tope
  de cada agente, D27). Incluye las pruebas a cargo del cliente (`debit_tests`),
  como «lo gastado este mes» del partner en Consumo.
- **El reparto por agente** son los cobros `debit_turn` y `debit_tests` del mes
  por `agent_id`, repartidos al céntimo sobre el total (`split_cents`); los de
  sin agente, del principal, como en el libro.
- **La bolsa sin tocar este mes gasta cero** (`spent_this_month`), también en la
  bolsa del partner: hasta el primer movimiento del mes, `month_spent_micros`
  guardaba lo del mes pasado.
- **El Panel del cliente del partner** tenía el mismo fallo (`month.spent`,
  `spend_by_agent` y `top_agents` a cero junto a `bag.spent` bien) y se arregla
  con la misma lectura, para que las dos vistas cuadren.
- **La moneda en la consola**: además de la tarjeta, el saldo (Panel y Consumo),
  las cifras de Consumo, su gráfica y el detalle técnico, que también pintaban
  US$ con la bolsa en EUR.

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/api/src/nexus_api/services/wallet/bags.py` | modified | `spent_this_month`, `BagSpend`, `bag_spend` (sesión del partner con `as_client`; `None` sin bolsas) |
| `apps/api/src/nexus_api/services/client_overview.py` | modified | La bolsa del partner usa `spent_this_month` |
| `apps/api/src/nexus_api/services/lite_home.py` | modified | El gasto del mes y el reparto, de la bolsa; `LiteSpendMonth.currency`; `agent_spend(burn=)` |
| `apps/api/src/nexus_api/api/console/lite/home.py` | modified | `spend_month.currency` |
| `apps/api/src/nexus_api/api/console/lite/usage.py` | modified | `/usage/summary` y `/usage/spend` con bolsas: total, reparto, proyección a 7 días y serie diaria de la bolsa (también con `?agent=`); `month.currency` |
| `apps/api/src/nexus_api/api/console/tenants.py` | modified | `/console/clients/{ref}/panel`: el mes y el reparto de la bolsa, en su moneda |
| `apps/api/tests/integration/wallet/test_client_month_spend_from_bag.py` | added test | Dos pruebas: el cuadre con turnos por `charge_turn` y la bolsa sin tocar este mes |
| `apps/console/src/lib/backend/lite.ts` | modified | `currency` en el saldo, `spend_month` y `month` |
| `apps/console/src/components/lite/lite-spend-card.tsx` | modified | La tarjeta y `MoneyFigure` en la moneda que llega (USD si no llega) |
| `apps/console/src/components/lite/lite-balance-card.tsx` | modified | El saldo de Consumo en la moneda de la bolsa |
| `apps/console/src/components/lite/lite-usage-view.tsx` | modified | Las cifras de Consumo y el detalle técnico en la moneda que llega |
| `apps/console/src/components/lite/lite-panel-view.tsx` | modified | El saldo del Panel en la moneda de la bolsa |
| `apps/console/src/lib/money.ts` | modified | `formatMoneyCompact(cents, locale, currency = "USD")` |
| `apps/console/src/app/(console)/usage/spend-chart.tsx` | modified | Formatea con `spend.currency` (el partner sigue en USD) |
| `apps/console/src/components/lite/__tests__/lite-spend-card.test.tsx` | added test | La tarjeta en EUR y, sin moneda, en US$ |
| `apps/console/src/components/lite/__tests__/lite-usage.test.tsx` | added test | Consumo entero en EUR |
| `docs/consola-lite.md`, `docs/billing.md` | modified | De dónde sale el gasto del cliente con bolsas |

## Fuera de alcance

- La app del teléfono (`apps/mobile`) lee las mismas rutas: recibe la cifra
  buena y el campo `currency` nuevo, pero su formato no se ha revisado.
- Siguen leyendo `usage_ledger` y no se han revisado con bolsas:
  `api/admin/usage_overview.py`, `api/admin/partners.py` (`credit_burn`),
  `api/console/home.py` y `/console/usage/spend` del partner. El Panel y el
  Consumo de la consola nueva del partner salen de `wallet/usage_lines`, que ya
  lee la bolsa.
