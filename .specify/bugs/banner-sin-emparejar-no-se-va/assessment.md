# Bug Assessment: el banner de «sin emparejar» no se va al emparejar

- **Slug**: banner-sin-emparejar-no-se-va
- **Created**: 2026-09-15
- **Source**: pasted text (`docs/bugs-app-escritorio-2026-09-15.md` §2, reproducido por Luis)
- **Verdict**: valid
- **Severity**: medium

## Report

> Se empareja la máquina con el código y el emparejamiento funciona, pero el banner
> superior sigue diciendo que no está emparejada.

## Symptom

Tras un emparejamiento correcto, **la barra se actualiza y el banner de la pantalla no**.
Las dos superficies quedan diciendo cosas contrarias sobre el mismo hecho, y la que
miente es la más visible.

## Reproduction

1. Abrir la app con una persona cuyo partner no tiene esta máquina emparejada.
2. La pantalla pinta el banner `session.pair` y la barra dice «Esta máquina no está
   emparejada».
3. Introducir un código válido en la barra.
4. La barra pasa a `conectada` con el nombre de la máquina. **El banner sigue ahí.**

## Suspected Code Paths

- `apps/desktop/src/app/App.tsx:266` — `session?.kind === "pair_needed"` pinta el banner.
- `apps/desktop/src/app/App.tsx:95` — `session` se alimenta **solo** de `app:session`.
- `apps/desktop/src/electron/main.ts:223-233` — `app:session` se empuja **solo** desde
  `gate.onDecision`, y `main.ts:353` una vez al arrancar.
- `apps/desktop/src/electron/main.ts:234` — `gate.watch(sessionCookieWatcher())`: la
  única cosa que vuelve a evaluar la puerta es un cambio de la **cookie de sesión**.
- `apps/desktop/src/electron/main.ts:282` — `onSessionLost: () => void gate.refresh()`:
  el único `refresh()` explícito, y solo cuando el BFF contesta «sin sesión».
- `apps/desktop/src/app-runtime.ts:283-286` — `pair()` guarda la credencial y actualiza
  **la barra**. Nada más se entera.
- `apps/desktop/src/app-runtime.ts:295-300` — `unpair()`, el problema espejo.

## Root Cause Hypothesis

**Confianza: alta.**

Hay dos superficies leyendo el mismo hecho por caminos distintos:

| | Quién la mueve | Cuándo |
|---|---|---|
| Barra | `runtime.setBar(...)` | En cada evento del puente, incluido `pair_ok` |
| Banner | `gate.onDecision` → `app:session` | Al arrancar, al cambiar la cookie, y en `onSessionLost` |

Emparejar cambia el **almacén de credenciales**, que es de donde
`SessionGate.evaluate()` saca su veredicto (`session-gate.ts:56`). Pero emparejar no
toca la cookie y no pierde la sesión, así que **nada vuelve a preguntarle a la puerta**.
El banner se queda con el último veredicto, que era `pair_needed`, hasta el siguiente
cambio de cookie — que puede no llegar en horas.

`unpair()` tiene el mismo agujero al revés: olvida la credencial y el banner **no**
aparece.

## Proposed Remediation

**Primero, la decisión que la hipótesis del documento original dejaba abierta: manda la
puerta.**

No es arbitrario. `SessionGate.evaluate()` deriva su veredicto del almacén de
credenciales, que es donde la credencial **está**; la barra refleja eventos del puente,
que es una consecuencia. Hacer que el banner escuche a la barra sería conectar dos
consecuencias entre sí y dejar la fuente sin consultar. Emparejar cambia la fuente, así
que lo que toca es **volver a derivar**.

**El cambio**: `AppRuntime` anuncia que la identidad guardada cambió, y la cáscara
responde refrescando la puerta.

```ts
// app-runtime.ts
onIdentityChanged(listener: () => void): () => void
// se dispara tras `store.put(...)` en `pair()` y tras `store.forget(...)` en `unpair()`

// main.ts — una línea de pegamento
runtime.onIdentityChanged(() => void gate.refresh());
```

Por qué así y no llamando a `gate.refresh()` dentro del handler de `bar:pair`: el runtime
no debe conocer la puerta —hoy no la conoce— y el anuncio es cierto para cualquier cosa
que cambie la credencial, no solo para el canje desde la barra. Además deja la parte que
decide en un módulo puro con test, y en la cáscara solo la suscripción.

**Alternativa descartada**: empujar `app:session` a mano desde el handler de `bar:pair`.
Funciona para este caso y deja el de `unpair` abierto, más cualquier camino futuro. Y
sobre todo, **fabrica** un veredicto en vez de derivarlo: el día que la puerta tenga una
condición más (una pertenencia revocada, por ejemplo), esa copia mentiría.

**Sin riesgo de bucle**: `gate.refresh()` acaba en `runtime.applyGate(...)`, que no toca
el almacén, así que no vuelve a disparar el anuncio.

**Files likely to change**:
- `apps/desktop/src/app-runtime.ts`
- `apps/desktop/src/electron/main.ts`
- `apps/desktop/tests/app-runtime-identity.test.ts`

**Tests to add or update**:
- Emparejar anuncia el cambio de identidad; desemparejar también.
- **El que importa**: cableando `AppRuntime` y `SessionGate` sobre el mismo almacén como
  hace `main.ts`, el veredicto que recibiría el banner pasa de `pair_needed` a `start` al
  emparejar, y vuelve a `pair_needed` al desemparejar. Sin el anuncio se queda en
  `pair_needed`, que es el fallo.

## Risks & Considerations

- **Roce en la barra, no defecto.** Tras emparejar, `applyGate` con `start` vuelve a
  poner `restored` y luego `session_same_person`; los dos resuelven a `conectada` con los
  mismos valores. Es ruido interno, no algo que se vea.
- `gate.refresh()` hace una petición de red (`whoami`). Emparejar es un acto manual y
  poco frecuente: una petición más ahí no es un coste.
- **No toca ninguna frontera de tenant.** La puerta sigue decidiendo igual y la
  credencial de otra persona sigue sin ser legible (`session-gate.ts:59`). Ninguna de las
  7 garantías queda rozada.
- **Sin dependencias nuevas** (§VIII).

## Open Questions

Ninguna. La que el documento original dejaba abierta —«cuál de las dos manda»— se
resuelve arriba: manda la puerta, porque es la que lee la fuente.
