# Plan: Dinero que cuadra (spec 072)

**Rama**: `072-dinero-que-cuadra` · **Fecha**: 2026-11-22 · **Spec**: `spec.md` (D1–D4 cerradas por el owner el 2026-11-21)

## Constitution Check

| Principio | Cómo se cumple |
|---|---|
| Tests primero | Cada requisito tiene su test antes del cambio: el formato (`amount.test.ts`, `money.test.ts`, `format.test.ts`), la barra (`clients-list-v2`, `client-panel`), las partes del gasto (`test_usage_lines.py`), Consumo (`usage-proto`), las barras macizas (`block-chart.test.tsx`) y los diálogos (`assign-dialog`, `buy-credit-form`). |
| Aislamiento | Sin lecturas nuevas. El único cambio de servidor filtra partidas de lecturas que ya eran del partner que pregunta. No hace falta un test de aislamiento nuevo. |
| Superficie | `0`. |
| Puente con la KB | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`, lote 4. |
| Medición | Nada nuevo. |
| Compartido con el Admin | `formatCurrency` de `@nexus/ui` no cambia: lo usa el Admin. La consola usa la nueva `currencyFormat` y `formatUnits`. `BlockChart` solo lo usa la consola. |

## Por dónde va cada requisito

| Requisito | Dónde |
|---|---|
| §1 Formato único | `packages/ui/src/lib/format.ts` (`currencyFormat`), `apps/console/src/lib/amount.ts` (delega en `formatMoney` en español; `formatUnits`), `lib/money.ts`, Facturación y `home/spend-card.tsx`. Una prueba barre `src` y falla con `style: "currency"` o `formatCurrency` (1.4). |
| §2 Barras con lo que queda | `clients/v2/client-v2-model.ts` (`bagBar`, `bagPace`), `clients/v2/bag-meter.tsx` (nuevo), `clients-list-v2.tsx`, `client-panel.tsx`, `home/partner-panel.tsx` (2.5). |
| §3 Gasto del mes | API: `services/partner_panel.py` (solo las bolsas), `api/console/usage_lines.py` (`_CLIENT_BAGS`). Consola: `partner-panel.tsx` (`BuildLine`, nombres enteros), `app/(console)/page.tsx` (lee el tope de construcción). |
| §4 Consumo | `app/(console)/usage/usage-v2.tsx`, `money/usage-figure.tsx` (marca), `money/meta-mark.tsx` + `public/third-party/meta.svg`, `money/usage-detail.tsx` (Companion), `money/spend-by-day.tsx` (sin partida). Fuera `money/usage-lines.tsx`. |
| §5 Barras macizas | `packages/ui/src/components/block-chart.tsx`, `tokens.css` (`bar-grow`). |
| §6 Elegir un importe | `money/amount-option.tsx` (nuevo), `money/assign-dialog.tsx`, `billing/buy-credit-form.tsx`. |

## Lecturas de la spec (research)

- **R1, 1.1.** «Una delega en la otra»: `formatAmount` delega en `formatMoney` de `@nexus/ui` para el euro y el dólar en español, así que el texto es idéntico. En inglés usa Intl con `currencyDisplay: "code"` para el dólar («USD 10.00»). Con esto, en español los miles se agrupan siempre («1.500,00 €»), como ya hacía `formatMoney`.
- **R2, 2.1 en Consumo.** La tabla de Consumo no trae lo asignado (`ClientUsage` no tiene `assigned`), así que no hay de qué sacar el porcentaje. Allí no se pinta barra: ya dice lo que queda y los días en sus columnas, y «Saldo bajo» con texto (071). No hay ninguna barra al revés que corregir.
- **R3, 2.3.** Solo `state: "low"` va en ámbar. `not_enough` («no llega a fin de mes») no, para no contradecir la lista de la 071, que no lo cuenta como saldo bajo.
- **R4, 3.1.** El total del Panel es la suma de las bolsas de sus clientes. La consulta del Panel solo lee esas dos partidas (`conversations`, `client_tests`). El contrato de `/console/home` no cambia de forma: `kind: "line"` deja de salir, pero sigue en el esquema.
- **R5, 3.4.** El Panel lee el tope con `GET /console/usage/build-budget` (quien tiene `usage:read`). Desde el 80 % usa la fila de la 071, que manda la API.
- **R6, 4.3.** El periodo del gasto del mes va del día 1 a hoy en UTC, como lo cuenta la API (`periodLabel`).
- **R7, §5 y §6.** Las lecturas del ayudante: el eje en pasos de 1, 2 o 5 × 10ⁿ con un mínimo de un céntimo en dinero; hoy es la última columna si ninguna lo dice; un recibo de cuatro líneas, con el cambio del BCE como nota bajo «Asignas»; el tinte `bg-primary/10` con borde primario en los dos diálogos.
