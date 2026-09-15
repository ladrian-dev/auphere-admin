# Bug Fix: el actualizador nunca se arma en el binario publicado

- **Slug**: updater-no-arranca
- **Fixed**: 2026-09-15
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`electron-updater` es CommonJS y expone `autoUpdater` con un getter perezoso que
`cjs-module-lexer` no reconoce, así que desde ESM el desestructurado del espacio de
nombres daba `undefined`. Se toma ahora por `default`, y el rechazo de `startUpdater`
se registra en vez de morir como aviso en `stderr`.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/desktop/src/electron/updater.ts` | modificado | El import pasa por `default`; el porqué queda escrito al lado, incluida la advertencia de que vitest no lo reproduce |
| `apps/desktop/src/electron/main.ts` | modificado | `catch` sobre `startUpdater`: se traga la excepción a propósito, pero la registra |
| `apps/desktop/tests/updater-module-shape.test.ts` | añadido | Cuatro tests: dos de reproducción en Node real, dos que vigilan el punto de llamada |

## Diff Highlights

```ts
// updater.ts — antes
const { autoUpdater } = await import("electron-updater");

// updater.ts — después
const updaterModule = await import("electron-updater");
const { autoUpdater } = updaterModule.default ?? updaterModule;
```

```ts
// main.ts — después
await startUpdater({ … }).catch((error: unknown) => {
  console.error("[updater] no se pudo armar", error);
});
```

## Tests Added or Updated

`apps/desktop/tests/updater-module-shape.test.ts`, cuatro casos en dos grupos:

- **`la forma real del módulo … (Node ESM, no vitest)`** — la reproducción. Lanza un
  `node --input-type=module` como subproceso porque **vitest no puede reproducir el
  fallo**: su interop de CJS sí expone la exportación nombrada.

  ```
  bajo vitest   → 'autoUpdater' in mod === true
  bajo node ESM → 'autoUpdater' in mod === false
  ```

  Un test escrito con el `import` de vitest habría estado verde antes del arreglo. Los
  dos casos afirman `ausente` en el espacio de nombres y `presente` bajo `default`. Si
  `electron-updater` publica ESM algún día, el primero se pone rojo y avisa de que el
  rodeo sobra.

- **`cómo lo carga la cáscara`** — lo que vigila el código, recorriendo el fuente. No
  llama a la función **a propósito**: leer `.autoUpdater` dispara el getter, que
  construye `MacUpdater` y necesita `electron.app`, así que fuera de Electron lanza por
  una causa distinta — un test que llamara estaría rojo siempre y se volvería verde por
  accidente en cuanto alguien lo envolviera en un `try`. Es el recurso que ya usan
  `no-own-auth.test.ts` y `no-credentials-over-ipc.test.ts`.

## Local Verification

**El test se vio rojo antes de tocar el código** (2 de 4):

```
 ✓ … > NO expone `autoUpdater` como exportación nombrada 59ms
 ✓ … > sí lo expone bajo `default`, que es de donde hay que sacarlo 57ms
 × … > no desestructura `autoUpdater` directamente del import dinámico 2ms
   → expected '/**\n * El updater — spec 001, Requis…' not to match /\{[^}]*\bautoUpdater\b[^}]*\}\s*=\s*a…/
 × … > pasa por `default` antes de leer `autoUpdater` 0ms
   → expected '/**\n * El updater — spec 001, Requis…' to match /\.default\s*\?\?/

 Test Files  1 failed (1)
      Tests  2 failed | 2 passed (4)
```

**Verde después:**

```
 Test Files  1 passed (1)
      Tests  4 passed (4)
```

**Prueba de mutación** — se revirtió el arreglo al desestructurado original y el test
volvió a rojo, que es lo que demuestra que vigila algo:

```
MUTADO: vuelto al desestructurado que rompió v0.1.0
 × … > no desestructura `autoUpdater` directamente del import dinámico 2ms
 × … > pasa por `default` antes de leer `autoUpdater` 0ms
⎯⎯⎯⎯⎯⎯⎯ Failed Tests 2 ⎯⎯⎯⎯⎯⎯⎯
```

**Suite completa del escritorio y typecheck:**

```
> @nexus/desktop@0.1.1 test
 Test Files  41 passed (41)
      Tests  363 passed (363)

> @nexus/desktop@0.1.1 typecheck
> tsc --noEmit && tsc --noEmit -p tsconfig.app.json
   (sin salida)
```

Los 363 son los 359 de antes más los 4 nuevos.

### Lo que esta verificación NO cubre

**Nadie ha visto todavía el actualizador armarse de verdad.** Eso exige un binario
empaquetado y firmado, que es justo el contexto donde el fallo vivía escondido. La
prueba de que el camino entero funciona es **T031 de la spec 008** —instalar N, publicar
N+1, ver el ciclo completo con una tarea esperando— y sigue sin ejecutarse. Hasta
entonces lo verificado es que el módulo se carga por donde debe, no que la actualización
llegue.

## Deviations from Assessment

Una, y cambió el diseño del test.

La evaluación proponía un test que importara `electron-updater` con el `import` de
vitest y afirmara sobre la forma del módulo. **Eso habría dado un falso verde**: se
comprobó antes de escribirlo y vitest expone `autoUpdater` como nombrada (`true`) donde
Node real no lo hace (`false`). La evaluación daba por supuesto que el entorno de tests
y el del `.app` ven el mismo módulo, y no es así.

El test se rediseñó en dos mitades: la reproducción sale a un `node` de verdad por
subproceso, y el punto de llamada se vigila recorriendo el fuente. El criterio de
aceptación no cambió; cambió por dónde se comprueba.

No hubo ampliación de alcance: los ficheros tocados son los tres que la evaluación
listaba.

## Follow-ups

- **No publicar 0.1.2 todavía.** Por decisión de Luis del 2026-09-15 va agrupado con el
  arreglo del empaquetado hinchado, que aún no está hecho.
- **Las notas de versión tienen que decir que este arreglo no se auto-entrega.** El
  canal está en 0.1.1 con el mismo updater roto: toda máquina con 0.1.0 o 0.1.1 instala
  0.1.2 **a mano**, y a partir de ahí sí se actualiza sola.
- **T031 de la spec 008** deja de ser deuda opcional: es la única prueba de que el
  camino que este arreglo enciende funciona de punta a punta.
- `updater.ts` sigue sin test de comportamiento, solo de forma y de fuente. La cabecera
  del fichero dice que el pegamento no se cubre; ahora está cubierto a medias y
  conviene que alguien decida si eso se queda así o `startUpdater` se hace inyectable.
