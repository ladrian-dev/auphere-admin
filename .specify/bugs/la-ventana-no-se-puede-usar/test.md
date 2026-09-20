# Bug Verification: la ventana se puede usar

- **Slug**: la-ventana-no-se-puede-usar
- **Tested**: 2026-09-20
- **Assessment**: ./assessment.md · **Fix**: ./fix.md
- **Result**: **verified** (V1-V4)

## Lo que se vio en rojo, y cómo

**V2 — los bordes.** Seis guardas nuevas en `contrast.test.ts`. Con el arreglo
retirado a propósito:

```
× --color-border se declara para el tema oscuro
× --color-border-soft se declara para el tema oscuro
× --color-border no es el mismo valor en los dos temas
× --color-border-soft no es el mismo valor en los dos temas
× el borde se distingue sobre --background en oscuro
× el borde se distingue sobre --card en oscuro
      Tests  6 failed | 31 passed (37)
```

Con él: 37 verdes.

**V3 — la ventana en negro.** Con la guarda de `format()` retirada:

```
× no lanza: registra y devuelve la clave
× y deja constancia, porque es un defecto
```

Con ella, 8 verdes. Los otros seis casos prueban la tabla de códigos y el armazón,
que antes no existían.

**V1 — el ancho.** No se prueba con un test de unidad: jsdom no calcula diseño y un
test sobre nombres de clase no habría visto el defecto, porque **cada clase era
correcta por separado**. Se mide en un navegador de verdad, con el renderer servido
y un puente falso (`evidencia/scripts/medir.mjs`):

| Ventana | Antes | Después |
|---|---|---|
| 1280×800 | `chat: 311` | `chat: 684` · `panel: 320` |
| 1024×700 | — | `chat: 748` · `panel: 0` |
| 900×600 | `chat: 32` | `chat: 624` · `panel: 0` |

Sin desbordamiento horizontal en ninguna. La misma sonda leyó `--color-border` ya
resuelto en oscuro (`oklch(0.971 … / 0.14)`), que es V2 confirmado fuera del test.

**Y se miraron las capturas**, que era el punto: `evidencia/capturas-despues-2026-09-20/`
en la KB. En la de 1280 oscuro se ven, por primera vez, el separador de la lista
lateral, el contorno de la tarjeta de aprobación y el borde del campo de escribir.

## Checks Performed

| Check | Command | Result | Notes |
|---|---|---|---|
| V2 | `vitest run contrast` en `packages/ui` | **pass** | 37 |
| V3 | `vitest run error-boundary` | **pass** | 8 |
| V1 · V2 | `node evidencia/scripts/medir.mjs` | **pass** | 4 tamaños, 2 temas |
| Escritorio entero | `vitest run` | **pass** | **942** en 97 ficheros |
| Puerta JS completa | `./scripts/verify.sh js` | **pass** | consola, panel, `@nexus/ui`, companion-ui, escritorio |
| Tipos y lint | `tsc --noEmit -p tsconfig.app.json` · `eslint` | **pass** | la regla `nexus-ui/spacing-scale` cazó dos `py-1.5` míos |

## Lo que NO está verificado

- **Nada de esto se ha visto en Electron de verdad**, solo en el renderer servido
  con un puente falso. El diseño y los tokens son los mismos; lo que no cubre son
  los semáforos, la franja de arrastre y la consola embebida.
- **V4 no tiene test propio.** Es un `return` temprano que ahora deja el estado en
  un valor terminal; probarlo pediría montar `Workspace` entero con su puente. Se
  verá en el recorrido manual, en el primer arranque sin sesión.
- **Ningún lector de pantalla** ha pasado por la pantalla nueva del armazón. Tiene
  `role="alert"` y foco visible declarado; no es lo mismo que haberlo oído.
