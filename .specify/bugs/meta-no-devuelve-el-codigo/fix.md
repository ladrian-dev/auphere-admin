# Bug Fix: Meta devuelve el código

- **Slug**: meta-no-devuelve-el-codigo
- **Fixed**: 2026-09-23
- **Assessment**: ./assessment.md
- **Status**: applied; pendiente de verificar en staging con el número real del owner

## Summary

`frame-src` de la consola admite `https://staticxx.facebook.com`, el frame por el
que el SDK de Facebook devuelve el código de autorización del Embedded Signup.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/console/src/proxy.ts` | modificado | `staticxx.facebook.com` en `frame-src`, con el porqué al lado |
| `apps/console/src/__tests__/csp.test.ts` | añadido | las tres piezas del SDK (script, connect, frames) están en la CSP que emite el proxy |

## Verification

- `pnpm --dir apps/console test src/__tests__/csp.test.ts` en verde.
- Staging: repetir «Conectar WhatsApp» con un número real; la tarjeta del número
  debe aparecer sin el toast de «Meta no devolvió el código».
