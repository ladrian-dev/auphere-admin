# T140 — el binario empaquetado

**Fecha**: 2026-09-18 · **Versión**: `0.1.3` · **Arquitectura**: arm64

## Lo que se hizo

```bash
pnpm --filter @nexus/desktop build
cd apps/desktop && pnpm package
AUPHERE_EVIDENCE_DIR=/tmp/auphere-evidence ./release/mac-arm64/Auphere.app/Contents/MacOS/Auphere
```

El binario arranca, habla con producción (`console.auphere.com`) y **pinta el
armazón entero**. `app.json` y `armazon-empaquetado.png` son la captura del
recorrido de evidencia, tomada desde la aplicación empaquetada y no desde el
repositorio — que es donde aparecieron los fallos que más han dolido en esta
aplicación (el updater que no arrancaba, el paquete que se tragaba su salida).

Lo que se lee en la pantalla, y que es exactamente lo que esta spec construyó:

```
Inicio · sin emparejar · Buscar ⌘K      ← la franja, con el objeto y la búsqueda
OPERAR   Hoy · Pendientes               ← una sola navegación
TEAMMATES  Todavía no tienes ninguno.   ← el vacío que antes era un hueco
           Crear teammate
ADMINISTRAR  Inicio · Clientes · …      ← las secciones de la consola, filtradas
Cuenta · sin emparejar                  ← el pie: identidad y máquina
Emparejar esta máquina                  ← la acción, sin barra de 44 px
```

## Lo que falta, y por qué

* **La firma es ad-hoc, no Developer ID.** `codesign` dice
  `flags=0x20002(adhoc,linker-signed)`. Firmar y notarizar de verdad exige el
  certificado y las credenciales de notarización, que no están en este entorno.
  Es exactamente lo que `update-policy.ts` mira antes de hablar con el canal: un
  binario ad-hoc **no se actualiza**, y eso está probado sin Electron.
* **El recorrido de emparejamiento en una máquina de verdad** necesita un código
  de la consola, que se pide desde `/workstation` con una sesión con
  `workstation:manage`. La mitad de la aplicación está probada
  (`pairing-flow.test.tsx`, 14 casos); lo que falta es el extremo.

## El `pnpm package` que estaba roto, y ya no

`apps/desktop` tenía su propio `pnpm-workspace.yaml`, heredado de cuando era un
workspace aparte como `apps/admin`. Ya no lo es —la raíz lo lista y sus
dependencias (`@nexus/ui`, `@nexus/companion-ui`) viven allí— y el fichero
declaraba `packages` **vacío**. Como pnpm resuelve el `pnpm-workspace.yaml` más
cercano subiendo desde el cwd, ejecutar pnpm desde dentro de `apps/desktop`
encontraba un workspace de un solo paquete y no podía resolver
`@nexus/companion-ui@workspace:*`.

Lo tramposo era **dónde se veía**: todo lo lanzado desde la raíz funcionaba.
Sólo fallaba `pnpm package`, porque electron-builder arranca con su propio
`pnpm install` dentro del directorio del proyecto — un fallo que sólo aparece al
empaquetar es un fallo que se descubre el día que hay que publicar.

Y `package` dejó de exigir el certificado de distribución: `--dir` es «hazme el
`.app` para probarlo aquí», y electron-builder firmaba en cuanto encontraba una
identidad en el llavero. `dist`, el que publica, sigue firmando y notarizando.

`tests/packaging-config.test.ts` falla si el fichero vuelve o si los dos guiones
cambian de significado.
