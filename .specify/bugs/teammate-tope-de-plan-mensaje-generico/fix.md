# Bug Fix: el tope del plan se cuenta como avería pasajera

- **Slug**: teammate-tope-de-plan-mensaje-generico
- **Fixed**: 2026-09-15
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

El rechazo por tope de plan ya no se presenta como un fallo transitorio. La pantalla
distingue «tu plan no incluye teammates» de «tu plan admite N y ya tienes N», nombra
Cuenta como el sitio donde se cambia, y ninguna de las dos frases dice «vuelve a
intentarlo». Los números que la API manda a propósito dejan de tirarse.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/desktop/src/app/i18n.ts` | modificado | Tres claves nuevas en `es` y `en`: `tier_none`, `tier_full` y el respaldo sin números |
| `apps/desktop/src/app/routes/new-teammate.tsx` | modificado | `tier_limit_reached` entra en `KNOWN_ERRORS`; `TierCap`, `tierCopyKey` y `capOf` |
| `apps/desktop/src/app/App.tsx` | modificado | Deja de tirar `res.body`: lo pasa por `capOf` |
| `apps/desktop/tests/new-teammate-form.test.tsx` | modificado | 10 casos nuevos sobre los 13 que ya había |

## Diff Highlights

```tsx
// App.tsx — antes
if (!res.ok) return { ok: false as const, error: res.code ?? "unknown" };

// App.tsx — después
if (!res.ok) return { ok: false as const, error: res.code ?? "unknown", ...capOf(res.body) };
```

```tsx
// new-teammate.tsx — qué frase toca
export function tierCopyKey(cap: TierCap | undefined): AppKey {
  if (!cap || !Number.isFinite(cap.limit)) return "create.failed.tier_limit_reached";
  return cap.limit === 0 ? "create.failed.tier_none" : "create.failed.tier_full";
}
```

La copia, en `es`:

- `tier_none` — «Tu plan no incluye teammates. Para crear uno hay que cambiar de plan,
  en Cuenta.»
- `tier_full` — «Tu plan admite {limit} teammates y ya tienes {current}. Archiva uno o
  cambia de plan, en Cuenta.»
- `tier_limit_reached` — «Tu plan no permite crear más teammates. Puedes cambiarlo en
  Cuenta.»

Tres decisiones dentro de esas frases:

1. **Ninguna dice «vuelve a intentarlo».** Era la palabra que convertía un rechazo
   correcto en una avería, y manda a la persona a repetir lo único que no puede
   funcionar.
2. **`tier_none` no ofrece archivar.** Con un tope de cero no hay nada que liberar;
   sugerirlo sería mandarla a buscar una salida que no existe.
3. **Las dos nombran Cuenta**, que es la pantalla que ya lleva a la consola
   (`account.tsx:233`). Sin eso la frase explica el muro y no la puerta.

## Tests Added or Updated

En `tests/new-teammate-form.test.tsx`, que tenía 13 casos y ahora tiene 23.

Cuatro sobre la pantalla:
- con `limit: 0` dice que es el plan, **no** dice «vuelve a intentarlo», nombra Cuenta y
  **no** ofrece archivar;
- con `limit: 3, current: 3` da los dos números y sí ofrece archivar;
- sin `cap` sigue diciendo que es el plan y no pinta `undefined`, `NaN` ni llaves;
- lo escrito sobrevive al rechazo.

Seis sobre `capOf`, y existen porque **el resto no lo cubría**: el formulario recibe
`cap` ya hecho, así que los cuatro de arriba pasarían igual con la lectura del cuerpo
rota — que es justo la mitad del fallo que vivía en `App.tsx`. Uno usa la forma literal
que aplana `_guard.ts:90`; los otros cinco son cuerpos malformados (nulo, cadena, sin
campos, `limit` de texto, sin `tier`) y esperan `{}`.

## Local Verification

**Rojo antes de tocar el código**, con el texto del fallo en la salida:

```
 × … > con un plan sin teammates, dice que es el plan y no manda reintentar 30ms
   → Expected element to have text content:
       /no incluye teammates/i
     Received:
       No se pudo crear. No se ha creado nada; vuelve a intentarlo.
 × … > con el plan lleno, da los dos números y ofrece archivar 31ms
   → Expected element to have text content:
       /3/
     Received:
       No se pudo crear. No se ha creado nada; vuelve a intentarlo.
```

**Verde después**: `Tests  23 passed (23)`.

**Dos pruebas de mutación**, una por cada mitad del fallo:

```
══════ MUTACIÓN 1: la pantalla vuelve a tratarlo como error genérico ══════
      Tests  2 failed | 21 passed (23)

══════ MUTACIÓN 2: capOf vuelve a tirar el cuerpo, como App.tsx:296 ══════
      Tests  1 failed | 22 passed (23)
```

La segunda mata un solo caso, y es correcto: los cinco de cuerpo malformado esperan `{}`
y bajo esa mutación siguen acertando por accidente. Solo el que usa la forma buena la
caza. Queda anotado para que nadie lea ese `1 failed` como cobertura floja.

**Suite completa del escritorio y typecheck:**

```
> @nexus/desktop@0.1.1 test
 Test Files  41 passed (41)
      Tests  373 passed (373)

> @nexus/desktop@0.1.1 typecheck
> tsc --noEmit && tsc --noEmit -p tsconfig.app.json
   (sin salida)
```

### Lo que esta verificación NO cubre

**Nadie ha visto la frase nueva contra la API de verdad.** Los tests mockean `onSubmit` y
`capOf` se prueba con cuerpos escritos a mano a partir de lo que `_guard.ts` promete. Que
el 422 real de un partner en Free llegue con esa forma exacta está leído en el código de
los tres tramos, no observado en vivo. Se confirma en cuanto se instale 0.1.2 en una
máquina con la cuenta de prueba: es un clic.

## Deviations from Assessment

Una, y añade cobertura en vez de quitarla.

La evaluación listaba `App.tsx` entre los ficheros a cambiar y daba por hecho que la
lectura del cuerpo viviría ahí. Al escribir los tests se vio que **ahí no la cubre
nadie**: el arnés de `new-teammate-form.test.tsx` mockea `onSubmit`, así que una `capOf`
rota en `App.tsx` habría dejado los cuatro casos de pantalla en verde. Se movió junto a
`TierCap` y `tierCopyKey` en `new-teammate.tsx` —misma concernencia, módulo que el test
ya importaba— y se le escribieron seis casos propios. `App.tsx` la importa.

## Follow-ups

- **Va en 0.1.2**, agrupado con el updater y el empaquetado, por decisión del 2026-09-15.
- **Queda la pregunta de §V**, sin bloquear: la constitución dice que la ausencia se
  diseña, y el propio fichero ya lo aplica para «cero modelos». Un partner en Free nunca
  podrá terminar este formulario. No ofrecerlo exige que la app conozca el tope, y
  `/api/teammates/usage` no devuelve `max_teammates` — eso es spec, no bug. La frase
  seguiría haciendo falta igualmente para el caso `limit > 0`.
- `teammate-settings.tsx` comparte `isKnownError` y hereda la clave nueva. Ahí
  `tier_limit_reached` no se puede dar —editar no crea nada— así que no se tocó.
