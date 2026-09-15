# Bug Assessment: el actualizador nunca se arma en el binario publicado

- **Slug**: updater-no-arranca
- **Created**: 2026-09-15
- **Source**: pasted text (salida cruda del binario instalado, ejecutado desde la terminal)
- **Verdict**: valid
- **Severity**: critical

## Report (verbatim)

Ejecutando el binario instalado de `/Applications` en la máquina de Luis, donde la
aplicación por lo demás funciona:

```
(node:53798) UnhandledPromiseRejectionWarning: TypeError: Cannot set properties of undefined (setting 'autoDownload')
    at startUpdater (file:///Applications/Auphere.app/Contents/Resources/app.asar/dist/electron/updater.js:71:30)
    at process.processTicksAndRejections (node:internal/process/task_queues:104:5)
    at async file:///Applications/Auphere.app/Contents/Resources/app.asar/dist/electron/main.js:396:13
(Use `Auphere --trace-warnings ...` to show where the warning was created)
(node:53798) UnhandledPromiseRejectionWarning: Unhandled promise rejection. This error originated either by throwing inside of an async function without a catch block, or by rejecting a promise which was not handled with .catch(). (rejection id: 1)
```

## Symptom

En un binario **empaquetado y firmado**, `startUpdater` lanza un `TypeError` en cuanto
pasa la decisión de comprobar, y muere ahí. Se esperaba que armara `electron-updater`,
fijara el canal y empezara el ciclo de cuatro horas; en vez de eso la promesa queda
rechazada sin manejar y **la aplicación nunca comprueba si hay versión nueva**.

El canal (`updates.auphere.com`) está construido, firmado, notarizado y sirviendo
correctamente — `latest-mac.yml` y los cuatro paquetes de 0.1.0 y 0.1.1 están
publicados. Simplemente no lo consulta nadie.

## Reproduction

La reproducción completa del síntoma exige un binario firmado, pero **la causa se
reproduce en Node puro**, sin Electron, sin empaquetar y sin firmar:

```
$ node --input-type=module -e '
  const mod = await import("<ruta>/electron-updater/out/main.js");
  console.log(Object.keys(mod).filter(k => k !== "default").length, "nombradas");
  console.log("mod.autoUpdater             ->", mod.autoUpdater);
  console.log("\"autoUpdater\" in mod.default ->", "autoUpdater" in mod.default);
'
17 nombradas
mod.autoUpdater             -> undefined
"autoUpdater" in mod.default -> true
```

Las 17 que Node sí detecta: `AppImageUpdater, AppUpdater, BaseUpdater,
CancellationToken, DOWNLOAD_PROGRESS, DebUpdater, MacUpdater, NoOpLogger,
NsisUpdater, PacmanUpdater, Provider, RpmUpdater, UPDATE_DOWNLOADED, UpdaterSignal,
__esModule, addHandler, module.exports`. `autoUpdater` no está.

Para el síntoma entero:

1. Etiquetar y dejar que `release-desktop.yml` publique, o construir y firmar a mano.
2. Instalar el `.app` resultante.
3. Lanzarlo desde la terminal: `/Applications/Auphere.app/Contents/MacOS/Auphere`.
4. El `TypeError` sale en los primeros segundos.

## Suspected Code Paths

- `apps/desktop/src/electron/updater.ts:91` — `const { autoUpdater } = await import("electron-updater");`.
  El desestructurado de una exportación que Node no expone como nombrada. Es el origen.
- `apps/desktop/src/electron/updater.ts:92` — `autoUpdater.autoDownload = true;`. Donde
  lanza. Compila a `dist/electron/updater.js:71`, que es la línea del rastro.
- `apps/desktop/src/electron/updater.ts:95,96,100,104,115,127` — el resto de usos de
  `autoUpdater` (`setFeedURL`, los dos `on`, `quitAndInstall`, `checkForUpdates`).
  Todos inalcanzables hoy, y todos se arreglan con el mismo cambio.
- `apps/desktop/src/electron/main.ts:453` — `await startUpdater({...})` dentro del
  `app.whenReady().then(async () => …)` **sin `catch`**. Es lo que convierte el fallo
  en un aviso en `stderr` que nadie ve, en vez de en algo registrado.
- `node_modules/.pnpm/electron-updater@6.8.9/node_modules/electron-updater/out/main.js:78`
  — la forma exacta que rompe la detección (ver abajo).
- `apps/desktop/package.json` — `"type": "module"`, que es lo que pone todo esto en
  contexto ESM.

## Root Cause Hypothesis

**Confianza: alta.** Está probado, no inferido.

`electron-updater@6.8.9` es CommonJS puro (`package.json` solo declara
`main: out/main.js` — sin `type`, sin `exports`, sin `module`) y expone `autoUpdater`
como *getter perezoso*:

```js
// out/main.js:78
Object.defineProperty(exports, "autoUpdater", {
    enumerable: true,
    get: function () { return _autoUpdater || doLoadAutoUpdater(); }
});
```

Node construye las exportaciones nombradas de un CJS importado desde ESM con
`cjs-module-lexer`, que es un analizador **estático**. Reconoce
`Object.defineProperty(exports, …)` únicamente cuando el cuerpo del getter es una
reexportación simple. Aquí el cuerpo es `_autoUpdater || doLoadAutoUpdater()` y no
encaja, así que `autoUpdater` **no** entra en el espacio de nombres. El valor real
sigue estando, colgado de `default`.

Por eso `const { autoUpdater } = await import("electron-updater")` da `undefined` y la
asignación de la línea siguiente lanza.

El getter es perezoso a propósito: construye `MacUpdater`, que necesita `electron.app`.
Eso importa para el arreglo y para el test — tocar `.autoUpdater` fuera de Electron
lanza por una razón **distinta**, y un test descuidado confundiría las dos.

### Por qué no se cazó antes

La línea es **inalcanzable salvo en un binario empaquetado y firmado**:

| Contexto | `app.isPackaged` | `detectBuildKind()` | `decideUpdate` | ¿Llega al import? |
|---|---|---|---|---|
| `pnpm start` / desarrollo | `false` | `unpackaged` | `do-not-check` | **No** — retorna en la 88 |
| Tests (`vitest`) | no hay Electron | — | — | **No** — nadie llama a `startUpdater` |
| `--dir` sin firmar | `true` | `adhoc` | `do-not-check` | **No** |
| Publicado y firmado | `true` | `signed` | `check` | **Sí** |

La primera vez que ese código se ejecutó fue la publicación real del 2026-09-14.

Y la cobertura refuerza el hueco: `tests/update-policy.test.ts` cubre el módulo puro de
decisión, que está **bien** y decidió correctamente `check`. `updater.ts` no tiene
ningún test, por la decisión declarada en su propia cabecera («pegamento… lo que decide
está en `update-policy.ts`»). El fallo vive exactamente en el pegamento que se decidió
no cubrir.

## Proposed Remediation

**Preferido.** Tomar el módulo por `default` con respaldo al espacio de nombres, en un
solo sitio y con la razón escrita al lado:

```ts
// `electron-updater` es CJS y expone `autoUpdater` como getter perezoso, que
// cjs-module-lexer no detecta como exportación nombrada: desde ESM el
// desestructurado directo da `undefined`. El valor vive en `default`.
const updaterModule = await import("electron-updater");
const { autoUpdater } = updaterModule.default ?? updaterModule;
```

El `?? updaterModule` no es adorno defensivo: si una versión futura de
`electron-updater` publica ESM o cambia la forma del getter, el código sigue
funcionando en vez de romperse al revés.

Y **manejar el rechazo en `main.ts`**, que es la mitad que convirtió un fallo duro en un
aviso invisible. Que el updater no arranque no puede tumbar la aplicación —el puente y
la pantalla son más importantes— pero tiene que quedar registrado:

```ts
await startUpdater({ ... }).catch((error: unknown) =>
  console.error("[updater] no se pudo armar", error),
);
```

**Alternativa considerada y descartada**: `createRequire(import.meta.url)("electron-updater")`.
Funciona y es explícita sobre el CJS, pero introduce un segundo mecanismo de carga en un
fichero que ya usa `import` dinámico, y no aporta nada sobre `.default`.

**Sobre la decisión de no cubrir el pegamento: se revisa, no se deroga.** La cabecera de
`adapters.ts` la justifica bien —«probarlos con dobles solo demostraría que los dobles
hacen lo que les dijimos»— y eso sigue siendo cierto para un adaptador que solo delega.
Pero aquí lo que falló no es la delegación: es **la forma del módulo importado**, que es
un hecho verificable sobre una dependencia real y no un doble. Un test que afirme sobre
el paquete de verdad no es un doble confirmando lo que le dijimos: es exactamente el
contrato que se rompió.

## Files likely to change

- `apps/desktop/src/electron/updater.ts`
- `apps/desktop/src/electron/main.ts`
- `apps/desktop/tests/updater-module-shape.test.ts` (nuevo)

## Tests to add or update

1. **`updater-module-shape.test.ts`** — el test del criterio de aceptación. Importa
   `electron-updater` **de verdad** (no un doble) desde un contexto ESM y afirma que el
   accesor que usa el código da algo definido:
   - `(mod.default ?? mod).autoUpdater` no es `undefined` — es lo que el código lee.
   - Se comprueba con `Object.getOwnPropertyDescriptor` / `"autoUpdater" in …`, **sin
     leer el valor**: leerlo dispara el getter perezoso, que construye `MacUpdater` y
     lanza fuera de Electron por un motivo distinto. Un test que confunda las dos causas
     pasaría a verde por accidente.
   - Se afirma además que el desestructurado ingenuo (`mod.autoUpdater`) **es**
     `undefined`, para que el test documente el porqué del rodeo y se ponga rojo si
     alguien «simplifica» el código de vuelta.
2. Si `electron-updater` sube de versión y publica ESM, el punto 1 seguirá en verde y el
   punto 2 se pondrá rojo. Eso es correcto: avisa de que el rodeo ya no hace falta.

## Risks & Considerations

- **Esto enciende un camino que nunca ha corrido.** Hoy el updater no hace nada; con el
  arreglo empezará a descargar e instalar en las máquinas de los partners. Todo lo que
  hay detrás —`decideUpdate`, `install-on-quit`, la espera por trabajo vivo— está
  cubierto por `update-policy.test.ts` pero **nunca se ha ejecutado de verdad**. Es
  justo lo que T031 de la spec 008 existe para recorrer, y sigue sin hacerse.
- **Qué versión se instalará.** El canal está en 0.1.1. Una máquina con 0.1.0 y el
  arreglo puesto saltaría a 0.1.1 — que lleva el mismo updater roto. El arreglo solo
  surte efecto de 0.1.2 en adelante, y **la instalación de 0.1.2 sigue siendo manual en
  toda máquina que hoy tenga 0.1.0 o 0.1.1**. Conviene decirlo en las notas: este
  arreglo no se auto-entrega.
- **No toca ninguna frontera de tenant.** Ninguna de las 7 garantías de
  `architecture/agent-isolation.md` queda rozada: es carga de módulo dentro del proceso
  principal de la cáscara. No hace falta test en `tests/isolation/`.
- **Sin dependencias nuevas**, así que no hay licencia que leer (constitución §VIII).
- `detectBuildKind()` y `feedIsAcceptable()` siguen delante: el arreglo no relaja ninguna
  de las dos guardas — una copia recompilada por otro sigue sin llegar al canal.

## Open Questions

Ninguna abierta.

- ~~¿0.1.2 con este arreglo solo, o agrupado con el empaquetado hinchado?~~
  **Resuelto el 2026-09-15 por Luis: agrupados en 0.1.2.** Los dos van en la misma
  publicación, así que el ciclo de firma y notarización se paga una vez. Consecuencia
  para este bug: la publicación de 0.1.2 **no** se hace hasta que el otro también esté
  arreglado y verificado.
