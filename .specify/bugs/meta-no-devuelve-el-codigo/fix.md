# Bug Fix: Meta devuelve el código

- **Slug**: meta-no-devuelve-el-codigo
- **Fixed**: 2026-09-23
- **Assessment**: ./assessment.md
- **Status**: applied; pendiente de verificar en staging con el número real del owner

## Summary

Dos cabeceras de la consola impedían que el SDK de Facebook devolviera el código
del Embedded Signup: `frame-src` no admitía `staticxx.facebook.com` (el frame de
vuelta) y `Cross-Origin-Opener-Policy: same-origin` cortaba `window.opener` con
la ventana de Meta. Ahora `frame-src` admite el host y la COOP es
`same-origin-allow-popups`.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/console/src/proxy.ts` | modificado | `staticxx.facebook.com` en `frame-src`, con el porqué al lado |
| `apps/console/next.config.ts` | modificado | COOP `same-origin-allow-popups`, con el porqué al lado |
| `apps/console/src/__tests__/csp.test.ts` | añadido | las tres piezas del SDK (script, connect, frames) están en la CSP que emite el proxy |

## Verification

- `pnpm --dir apps/console test src/__tests__/csp.test.ts` en verde.
- Staging: repetir «Conectar WhatsApp» con un número real; la tarjeta del número
  debe aparecer sin el toast de «Meta no devolvió el código».
