# Implementation Plan: Liquid Glass en la app, y lo que la auditoría encontró

**Branch**: `042-liquid-glass-en-la-app` | **Date**: 2026-10-20 | **Spec**: [spec.md](spec.md)

**Input**: `specs/042-liquid-glass-en-la-app/spec.md` ·
[research.md](research.md) · KB
`[[research/2026-10-20-liquid-glass-app-movil]]`

## Summary

**Qué se construye.** Un cambio de presentación de Auphere Customers
(`apps/mobile`), sin tocar la API, el worker ni la consola, salvo una cadena de
texto compartida. Dos capas:

- **Contenido, en todas las plataformas.** Inicio pasa a tres bloques (atención,
  dinero, conversaciones) y dice cada dato una vez; Consumo pasa a una lista
  agrupada con un gráfico; Ajustes separa cerrar sesión de borrar la cuenta;
  toda la navegación es una fila con chevrón o con enlace externo; los textos
  de H10 a H12. Cierra H1, H2, H3, H5, H7, H10, H11, H12 y H13.
- **Material y forma, en iOS 26.** La cabecera y los botones de barra son los
  del sistema (sin fondo propio, `Stack.Toolbar`); el pie de la conversación es
  **una sola superficie de vidrio** que cambia de forma entre «Tomar el
  control» y el cuadro de escribir, con el hilo pasando por debajo; Ajustes es
  una hoja; cápsulas, pulsación al apoyar el dedo y los estilos de texto del
  sistema. En iOS anterior a 26 y en Android, la superficie es la tarjeta opaca
  de hoy y nada imita el vidrio. Cierra H4, H6, H8 y H9.

**Lo nuevo que entra:** `expo-glass-effect` (MIT), una primitiva
`FloatingSurface`, dos primitivas de lista (`Group`, `Row`), un hook
`useSystemAppearance()` que lee en vivo «Reducir transparencia», «Aumentar
contraste» y «Reducir movimiento», y un perfil de EAS para compilar en la nube
un build de simulador de iOS 26 sin tocar el Xcode de la máquina.

**Cuatro iteraciones, en orden de valor y de riesgo:**

0. **Spike S2** por el flujo `assess`. No se fusiona. En el simulador de iOS 26
   cierra seis cosas marcadas «por ver»: el vidrio que sigue a un cambio de
   altura, la lista con el teclado bajo una cabecera transparente, dónde cae la
   búsqueda, la hoja a 0,6, los botones de barra y «Reducir transparencia».
1. **El contenido.** Historias 2 y 5: Inicio, Consumo, Ajustes, filas de
   navegación y textos. Se verifica hoy, en Android, sin esperar al vidrio.
2. **El material y la forma.** Historias 1, 3, 4 y 6: `expo-glass-effect`,
   `FloatingSurface`, cabeceras y barras, el pie de la conversación con el
   teclado, hojas, apariencia en vivo, cápsulas, pulsación y tipografía.
3. **El pase visual y la evidencia.** iOS 26 en SE y 17, Android, contraste
   medido sobre vidrio, revisión heurística con las skills, y la documentación
   viva al día.

## Technical Context

| | |
|---|---|
| **Language/Version** | TypeScript 6 en la app (Expo SDK 58, React Native 0.88, React 19.3). Una línea de TypeScript en la consola (la cadena de D15). Sin código nativo propio |
| **Primary Dependencies** | Ya instaladas: expo-router 58.0.24 con pestañas nativas y `Stack.Toolbar`, react-native-screens 4.30, react-native-reanimated 4.7.1, react-native-keyboard-controller 1.22.7, expo-symbols, expo-haptics. **Nueva:** `expo-glass-effect` ~58.0.4 (MIT, [research §Licencias](research.md#licencias-de-lo-que-entra-constitución-viii)). **No entran** `@expo/ui` ni `expo-blur` |
| **Storage** | Ninguno. No hay datos nuevos ni cambios en los que hay |
| **Testing** | jest-expo + RNTL 14 (`apps/mobile/__tests__`), con pruebas primero por requisito · Maestro (`e2e/`) para «Tomar el control» con los `testID` de hoy · capturas del simulador de iOS 26 y del emulador de Android en `evidence/`, con el contraste medido sobre vidrio · revisión heurística con `ux-heuristics`, `design-critique` e `impeccable` sobre las capturas |
| **Target Platform** | iOS 16.4+ (vidrio solo en 26+, decidido con `isLiquidGlassAvailable()`) · Android targetSdk 36 · El build de iOS lo hace EAS con `macos-tahoe-26.6-xcode-27.1` |
| **Project Type** | móvil: una app Expo en su propio workspace |
| **Performance Goals** | El paso del panel al cuadro en 240 ms (`durations.state`), nunca más de 300 ms (CE-004) · Ningún fotograma sin controles · El hilo sigue desplazándose a 60 fps con el vidrio encima (se mira en el spike) |
| **Constraints** | Sin hex escritos a mano; lo propio de la app en `theme.ts`, no en los tokens generados · Nada de opacidad sobre el `GlassView` · Nunca vidrio sobre vidrio · Texto ≥ 4,5:1 e iconos ≥ 3:1 sobre vidrio, en claro, oscuro, «Reducir transparencia» y «Aumentar contraste» (CE-005) · `testID` de Maestro intactos · Documentación viva (`docs/app-movil.md`) en el mismo commit que lo que describe |
| **Scale/Scope** | 6 pantallas tocadas (Inicio, Consumo, Bandeja, conversación, contacto, Ajustes), 7 primitivas de `src/ui/`, 2 ficheros de tema, 1 de movimiento, 1 de i18n de la consola |

## Constitution Check

*Rellenado antes de la Fase 0 y comprobado otra vez tras el diseño: sigue en verde.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | No se toca ninguna frontera: ni datos, ni rutas, ni permisos. Las mismas lecturas de la 031, presentadas de otra forma. Ningún test de aislamiento nuevo, y los de la 031 siguen bloqueando |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0`, ya abierta, sin cambios. Nada nuevo sale del teléfono |
| III | Lo leído es dato, nunca instrucción | ☑ | No cambia qué se lee ni qué hace la app con ello |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Las acciones son las de la 031, con sus mismas confirmaciones (`Alert`) y su misma auditoría. Separar el borrado de la cuenta de cerrar sesión (D10) añade distancia, no quita confirmación |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Los cinco estados de cada pantalla se conservan y se vuelven a probar (R10.2). La ausencia se diseña: sin módulo de Consumo, el bloque de dinero no parece navegable (R6.4); sin gasto, no hay selector de periodo (R9.2); sin nada pendiente, no hay cifra a cero (R5.3). Los controles desactivados se distinguen sobre vidrio (R4.8) |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | La app sigue usando la API. La fila «Abrir la consola web» abre el navegador del sistema, como hoy |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada requisito nace como prueba de RNTL (`__tests__/`), en rojo antes de tocar la pantalla: cuántas veces aparece el número de espera, el orden de las secciones de Ajustes, el selector escondido, el respaldo de `FloatingSurface` por disponibilidad y por «Reducir transparencia», la pulsación al apoyar. Lo que solo se ve en el simulador (CE-002, CE-004 a CE-007) tiene su captura y su medida en `evidence/`, nunca un `skip` |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | `expo-glass-effect`: MIT, leída en el `LICENSE` del paquete y citada en research. Nada más entra |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[research/2026-10-20-liquid-glass-app-movil]]` justifica la spec y ya apunta a `specs/042-…/` en su frontmatter. No hace falta ADR nuevo: la dirección es la D24 del ADR-042 concretada para iOS 26, y la nota la recoge |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Ninguna garantía tocada. La spec lo declara y este plan no toca datos, rutas ni permisos | Ninguna tarea nueva en `tests/isolation/`; la suite de la 031 sigue siendo la que bloquea |
| **Licencias** | `expo-glass-effect` ~58.0.4, MIT, párrafo citado en [research](research.md#licencias-de-lo-que-entra-constitución-viii) | La tarea de instalación de la iteración 2 cita el párrafo y añade la fila a `docs/app-movil.md` |
| **Medidor** | Nada gasta. No hay modelo, máquina ni herramienta de pago | Ninguna |

**Complejidad que hay que justificar:** ver Complexity Tracking. Nada que la
spec no pida.

## Decisiones

Están todas en [research.md](research.md), con su porqué, sus alternativas y
lo que queda «por ver». En corto:

| # | Decisión |
|---|---|
| D1 | La cabecera de iOS 26 es la del sistema: sin `headerStyle` ni `headerLargeStyle` con fondo; `headerLargeTitleEnabled`; `scrollEdgeEffects` en `automatic`. Antes de 26 y en Android, como hoy |
| D2 | Botones de barra con `Stack.Toolbar` en iOS (SF Symbol, menú nativo con «Devolver al agente» primero). Android sigue con `headerRight` |
| D3 | Entra `expo-glass-effect`. El pie de la conversación es **una** `FloatingSurface` que cambia de contenido y de altura con `LinearTransition` de 240 ms; nada de vidrio dentro. Respaldo opaco antes de 26 y en Android. `@expo/ui` queda como respaldo del spike |
| D4 | El hilo pasa por debajo: `KeyboardChatScrollView` + `KeyboardStickyView`, relleno igual a la altura de la superficie |
| D5 | `useSystemAppearance()` lee en vivo «Reducir transparencia», «Aumentar contraste» y «Reducir movimiento»; la superficie se vuelve opaca y con borde; `motionFor()` recibe el valor en vivo |
| D6 | Pestañas sin cambios. Búsqueda en la cabecera con `placement: "automatic"`, respaldo `stacked` |
| D7 | Ajustes como `formSheet` `[0.6, 1]` en iOS; en Android, pantalla. Las hojas no pintan fondo sobre el vidrio |
| D8 | Inicio en tres bloques: atención sin insignia, dinero como lista agrupada, conversaciones con cifra protagonista y barras |
| D9 | Consumo: sin frase de entrada, lista agrupada, selector solo con gasto en 90 días, fila de enlace externo |
| D10 | Ajustes: cerrar sesión y borrar la cuenta en grupos distintos; solo el borrado en peligro, con su línea de pie |
| D11 | `RowButton` es la única forma de ir a otro sitio; enlace externo con destino |
| D12 | Cápsulas en todos los botones; `CARD_RADIUS` 12 y `concentric()` en `theme.ts`; pulsación al apoyar (escala y tono en iOS, ondulación en Android); fuera la bajada de opacidad |
| D13 | `type.ts` por plataforma: los estilos del HIG en iOS, sin tracking; la escala de la consola en Android |
| D14 | `headerTitleStyle.fontSize` en Android para que el título escale |
| D15 | `lite.attention.attend` → «Atender ahora» / «Answer now», en la consola |
| D16 | Build de simulador en EAS (`development-simulator`) instalado en el runtime local de iOS 26.0.1; SE 3.ª gen e iPhone 17; `simctl ui` para apariencia, contraste y texto |
| D17 | Lo que no cambia: pestañas, transiciones, cifras, `testID`, tokens generados |
| D18 | Spike S2 antes del material, con su tabla de seis comprobaciones y el respaldo de cada una |

## Contratos

- [contracts/ui.md](contracts/ui.md): qué material lleva cada superficie según
  plataforma, versión y ajustes; las primitivas (`FloatingSurface`, `Group`,
  `Row`, `Button`) con sus estados; la composición de Inicio, Consumo, Ajustes
  y el pie de la conversación; el contrato de movimiento; la cadena de i18n
  que cambia.

No hay `data-model.md`: la spec no toca datos (Encabezado Auphere).

## Project Structure

### Documentation (this feature)

```text
specs/042-liquid-glass-en-la-app/
├── spec.md
├── plan.md              # este fichero
├── research.md          # D1–D18 y licencias
├── contracts/ui.md      # el contrato de superficies y primitivas
├── quickstart.md        # cómo se verifica, historia por historia
├── checklists/requirements.md
├── evidence/            # capturas y medidas (se crea en la iteración 3)
└── tasks.md             # lo genera /speckit-tasks
```

```text
.specify/assessments/042-s2-vidrio-en-el-pie/   # el spike S2 (D18): no se fusiona
```

### Source Code (repository root)

```text
apps/mobile/
├── eas.json                                 # perfil development-simulator (D16)
├── package.json · pnpm-lock.yaml            # expo-glass-effect (D3)
├── src/
│   ├── app/
│   │   ├── _layout.tsx                      # ajustes → formSheet en iOS; hojas sin fondo (D7)
│   │   ├── (app)/bandeja/index.tsx          # placement de la búsqueda (D6)
│   │   ├── (app)/inicio/index.tsx           # sin cambios de datos; usa el nuevo HomeView
│   │   ├── conversacion/[id]/index.tsx      # lista + KeyboardChatScrollView + FloatingSurface (D3, D4); menú con Stack.Toolbar (D2)
│   │   ├── conversacion/[id]/contacto.tsx   # sin colors.background en el contenedor (D7)
│   │   └── ajustes.tsx                      # secciones y pie del borrado (D10)
│   ├── features/
│   │   ├── tab-stack.tsx                    # cabecera por disponibilidad de vidrio (D1); Stack.Toolbar en iOS (D2); fontSize en Android (D14)
│   │   ├── home/home-view.tsx               # tres bloques (D8)
│   │   ├── home/attention.tsx               # sin insignia (H13)
│   │   ├── home/metric.tsx · spend-card.tsx # se retiran
│   │   ├── usage/usage-view.tsx             # lista, gráfico, selector condicionado, fila externa (D9)
│   │   ├── inbox/thread/control.tsx         # contenido del panel, sin tarjeta propia (D3)
│   │   ├── inbox/thread/composer.tsx        # contenido del cuadro, sin tarjeta propia; botón de enviar concéntrico (D3, D12)
│   │   ├── inbox/thread/bubble.tsx          # pulsación sin opacidad (D12)
│   │   └── inbox/list/filters.tsx           # pulsación sin opacidad (D12)
│   ├── motion/use-motion.ts                 # motionFor(reducedEnVivo), ReduceMotion explícito (D5)
│   ├── theme/
│   │   ├── theme.ts                         # CARD_RADIUS, concentric() (D12)
│   │   ├── type.ts                          # escala por plataforma (D13)
│   │   └── system-appearance.ts             # useSystemAppearance() (D5)  [nuevo]
│   └── ui/
│       ├── floating-surface.tsx             # GlassView ↔ tarjeta opaca (D3, D5)  [nuevo]
│       ├── group.tsx                        # Group y Row de lista agrupada (D8, D9)  [nuevo]
│       ├── button.tsx                       # cápsula, pulsación al apoyar (D12)
│       ├── bits.tsx                         # RowButton con enlace externo (D11), pulsación (D12)
│       └── card.tsx                         # CARD_RADIUS (D12)
├── __tests__/                               # inicio, consumo, ajustes-avisos, atender, hilo, states + floating-surface, system-appearance, group  [nuevos]
└── e2e/send-flaky.yaml                      # sin cambios: mismos testID

apps/console/src/i18n/lanes/lite.ts          # «Atender ahora» / «Answer now» (D15)
docs/app-movil.md                            # Arquitectura: cabeceras, pie, apariencia, movimiento; licencias (mismo commit)
```

**Structure Decision**: todo vive donde ya vivía. Lo nuevo son tres ficheros
(`floating-surface.tsx`, `group.tsx`, `system-appearance.ts`) y se retiran dos
(`metric.tsx`, `spend-card.tsx`). La consola solo cambia una cadena.

## Complexity Tracking

Sin violaciones. Dos cosas que la spec no nombra y el plan añade, con su razón:

| Añadido | Por qué | Alternativa más simple descartada porque |
|---|---|---|
| `useSystemAppearance()` (D5) | R4.2, R4.3 y R4.5 exigen reaccionar en vivo a tres ajustes del sistema; Reanimated solo lee «Reducir movimiento» al arrancar | Fiarse de UIKit no está verificado y dejaría tres criterios sin prueba |
| Perfil `development-simulator` de EAS (D16) | CE-002 y CE-004 a CE-007 solo se cierran viendo iOS 26, y la máquina no puede compilar para iOS | Actualizar Xcode y liberar disco depende de Luis y no es necesario para ver el vidrio |

## Riesgos y dependencias externas

- **El vidrio no sigue al cambio de altura (D3).** Lo mide el spike S2 antes
  de construir nada; el respaldo es `@expo/ui` solo en el pie, con su coste
  escrito.
- **La búsqueda cae en un sitio raro con `automatic` (D6).** Respaldo:
  `stacked`, que es el aspecto de hoy.
- **El runtime local es iOS 26.0.1.** Sirve para todo menos para el vidrio
  claro o tintado (26.1) y para el respaldo anterior a 26. Esas dos cosas se
  cierran en un iPhone o con más disco, y la spec las deja en manos de Luis.
- **EAS compila con Xcode 27.1 RC.** Es la imagen por defecto del SDK 58; si
  cambiara, se fija el nombre completo de la imagen en `eas.json`.
- **Las skills de revisión son locales** (`apps/mobile/.claude/skills/`, fuera
  de git). La revisión heurística de la iteración 3 depende de que estén
  instaladas en la máquina que la hace (`npx skills experimental_install`).
