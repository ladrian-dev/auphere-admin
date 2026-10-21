# Los hallazgos de la auditoría y los criterios de éxito — spec 042

Cada hallazgo de `research/2026-10-20-liquid-glass-app-movil` (KB) con el
requisito que lo cierra y la captura que lo demuestra. Sin captura no se
cierra. Lo que depende de Luis queda escrito con su razón, nunca como `skip`.

## Hallazgos

| # | Hallazgo | Sev. | Requisito | Captura que lo cierra | Estado |
|---|---|---|---|---|---|
| H1 | Inicio repite tres veces que alguien espera | 3 | R5.1–R5.3 | `capturas/ios26-se-inicio-claro.png`: «2» una vez en el contenido, más la insignia de la pestaña | cerrado 2026-10-21 |
| H2 | Inicio y Consumo duplican el dinero | 3 | R5.4 | `capturas/ios26-se-inicio-claro.png`: un solo grupo de dinero; Consumo con sus filas (`consumo.test.tsx`) | cerrado 2026-10-21 (captura de Consumo pendiente, T048) |
| H3 | Rejillas de tarjetas iguales | 2 | R5.5 | `capturas/ios26-se-inicio-claro.png`: lista agrupada y una cifra por bloque; `Metric` retirado | cerrado 2026-10-21 |
| H4 | El panel de «Tomar el control» tapa el hilo | 2 | R2 | `capturas/ios26-13-conversacion-espera-claro.png` y `-oscuro.png`: el panel flota en vidrio sobre el hilo, el último mensaje y el aviso del agente quedan a la vista; `ios26-13-conversacion-espera-texto-max.png`: con el texto al máximo el panel se detiene al 60 % y el hilo sigue ahí | cerrado 2026-10-21 |
| H5 | Tres maneras de ir a otro sitio | 2 | R6 | `capturas/ios26-13-inicio-claro.png` (solo el chevrón de «Ver consumo») y `ios26-13-ajustes-hoja-abajo.png` (el enlace externo con su destino); `group.test.tsx` | cerrado 2026-10-21 |
| H6 | Formas de la web | 2 | R7.1, R7.2 | `capturas/ios26-13-botones-vs-sistema.png` (la hoja de Ajustes junto a los Ajustes del sistema: cápsulas y grupos agrupados), `ios26-13-bandeja-claro.png` (chips en cápsula); `states.test.tsx` (pulsación por tono y escala, nunca opacidad) | cerrado 2026-10-21 |
| H7 | Ajustes junta cerrar sesión con borrar la cuenta | 2 | R8 | `capturas/ios26-13-ajustes-hoja-abajo.png`: grupos distintos, el borrado el último y en rojo con su consecuencia escrita; `ajustes-avisos.test.tsx` | cerrado 2026-10-21 |
| H8 | Con el texto grande, la jerarquía se invierte | 2 | R4.6 | Confirmado en iOS 26: con un color en el título, react-native-screens lo pinta con una fuente fija y el título grande se quedaba en 34 pt mientras el cuerpo crecía a 53 (`capturas/ios26-13-inicio-texto-max-antes.png`). `headerSize()` pone el tamaño de la tabla de Dynamic Type de Apple al título grande (60 en AX5; el título normal de la barra se queda fijo, como el de Apple) y cada estilo de `Text` lleva su tope (`maxScale`); `states.test.tsx`; después: `ios26-13-inicio-texto-max.png` | cerrado 2026-10-21 (iOS); Android pendiente del emulador |
| H9 | Escala de texto de la consola | 1 | R7.3 | `type.ts` con los estilos del sistema en iOS (cuerpo 17/22, título 22, título grande 34, cifras 28) y los tokens en Android; `capturas/ios26-13-conversacion-espera-claro.png`; `states.test.tsx` | cerrado 2026-10-21 |
| H10 | Consumo abre repitiendo su título | 1 | R9.1 | `capturas/ios26-13-consumo-oscuro.png`: el título una vez, grande | cerrado 2026-10-21 |
| H11 | Gráfico vacío con selector de periodo | 1 | R9.2 | `capturas/ios26-13-consumo-oscuro.png`: sin selector; «Gasto por día» dice cuándo habrá algo; `consumo.test.tsx` | cerrado 2026-10-21 |
| H12 | «Attend» en inglés | 1 | R9.3 | `inicio.test.tsx` (en inglés dice «Answer now»); sin captura en inglés: el simulador del pase va en español | cerrado 2026-10-21 (por test) |
| H13 | La insignia de atención cuenta otra cosa | 3 | R5.2 | `capturas/ios26-se-inicio-claro.png`: sin insignia junto al título | cerrado 2026-10-21 |

### Hallazgos nuevos del pase en simulador (2026-10-21)

| # | Hallazgo | Sev. | Requisito | Captura | Estado |
|---|---|---|---|---|---|
| H14 | **El título grande es invisible en iOS 26.** «Hola, Valeria» no se pinta: queda un hueco vacío bajo la barra de estado. Es el aviso del código de react-native-screens que recoge la D1 (fondo de color + título grande en iOS 26). Afecta a lo que hoy está en `develop`, en cualquier build hecho con Xcode 26 o 27. | 3 | R1.1, R4.6 (T064, T060) | Antes: `capturas/ios26-se-inicio-claro.png`. Después: `capturas/ios26-13-inicio-claro.png` y `-oscuro.png` (sin fondo en la cabecera, el título vuelve) | cerrado 2026-10-21 (T064) |
| H17 | **El botón de atrás de la conversación decía «(app)».** Con la cabecera del sistema, el botón de volver enseña el título de la pantalla anterior, y la anterior es el grupo de pestañas, cuyo nombre de ruta no significa nada para una persona. | 2 | R1.1 | `headerBackButtonDisplayMode: "minimal"` en la conversación; `capturas/ios26-13-conversacion-espera-claro.png` (solo el chevrón) | cerrado 2026-10-21 |
| H18 | **La última fila del hilo quedaba bajo el pie flotante.** La holgura que la lista usaba de relleno era la altura del contenido, sin el margen flotante (área segura + 8) ni el borde: el aviso «El agente pidió ayuda» salía cortado por el pie. | 2 | R2.2 | `FloatingSurface` escribe la **holgura** (contenido + borde + margen + `FOOT_GAP`) y la recalcula si cambia el marco; `floating-surface.test.tsx`; `capturas/ios26-13-conversacion-espera-claro.png` | cerrado 2026-10-21 |
| H19 | **Con el texto al máximo, el panel de espera ocupaba toda la pantalla** (título a tres líneas, motivo, dos botones a dos líneas) y el hilo desaparecía: incumplía R4.7. | 3 | R4.7 | La superficie se detiene en `FOOT_MAX_SHARE` (0,6 de la ventana) y su contenido se desplaza dentro; `floating-surface.test.tsx`; antes: `capturas/ios26-13-conversacion-espera-texto-max-antes.png`; después: `ios26-13-conversacion-espera-texto-max.png` | cerrado 2026-10-21 |
| H20 | **Las filas del hilo se pintaban al 13 % de opacidad en iOS 26** (y desaparecían con «Aumentar contraste» o «Reducir transparencia») en cuanto el hilo era más alto que la pantalla. Es el efecto de borde del `UIScrollView` de iOS 26 sobre la lista invertida (`scaleY: -1`): el degradado que debería quedar bajo la barra cubre todo el contenido. La opción `scrollEdgeEffects` de la pantalla no llega a la lista (lo más probable: se aplica al llegar las opciones, cuando el hilo aún es el esqueleto de carga). | 4 | R2.1, R4.1 | Antes: `capturas/ios26-13-conversacion-atenuada-antes.png` (marcadores rojos con el degradado). Después: `ScrollViewMarker` (en `ContentScroll`) con los cuatro bordes en `hidden`, la lista bajo la cabecera y el relleno como separador en estado (research D4); `capturas/ios26-13-conversacion-espera-claro.png` | cerrado 2026-10-21 |
| H21 | **Falsa alarma: botones de barra claros en oscuro con «Aumentar contraste».** En dos capturas de la tanda D/E, en oscuro y con contraste alto, los botones de vidrio de la barra salieron como discos **claros** y el tinte menta daba 1,85:1. No se reproduce con el código congelado en ninguno de los tres órdenes de conmutación (contraste→oscuro, oscuro→contraste, claro→oscuro con contraste): iOS 26 pinta el disco siguiendo el esquema (oscuro en oscuro) y el menta da 6,9:1; en claro el tinte es `#03624C` y da 7,4:1. Las dos capturas se tomaron con una recarga en caliente de Metro a mitad de tanda (edición de código), que deja los elementos de barra con el rasgo anterior. Un tinte distinto con contraste alto (`primaryDeep`) se probó y **empeora** el estado estable (3,4:1): se retiró. | 0 | R4.3 | `capturas/ios26-13-conversacion-aumentar-contraste-oscuro-antes.png` (el artefacto) frente a `ios26-13-conversacion-aumentar-contraste-oscuro.png` (estable) | cerrado 2026-10-21, sin cambio de código |
| H22 | **La barra de pestañas se encoge al bajar pero no vuelve al subir** en el simulador, ni arriba del todo; vuelve al tocarla. Mientras está encogida no se ve la insignia de la Bandeja. Con los gestos sintéticos de Maestro sobre «13 26»; con y sin `ScrollViewMarker`. Puede ser del gesto sintético (UIKit documenta que `onScrollDown` vuelve al subir) | 2 | R1.5 | `capturas/ios26-13-pestanas-encogidas.png`, `-arriba.png`, `-tras-tocar.png` | abierto: comprobar en un iPhone; si se confirma, `minimizeBehavior="never"` (la insignia de espera manda) y enmendar R1.5 |
| H16 | **Tras «Reintentar» un error de `/me`, el contenido de Inicio y la Bandeja quedaba empujado ~120 pt bajo la cabecera transparente** (spike S2, primer intento). | 2 | R1.1 (T069) | Repetido en «13 26» con la API parada de verdad: `capturas/ios26-13-h16-api-caida.png` (el error con «Reintentar»), y tras levantar la API y pulsarlo, `ios26-13-inicio-tras-reintentar.png` y `ios26-13-bandeja-tras-reintentar.png`: el título grande y el contenido en su sitio, igual que en reposo. No se reproduce con la cabecera sin fondo de T064 (en el spike la cabecera aún llevaba fondo y el título grande no se pintaba, H14) | cerrado 2026-10-21, sin cambio de código |
| H15 | **En un iPhone de 4,7″, «Ahora no» de la pantalla de avisos queda bajo el pliegue.** La hoja de la 031 (R10) enseña el título, los tres avisos y la nota de privacidad, y la acción secundaria solo aparece desplazando; la persona puede no saber que puede declinar. | 2 | Fuera de esta spec (031 R10.1). Propuesta: la nota de privacidad después de las acciones, o las acciones fijas al pie | `scratchpad` del pase (sin captura en evidencia; se repite al abrir su tarea) | abierto; para la 031 o una spec propia |

## Criterios de éxito

| CE | Qué | Evidencia | Estado |
|---|---|---|---|
| CE-001 | El número de espera, una vez en Inicio | `capturas/ios26-se-inicio-claro.png` y `inicio.test.tsx` (CE-001) | cerrado 2026-10-21 |
| CE-002 | Sin desplazar en «13 26»: Inicio y la conversación en espera | Inicio: `capturas/ios26-13-inicio-claro.png` (título grande, la atención entera, el dinero y el principio de las conversaciones a la vista). Conversación: `capturas/ios26-13-conversacion-espera-claro.png` (último mensaje, aviso del agente, motivo y «Tomar el control» sin desplazar) | cerrado 2026-10-21 |
| CE-003 | Dos toques desde Inicio hasta escribir | «Atender ahora» (Inicio) → la conversación en espera → «Tomar el control» → el cuadro toma el foco y sube el teclado (`capturas/ios26-13-conversacion-recien-tomada.png`, `morph.mp4`) | cerrado 2026-10-21 |
| CE-004 | Panel → cuadro en ≤ 300 ms, sin fotograma vacío | `motion.md`: el fundido dura ~200 ms (6 fotogramas a 30 fps), delta máximo 11,7 sin picos de remontaje, el hilo quieto | cerrado 2026-10-21 |
| CE-005 | Contraste sobre vidrio en las ocho combinaciones | `a11y.md`: las ocho medidas en la conversación y cinco en Inicio/Bandeja; H21 corregido en el pase | cerrado 2026-10-21 en iOS 26.0; el vidrio tintado (26.1) y una etiqueta de pestaña en oscuro (R-02) pendientes de Luis |
| CE-006 | Revisión heurística sin severidad 3 o 4 | `revision.md`: 9/10 en `ux-heuristics`, 19/20 en `impeccable`; ninguna severidad ≥ 2 abierta | cerrado 2026-10-21; las capturas de iOS < 26 pendientes de Luis |
| CE-007 | Nada imita el vidrio en Android ni en iOS < 26 | Por código y test: `FloatingSurface` se presenta anclada y opaca sin `isLiquidGlassAvailable()` (`floating-surface.test.tsx`); `useSheetOptions` y `useHeaderOptions` pintan el fondo de siempre sin vidrio (`sheets.test.tsx`, `tabs.test.tsx`) | abierto por evidencia: Android (sin disco para el emulador) e iOS < 26 (sin runtime) pendientes de Luis |
| CE-008 | Ninguna cifra difiere de la consola | `pnpm test --ci`: 193 en verde el 2026-10-21 (`inicio`, `consumo` con las mismas fórmulas); `gen:check` en verde | cerrado 2026-10-21 |

## Skills de revisión instaladas (T004)

Instaladas en `apps/mobile/.claude/skills/` el 2026-10-20 (fuera de git;
`npx skills experimental_install` las restaura desde `skills-lock.json`).

| Skill | Versión declarada | Hash (`skills-lock.json`) |
|---|---|---|
| `ux-heuristics` | 1.6.0 | `078959463a4d…` |
| `impeccable` | 4.7.0 | `84572f92d75b…` |
| `design-critique` | sin versión declarada | `55100e100ac2…` |
| `apple-design` | sin versión declarada | `0190417d092a…` |
| `ui-ux-pro-max` | sin versión declarada | `27b1e8c953e2…` |

## Lo que depende de Luis

| Qué | Por qué | Cómo se cierra |
|---|---|---|
| Vidrio claro o tintado (iOS 26.1) | Runtime local 26.0.1; otro son ~7,5 GB con 7,7 GB libres | iPhone con 26.1 o runtime nuevo |
| Respaldo en iOS anterior a 26 | No hay runtime de iOS 18 en la máquina | iPhone con iOS 18 o runtime nuevo |
| El build de simulador en EAS | Usa su cuenta y sus minutos de build | `eas build -p ios --profile development-simulator` |
| Las capturas de Android (T048, T070, T076, T083) | El emulador Pixel 9 no arranca con menos de ~2 GB libres («not enough disk space»); con 12 GB en el disco, lo que sobra son los simuladores de iOS de serie (iPhone 17 Pro, 6,3 GB; iPhone 17, 4,5 GB; iPhone 16e, 3,6 GB) y las cachés de `~/Library/Caches`, que no se borran sin su permiso | Liberar disco (o un Mac con espacio) y seguir `quickstart.md` §Android: el build de desarrollo ya está en EAS (`f6f47ac2`, 2026-10-21, keystore de desarrollo creado en la cuenta) |
| H22: la barra de pestañas al subir | En el simulador, con gestos sintéticos, no vuelve al subir (sí al tocarla) | En un iPhone con iOS 26: bajar en Inicio con el texto grande y volver a subir. Si no vuelve, `minimizeBehavior="never"` y enmendar R1.5 |
