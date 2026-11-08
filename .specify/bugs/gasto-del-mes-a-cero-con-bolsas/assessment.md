# Bug Assessment: el gasto del mes del cliente se queda a cero con bolsas

- **Slug**: gasto-del-mes-a-cero-con-bolsas
- **Created**: 2026-11-08
- **Source**: QA, hallazgo H-20 (consola del cliente, comprobado en el código)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

En la consola del cliente (lite), «Gasto del mes» y el gasto de cada agente se
quedan en 0,00 mientras el saldo baja unos 0,05 US$ con cada respuesta del
agente. La tarjeta, además, siempre pinta US$ aunque la bolsa esté en EUR.

## Symptom

Con un partner que cobra de las bolsas (spec 047, D25), el cliente ve:

- Panel (`/`): «Gasto del mes» 0,00 y el reparto por agente a cero.
- Consumo (`/usage`): «Gasto del mes» 0,00, sin proyección, la tabla por agente
  a cero y la gráfica de gasto plana.
- El saldo, «Cubre N de M días» y «No llega a fin de mes» sí cuadran: salen de
  la bolsa.

Lo esperado: la misma cifra que el partner ve de ese cliente (requisito 46.7 y
`contracts/lite-app-api.md` §4: «lee la bolsa del libro: la misma cifra que la
consola de partners»), en la moneda de la bolsa.

## Reproduction

1. Partner con la consola nueva y sin asignaciones de antes (`bags_active`).
2. Asignar saldo a la bolsa de un cliente con dos agentes.
3. Cobrar unos turnos por `wallet/turns.charge_turn` (el camino del medidor).
4. `GET /console/lite/home` → `spend_month.total_cents == 0` y el reparto a cero;
   `GET /console/lite/usage/summary` → `month.spent_cents == 0`;
   `GET /console/clients/{ref}/panel` (partner) → `bag.spent` > 0, pero
   `month.spent` y `spend_by_agent` también a cero.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/metering/consumer.py:424-437` — con bolsas cobra
  el turno con `charge_turn` y hace `continue`: no escribe en `usage_ledger`.
- `apps/api/src/nexus_api/services/wallet/bags.py` `debit_turn` — el cobro va a
  `client_wallet_entries` (`debit_turn`) y suma `month_spent_micros`.
- `apps/api/src/nexus_api/services/lite_home.py:331-351` — el gasto del mes y el
  reparto salen de `credit_burn` / `credit_burn_by_agent` (`usage_ledger`,
  `kind = debit`): cero con bolsas.
- `apps/api/src/nexus_api/api/console/lite/usage.py:137` (`spend_report`) y
  `/usage/spend` — el mismo libro: cero.
- `apps/api/src/nexus_api/api/console/tenants.py:1215-1228` — el Panel del
  cliente en la consola del partner lee el mismo libro para `month.spent`,
  `spend_by_agent` y `top_agents`: la misma cifra a cero, junto a `bag.spent`
  bien.
- `apps/api/src/nexus_api/services/client_overview.py:364` — la bolsa del
  partner lee `bag.month_spent_micros`: la cifra buena.
- `apps/console/src/components/lite/lite-spend-card.tsx:15-17` — formatea
  siempre en USD; también `MoneyFigure` (compartida con el saldo de Consumo), el
  saldo del Panel (`formatMoneyCompact`), las cifras de Consumo y su gráfica.

## Root Cause Hypothesis

Con bolsas el turno se cobra **solo** de la bolsa; las lecturas del gasto del
cliente siguen en el libro de la cuenta, que ya no lo ve. El saldo se arregló en
la ola 7 (`bag_balance`, 46.7) y el gasto se quedó atrás. Confianza: **alta**
(lectura directa y reproducción con la prueba de integración).

Un borde relacionado: `month_spent_micros` solo vuelve a cero al tocar la bolsa
(`_roll`). Entre el día 1 y el primer cobro del mes guarda lo del mes pasado, y la
bolsa del partner lo enseñaría como gasto de este mes.

## Proposed Remediation

**Preferred** (una sola lectura para todas las vistas):

- `bags.spent_this_month(bag, now)`: `month_spent_micros` si la bolsa es de este
  mes, cero si aún no se ha tocado. Lo usan la bolsa del partner y el cliente.
- `bags.bag_spend(partner_id, tenant_id, since, now)`: con bolsas, la moneda de la
  bolsa, su gasto del mes y sus cobros (`debit_turn` y `debit_tests`) por día UTC
  y agente; `None` con `partner_allocations`. Se lee en la sesión del partner con
  el contexto del cliente puesto (`as_client`): el tenant sale de quien entra,
  nunca de la petición.
- Panel lite, Consumo lite (resumen y gráfica) y Panel del cliente del partner:
  con bolsas, total = gasto del mes de la bolsa; reparto por agente = sus cobros
  del mes por `agent_id`, repartidos al céntimo con `split_cents`; proyección al
  ritmo de 7 días de la bolsa. Sin bolsas, el camino del libro de siempre.
- Las respuestas ganan `currency` (la de la bolsa; USD sin bolsas) y la consola
  formatea con ella la tarjeta, el saldo, Consumo y su gráfica.

**Alternative**: que el medidor escriba también un `debit` en `usage_ledger`
con bolsas. Descartada: duplicaría el dinero en dos libros, el cuadre diario
(`ledger-reconciliation-cron`) y Consumo por partidas lo contarían dos veces.

## Test plan

- Integración (`tests/integration/wallet/test_client_month_spend_from_bag.py`):
  bolsa en EUR, dos agentes, turnos por `charge_turn`; `/console/lite/home`,
  `/console/lite/usage/summary` y `/console/lite/usage/spend` dan el mismo gasto
  del mes y por agente que `/console/clients/{ref}/panel`, en EUR, y no cero.
- Integración: la bolsa sin tocar este mes no enseña el gasto del mes pasado.
- Consola: la tarjeta y Consumo formatean en la moneda que llega (EUR).
- Sin regresiones: `test_client_panel.py`, `test_lite_home.py`,
  `test_lite_usage.py`, `test_lite_by_agent.py`, aislamiento de la consola.
