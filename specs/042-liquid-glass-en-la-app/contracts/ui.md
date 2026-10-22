# Contrato de UI: superficies, primitivas y composición

**Spec**: [../spec.md](../spec.md) · **Decisiones**: [../research.md](../research.md)

Es lo que las pantallas pueden dar por hecho y lo que las pruebas comprueban.
Nada de aquí cambia qué datos se leen ni qué acciones existen (031).

## 1. Qué material lleva cada superficie

«Vidrio» es el material del sistema de iOS 26 (barras, hojas, elementos de
barra) o un `GlassView` de `expo-glass-effect` donde el sistema no llega.
«Opaco» es la tarjeta de hoy: `colors.card` con borde `colors.border`.

| Superficie | iOS 26+ | iOS 26+ con «Reducir transparencia» | iOS < 26 | Android |
|---|---|---|---|---|
| Barra superior (y título grande) | Vidrio del sistema, sin fondo propio | El sistema la vuelve opaca (lo comprueban T018 y T074) | Opaca `colors.background`, como hoy | Material, `colors.background`, como hoy |
| Barra de pestañas | Vidrio del sistema | El sistema la vuelve opaca (T018, T074) | La de siempre | Material 3 |
| Botones de barra | `Stack.Toolbar.Button` / `.Menu`, tinte `primaryText` | Ídem | Ídem | `headerRight` con `IconButton` |
| Pie de la conversación (`FloatingSurface`) | `GlassView` `regular`, flotante, radio `concentric` | **Opaca y anclada** (la app lo decide) | Opaca y anclada: el pie de la 031 | Opaca y anclada |
| Hojas (contacto, Ajustes) | Material del sistema; el contenedor no pinta fondo | El sistema las vuelve opacas (T018, T074) | Contenedor con `colors.background` | Hoja de Material (`formSheet`) / pantalla (Ajustes) |
| Tarjetas, grupos, filas, burbujas, cifras, gráficos, formularios, avisos | **Opacos siempre** | | | |

Con «Aumentar contraste» (iOS) o contraste alto (Android), toda superficie
flotante lleva un borde de 1 pt en `colors.border`.

Prohibido: un `GlassView` dentro de otro; opacidad menor que 1 en un
`GlassView` o en sus padres; `expo-blur`.

## 2. Primitivas

### `FloatingSurface`

```ts
<FloatingSurface
  tone?: "neutral" | "warning"   // warning: el panel de espera
  radius?: number                // por defecto CARD_RADIUS; el cuadro usa concentric()
  style?, testID?, children
/>
```

- Decide el material con `isLiquidGlassAvailable()` y `useSystemAppearance()`
  (tabla §1). La decisión es por render: si el ajuste cambia con la app
  abierta, la superficie cambia.
- **Dos presentaciones, un solo código.** Con vidrio, **flota**: márgenes
  laterales de 12, radio `CARD_RADIUS` o `concentric`, sin borde. Opaca, se
  presenta **anclada**: ancho completo, sin márgenes ni radio, con borde
  superior hairline en `colors.border`. Sobre la lista con su relleno, la
  anclada se ve exactamente como el pie de la 031 (spec R3.1). Solo cambia el
  estilo; la pila, la medida de altura y el teclado son los mismos.
- `tone="warning"` tiñe el **borde** y un filete superior, no el vidrio: el
  texto se sigue leyendo sobre cualquier fondo.
- Nunca anima su propia opacidad. Los hijos entran y salen con `motion.enter`
  y `motion.exit`.
- **Anima su propia altura** (spike S2, comprobación 1): mide su contenido con
  `onLayout` y lleva la altura del contenedor con `withTiming` a
  `durations.state` y `Easing.out(cubic)`; con «Reducir movimiento», sin
  animar. Una transición `layout` en un envoltorio no mueve el vidrio.
- **`clearance`**: la pantalla le pasa un `SharedValue` y la superficie
  escribe en él la **holgura** — contenido, borde, margen flotante y
  `FOOT_GAP` (8) — que la lista usa como relleno inferior; si solo cambia el
  marco (borde con «Aumentar contraste», margen al cambiar el material), la
  holgura se recalcula sin volver a medir.
- **Nunca ocupa toda la pantalla** (R4.7): con el texto al máximo el panel de
  espera sobrepasa la ventana; la superficie se detiene en `FOOT_MAX_SHARE`
  (0,6) de la altura de la ventana y su contenido se desplaza dentro
  (`ScrollView`, solo entonces), de modo que el hilo conserva el resto.
- Expone `onLayout` para que la pantalla mida su altura.

**Pruebas:** con vidrio disponible renderiza `GlassView` flotante; sin él,
`View` anclada con `colors.card`, ancho completo y borde superior; con
«Reducir transparencia», `View` anclada aunque haya vidrio; con «Aumentar
contraste», `borderWidth` 1 y `colors.border` en todo el contorno.

### `Group` y `Row`

```ts
<Group title?: string accessibilityLabel?>      // lista agrupada: fondo card, CARD_RADIUS, separadores
  <Row label value? hint? tone? onPress? kind?: "push" | "external" | "none" testID? />
  <Row ...>{children}</Row>                       // una fila con contenido propio (el Meter)
</Group>
```

- `kind="push"` pinta el chevrón; `kind="external"` el icono de enlace externo
  y exige `hint` con el destino; `kind="none"` (por defecto) no responde al
  toque y no pinta indicador.
- `onPress` sin `kind` es un error de tipo: la forma y la acción van juntas
  (R6.1, R6.4).
- La pulsación es la de D12 (fondo `colors.muted` al apoyar; ondulación en
  Android). Nada de opacidad.
- Con el texto al máximo, `label` y `value` se apilan (`flexWrap`), nunca se
  cortan.

### `Button`

- Variantes: `primary`, `secondary`, `ghost`, `destructive`. Sin cambios de
  API.
- Forma: cápsula (`radius.full`) en todas las plataformas. Altura mínima
  `TOUCH`.
- Pulsación (R7.2): iOS, escala 0,97 con `withTiming(durations.fast)` y fondo
  al tono de pulsación (`primary` → `primaryDeep`, `secondary` → `muted`);
  Android, `android_ripple`. Fuera la opacidad 0,75.
- `busy` y `disabled` se distinguen sobre vidrio y sobre opaco: `disabled` baja
  el contraste del **contenido** (`mutedForeground`) y apaga el relleno
  (`muted`; `ghost` sigue sin fondo), nunca la opacidad del botón (R4.8).
  `busy` conserva los tonos y el tamaño del botón, y lo dice a la tecnología
  de apoyo. Con «Reducir movimiento», la pulsación es solo el tono, sin escala.
- `IconButton` es la misma cápsula: tono `muted` al apoyar, ondulación sin
  borde en Android, el icono en `mutedForeground` si está desactivado.

### `RowButton` (existente)

Gana `kind: "push" | "external"` con las mismas reglas que `Row`. Es la única
forma de ir a otro sitio en Inicio, Consumo y Ajustes (R6).

### Tema (`src/theme/theme.ts`)

```ts
export const CARD_RADIUS = 12;                 // tarjetas y grupos
export function concentric(outer: number, padding: number): number; // max(outer - padding, 4)
export function useSystemAppearance(): { reduceTransparency: boolean; increaseContrast: boolean; reduceMotion: boolean };
```

Lo propio de la app vive aquí, no en `tokens.gen.ts` (`gen:check` lo compara
byte a byte con la consola).

### Tipografía (`src/theme/type.ts`)

| Variante | iOS (pt, tamaño/interlineado, peso) | Android (de los tokens) |
|---|---|---|
| largeTitle | 34/41 700 | 2xl 32 |
| title | 22/28 700 | xl 24 |
| headline | 17/22 600 | md 18 |
| body | 17/22 400 | base 16 |
| bodyStrong | 17/22 600 | base 16 |
| callout | 16/21 400 | sm+1 15 |
| subhead | 15/20 500 | sm 14 |
| footnote | 13/18 400 | sm−1 13 |
| caption | 12/16 500 | xs 12 |
| figure | 28/34 700 tabular | 2xl 32 tabular |

Sin `letterSpacing` en ninguna variante de iOS. Cada variante de iOS lleva
`maxFontSizeMultiplier` = su tamaño en AX5 de la tabla de Apple entre el de
base (`maxScale` en `type.ts`): largeTitle 60, title 43, headline/body 53,
callout 51, subhead 49, footnote 44, caption 43, figure 44 (R4.6).

## 3. Composición de las pantallas

### Inicio (`HomeView`)

```
[PartialNotice]                       solo si home.errors > 0
Atención  (Card tone danger)          solo si home.attention > 0
  título «Necesita tu atención»       sin insignia
  fila espera: «N conversaciones esperan a una persona» + Button «Atender ahora»
  fila saldo: texto + RowButton kind=push a Consumo (si módulo)
—o— línea tranquila (Card tone positive)
Dinero  (Group)                       solo si home.balance
  Row «Saldo disponible» value
  Row «Alcanza» value «N días» + Meter      (si runway)
  Row «Gasto del mes» value                  (si home.spend_month)
  Row kind=push «Ver consumo» (`lite.spend.see`)   (si módulo usage; si no, no hay fila)
Conversaciones  (Card)                solo si home.conversations
  figure N  + hint tendencia
  DayBars
```

Invariantes que prueban los tests: el número de conversaciones que esperan
aparece **una** vez en el árbol (CE-001); con `attention` vacío no existe
ningún texto «esperan»; sin módulo `usage` el grupo de dinero no tiene
ninguna fila con `onPress`.

### Consumo (`UsageView`)

```
Cifras  (Group)
  Row «Saldo disponible» · Row «Alcanza» + Meter · Row «Gasto del mes» hint proyección
  Row «Conversaciones este mes» hint media
Gasto por día  (Card)
  figure gasto del periodo
  Segmented 7 · 30 · 90            solo si la serie de 90 días tiene gasto
  DayBars                           —o— texto: qué hará aparecer el gráfico
  Button «Por agente»               si hay más de un agente
Row kind=external «Abrir la consola web» hint «El detalle técnico y la exportación»
```

Sin frase de introducción.

### Ajustes

```
Group Cuenta        persona, correo, negocio, papel
Group Avisos        interruptores
Row kind=external   «Abrir la consola web»
Group               RowButton «Cerrar sesión»  (tone foreground)
Group               RowButton «Solicitar el borrado de la cuenta» (tone destructive)
                    pie: «Auphere te escribirá para confirmarlo y cerrará tu acceso.»
Caption versión
```

iOS: `formSheet` `[0.6, 1]`. Android: pantalla.

### Pie de la conversación

Una `FloatingSurface` sobre el hilo, dentro de `KeyboardStickyView`. Su
contenido según `mode`:

| `mode.kind` | Contenido | Tono |
|---|---|---|
| `waiting` | icono mano + título + motivo (2 líneas, «Leer más» abre el motivo entero en una hoja de acciones) + Button primary «Tomar el control» (`take-over`) + Button ghost «Devolver al agente» | warning |
| `agent` / `other` | quién atiende + Button secondary «Tomar el control» | neutral |
| `resolved` | texto + Button secondary «Reabrir» | neutral |
| `mine` | `TextInput` (`composer-input`) + adjuntar + respuestas + enviar (`send`, círculo `primary`, radio `concentric`) | neutral |
| `mine` sin ventana de 24 h | el texto del bloqueo, sin cuadro | neutral |

- El cambio de `mode` cambia los **hijos**; la superficie es la misma y es
  ella quien anima su altura (`withTiming`, `durations.state`,
  `Easing.out(Easing.cubic)`); con «Reducir movimiento», la altura cambia sin
  animar y los hijos solo se funden (R2.5, R2.6).
- La lista es el `FlatList` invertido de React Native, envuelto en el
  `ScrollViewMarker` de react-native-screens con los efectos de borde de iOS
  26 en `hidden` (H20), y empieza bajo la cabecera (`marginTop: headerHeight`).
- La superficie entrega su holgura por `onClearance`; la pantalla la guarda en
  estado y pinta un separador al pie visual de la lista con esa altura más lo
  que el teclado levanta el pie, animado con `LayoutAnimation` (R2.2). Nada
  de propiedades de layout animadas por Reanimated dentro de la lista.
- `testID` que no cambian: `waiting-card` (ahora en la superficie en modo
  `waiting`), `take-over`, `composer-input`, `send`.

### Cabecera (`useHeaderOptions`)

```ts
// iOS 26+: { headerTintColor, headerTitleStyle: {color}, headerLargeTitleStyle: {color} }
// iOS < 26 y Android: lo de hoy, más headerTitleStyle.fontSize en Android
// iOS: headerLargeTitleEnabled: true en las pestañas
```

Botones de barra en iOS: `Stack.Toolbar placement="right"` con
`Stack.Toolbar.Button icon="gearshape" accessibilityLabel`; en la conversación,
`Stack.Toolbar.Menu` con «Devolver al agente» la primera. Android: `headerRight`.

## 4. Movimiento

| Momento | iOS 26 | Antes de 26 y Android | «Reducir movimiento» |
|---|---|---|---|
| Panel → cuadro (tomar el control) | La superficie anima su altura (`withTiming`, 240 ms) y los hijos se funden; vibración de éxito. Medido en el spike: 10 fotogramas continuos a 30 fps | Igual, sobre la tarjeta opaca | Fundido de 160 ms, sin cambio de altura animado |
| Pulsar un control | Escala 0,97 + tono, 160 ms | Ondulación (Android) / igual (iOS) | Solo el tono, sin escala |
| Llega un mensaje | `motion.enter` (fundido + 8 pt) | Igual | Fundido |

Nada pasa de 300 ms (`durations.ts` lo comprueba al arrancar).

## 5. Texto compartido

| Clave | Antes | Después |
|---|---|---|
| `lite.attention.attend` (`apps/console/src/i18n/lanes/lite.ts`) | es «Atender» · en «Attend» | es «Atender ahora» · en «Answer now» |

La app lo recibe por `pnpm gen`; `gen:check` falla hasta que se regenere.
Claves propias nuevas en `app.{es,en}.ts`: la fila de avance a Consumo, el pie
del borrado, el texto del gráfico vacío, «Leer más».
