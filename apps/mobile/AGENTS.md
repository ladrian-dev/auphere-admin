# Para agentes que trabajen en apps/mobile

Expo/React Native (SDK 58). Antes de tocar nada, lee `docs/app-movil.md` y la
spec 031; la spec viva manda.

## Expo cambia en cada SDK: no te fíes de lo que recuerdas

Antes de escribir código que toque una API de Expo, EAS o React Native:

1. Mira la versión de `expo` en `package.json`.
2. Lee la documentación de esa versión: `https://docs.expo.dev/versions/v<major>.0.0/`
   o el índice `https://docs.expo.dev/llms.txt`.
3. Deja que `pnpm typecheck` valide: los tipos de los módulos son la verdad.

## Reglas de esta app

- Instala con `npx expo install <paquete>` (elige la versión compatible con el
  SDK) y lee su licencia antes (constitución §VIII; tabla en `research.md`).
- Nada de hex: el color sale de `useTheme().colors` (`tokens.gen.ts`).
- Las palabras de la consola salen de `src/i18n/lite.gen.ts`; las propias, de
  `src/i18n/app.{es,en}.ts`. Nunca las dupliques.
- Las rutas son de expo-router en `src/app/`; lo demás vive fuera.
- Antes de dar algo por hecho: `pnpm verify` (o `./scripts/verify.sh mobile`
  desde la raíz).

## Dirección de diseño: Liquid Glass, con exigencia

Luis lo pidió el 2026-10-20: la interfaz de iOS adopta **Liquid Glass**, y cada
cambio de UI se mira con ojo crítico y perfeccionista. Esto concreta la D24 de
la spec 031 (nativo primero; la marca en el color, el contenido y la voz), no
la sustituye.

- **El vidrio es para navegar y para los controles, nunca para el contenido.**
  - Lleva vidrio: barras, pestañas, la barra de herramientas, el cuadro de
    escribir y los controles que flotan sobre el hilo.
  - Se queda opaco: listas, burbujas, cifras y gráficos.
  - Nunca vidrio sobre vidrio.
- **Primero el del sistema.**
  - Las pestañas nativas, la cabecera nativa sin fondo propio, las hojas y los
    elementos de barra nativos ya traen Liquid Glass en iOS 26.
  - `expo-glass-effect` solo para lo que el sistema no da.
  - Nada de vidrio hecho a mano con `expo-blur`.
- **Respaldo para iOS anterior a 26.**
  - La app arranca en iOS 16.4. Sin `isLiquidGlassAvailable()`, la superficie
    se queda como hoy.
  - «Reducir transparencia» y «Aumentar contraste» se respetan siempre.
  - Android sigue en Material 3 Expressive, sin imitar el vidrio.
- **Se ve en el simulador o no está hecho.**
  - Capturas de iOS 26 en claro y oscuro, con texto grande y con «Reducir
    transparencia»; además, Android en claro y oscuro.
  - Una captura de Android no prueba nada sobre el vidrio.
- **Antes de dar una pantalla por buena,** pásale las skills de
  `.claude/skills/`. Son locales y no van a git, igual que las de la raíz:
  - se restauran con `npx skills experimental_install`, que lee
    `skills-lock.json`;
  - su `README.md` recoge los orígenes, las licencias y las advertencias.

  Las tres que se pasan son:
  - `ux-heuristics`, con severidades de 0 a 4;
  - `design-critique`, sobre las capturas;
  - `impeccable`, con `reference/ios.md` y `reference/audit.native.md`.

  Un hallazgo de severidad 3 o 4 bloquea igual que un test rojo.
- **De dónde se parte.** La auditoría de partida está en la KB:
  `research/2026-10-20-liquid-glass-app-movil.md`.
- **El rediseño cambia comportamiento y va por la spec 042**
  (`specs/042-liquid-glass-en-la-app/`, regla nº1). Los cambios de UI citan
  la spec 042 (su requisito o su tarea) y actualizan `docs/app-movil.md` en
  el mismo commit; lo que la spec no cubre abre una spec nueva, no un parche.

## Spec 069: el diseño nuevo (2026-11-21)

El aspecto lo manda el diseño aprobado por el owner. La spec está en `specs/069-la-app-con-el-diseno-nuevo/` y el inventario del diseño en la KB, en `research/2026-11-21-app-movil-a-tiendas/`. Lo que cambia para quien trabaje aquí:

- **Iconos:**
  - `<Icon name={icons.x} />` dibuja **Lucide** (trazo 1,75). Cada entrada de `icons` lleva también su símbolo del sistema (`.ios` y `.android`), que es lo único que aceptan el cromo nativo, `Stack.Toolbar`, los menús nativos y `NativeTabs`.
  - Un icono nuevo se importa por su ruta, `lucide-react-native/icons/<nombre>`, nunca desde el barril: Metro no lo poda.
  - Los logos de canal y la «G» de Google están en `ui/brand-icons.tsx`.
- **Letra:**
  - Los títulos y las cifras del diseño son los estilos `screenTitle`, `sheetTitle`, `dialogTitle`, `name` y `figureLarge` de `theme/type.ts`. El resto, fuente del sistema con Dynamic Type.
  - Ningún peso por encima de 600.
  - Helvena va en todos los builds (licencia confirmada el 2026-11-21): sus tres TTF están en `assets/fonts/helvena/`. Si falta uno, `app.config.ts` para el build. `APP_HELVENA=0` deja la fuente del sistema en un build local, para medir.
- **Color:**
  - Los roles nuevos de la app (`selection`, `highlight*`, `bubbleAgent`, `toast*`) salen del generador (`scripts/gen-tokens.mts`, `APP_ROLES`), sin tocar `tokens.css`.
  - Los colores de marca de los canales están en `useTheme().brand`.
- **Radios:** `RADII` de `theme/theme.ts`; las tarjetas usan 16.
- **Movimiento:**
  - Las microinteracciones del diseño están en `motion/micro.tsx`.
  - Nada pasa de 300 ms ni rebota.
  - Con «Reducir movimiento», fundido o estado final, sin acortar esperas que no son animación.
- **Datos de ejemplo:** `EXPO_PUBLIC_DEMO=1` en un build de desarrollo sirve toda la app con un negocio ficticio (`src/api/demo/`). Fuera de `__DEV__` no existe, y ningún perfil de `eas.json` lo activa (hay un test que lo comprueba).
- **Android:** sigue en Material 3, sin vidrio imitado y con las mismas funciones que iOS.
