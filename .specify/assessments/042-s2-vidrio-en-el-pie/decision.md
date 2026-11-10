# Decisión: spike S2, el vidrio en el pie de la conversación

- **Slug**: 042-s2-vidrio-en-el-pie
- **Fecha**: 2026-10-21
- **Veredicto**: **go**, con una corrección a la D3 y cuatro hallazgos nuevos
  para las tareas de la iteración 2. El código del spike (`src/app/spike/`,
  una línea en `+native-intent.tsx` y una ruta en `_layout.tsx`) **se borró**;
  queda esta carpeta y lo que se corrige en `specs/042-liquid-glass-en-la-app/`.

Hecho en «SE 26» (iPhone SE 3.ª gen., iOS 26.0.1) con el build 2 de EAS
(`evidence/build.md`), la interfaz movida por Maestro y las capturas de
`xcrun simctl io`. El vídeo se midió con un script Swift que calcula la
diferencia media entre fotogramas consecutivos a 30 fps
(`evidence/01-fotogramas-*/deltas.txt`).

## Las seis comprobaciones

| # | Qué comprobaba | Resultado | Decisión |
|---|---|---|---|
| 1 | Un `GlassView` sigue un cambio de altura de Reanimated sin parpadear ni recrearse | **Se sostiene, pero no como estaba escrito.** Con `LinearTransition` en un envoltorio, el envoltorio se anima y el `GlassView` recibe su tamaño final de golpe: un solo fotograma (Δ 14 a los 200 ms del toque) y nada entre medias (`01-fotogramas-2/`). **Animando la altura del propio contenedor** (`withTiming`, 240 ms, `Easing.out(cubic)`), Yoga recoloca el `GlassView` en cada fotograma y el vidrio se encoge de panel a cuadro de forma continua (`01-fotogramas-3/`, Δ 16→12→11→11→10→11→9→6→2 en 10 fotogramas, solapado con la subida del teclado) | D3 se corrige: la superficie mide su contenido y anima su altura; nada de `layout` en el envoltorio. `@expo/ui` no hace falta |
| 2 | `KeyboardChatScrollView` + `KeyboardStickyView` con lista invertida bajo cabecera transparente | **Se sostiene.** El cuadro queda pegado al teclado (`02-vidrio-cuadro-teclado.png`), crece con el texto (`02-vidrio-cuadro-escrito.png`) y el hilo pasa por debajo de la cabecera de vidrio. Dos cuidados: `renderScrollComponent` tiene que ser un componente memorizado (como inline, remonta el scroll en cada render y en un arranque la lista salió vacía, `06-spike-panel-rt.png`); y el hueco de la cabecera con `contentInsetAdjustmentBehavior="never"` hay que ponerlo a mano y comprobar el efecto de borde | D4 se mantiene, con esos dos cuidados en T053 |
| 3 | Dónde cae `headerSearchBarOptions.placement: "automatic"` dentro de las pestañas | **Se sostiene.** En la cabecera de la Bandeja, bajo el título, y fija al desplazar (`03-bandeja-busqueda.png`, `03-bandeja-desplazada.png`) | D6: `automatic`. T068 hecho |
| 4 | Una `formSheet` a 0,6 con contenido transparente se pinta de vidrio y las filas se leen | **Se sostiene.** Asa, detención a 0,6, material del sistema (el fondo se adivina detrás), filas opacas legibles (`04-hoja-06.png`). Un hallazgo: con vidrio, la cabecera de la hoja es transparente y el título se solapa con el contenido si el contenido no respeta su inset | D7 se mantiene. T066 y T067 añaden `contentInsetAdjustmentBehavior="automatic"` al contenido de las hojas (Ajustes ya lo tiene; contacto no) |
| 5 | `Stack.Toolbar.Button` se agrupa en cápsula y el tinte se lee sobre contenido claro y oscuro | **Se sostiene, con un ajuste.** Dos botones se agrupan en una cápsula de vidrio y el de volver va en la suya (`05-botones-de-barra.png`). El botón **no hereda `headerTintColor`**: hay que pasarle `tintColor` (hecho en `SettingsToolbar`, `07-inicio-titulo-h14.png` vs `06-inicio-rt.png`). Sobre contenido oscuro queda por medir en US3 | D2 se mantiene; el tinte va explícito |
| 6 | `GlassView`, barras y hoja con «Reducir transparencia» | **Se sostiene.** UIKit vuelve opacos las barras, la cápsula de pestañas, la hoja y el propio `GlassView` (gris plano); todo se lee (`06-*-rt.png`). La app además pasa `FloatingSurface` a su presentación anclada en `colors.card`, que es más consistente con las tarjetas que el gris del sistema | D5 se mantiene |

**Además, se verificó H14:** sin fondo en la cabecera, el título grande vuelve
(`07-inicio-titulo-h14.png`, `09-inicio-reposo.png`).

## Hallazgos nuevos

- **H16 · Tras recuperarse de un error de `/me` con «Reintentar», el contenido
  de Inicio y de la Bandeja queda empujado ~120 pt bajo la cabecera
  transparente** (`06-inicio-rt.png` del primer intento, `03-bandeja-busqueda.png`).
  En reposo y tras un pull-to-refresh real está bien (`09-inicio-reposo.png`,
  `09-inicio-tras-recarga.png`). Es el remontaje de las pestañas con la
  cabecera sin fondo (iOS 26 + react-native-screens). Severidad 2. Va a US4
  como tarea propia.
- **El cliente de desarrollo abre su menú con cada enlace que entra** (y el de
  bienvenida tras cada instalación). Los flujos de Maestro de la 042 lo cierran
  por «Cerrar»; `_dev-server.yaml` ya acepta el diálogo «¿Abrir en…?» de iOS.
- **`+native-intent.tsx` manda a casa cualquier enlace que no conozca**, así
  que una ruta nueva no se puede abrir por enlace sin declararla ahí. Es lo
  correcto para el producto; se anota para quien haga el próximo spike.
- **Disco.** Un simulador arrancado ocupa ~2,5 GB; el «iPhone 17» de serie,
  que Maestro arrancó por error, 4,5 GB. El disco llegó a cero, tumbó Postgres
  (recuperó por WAL) y colgó Docker Desktop (reinicio forzado). «17 26» queda
  creado pero sin arrancar; las capturas de US4 en pantalla grande esperan a
  que haya disco, o a que Luis autorice borrar el iPhone 17 de serie.

## Lo que se corrige en la spec

- `research.md`: D3 (altura animada), D4 (componente memorizado e inset), D2
  (`tintColor`), D18 (esta tabla), D16 (disco).
- `contracts/ui.md`: §2 `FloatingSurface` anima su altura; §4 el paso del panel
  al cuadro.
- `tasks.md`: T053 y T056 (altura animada, scroll memorizado), T066 y T067
  (inset de las hojas), T069 (H16), T068 hecho; T011–T019 cerradas.
- `evidence/hallazgos.md`: H14 cerrado, H16 abierto.
