# Implementation Plan: La app con el diseño nuevo

**Branch**: `069-la-app-con-el-diseno-nuevo` | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/069-la-app-con-el-diseno-nuevo/spec.md`

## Summary

Vestir `apps/mobile` con el diseño aprobado y ponerla al día con la web, sin cambiar la API. El trabajo se ordena así:

1. **Un sistema primero** (F1):
   - roles de color propios de la app en el generador de tokens;
   - una familia de títulos detrás de un solo valor (Helvena o el sistema);
   - iconos Lucide detrás del mismo componente `Icon` de hoy;
   - una escala de radios;
   - las microinteracciones como piezas reutilizables;
   - un modo de datos de ejemplo solo para desarrollo, para verificar todo en el simulador.
2. **Las pantallas, por áreas que no se pisan:** Inicio, Bandeja y Conversación, Reservas, Consumo y Ajustes, y Entrar. Lo de la web va en el área que le toca.
3. **Verificar:** `pnpm verify`, simulador de iOS 26 en claro y oscuro con datos de ejemplo, las puertas del workspace y una bitácora para la revisión de Luis.

## Technical Context

**Language/Version**: TypeScript (strict, `noUncheckedIndexedAccess`), React 19.3, React Native 0.88 (New Architecture), Expo SDK 58, expo-router 58
**Primary Dependencies**: las de hoy, más tres:
- `react-native-svg`, para los iconos Lucide y los logos de canal;
- `lucide-react-native`;
- `@shopify/react-native-skia`, para el líquido de Entrar.

Versiones y licencias, abajo («Licencias»).
**Storage**: ninguno nuevo. La sesión sigue en `expo-secure-store` (031) y lo de los clientes finales vive en memoria.
**Testing**: Jest 30 + `jest-expo` + `@testing-library/react-native` 14 (`fireEvent` es async: siempre con `await`). Los 442 tests de hoy son la red de «nada se pierde» (Requisito 20).
**Target Platform**: iOS 16.4+ (Liquid Glass desde iOS 26) · Android con API objetivo de SDK 58 (≥ 36)
**Project Type**: app móvil (Expo, CNG: sin carpetas `ios/` ni `android/` en el repo)
**Performance Goals**: el arranque a Inicio no empeora más de un 10 %; la Bandeja se desplaza sin saltos con 1.000 filas; el líquido va a ≥ 50 fps o se queda quieto
**Constraints**:
- Sin cambios de API.
- Sin hex en pantallas.
- Ninguna transición de más de 300 ms ni con rebote.
- Pesos de letra hasta 600.
- Vidrio solo en barras y controles.
**Scale/Scope**: 13 pantallas y 3 hojas del diseño, más las rutas que se conservan (llegada sin reserva, bloqueos, Aforo, actualizar, sin acceso)

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants | ☑ | No hay rutas nuevas. La app usa las de `main` con su `ClientPrincipal`, y el barrido de `tests/isolation/` ya las cubre (specs 031, 043, 049 y 056). |
| II | Corte por superficie | ☑ | Superficie 0, la misma de la 031. |
| III | Lo leído es dato | ☑ | La app pinta texto de clientes como texto, sin enlaces activos que el negocio no puso. El diseño se trató como dato externo (KB). |
| IV | Acción con aprobación | ☑ | Las acciones de la persona (tomar el control, cancelar, mover y eliminar chat) piden confirmación donde la web la pide, y la API audita quién. |
| V | Estados honestos; la ausencia se diseña | ☑ | Requisito 3. Seis estados por pantalla. Sin botón de recarga ni botones que no hacen nada (Requisitos 17.3 y 18.2). |
| VI | Por API | ☑ | Solo `/console/lite/*` y `/app/*`. |
| VII | Test primero | ☑ | Cada criterio nace como test de Jest/RNTL. Los arreglos visibles (canal del contacto, moneda, precio, teléfono obligatorio y ventana del agente) empiezan en rojo. |
| VIII | Licencias leídas | ☑ | Tres dependencias con su párrafo citado (abajo). **Helvena no entra en ningún build** mientras no se lea su licencia (analyze C1, 2026-11-21). |
| IX | La KB es dueña del porqué | ☑ | `[[research/2026-11-21-app-movil-a-tiendas]]`. Al cerrar, la KB enlaza esta carpeta. |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Ninguna garantía tocada; sin rutas nuevas. | T002 (comprobación de que no se añade ninguna ruta y de que `openapi.json` sigue igual a la API) |
| **Licencias** | `react-native-svg` (MIT), `lucide-react-native` (ISC) y `@shopify/react-native-skia` (MIT). Helvena (Zippie Letras, comercial) apagada en todos los builds hasta leer su EULA (`APP_HELVENA=1` y los archivos en `assets/fonts/helvena/`, que git ignora; analyze C1). | T003, T004 |
| **Medidor** | Nada. | — |

## Decisiones

**D1 — Iconos: Lucide hasta el borde del sistema.**
- `ui/icon.tsx` conserva su API (`<Icon name={icons.x} />`). Cambia su interior:
  - cada nombre de `icons` apunta a un componente de Lucide;
  - trazo 1,75;
  - color desde un rol.
- Los logos de WhatsApp, Instagram y Messenger son SVG propios en `ui/brand-icons.tsx`, con sus colores de marca emitidos por el generador como constantes de marca (no son colores de tema).
- **El cromo del sistema sigue con símbolos del sistema:**
  - los iconos de `NativeTabs`;
  - los botones de `Stack.Toolbar`;
  - los menús nativos y `ActionSheetIOS`.

  Allí la app no dibuja: el sistema pide SF Symbols o imágenes. No se rehace ninguna barra a mano para meter Lucide (advisor, 2026-11-21).
- `expo-symbols` se queda solo para ese cromo.

**D2 — Color.**
- `scripts/gen-tokens.mts` añade un bloque `APP_ROLES` que solo lee la app. Se calcula desde las variables de `tokens.css` (paleta de marca y `color-mix`), así que no se toca `tokens.css` ni la web.
- Roles nuevos:
  - selección: `selection` y `onSelection`;
  - destacado: `highlight`, `highlightSoft`, `onHighlight` y `highlightInk`;
  - `controlBorder` (la tinta al 50 %), que garantiza 3:1 sobre la tarjeta, el fondo y `muted`, con su test (`v13-revision-aa`);
  - burbuja del agente: `bubbleAgent`;
  - toast: `toastBg`, `toastFg` y `toastAccent`.
- **Enmienda del cierre (revisión, H11):** `warningTint`, `successText`, `successTint` y `bubbleMine` no se generaron. Los estados usan los roles que ya trae `tokens.css` (`warningBg`, `warningText`, `positiveBg` y `positiveText`), y la burbuja propia, `card`. `controlBorder` se generó tarde, tras la revisión: hasta entonces T010 estaba marcada sin él.
- Las marcas de canal salen en `brand.whatsapp`, `brand.instagram` y `brand.messenger`, con variantes para oscuro.
- `gen:check` compara byte a byte, como hoy.

**D3 — Letra.**
- `theme/type.ts` gana una familia de títulos, `display`, y sus estilos:
  - `screenTitle` 28/34;
  - `sheetTitle` 18/24;
  - `dialogTitle` 19/25;
  - `figure` 24/30, tabular;
  - `name` 17/22.
- Todos a 600. Los 700 de hoy pasan a 600.
- **La familia sale de un solo valor**, `DISPLAY_FONT` en `theme/fonts.ts`:
  - `"Helvena"` si `extra.helvena` es verdadero en `app.config.ts`, cosa que solo pasa con `APP_HELVENA=1` y los TTF en `assets/fonts/helvena/`;
  - si no, `undefined`, que es la fuente del sistema.
- **Hoy ningún build la lleva.** La licencia no está leída (analyze C1). Los archivos originales están en `~/Downloads/Helvena Font File/TTF/`, con estáticos `Regular`, `Medium` y `Semibold` (no hace falta convertir nada), y vienen, al parecer, de una descarga de Envato Elements sin texto de licencia.
- Con la licencia confirmada, se copian a `assets/fonts/helvena/` (ignorado por git hasta entonces) y se construye con `APP_HELVENA=1`. Van incrustados por el plugin de `expo-font`, sin cargarse en tiempo de ejecución: no se pierde rendimiento.
- **2026-11-21, tarde:** Luis confirmó la licencia. Los tres TTF se versionan y Helvena va en todos los builds; `APP_HELVENA=0` la quita en un build local, para medir. Si falta un archivo, `app.config.ts` para el build.
- El texto corrido sigue en la fuente del sistema, con Dynamic Type.

**D4 — Radios.** `theme/theme.ts` gana `RADII = { sm: 8, md: 12, lg: 16, xl: 20, sheet: 28, pill: 999 }`. `CARD_RADIUS` pasa a 16 (tarjetas del diseño). `concentric()` sigue.

**D5 — Movimiento.**
- `motion/micro.ts` reúne las microinteracciones 2 a 8 como hooks de Reanimated:
  - `useDrawCheck` (2 y 8);
  - `useArrival` y `useBeat` (3);
  - `useCountUp` (4);
  - `useFadeIn` (5).
- El toast (6) gana la barra de tiempo y eleva lo flotante mientras dura. Enviar (7) vive en el composer.
- Tiempos: 120, 160, 200 y 240 ms. Tope de 300 ms. Sin rebote.
- Con «Reducir movimiento», fundido o estado final, sin acortar las esperas que no son animación (Requisito 2.5).

**D6 — Datos de ejemplo** (Requisito 23).
- `config.ts` expone `DEMO = __DEV__ && process.env.EXPO_PUBLIC_DEMO === "1"`. Con `DEMO`:
  - `client.ts` usa `demoFetch` en lugar de `fetch` (cliente privado y público);
  - `sse.ts` se suscribe a `demoEvents`;
  - Reservas reutiliza `reservas-demo.ts` (044).
- Fuera de `__DEV__`, `DEMO` es siempre falso y Metro no incluye `api/demo/` (se carga con `require` dentro de la rama).

**D7 — Búsqueda** (Requisito 10).
- En iOS 26, una pestaña de búsqueda de `NativeTabs`. Se confirma en la documentación de SDK 58; si su API no lo permite, solo existe la búsqueda de la Bandeja.
- En todas las plataformas, la cabecera de la Bandeja lleva búsqueda (`headerSearchBarOptions`), que usa `q`.

**D8 — Entrar con el líquido** (Requisito 5).
- `scripts/gen-liquid.mts` copia del código de la consola el modelo (`liquid-backdrop-model.ts`) y el fragment shader a `src/features/entry/liquid.gen.ts`, con `--check` dentro de `gen:check`. Así el shader es uno solo.
- La app lo pinta con un `RuntimeEffect` de Skia: el GLSL pasa a SkSL (`half4 main(float2 p)`, la `y` invertida).
- Lo mueven valores compartidos de Reanimated y un `Gesture.Pan`/`Tap`.
- Media resolución.
- Cuadro quieto con «Reducir movimiento» o si 30 cuadros seguidos pasan de 20 ms, es decir, por debajo de 50 fps (R22.4; analyze H1). El umbral es de la app; la web usa 50 ms.

**D9 — Android.** `NativeTabs` y cabeceras nativas de Material. Lo que en iOS es `GlassView` es en Android una superficie tonal (`card` más borde suave). Sin desenfoque. Las funciones son las mismas (Requisito 4.2).

**D10 — Versión 1.3.0.** `app.config.ts` y `package.json`, con su test (`__tests__/version.test.ts`). `runtimeVersion` sigue a la versión: nada de esto llega por OTA a la 1.2.0.

**D11 — Reparto por áreas** (un solo árbol de trabajo y escritores en paralelo).
- **Compartido, de una sola mano:**
  - `package.json` y lockfile;
  - `theme/`, `ui/` y `motion/`;
  - los registros de i18n (`app.es.ts` y `app.en.ts`);
  - `ui/icon.tsx`;
  - `api/client.ts`, `api/sse.ts`, `api/endpoints.ts` y `api/hooks.ts`;
  - `config.ts`, `app/_layout.tsx` y `app/(app)/_layout.tsx`.
- **Cada área tiene su archivo de textos** (`i18n/v13-<area>.{es,en}.ts`), ya registrado antes de repartir.
- **Áreas:**
  - Inicio: `features/home` y `app/(app)/inicio`.
  - Bandeja: `features/inbox`, `app/(app)/bandeja` y `app/conversacion`.
  - Reservas: `features/reservas`, `app/reserva`, `app/(app)/reservas` y `api/reservas*.ts`.
  - Consumo y Ajustes: `features/usage`, `app/(app)/consumo` y `app/ajustes.tsx`.
  - Entrar: `features/entry`, `app/sign-in.tsx`, `app/forgot-password.tsx` y `app/notices-permission.tsx`.
- **Los tests existentes solo se cambian donde la spec enmienda comportamiento**, y cada cambio se anota en `log.md`.

## Licencias

| Dependencia | Licencia | Párrafo que lo permite |
|---|---|---|
| `react-native-svg` 15.16.0 (versión de `npx expo install` para SDK 58) | MIT, leída entera en `node_modules/react-native-svg/LICENSE` | «Permission is hereby granted, free of charge, to any person obtaining a copy of this software … to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies…» |
| `lucide-react-native` 1.77.0 | ISC (los iconos derivados de Feather, MIT), leída entera | «Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.» |
| `@shopify/react-native-skia` 2.14.0 (versión de `npx expo install` para SDK 58) | MIT (Shopify Inc. y William Candillon), leída entera en `LICENSE.md` | el mismo párrafo MIT |
| Helvena (Zippie Letras) | Comercial, «All rights reserved». Sin EULA en el repo | **Ninguno todavía.** Apagada en todos los builds, también en desarrollo, salvo que se encienda a mano con `APP_HELVENA=1` y los archivos sin versionar. Se usa la fuente del sistema hasta que Luis aporte el EULA. |

## Project Structure

### Documentation (this feature)

```text
specs/069-la-app-con-el-diseno-nuevo/
├── spec.md
├── plan.md            # este archivo
├── research.md        # las respuestas de los spikes (documentación de SDK 58)
├── quickstart.md      # cómo probarla mañana (simulador, staging, datos de ejemplo)
├── log.md             # bitácora de la noche: decisiones sin Luis, qué se verificó y qué no
├── checklists/requirements.md
└── tasks.md
```

### Source Code

```text
apps/mobile/
├── app.config.ts                   # 1.3.0, plugin de fuentes (solo con APP_HELVENA=1), extra.helvena
├── scripts/gen-tokens.mts          # APP_ROLES + brand
├── scripts/gen-liquid.mts          # nuevo: modelo y shader de la consola → liquid.gen.ts
├── src/config.ts                   # DEMO
├── src/api/{client,sse}.ts         # transporte de ejemplo
├── src/api/demo/                   # datos de ejemplo (solo __DEV__)
├── src/theme/{theme,type,fonts,tokens.gen}.ts
├── src/motion/{micro,durations,haptics}.ts
├── src/ui/{icon,brand-icons,toast,chip,states,card,group,bits,button,...}.tsx
├── src/i18n/v13-*.{es,en}.ts       # textos por área
├── src/features/{home,inbox,reservas,usage,entry}/…
└── src/app/…                       # rutas de expo-router
```

**Structure Decision**: se mantiene la estructura de la 031, la 042 y la 044. Lo nuevo entra en los mismos sitios.

## Complexity Tracking

| Añadido que la spec no pedía | Por qué | Alternativa descartada |
|---|---|---|
| `scripts/gen-liquid.mts` | Un solo shader para la web y la app; si la consola lo cambia, `gen:check` lo avisa | Copiar el shader a mano: dos copias divergen |
| Modo de datos de ejemplo de toda la app | La spec lo pide (Requisito 23) para verificar sin servidor y preparar capturas sin tocar staging ni la base compartida | La API local: aplicar migraciones sobre la base que usan otras sesiones |
