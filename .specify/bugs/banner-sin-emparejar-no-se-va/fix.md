# Bug Fix: el banner de «sin emparejar» no se va al emparejar

- **Slug**: banner-sin-emparejar-no-se-va
- **Fixed**: 2026-09-15
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`AppRuntime` anuncia que la credencial guardada cambió —al canjear y al olvidar— y la
cáscara responde volviendo a derivar el veredicto de `SessionGate`. Manda la puerta,
porque es la que lee la credencial donde está.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/desktop/src/app-runtime.ts` | modificado | `onIdentityChanged`, disparado tras `store.put` en `pair()` y tras `store.forget` en `unpair()` |
| `apps/desktop/src/electron/main.ts` | modificado | Una línea: `runtime.onIdentityChanged(() => void gate.refresh())` |
| `apps/desktop/tests/app-runtime-identity.test.ts` | modificado | 4 casos nuevos sobre los 17 que había |

## Diff Highlights

```ts
// app-runtime.ts — en pair(), al final y no antes
this.setBar({ kind: "pair_ok", machine: { … } });
if (!this.running) await this.start();
// Quien escuche va a volver a derivar el veredicto, y debe encontrar el
// almacén y la barra ya en su sitio.
this.announceIdentityChanged();
```

```ts
// main.ts — la única línea de pegamento
runtime.onIdentityChanged(() => void gate.refresh());
```

## Tests Added or Updated

Cuatro casos en `app-runtime-identity.test.ts`, en un grupo nuevo. Tres de ellos cablean
`AppRuntime` y `SessionGate` **sobre el mismo almacén, como hace `main.ts`**, así que
prueban el camino entero y no solo el anuncio:

- emparejar y desemparejar anuncian el cambio;
- un código inválido **no** anuncia nada, porque no se guardó nada;
- tras emparejar, el veredicto que recibiría el banner pasa de `pair_needed` a `start`
  **y** la barra queda en `conectada` — las dos superficies, que es lo que fallaba;
- al desemparejar, el veredicto vuelve a `pair_needed`.

## Local Verification

**Rojo antes del arreglo**, los cuatro:

```
 × … > avisa de que la identidad cambió al emparejar y al desemparejar 3ms
   → app.onIdentityChanged is not a function
 × … > un código que no vale no anuncia nada: no se guardó nada 0ms
 × … > tras emparejar, el veredicto que recibe el banner deja de ser pair_needed 0ms
 × … > y al desemparejar el banner vuelve a aparecer 0ms
```

**Verde después**: `Tests  21 passed (21)` en ese fichero.

**Prueba de mutación** — quitado el anuncio de `pair()`:

```
══════ MUTACIÓN: quitar el anuncio de pair() ══════
⎯⎯⎯⎯⎯⎯⎯ Failed Tests 3 ⎯⎯⎯⎯⎯⎯⎯
      Tests  3 failed | 18 passed (21)
```

**Suite completa y typecheck:**

```
 Test Files  42 passed (42)
      Tests  382 passed (382)

> tsc --noEmit && tsc --noEmit -p tsconfig.app.json
   (sin salida)
```

### Lo que esta verificación NO cubre

**La línea de `main.ts` no la prueba nadie.** Es pegamento de Electron, y el test cablea
a mano lo que esa línea cablea en producción: si alguien la borra, los tests siguen en
verde. Es la misma frontera que el resto de `src/electron/`, y el arreglo se diseñó para
que **lo único** que quede fuera sea una suscripción de una línea.

Tampoco se ha visto el banner desaparecer en una app de verdad; eso llega con 0.1.2.

## Deviations from Assessment

Ninguna en el diseño. Un tropiezo al escribir el test: usé `new PairingFailed("invalid_code")`
y el tipo solo admite `"pairing_code_invalid" | "pairing_rate_limited"`. Lo cazó
`tsc --noEmit`, no la suite — los tests pasaban en verde con el código inventado, porque
a vitest le daba igual. Anotado porque es justo el motivo por el que `typecheck` va en
`verify.sh` y no solo el `test`.

## Follow-ups

- Va en **0.1.2**, con los otros tres.
- Queda cerrada la pregunta que el documento original dejaba abierta: **manda la puerta**.
  Si algún día aparece una tercera superficie que cuente este mismo hecho, se suscribe al
  mismo sitio en vez de inventarse su propia fuente.
