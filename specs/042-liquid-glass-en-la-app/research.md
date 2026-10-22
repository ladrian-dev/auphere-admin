# Research: Liquid Glass en la app (spec 042)

**Fecha**: 2026-10-20 · **Spec**: [spec.md](spec.md) · **KB**:
`[[research/2026-10-20-liquid-glass-app-movil]]`

Lo que se leyó para decidir, con el código instalado en `apps/mobile` delante:
- `expo-glass-effect` 58.0.4 y `@expo/ui` 58.0.21, descargados y leídos (tipos,
  Swift y licencias), más la documentación v58 de Expo.
- `expo-router` 58.0.24 y `react-native-screens` 4.30.0, tal como están en
  `node_modules`: `useHeaderConfigProps.js`, `RNSScreenStackHeaderConfig.mm`,
  `StackToolbar*`, `NativeTabsView.ios.js`, `ScreenStackHeaderConfig.kt`.
- React Native 0.88 (`AccessibilityInfo`), Reanimated 4.7.1 y
  `react-native-keyboard-controller` 1.22.7.
- La infraestructura de EAS Build (imágenes y Xcode por SDK).
- El HIG de Apple (tipografía) y los tokens de Material 3 Expressive.

Cada decisión lleva su porqué y las alternativas. Lo que solo se puede
comprobar en un simulador o en un teléfono va marcado **por ver** y lo cierra
el spike S2 (D18).

## D1 · La cabecera de iOS 26 es la del sistema: sin fondo propio

**Decisión:**
- En iOS 26, `useHeaderOptions()` deja de fijar `headerStyle`,
  `headerLargeStyle` y `contentStyle` con `colors.background`. Se quedan el
  tinte (`headerTintColor`) y los colores del título.
- En iOS anterior a 26 y en Android, todo sigue como hoy. La condición es
  `isLiquidGlassAvailable()`, de `expo-glass-effect` (D3).
- `headerLargeTitle` pasa a `headerLargeTitleEnabled`, que es el nombre vivo.
- `scrollEdgeEffects` se queda en `automatic`: el sistema pone el efecto de
  borde donde el contenido toca la barra.
- Las pantallas siguen con `contentInsetAdjustmentBehavior="automatic"`, que
  es lo que deja al título grande plegarse.

**Por qué:**
- expo-router solo usa la barra de vidrio del sistema cuando no hay
  `headerTransparent`, ni `headerStyle.backgroundColor`, ni `headerBackground`
  (`useHeaderConfigProps.js`, «usesSystemBackground»). Nuestro color de fondo
  la apaga: RNS llama a `configureWithOpaqueBackground` y la barra sale sólida
  (`RNSScreenStackHeaderConfig.mm:402-424`).
- Un comentario de ese mismo fichero avisa: «The title becomes invisible if
  background color is set with large title on iOS 26». Es un riesgo que hoy
  corremos sin saberlo.
- En iOS 27, una cabecera opaca apaga además la minimización de la barra.

**Alternativas:**
- **`headerTransparent` + `headerBlurEffect`.** Es el vidrio antiguo, no el de
  iOS 26, y se solapa con `scrollEdgeEffects`.
- **`enableLegacyHeaderAppearance()`.** Está en desuso.

## D2 · Los botones de las barras son de la plataforma

**Decisión:**
- En iOS, el botón de Ajustes de cada pestaña y el menú de la conversación
  pasan a `Stack.Toolbar placement="right"` con `Stack.Toolbar.Button` (SF
  Symbol, `onPress`, `accessibilityLabel`) y `Stack.Toolbar.Menu` para el menú
  de la conversación, con «Devolver al agente» como primera acción (031 R6.7).
- En Android se queda el `headerRight` de hoy con el `IconButton`, que es un
  botón de Material.

**Por qué:**
- En iOS, `placement="right"` se convierte en `unstable_headerRightItems`:
  elementos nativos que iOS 26 agrupa en su cápsula de vidrio y que colapsan
  en un menú cuando no caben.
- El `headerRight` de hoy entra en un `UIBarButtonItem` con vista propia, que
  iOS 26 estira a 36 pt como mínimo dentro del fondo compartido. Funciona,
  pero es una vista web metida en una cápsula; la respuesta al toque es la
  nuestra (opacidad), no la del sistema.
- En Android, `Stack.Toolbar` exige `@expo/ui` y lanza una excepción si no está
  (`processHeaderItemsForPlatform.android.js`). No vamos a instalar `@expo/ui`
  solo para eso (D3).

**Alternativas:**
- **`unstable_headerRightItems` a mano.** Es lo mismo con el nombre inestable.
- **Mantener el `IconButton` con `hidesSharedBackground`.** Seguiría sin la
  respuesta del sistema.

## D3 · El pie de la conversación: una sola superficie de vidrio que cambia de forma

**Decisión:**
- Entra **`expo-glass-effect` ~58.0.4** (MIT). No entra `@expo/ui`.
- El panel de espera, el de quién atiende, el de resuelta y el cuadro de
  escribir dejan de ser cuatro tarjetas y pasan a **una sola superficie**,
  `FloatingSurface`, que en iOS 26 es un `GlassView` (`regular`) y que cambia
  de contenido y de altura. Lo que cambia es lo de dentro; la superficie es la
  misma.
- **El cambio de altura lo anima la propia superficie** (corregido por el
  spike S2, comprobación 1): el contenido se mide con `onLayout` y la altura
  del contenedor va con `withTiming` a `durations.state` (240 ms) y
  `Easing.out(Easing.cubic)`, sin muelle; Yoga recoloca el `GlassView`
  (absoluteFill) en cada fotograma. Una transición `layout` en un envoltorio
  **no vale**: anima el envoltorio y el vidrio salta en un fotograma. Lo de
  dentro entra con `motion.enter` y sale con `motion.exit`. Es la coreografía
  de la D24 de la 031, sobre vidrio.
- Dentro de la superficie no hay más vidrio: «Tomar el control» es una cápsula
  sólida de `primary`; «Devolver» es texto; el botón de enviar es un círculo
  sólido de `primary`. Nunca vidrio sobre vidrio.
- **Respaldo:** en iOS anterior a 26, `FloatingSurface` es la tarjeta opaca con
  borde de hoy (`colors.card`, `colors.border`), **anclada** al borde de abajo
  a ancho completo, como el pie de la 031: el mismo código, otro estilo
  (contrato §2). En Android, lo mismo. Con «Reducir transparencia», también
  (D5).

**Por qué:**
- `expo-glass-effect` tiene `GlassView` y `GlassContainer`, pero **no** tiene
  `glassEffectId`: no puede fundir dos superficies en una. Con una sola
  superficie no hace falta fundir nada: el vidrio sigue al marco, que es lo que
  queremos.
- Solo `@expo/ui` tiene el *morph* de verdad (`Namespace` + `glassEffectId`),
  pero exige un `Host` de SwiftUI en el pie: sin flexbox dentro, el `TextInput`
  dentro de `RNHostView` o un `TextField` de SwiftUI, y el teclado sin probar en
  ninguno de los dos casos. Son 2,7 MB y 1 628 ficheros, con una API que
  todavía cambia (56.0.0 rompió; 58.0.0 cambió el `spacing` por defecto). Los
  `testID` que usa Maestro (`composer-input`, `send`) se perderían o habría que
  reconstruirlos.
- El presupuesto de movimiento es de 300 ms (`durations.ts`). `withSpring` con
  `duration` dura 1,5 veces lo que dice; `withTiming` dura lo que dice.

**Lo que el spike cerró (2026-10-21,
`.specify/assessments/042-s2-vidrio-en-el-pie/decision.md`):** el vidrio sigue
al cambio de altura cuando es la altura del contenedor la que se anima
(10 fotogramas continuos a 30 fps, solapados con el teclado); con una
transición `layout` en un envoltorio, salta en uno. `@expo/ui` no hace falta.

**Cuidados que vienen de la documentación:**
- Ninguna opacidad menor que 1 en el `GlassView` ni en sus padres: con una
  opacidad combinada por debajo de 0,02 el efecto no se instala. Los fundidos
  de entrada y salida van en los **hijos**, nunca en la superficie.
- `glassEffectStyle` puede cambiar con `{ animate: true }`; cambiar
  `isInteractive` recrea el efecto. No se usan a mitad de una transición.

**Alternativas:**
- **`@expo/ui` desde el principio.** Descartado por lo de arriba. Queda como
  respaldo del spike.
- **`expo-blur`.** Es el material antiguo, y la dirección prohíbe el vidrio
  hecho a mano.

## D4 · El hilo pasa por debajo: lista invertida con un separador, y el pie en `KeyboardStickyView`

**Decisión (revisada el 2026-10-21, H20):**
- La conversación deja el `KeyboardAvoidingView` con el pie anclado: el
  `FloatingSurface` va dentro de un `KeyboardStickyView` superpuesto al pie,
  y el `FlatList` invertido sigue siendo el de React Native, sin
  `renderScrollComponent`.
- La superficie mide su contenido con `onLayout` y entrega su **holgura**
  (contenido, borde, margen flotante y `FOOT_GAP`) a la pantalla como un
  número (`onClearance`). La pantalla la guarda en estado y pinta un
  **separador** al pie visual de la lista (`ListHeaderComponent` de la lista
  invertida) con esa altura más lo que el teclado levanta el pie
  (`Keyboard.addListener`, `keyboardWillShow/Hide`). Los cambios van con
  `LayoutAnimation` del sistema (`durations.state` para el pie; la duración y
  curva del teclado para el teclado), nunca con una propiedad de layout
  animada por Reanimated dentro de la lista.
- La lista va envuelta en el `ScrollViewMarker` de react-native-screens
  (`react-native-screens/experimental`; está compilado porque expo-router
  construye la librería con `RNS_GAMMA_ENABLED`) con los cuatro efectos de
  borde en `hidden`, y, donde la cabecera es transparente (Liquid Glass),
  arranca bajo su borde inferior (`marginTop: headerHeight`); en Android y
  antes de iOS 26 el contenido ya empieza bajo la cabecera opaca, sin hueco.
  El hueco de arriba es solo 8 pt.
- `offset.opened` del `KeyboardStickyView` compensa `insets.bottom`, para que
  no quede un hueco entre el cuadro y el teclado.

**Por qué (lo que el pase en «13 26» enseñó, H20):**
- **iOS 26 dibuja su efecto de borde (`UIScrollEdgeEffect`) sobre toda la
  lista invertida** en cuanto el hilo puede desplazarse: con el `scaleY: -1`
  de `inverted`, el degradado que debería quedar bajo la barra cubre el hilo
  entero y las filas quedan al 13 % de opacidad (y desaparecen con «Aumentar
  contraste» o «Reducir transparencia», que vuelven el efecto opaco). Se vio
  con `KeyboardChatScrollView`, con un separador animado por Reanimated y con
  un separador fijo: cualquier hilo más alto que la pantalla.
- La opción `scrollEdgeEffects` de la pantalla no llega al hilo (medido:
  sigue al 13 %). react-native-screens la aplica a la primera vista de
  desplazamiento de la cadena de primeros descendientes **cuando llegan las
  opciones**; lo más probable es que entonces el hilo aún no exista (la
  pantalla pinta primero el esqueleto de carga y monta la lista al llegar la
  conversación). El `ScrollViewMarker` aplica el efecto a lo que envuelve
  cada vez que se monta, y sí llega. (Una primera explicación —que el primer
  descendiente era la configuración de la cabecera— era falsa: la librería
  pinta esa configuración *después* del contenido.) El marcador va en
  `ContentScroll` (`src/ui/content-scroll.tsx`), que en Android es una vista
  normal.
- Sin efecto suave, el contenido que pasara bajo el título de la cabecera
  chocaría con él; por eso la lista empieza bajo la cabecera. La cabecera de
  vidrio sigue siendo la del sistema (sus botones son cápsulas de vidrio); lo
  que se pierde es el fundido del contenido bajo el título.
- `KeyboardChatScrollView` queda fuera de la conversación: su relleno es un
  `contentInset` grande (hasta una pantalla de «espacio en blanco») que, con
  el efecto de borde, es exactamente lo que fallaba; y con el efecto oculto,
  el separador en estado hace lo mismo con menos piezas. La librería se queda
  para el `KeyboardStickyView`.

**Lo que el spike cerró (comprobación 2) y sigue valiendo:** el cuadro queda
pegado al teclado y crece con el texto; el cambio del panel al cuadro es
continuo (vídeo `evidence/morph.mp4`, T059).

**Alternativas:**
- **`KeyboardChatScrollView` como `renderScrollComponent` (la decisión
  original).** Descartada por lo de arriba: su inset es la zona que iOS 26
  atenúa.
- **Un separador animado por Reanimated (`useAnimatedStyle` con `height`).**
  Igual de atenuado; además, una propiedad de layout animada en el hilo del
  UI dentro de la lista obliga a recomprometer el árbol cada fotograma.
- **Lista sin `inverted`** (datos ascendentes y `scrollToEnd`). Evitaría el
  `scaleY: -1`, pero cambia el anclaje al final y el mantenimiento de la
  posición al cargar mensajes antiguos; no hace falta con el marcador.

## D5 · La apariencia del sistema se lee en vivo

**Decisión:**
- Un hook nuevo, `useSystemAppearance()`, en `src/theme/`, que devuelve
  `{ reduceTransparency, increaseContrast, reduceMotion }` y se actualiza con
  los eventos de `AccessibilityInfo`:
  - iOS: `reduceTransparencyChanged` y `darkerSystemColorsChanged`.
  - Android: `highTextContrastChanged`.
  - Las dos: `reduceMotionChanged`.
- `FloatingSurface` se vuelve opaca con «Reducir transparencia» (R4.2) y lleva
  un borde de `colors.border` con «Aumentar contraste» o con el contraste alto
  de Android (R4.3).
- `motionFor()` deja de depender de `useReducedMotion()` de Reanimated y recibe
  el valor en vivo, pasando `ReduceMotion.Always` o `ReduceMotion.Never` de
  forma explícita.

**Por qué:**
- `useReducedMotion()` de Reanimated devuelve el valor **del arranque** y no
  vuelve a renderizar; `ReduceMotion.System` lee ese mismo valor. La spec pide
  que el cambio se adopte con la app abierta (R4.5).
- `isLiquidGlassAvailable()` no mira «Reducir transparencia»; la documentación
  de Expo manda a `AccessibilityInfo.isReduceTransparencyEnabled()`. Nada en el
  Swift del paquete lo trata, así que lo decidimos nosotros y el resultado es
  el mismo con cualquier comportamiento de UIKit: opaco.

**Alternativas:**
- **Fiarse de UIKit.** No está verificado y dejaría el requisito sin prueba.

## D6 · Pestañas: nada que cambiar; búsqueda en `automatic`

**Decisión:**
- `NativeTabs` se queda como está: en iOS 26 ya es vidrio, con
  `minimizeBehavior="onScrollDown"`; en iOS anterior a 26 la opción se ignora
  (solo deja un aviso en el log) y la barra es la de siempre.
- La búsqueda de la Bandeja se queda en la cabecera (`headerSearchBarOptions`)
  con `placement: "automatic"`. **Por ver** dónde la coloca iOS 26 dentro de un
  controlador de pestañas; si cae en un sitio inusable, el respaldo es
  `stacked`, que es exactamente el aspecto de hoy.
- No se usa la pestaña de búsqueda (`role="search"`): en iOS 26 es una pestaña
  separada sin título, y promete buscar en toda la app.

**Por qué:**
- `tintColor` baja a `controller.view.tintColor` y en iOS 26 tiñe también el
  brillo de la selección en el vidrio. Es el único color de acento (R1.6); lo
  que hay que verificar es que se lee sobre contenido claro y oscuro.
- La pestaña de búsqueda real (`UISearchTab`) exige iOS 26.1 y
  `unstable_nativeProps`; no es para un filtro de una lista.

## D7 · Hojas: Ajustes como hoja en iOS; el contenido no tapa el vidrio

**Decisión:**
- En iOS, `ajustes` pasa de `modal` a `formSheet` con `sheetAllowedDetents:
  [0.6, 1]` y `sheetGrabberVisible`, los mismos valores que la hoja de
  contacto: las dos hojas se detienen en el mismo sitio.
- En Android, Ajustes sigue como pantalla (`card`), que es lo que decía la D24
  de la 031.
- En iOS 26, las hojas no pintan `colors.background` en su contenedor: hoy
  `contacto.tsx` lo hace y tapa el material del sistema. Las filas y tarjetas
  de dentro siguen opacas.
- La cabecera de la hoja sigue la D1.

**Por qué:**
- Con Liquid Glass, expo-router deja `contentStyle` transparente y
  `headerTransparent` en las `formSheet`, pero solo si no se han fijado
  (`createNativeStackNavigator.js:104-118`). Nuestros fondos las anulan.
- RNS 4.30 implementa `formSheet` en Android como `BottomSheetBehavior` con
  tres estados; no hace falta tocarlo.

**Por ver:** que UIKit pinta de vidrio la hoja a 0,6 con el contenido
transparente, y que el texto de las filas se lee encima. Lo cierra el spike.

## D8 · Inicio: un bloque de atención, un bloque de dinero, un bloque de conversaciones

**Decisión.** `HomeView` pasa de «tarjeta + rejilla de tres métricas + gasto +
gráfico» a tres bloques, en este orden:
1. **Atención** (`attention.tsx`), sin la insignia que contaba avisos (H13). El
   número de conversaciones va una sola vez, en la fila, junto a la acción.
   Sin nada pendiente, la línea tranquila de hoy. La métrica «Esperan a una
   persona» **desaparece** (R5.1, R5.3): la insignia de la pestaña ya lo dice.
2. **Dinero**: una lista agrupada con tres filas (saldo disponible; días que
   alcanza, con el `Meter`; gasto del mes) y, WHERE hay módulo de Consumo, una
   fila de avance a Consumo. Sustituye a la métrica de saldo y a `SpendCard`
   (R5.4). Sin módulo de Consumo, el bloque no lleva fila de avance ni responde
   al toque (R6.4). Sin saldo asignado, lo dice como hoy.
3. **Conversaciones**: una cifra protagonista (últimos 7 días) con su tendencia
   y las barras por día debajo, en un solo bloque. Hoy son una métrica y una
   tarjeta aparte.

`Metric` y `SpendCard` se retiran. Entran dos primitivas, `Group` y `Row`
(contrato en [contracts/ui.md](contracts/ui.md)).

**Por qué:** H1, H2, H3 y H13. El contenido de Inicio es el mismo que pide la
031 R4.1; cambia cómo se agrupa.

## D9 · Consumo: lista agrupada, un gráfico y una sola salida a la web

**Decisión:**
- Sin la frase de introducción (R9.1): las claves `lite.usage.intro*` dejan de
  usarse en la app y se quedan en la consola.
- Las tres métricas pasan a filas de una lista agrupada (saldo, días,
  gasto del mes con proyección, conversaciones del mes con media).
- El gráfico es un bloque con su cifra protagonista (gasto del periodo) y el
  selector de 7, 30 y 90 días debajo. **El selector solo aparece si la serie
  de 90 días tiene algún gasto**: la app pide primero los 90 días, que
  contienen a los otros dos. Sin gasto, el bloque dice qué hará aparecer el
  gráfico (R9.2).
- La salida a la consola web pasa de párrafo centrado a una fila con el icono
  de enlace externo y el destino (R6.2). El test `consumo.test.tsx:89` cambia
  con ella.

## D10 · Ajustes: dos secciones para dos riesgos

**Decisión.** Cuenta · Avisos · Consola web · **Cerrar sesión** (su propio
grupo) · **Solicitar el borrado de la cuenta** (último grupo, en color de
peligro, con una línea de pie que dice qué pasa después). «Cerrar sesión» deja
de ir en rojo. Las confirmaciones (`Alert`) no cambian (031 R11.3, R11.4).

## D11 · Ir a otro sitio: una fila con chevrón; salir, una fila con enlace externo

**Decisión.** `RowButton` es la única forma de navegar en Inicio, Consumo y
Ajustes: chevrón para lo que es de la app; icono de enlace externo y subtítulo
con el destino para la consola web. Se retiran el chevrón en la cabecera de
tarjeta, el botón «Ver consumo» y el párrafo verde.

## D12 · Formas y pulsación

**Decisión:**
- **Botones y controles**: cápsula (`radius.full`) en iOS 26 **y** en Android,
  donde Material 3 Expressive también los hace redondos. En iOS anterior a 26,
  cápsula también: no hay razón para dos formas.
- **Tarjetas y grupos**: radio 12, un token propio de la app (`CARD_RADIUS` en
  `src/theme/theme.ts`, junto a `TOUCH` y `SHEET_RADIUS`). Hoy es 8, que es el
  de la web.
- **Esquinas concéntricas**: `concentric(outer, padding)` devuelve el radio
  interior; el botón de enviar dentro del cuadro de escribir y las cápsulas
  dentro de un grupo lo usan.
- **Pulsación**: en iOS, al apoyar el dedo (`onPressIn`) el control se encoge a
  0,97 con `withTiming(durations.fast)` y su fondo pasa al tono de pulsación
  (`primary` → `primaryDeep`; `card` → `muted`); al soltar, vuelve. En Android,
  `android_ripple` del `Pressable`, que es la pulsación de Material. Se retira
  la bajada de opacidad en `Button`, `IconButton`, `RowButton`, `Metric`,
  `bubble.tsx` y `filters.tsx`.

**Por qué:** H6 y R7.1, R7.2. Los tokens generados no pueden crecer
(`gen:check` compara byte a byte, y `--radius-lg` es `initial` en la fuente),
así que lo propio de la app vive a mano en `theme.ts`, como ya hacen `TOUCH` y
`SHEET_RADIUS`.

**Alternativas:**
- **Cambiar la forma al pulsar en Android** (de redondo a 8 dp, como Material
  3 Expressive). Queda fuera: la ondulación ya es la pulsación documentada.

## D13 · Tipografía: los estilos del sistema en iOS; la consola en Android

**Decisión.** `src/theme/type.ts` elige por plataforma:
- **iOS**, los tamaños del HIG al tamaño por defecto: largeTitle 34/41 bold ·
  title 22/28 bold (Title 2) · headline 17/22 semibold · body 17/22 · callout
  16/21 · subhead 15/20 · footnote 13/18 · caption 12/16 · figure 28/34 bold
  tabular (Title 1). Sin `letterSpacing` en los títulos (R7.3).
- **Android**, la escala generada de la consola, que ya es la de Material
  (body 16/24, title 22/28).

**Por qué:** H9. React Native escala en iOS con un solo multiplicador por
categoría (`RCTFontSizeMultiplier`), no con la curva por estilo de Apple:
al máximo, Body sale a ~61 pt donde Apple pone 53. Es el comportamiento de
la plataforma de RN y se acepta; lo que se corrige es el punto de partida.

## D14 · El título de Android al 200 %

**Decisión.** Fijar `headerTitleStyle.fontSize` en Android con el tamaño de
`type.title`; RNS lo aplica con `setTextSize(float)`, en `sp`, que escala.
**Por ver** en el emulador al 200 %: si sigue sin crecer, la causa es la
escala no lineal de Android 14 o el título de una línea de AndroidX, y se
documenta con la captura.

## D15 · Los textos

**Decisión.** `lite.attention.attend` pasa a «Atender ahora» / «Answer now»,
en `apps/console/src/i18n/lanes/lite.ts`, de donde la app lo genera. La
consola lo muestra en `lite-attention.tsx:72`: dice lo mismo en los dos
sitios (031 R14.6).

## D16 · Cómo se ve iOS 26 sin tocar el Xcode de la máquina

**Decisión:**
- Un perfil nuevo de EAS, `development-simulator` (`ios.simulator: true`,
  `developmentClient: true`), compilado en la nube. EAS compila el SDK 58 con
  la imagen `macos-tahoe-26.6-xcode-27.1` (alias `sdk-58`): SDK de iOS 27, que
  trae Liquid Glass y además ignora `UIDesignRequiresCompatibility`.
- El `.app` resultante se instala en el simulador local: la máquina tiene el
  runtime **iOS 26.0.1** y Xcode 26.0.1 lo ejecuta. Se crean dos dispositivos:
  iPhone SE (3.ª generación), el de 4,7″ de la spec, e iPhone 17.
- `xcrun simctl ui` cambia claro/oscuro, «Aumentar contraste» y el tamaño de
  texto, incluidas las categorías de accesibilidad. «Reducir transparencia» y
  «Reducir movimiento» se activan en Ajustes del simulador.
- `app.config.ts` no lleva `UIDesignRequiresCompatibility`: el vidrio está
  encendido.

**Lo que esto no cubre, y queda en manos de Luis:**
- **El vidrio claro o tintado** (Ajustes › Pantalla y brillo › Liquid Glass)
  llegó en iOS 26.1. El runtime local es 26.0.1; otro runtime son ~7,5 GB y
  quedan 7,7 GB de disco. Se prueba en un iPhone con 26.1, o cuando haya disco.
  No hay API pública para detectarlo: el material del sistema lo aplica solo.
- **El respaldo en iOS anterior a 26** necesita un runtime de iOS 18, con el
  mismo problema de disco, o un iPhone con iOS 18.
- **La postura, los gestos y el rendimiento** se juzgan en un teléfono.

## D17 · Lo que no cambia, a propósito

- La barra de pestañas y las transiciones entre pantallas (031 R14.8).
- Las cifras y de dónde salen (031 R4.3).
- Los `testID` de Maestro: `composer-input`, `send`, `take-over`,
  `waiting-card`.
- La escala de tokens generados y los generadores: nada nuevo entra en
  `tokens.gen.ts`.

## D18 · Spike S2, antes de construir el material

Va por el flujo `assess` (`.specify/assessments/042-s2-vidrio-en-el-pie/`) y
**su código no se fusiona**. Una sola pantalla de conversación y una hoja, en
el simulador de iOS 26 con el build de D16. Cierra lo marcado **por ver**:

| # | Qué comprueba | Decisión que cierra | Si falla |
|---|---|---|---|
| 1 | Un `GlassView` sigue un cambio de altura de Reanimated (240 ms) sin parpadear ni recrearse | D3 | `@expo/ui` solo en el pie, con `Host`; D3 se reescribe |
| 2 | `KeyboardChatScrollView` + `KeyboardStickyView` con lista invertida bajo una cabecera transparente, y con el texto al máximo | D4 | `KeyboardAvoidingView` y pie absoluto con relleno calculado |
| 3 | Dónde cae `headerSearchBarOptions.placement: "automatic"` dentro de las pestañas | D6 | `stacked` |
| 4 | Una `formSheet` a 0,6 con contenido transparente se pinta de vidrio y las filas se leen | D7 | Contenedor con `colors.background`, como hoy |
| 5 | `Stack.Toolbar.Button` se agrupa en cápsula y el tinte se lee sobre contenido claro y oscuro | D2, D6 | Ajustar el tono del tinte en la spec, no en el código |
| 6 | `GlassView` con «Reducir transparencia»: qué hace UIKit por su cuenta | D5 | Nada: la app ya lo vuelve opaca |

Evidencia: capturas en `evidence/`, y una línea por fila de esta tabla.

**Resultado (2026-10-21, «SE 26», build 2):** las seis se sostienen; la 1 con
la corrección de D3 (altura animada, no `layout`); la 2 con dos cuidados (D4);
la 5 con `tintColor` explícito en los botones de barra (D2, no heredan
`headerTintColor`); la 4 con `contentInsetAdjustmentBehavior="automatic"` en el
contenido de las hojas, porque con vidrio su cabecera es transparente (T066,
T067); la 6 confirma que UIKit vuelve opacos barras, hoja y `GlassView`, y la
app además pasa `FloatingSurface` a `colors.card` (D5). Se verificó H14 (el
título grande vuelve sin fondo) y apareció **H16**: tras «Reintentar» un error
de `/me`, el contenido queda empujado ~120 pt bajo la cabecera (T069). Detalle
y capturas en `.specify/assessments/042-s2-vidrio-en-el-pie/`.

## Licencias de lo que entra (constitución §VIII)

| Dependencia | Versión | Licencia | Dónde se leyó |
|---|---|---|---|
| `expo-glass-effect` | ~58.0.4 | **MIT** | `package.json` (`"license": "MIT"`) y el `LICENSE` del paquete, copyright «2015-present 650 Industries, Inc. (aka Expo)» |

El párrafo que lo permite: «Permission is hereby granted, free of charge, to
any person obtaining a copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software».

No entra `@expo/ui` (D3). Si el spike lo hiciera entrar: MIT según su
`package.json`, pero **el paquete no lleva fichero `LICENSE`**; el de la raíz
del repositorio de Expo es el mismo texto MIT. Se citaría ese.

No entra `expo-blur`. No entra nada en la API, en el worker ni en la consola.
