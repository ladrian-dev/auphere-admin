# Idea Intake: spike S2, el vidrio en el pie de la conversación

- **Slug**: 042-s2-vidrio-en-el-pie
- **Created**: 2026-10-21
- **Source**: puntero al repositorio — `specs/042-liquid-glass-en-la-app/research.md` §D18,
  `apps/mobile/src/app/conversacion/[id]/index.tsx`, `apps/mobile/src/features/tab-stack.tsx`
- **Type**: exploration

## Idea (as captured)

> Antes de construir el material de la spec 042, comprobar en el simulador de
> iOS 26 seis cosas que la investigación dejó «por ver», cada una con la
> decisión que cierra y el respaldo si falla. El código del spike no se
> fusiona.

## Restated

Un build de desarrollo con `expo-glass-effect` y una pantalla de prueba,
servida por Metro, con las que mirar cómo se comporta el vidrio de iOS 26 en
las seis situaciones que decide la iteración 2 de la spec 042.

## Origin & Context

- **Raised by**: la D18 de `research.md` (2026-10-20), escrita por el agente y
  aceptada por Luis al pedir que siguiera con la iteración 2 (2026-10-21).
- **Trigger**: `expo-glass-effect` no tiene `glassEffectId`; la decisión D3
  (una sola superficie que cambia de forma) solo se sostiene si el vidrio sigue
  a un cambio de altura sin recrearse. Lo mismo con el teclado (D4), la
  búsqueda (D6), las hojas (D7), los botones de barra (D2) y «Reducir
  transparencia» (D5).

## Las seis comprobaciones

| # | Qué comprueba | Decisión que cierra | Si falla |
|---|---|---|---|
| 1 | Un `GlassView` sigue un cambio de altura de Reanimated (240 ms) sin parpadear ni recrearse | D3 | `@expo/ui` solo en el pie, con `Host`; D3 se reescribe |
| 2 | `KeyboardChatScrollView` + `KeyboardStickyView` con lista invertida bajo una cabecera transparente, y con el texto al máximo | D4 | `KeyboardAvoidingView` y pie absoluto con relleno calculado |
| 3 | Dónde cae `headerSearchBarOptions.placement: "automatic"` dentro de las pestañas | D6 | `stacked` |
| 4 | Una `formSheet` a 0,6 con contenido transparente se pinta de vidrio y las filas se leen | D7 | Contenedor con `colors.background`, como hoy |
| 5 | `Stack.Toolbar.Button` se agrupa en cápsula y el tinte se lee sobre contenido claro y oscuro | D2, D6 | Ajustar el tono del tinte en la spec, no en el código |
| 6 | `GlassView`, las barras y una hoja con «Reducir transparencia»: qué hace UIKit | D5 | Nada: la app ya lo vuelve opaca |

## Cómo se hace

- `expo-glass-effect` se instala en la rama de trabajo (es la misma
  dependencia que la iteración 2 necesita, T023) y se compila **un** build de
  simulador en EAS (`development-simulator`).
- La pantalla de prueba vive en `apps/mobile/src/app/spike/` mientras dura el
  spike y **se borra al cerrarlo**; lo que queda es esta carpeta, con la
  evidencia y la decisión, y las correcciones a `research.md`.
- Las capturas salen de `xcrun simctl io <device> screenshot`; las
  interacciones, de Maestro; los ajustes del sistema, de `xcrun simctl ui` o
  de la app Ajustes del simulador.

## First-Glance Unknowns

- [NEEDS CLARIFICATION: ninguna. Las seis preguntas están cerradas en forma; lo
  que falta es verlas.]
