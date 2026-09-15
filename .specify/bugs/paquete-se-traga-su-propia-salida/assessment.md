# Bug Assessment: el paquete se traga su propia salida

- **Slug**: paquete-se-traga-su-propia-salida
- **Created**: 2026-09-15
- **Source**: pasted text + inspección de los artefactos publicados en `updates.auphere.com`
- **Verdict**: valid
- **Severity**: high

## Report

El `.dmg` de Intel de v0.1.0 pesa **1,0 GB**; el de Apple Silicon, 266 MB. Encontrado al
contrastar el canal mientras se investigaba «en otra máquina no funcionó». No estaba en
`docs/bugs-app-escritorio-2026-09-15.md`.

## Symptom

Cada arquitectura empaqueta dentro de su `app.asar` la salida que electron-builder ya
había escrito en el directorio de trabajo — incluida la aplicación de la otra
arquitectura, ya firmada y notarizada, y ficheros temporales a medio escribir.

Se esperaba un `app.asar` de unos pocos MB con el código de la aplicación.

## Reproduction

Se reproduce leyendo lo publicado, sin construir nada. Cabecera del asar de los dos
`.zip` del canal:

```
===== app.asar de arm64: 388,854,240 bytes, 12,575 ficheros =====
  raíz: ['assets', 'dist', 'node_modules', 'package.json']
    201,596,784  dist/mac-arm64/Electron.app/Contents/Frameworks/…/Electron Framework
     20,111,209  dist/mac-arm64/LICENSES.chromium.html
  por carpeta de primer nivel:
    320,766,335  dist/
     64,798,993  node_modules/

===== app.asar de x64: 1,982,761,659 bytes, 12,858 ficheros =====
    987,679,744  dist/.tempc5bkqpqxAuphere-0.1.0-arm64.dmg
    388,854,240  dist/mac-arm64/Auphere.app/Contents/Resources/app.asar
    200,443,040  dist/mac-arm64/Auphere.app/…/Electron Framework
     32,206,950  dist/ziGLCl5u
  por carpeta de primer nivel:
  2,032,894,001  dist/
```

Y en la máquina donde se instaló:

```
2.1G    /Applications/Auphere.app
-rw-r--r--@ 1 matos admin 1982761659 Sep 15 01:29 /Applications/Auphere.app/Contents/Resources/app.asar
```

## Suspected Code Paths

- `apps/desktop/package.json` → `build.files: ["dist/**", "package.json", "assets/**"]`
  y `build.directories` **sin `output`**. Ése es el fallo entero: sin `output`,
  electron-builder escribe en `dist`, que es justo lo que `files` empaqueta.
- `.github/workflows/release-desktop.yml:156,187,215,219` — las cuatro rutas que nombran
  `apps/desktop/dist`. No causan el fallo, pero **atan cualquier arreglo**: mover la
  salida sin tocarlas deja de publicar.

## Root Cause Hypothesis

**Confianza: alta.** Está leído en los artefactos, no inferido.

`directories.output` no está declarado, así que vale `dist` por defecto — el mismo
directorio que `files` empaqueta con `dist/**`. El orden del log del build lo confirma:

```
23:25:25  packaging  platform=darwin arch=arm64 appOutDir=dist/mac-arm64
23:28:47  building   target=macOS zip arch=arm64 file=dist/Auphere-0.1.0-arm64-mac.zip
23:28:47  building   target=DMG   arch=arm64 file=dist/Auphere-0.1.0-arm64.dmg
23:28:47  packaging  platform=darwin arch=x64   appOutDir=dist/mac
```

Dos consecuencias, y la segunda es una condición de carrera:

1. **Dentro de una misma arquitectura.** electron-builder extrae Electron en
   `dist/mac-arm64/Electron.app` y **después** copia los `files` dentro. Para cuando
   copia, `dist/mac-arm64/` ya existe: el asar de arm64 se lleva una copia entera de
   Electron. 320 MB de `dist/` en un paquete que debería tener unos pocos.
2. **Entre arquitecturas.** El empaquetado de x64 empieza en el mismo segundo en que
   arrancan el `.zip` y el `.dmg` de arm64, y lee `dist/**` mientras se escriben. Por eso
   se lleva `dist/.tempc5bkqpqxAuphere-0.1.0-arm64.dmg` — **el DMG sin comprimir, a medio
   escribir**, 987 MB — y la `Auphere.app` de arm64 ya firmada, con su propio asar dentro.

## Proposed Remediation

**Preferido: sacar el directorio de salida del árbol que se empaqueta.**
`"directories": { "buildResources": "build", "output": "release" }`.

Con eso `files: ["dist/**"]` vuelve a significar lo que siempre quiso decir — el código
compilado — y ni la salida de esta arquitectura ni la de la otra pueden colarse, porque
ya no están debajo.

Hay que actualizar **las cuatro rutas** de `release-desktop.yml` en el mismo commit, y
`apps/desktop/.gitignore`.

**Alternativa descartada: excluir con globs negativos** (`"!dist/mac*"`, `"!dist/*.dmg"`,
…). No funciona, y hay prueba: entre lo que se coló está **`dist/ziGLCl5u`**, 32 MB, un
temporal con nombre aleatorio y sin patrón. Una lista de exclusiones no puede cubrir lo
que no tiene forma. Además deja la trampa armada: el día que electron-builder invente
otro temporal, vuelve a colarse en silencio.

**Files likely to change**:
- `apps/desktop/package.json`
- `apps/desktop/.gitignore`
- `.github/workflows/release-desktop.yml`
- `apps/desktop/tests/packaging-config.test.ts` (nuevo)

**Tests to add or update**:

1. **Ningún `files` puede alcanzar el directorio de salida.** Es el invariante que se
   violó. Rojo hoy.
2. **El workflow apunta al directorio de salida declarado.** Verde hoy, y se pone rojo en
   cuanto se mueva `output` sin tocar las cuatro rutas — que es exactamente la forma en
   que esta tubería ya se ha roto dos veces (`CLAUDE.md`: un cron declarado en un sitio y
   no en el otro, con la suite sin correr en local).

Ninguno de los dos construye nada: son tests de configuración, y el fallo es de
configuración.

## Risks & Considerations

- **Toca la cadena que firma y publica.** Un error aquí no rompe la app: impide publicar,
  o publica de menos. El test 2 existe por eso.
- **Toca lo que se distribuye, que es una superficie de confianza** (spec 008). Hoy se
  está firmando y notarizando como «Auphere de FACELAD SpA» un binario que lleva dentro
  una **segunda copia de Electron** y las devDependencies. Reducirlo no es solo peso: es
  reducir lo que se firma a lo que de verdad es la aplicación.
- **No toca ninguna frontera de tenant**; ninguna de las 7 garantías queda rozada.
- **Sin dependencias nuevas** (§VIII).
- **El `node_modules` de 64 MB no se toca en este arreglo.** Lleva mapas de fuente
  (`lucide-react.js.map`, `Recharts.js.map`) y es bloat, pero es bloat *legítimo* de
  electron-builder empaquetando dependencias de producción. Es un asunto distinto y
  merece su propia decisión.
- **Lo que este arreglo NO promete**: que la app de Intel abra. Ver abajo.

## Open Questions

- **¿Es esto la causa del fallo 5?** No demostrado. Lo que se sabe de esa máquina: Intel
  de verdad (`x86_64`), el `.dmg` correcto y completo, macOS 26, Gatekeeper `accepted` y
  `Notarized Developer ID`, firma `valid on disk` y satisfaciendo su DR, sin informe de
  caída, y el proceso **se va con código 1 a los ~290 ms sin imprimir una sola línea**
  ni siquiera con `ELECTRON_ENABLE_LOGGING=1`. Todas las demás causas están descartadas;
  el asar de 1,98 GB es lo único objetivamente roto que le queda.

  **Este arreglo es el experimento que lo responde**: cambia esa variable y deja las
  demás quietas. Si un x64 delgado abre en esa máquina, era esto. Si no abre, se ha
  aislado un problema distinto con una variable menos y sin haber perdido nada — el
  paquete había que arreglarlo igual.
