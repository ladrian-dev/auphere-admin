# Bug Assessment: la tarjeta «Incluido restante» pinta el porcentaje consumido

- **Slug**: incluido-restante-muestra-lo-usado
- **Created**: 2026-09-23
- **Source**: auditoría de la consola, evidencia viva del 2026-09-22 (KB `nexus/INFORME-AUDITORIA-CONSOLA-2026-09-22.md`, «Evidencia viva», fila «b. Consumo»)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim)

> **«Incluido restante 0 %»** con `included_remaining = 115 000` en BD: la tarjeta
> pinta `included_percent_used` bajo la etiqueta *restante*. «Comprado restante 0 ·
> Tokens de cuota (C3)».

Partner `demo-audit` recién creado, sin consumo. `partner_wallets`:
`included_remaining = 115000`, `included_expires_at = 2026-09-29`. `/usage` muestra
la tarjeta «INCLUIDO RESTANTE» con el valor «0%».

## Symptom

Un partner nuevo abre Consumo y lee que le queda el 0 % de lo incluido, cuando le
queda el 100 %. La cifra es correcta para otra etiqueta («usado»), pero la tarjeta
dice «restante». Es el primer número que ve un partner sobre su saldo y es falso:
viola el principio V de la constitución (la pantalla no miente).

## Reproduction

1. Stack local arriba (`preview_start api` / `console`), partner con wallet sembrada
   y sin consumo (cualquier partner nuevo: `seed_console_memberships.py`).
2. Entrar como owner y abrir `/usage`.
3. La tarjeta «Incluido restante» muestra `0%`; en BD
   `select included_remaining from partner_wallets` devuelve el pool entero.

## Suspected Code Paths

- `apps/console/src/app/(console)/usage/page.tsx:58-60` —
  `const walletPercent = Math.round(wallet.included_percent_used ?? 0);` y luego
  `value={`${walletPercent}%`}` bajo `label={t("hu.usage.wallet.included")}`
  («Incluido restante»).
- `apps/api/src/nexus_api/api/console/wallet.py:101-116` — la API calcula
  `included_percent_used = used * 100 / pool_size` (spec 004, R7.1: «el consumo
  incluido se presenta como proporción»). La API es coherente con su nombre.
- `apps/console/src/lib/backend/home-usage.ts:91-101` — tipo `Wallet` con
  `included_percent_used?` y `pool_size?`.

## Root Cause Hypothesis

La spec 004 pidió que lo incluido se presentara «como proporción, no como cifra».
La API expuso la proporción **usada** y la consola la pintó tal cual bajo la etiqueta
que ya existía, «Incluido restante», sin invertirla. Con consumo cero (todo partner
recién creado y todo lunes tras la renovación semanal) el resultado es «0 %».

## Proposed Remediation

Pintar el complemento (`100 − included_percent_used`), con un helper puro y
testeado en `lib/usage-projection.ts` que además cubra el caso en que la API no
manda la proporción (deriva de `included_remaining / pool_size`) y el de pool
inexistente (0). Añadir la cifra absoluta en el pie de la tarjeta («115.000
créditos · se renueva el 29 sept») para que la proporción tenga contexto, y
retirar de paso «Tokens de cuota (C3)» del pie de la tarjeta de al lado, que es un
código interno de spec (decisión del owner 2026-09-23: la unidad se llama
«créditos»).

No se toca la API: `included_percent_used` es correcto y otros consumidores
(Companion) lo leen como «usado».

## Files likely to change

- `apps/console/src/lib/usage-projection.ts` (helper)
- `apps/console/src/lib/__tests__/usage-projection.test.ts` (tests)
- `apps/console/src/app/(console)/usage/page.tsx` (usar el helper y el pie nuevo)
- `apps/console/src/i18n/lanes/home-usage.ts` (dos claves nuevas, una corregida)

## Tests to add or update

- `includedRemainingPercent`: pool entero → 100; complemento del usado; deriva de
  cifras si falta la proporción; sin pool → 0; recorte a 0–100.

## Risks & Considerations

- Ninguno funcional: es una vista. El riesgo era seguir enseñando un 0 % falso.
- La etiqueta «Incluido restante» se mantiene; solo cambia el número y el pie.

## Open Questions

- Ninguna. La unidad «créditos» está decidida por el owner (2026-09-23).
