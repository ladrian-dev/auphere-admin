# Bug Fix: la tarjeta «Incluido restante» pinta el porcentaje consumido

- **Slug**: incluido-restante-muestra-lo-usado
- **Fixed**: 2026-09-23
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

La API manda `included_percent_used` (spec 004, R7.1) y la tarjeta lo pintaba tal
cual bajo la etiqueta «Incluido restante»: un partner nuevo leía «0 %» con el pool
entero. Ahora un helper puro calcula lo que **queda** (complemento del usado, o
`included_remaining / pool_size` si la API no manda la proporción, o 0 sin pool),
y el pie de la tarjeta añade la cifra absoluta y la fecha de renovación. De paso, el
pie de «Comprado restante» deja de decir «Tokens de cuota (C3)» —un código interno
de spec— y dice «Créditos comprados», la unidad que el owner fijó el 2026-09-23.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/console/src/lib/usage-projection.ts` | añadido `includedRemainingPercent()` | Puro, con el porqué escrito al lado |
| `apps/console/src/lib/__tests__/usage-projection.test.ts` | añadidos 4 tests | Pool entero = 100; complemento; derivación; recorte y sin pool |
| `apps/console/src/app/(console)/usage/page.tsx` | modificado | Usa el helper; pie con `{remaining} créditos · se renueva el {date}` |
| `apps/console/src/i18n/lanes/home-usage.ts` | modificado | `hu.usage.wallet.tokens` → «Créditos comprados»; dos claves nuevas `hu.usage.wallet.included.hint[.none]`; retiradas `hu.usage.wallet.expires[.none]`, que se quedaban sin uso |

## Diff Highlights

```ts
// usage/page.tsx — antes
const walletPercent = Math.round(wallet.included_percent_used ?? 0);

// usage/page.tsx — después
const walletPercent = includedRemainingPercent(wallet);
```

```ts
// usage-projection.ts
export function includedRemainingPercent(wallet) {
  if (typeof wallet.included_percent_used === "number" && Number.isFinite(wallet.included_percent_used)) {
    return Math.min(100, Math.max(0, Math.round(100 - wallet.included_percent_used)));
  }
  if (wallet.pool_size && wallet.pool_size > 0) {
    return Math.min(100, Math.max(0, Math.round((wallet.included_remaining * 100) / wallet.pool_size)));
  }
  return 0;
}
```

## Tests Added or Updated

`usage-projection.test.ts` › `includedRemainingPercent`: pool entero → 100 (el
caso del informe); complemento del usado (70 → 30, 100 → 0, 66,67 → 33); deriva de
cifras sin proporción (25 000 / 100 000 → 25); sin pool → 0; recorte a 0–100.

## Local Verification

```
pnpm exec tsc --noEmit                                     # limpio
pnpm exec eslint --max-warnings 0 src/app/(console)/usage … # limpio
NODE_OPTIONS=--experimental-require-module pnpm exec vitest run src/lib/__tests__/usage-projection.test.ts src/i18n
  Test Files  4 passed (4) · Tests  36 passed (36)
```

En el navegador, `/usage` del partner `demo-audit` (115 000 incluidos, cero
consumo): **«Incluido restante 100 % · 115.000 créditos · se renueva el 29 sept
2026, 19:25»** y «Comprado restante 0 · Créditos comprados».

Nota de entorno: en esta máquina hay Node 22.11 y Vite 8/rolldown exigen ≥ 22.12
(`require(esm)`); `NODE_OPTIONS=--experimental-require-module` lo salva hasta subir
Node. CI corre con Node más nuevo y no lo necesita.

## Deviations from Assessment

Ninguna.

## Follow-ups

- Renombrar el resto de «tokens»/«unidades» a «créditos» en toda la consola es el
  punto A7 del plan (`nexus/PLAN-ACCION-CONSOLA-2026-09-22.md`), no de este bug.
