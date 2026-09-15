# Bug Fix: el paquete se traga su propia salida

- **Slug**: paquete-se-traga-su-propia-salida
- **Fixed**: 2026-09-15
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`directories.output` pasa a `release`, fuera del `dist/**` que `files` empaqueta. Con eso
ni la salida de la propia arquitectura ni la de la otra pueden colarse en el `app.asar`.
Medido en un build local: el asar de arm64 baja de **388.854.240** a **76.418.304** bytes,
y lo que `dist/` aporta dentro cae de **320.766.335** a **657.293**.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/desktop/package.json` | modificado | `directories.output: "release"`; `mac.minimumSystemVersion: "13.0"` (T045 a) |
| `.github/workflows/release-desktop.yml` | modificado | Las 4 rutas a la salida, el comentario que las describe, y el glob del índice a `latest-mac*.yml` (T045 b) |
| `apps/desktop/.gitignore` | modificado | `release/` |
| `apps/desktop/tests/packaging-config.test.ts` | añadido | 5 casos |

## Diff Highlights

```json
"directories": {
  "buildResources": "build",
  "output": "release"
},
"mac": {
  "minimumSystemVersion": "13.0",
```

## Tests Added or Updated

`apps/desktop/tests/packaging-config.test.ts`, cinco casos en tres grupos. Ninguno
construye nada — el fallo es de configuración, así que se comprueba donde vive y puede
correr en cada push.

- **`el paquete no se traga su propia salida`** (2): ningún patrón de `files` alcanza el
  directorio de salida, y ese directorio está declarado en vez de dejarse al azar. El
  segundo existe porque el primero no significaría nada con `output` implícito.
- **`el paquete dice qué macOS necesita`** (1): `minimumSystemVersion` declarado y ≥ 13.
- **`la cadena de publicación mira donde la salida está`** (2): las rutas del workflow
  apuntan al directorio declarado. **Este es el que importa**: mover la salida sin tocar
  el workflow no rompe la aplicación, deja de publicarla — y es exactamente la forma en
  que esta tubería ya se rompió dos veces (`CLAUDE.md`: algo declarado en un sitio y no
  en el otro, con la suite sin correr en local).

## Local Verification

**Rojo antes de tocar nada**, con el patrón culpable señalado:

```
 × … > ningún patrón de `files` alcanza el directorio de salida 3ms
   → expected [ 'dist/**' ] to deeply equal []
 × … > el directorio de salida está declarado y no se deja al azar 0ms
   → expected undefined to be truthy
```

**El arreglo se aplicó en dos pasos a propósito, para ver el acoplamiento.** Con
`package.json` cambiado y el workflow todavía sin tocar:

```
 ✓ … > ningún patrón de `files` alcanza el directorio de salida 1ms
 ✓ … > el directorio de salida está declarado y no se deja al azar 0ms
 × … > todas las rutas del workflow apuntan al directorio declarado 2ms
   → expected [ 'dist' ] to deeply equal []
```

El test cazó en local, en dos segundos, la clase de error que ha abortado dos despliegues.
Tras actualizar las cuatro rutas: `Tests  5 passed (5)`.

### La medición, que es la prueba de verdad

Build local sin firmar (`electron-builder --mac --dir --arm64`), sobre un árbol limpio:

```
-rw-r--r--@ 1 lmatos staff 76418304 Sep 15 14:13 release/mac-arm64/Auphere.app/Contents/Resources/app.asar

ficheros: 12342
raíz: node_modules, assets, dist, package.json
dentro de dist/: app-bridge.js, app-ipc.js, … , app, bar, electron, …
--- por carpeta ---
   72540643 node_modules/
     657293 dist/
        602 assets/
        438 package.json/
```

Contra lo publicado en v0.1.0:

| | v0.1.0 arm64 | v0.1.0 x64 | tras el arreglo |
|---|---|---|---|
| `app.asar` | 388.854.240 | 1.982.761.659 | **76.418.304** |
| de eso, `dist/` | 320.766.335 | 2.032.894.001 | **657.293** |

Desaparecen del paquete `mac-arm64/`, `builder-debug.yml`, el `.dmg` temporal de 987 MB y
la aplicación de la otra arquitectura. El `.app` entero queda en 360 MB, que es
básicamente el framework de Electron y es irreducible.

### Un error propio, y cómo se cazó

El primer intento de arreglo **rompió el build**: metí las razones como claves
`_comment_*` dentro del JSON, y electron-builder valida su esquema de forma estricta:

```
- configuration.mac should be one of these:
   null
```

Lo cazó el build local en veinte segundos. En la tubería habría costado quince minutos de
runner de macOS, y habría sido el tercer despliegue abortado por la misma clase de
descuido. Las razones viven ahora en el test, que es donde JSON no estorba.

### Lo que esta verificación NO cubre

- **El build de x64 no se ha medido**, solo el de arm64: esta máquina es Apple Silicon.
  El mecanismo es el mismo y el de x64 mejora **más**, porque además deja de llevarse la
  app de arm64 entera — pero el número exacto no está medido, está deducido.
- **Nadie ha abierto todavía un x64 delgado.** Es el experimento que responde al fallo 5
  y solo se puede hacer en esa máquina, con 0.1.2 instalado.
- **No se ha probado el workflow entero.** Que las cuatro rutas nuevas encuentren los
  ficheros lo dice el test leyendo el YAML, no un runner ejecutándolo. Se sabrá en la
  publicación de 0.1.2.

## Deviations from Assessment

Una ampliación de alcance, deliberada y declarada: se incluyeron **T045 (a) y (b)** de la
spec 008 —`minimumSystemVersion: "13.0"` y el glob `latest-mac*.yml`—, que la evaluación
no listaba. Son tareas ya decididas y anotadas en `docs/pendientes-tras-el-go-live.md` §2,
tocan los mismos dos ficheros que este arreglo y pertenecen a la misma cosa: lo que se
entrega. Agruparlas evita un segundo ciclo de firma y notarización.

Nota sobre (a): **ya no es candidata a explicar el fallo 5** —esa máquina tiene macOS 26—,
pero sigue siendo correcta y sigue evitando que un Mac con macOS 12 instale algo que luego
no abre sin decir por qué.

## Follow-ups

- **`node_modules` es ahora el 95% del asar** (72,5 MB de 76). Lleva mapas de fuente
  (`lucide-react.js.map`, `Recharts.js.map`) y, sin que nadie lo pidiera,
  `@nexus/ui/storybook-static/` — **el build de Storybook, dentro de la aplicación firmada
  y notarizada**. Es inerte dentro del asar, pero no pinta nada ahí. Asunto aparte y
  decisión aparte: no se tocó.
- **`files: ["dist/**"]` sigue empaquetando lo que sea que haya en `dist/`.** En la
  tubería da igual —checkout limpio— pero en una máquina con residuo de builds viejos, no:
  el primer intento de medición dio 773 MB por eso. Narrar `files` a `dist/*.js`,
  `dist/app/**`, `dist/bar/**` y `dist/electron/**` lo haría inmune. No se hizo aquí para
  no ampliar el arreglo; merece su propia decisión.
- **Va en 0.1.2**, agrupado con el updater y el mensaje del tope.
