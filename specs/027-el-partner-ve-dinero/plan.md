# Implementation Plan: el partner ve, asigna y gasta dinero

**Branch**: `develop` | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)

## Summary

El libro sigue en créditos. Todo lo que la API de consola entrega o recibe del
partner sobre saldo, topes, restante y gasto pasa a **céntimos de dólar**
(`*_cents`, enteros, `currency: "USD"`). Una sola tasa y una sola conversión en
`nexus_api/billing/pricing.py`; la consola formatea céntimos y convierte lo que
escribe el partner a céntimos, nunca a créditos. El Companion lee y propone en
dólares. El panel de Auphere sigue en créditos.

## Technical Context

**Language/Version**: Python 3.14 · TypeScript 5 / Next.js 16
**Primary Dependencies**: ninguna nueva
**Storage**: sin migración. Los topes y saldos siguen guardados en créditos
**Testing**: pytest (unit + integration de wallet, home, companion), vitest, e2e de textos
**Constraints**: conversión exacta de dinero a créditos (1 céntimo = 1.000 créditos) · redondeo único de créditos a dinero · ninguna cifra en créditos para el partner · trabajo en `develop`

## Constitution Check

| # | Principio | ¿Cumple? | Prueba |
|---|---|---|---|
| I | Aislamiento | ☑ | Mismos endpoints partner-scoped; solo cambia la unidad |
| II | Superficie | ☑ | `0` |
| III | Lo leído es dato | ☑ | Sin texto nuevo de fuera |
| IV | Acción con aprobación | ☑ | El tope propuesto por el Companion sigue pasando por aprobación, ahora en dólares |
| V | La pantalla no miente | ☑ | Fuera la proyección de mensajes etiquetada como créditos; el mismo saldo al céntimo en todas partes (CE-003) |
| VII | Test primero | ☑ | Tabla de conversión en ambos sentidos antes de tocar endpoints |

## Decisiones

- **D1 · Unidad de contrato**: céntimos enteros (`*_cents`) más `currency`. Sin decimales en JSON: un float de dinero miente en el último céntimo.
- **D2 · Conversión**: `cents_to_credits(c) = c * 1000` (exacta). `credits_to_cents(q)` redondea al céntimo **hacia abajo** para saldos y restantes (nunca enseñar dinero que no hay) y **al más cercano** para gasto. Las dos viven en `billing/pricing.py`; `console_home_blocks.credits_to_cents` y `units_for_cents` pasan a usarlas.
- **D3 · Entradas**: `cap_cents` y `amount_cents` enteros ≥ 0 / ≥ 1. La API deja de aceptar `cap` y `qty` en créditos de la consola. Los errores devuelven `*_cents`.
- **D4 · Companion**: `console.get_wallet` y `console.list_allocations` devuelven dólares; `console.propose_allocation` recibe `cap_usd` (número con hasta dos decimales) y la propuesta guarda `cap_cents`.
- **D5 · Incluido**: se enseña en dólares con su fecha de renovación (clarificación). `pool_size` sale de la respuesta: el partner ve lo que le queda, no el tamaño de la bolsa.
- **D6 · Lo que no cambia**: tope de mensajes, Playground, medidor del Companion, multiplicadores ×n, panel Admin, payload interno de los avisos.

## Project Structure

```
apps/api/src/nexus_api/billing/pricing.py            # tasa + conversiones (única fuente)
apps/api/src/nexus_api/api/console/{wallet,tenants,home,billing}.py + schemas_*.py
apps/api/src/nexus_api/services/console_home_blocks.py
apps/api/src/nexus_api/companion/tools/{catalog,proposals,actions}.py + evals
apps/console/src/lib/money.ts                         # formatMoney / parseMoney
apps/console/src/app/(console)/usage/**               # saldo, reparto, tope, mover
apps/console/src/app/(console)/page.tsx + components/home/**
apps/console/src/components/clients/**                # ficha, lista, paso de crédito
apps/console/src/components/billing/buy-credit-form.tsx
apps/console/src/i18n/**                              # textos sin créditos/unidades/tokens/cupo
```
