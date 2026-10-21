---

description: "Tareas de la spec 042: Liquid Glass en la app, y lo que la auditoría encontró"
---

# Tasks: Liquid Glass en la app, y lo que la auditoría encontró

**Input**: `specs/042-liquid-glass-en-la-app/`: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [contracts/ui.md](contracts/ui.md), [quickstart.md](quickstart.md)

**Tests**: no son opcionales (constitución §VII). Cada bloque «Tests» se escribe y
se ve en rojo antes de su implementación. Lo que solo se ve en un simulador
tiene su captura y su medida en `evidence/`; nunca un `skip`.

**Organización**: las fases siguen las iteraciones del plan (0 → 3), que es el
orden de dependencias. Dentro de cada una, las historias van por prioridad.
`[USn]` es la **Historia n** de la spec:

| Etiqueta | Historia | Prioridad | Iteración |
|---|---|---|---|
| US2 | Inicio dice cada cosa una vez | P1 | 1 |
| US5 | Saber a dónde lleva cada cosa | P2 | 1 |
| US1 | Atender con el hilo a la vista | P1 | 2 |
| US4 | La navegación de iOS 26 es de vidrio | P2 | 2 |
| US3 | Legible siempre | P1 | 2 |
| US6 | Formas y tacto de la plataforma | P3 | 2 |

**Por qué US2 y US5 van antes que US1 (P1).** Son de contenido y se verifican
hoy en Android, sin vidrio. US1 depende del spike S2 y de instalar
`expo-glass-effect`. Poner vidrio sobre un Inicio que repite lo mismo sería
pulir lo que sobra (research, veredicto de la auditoría).

**Por qué US3 va después de US1 y US4.** Legibilidad se mide sobre las
superficies que las otras dos ponen. Su base (`useSystemAppearance` y el
respaldo opaco de `FloatingSurface`) va en Foundational, porque US1 la necesita.

## Reglas de este repo *(constitución)*

- Cada tarea termina con `_Requisitos: N.m_` o, si nace de la constitución, con
  `§N`. Los requisitos son los de **esta** spec; los de la 031 se citan como
  `031 R6.1`.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado
  YYYY-MM-DD`.
- Test primero (§VII). El rojo se ve antes de tocar la pantalla.
- **`apps/mobile` es su propio workspace de pnpm.** Todo se ejecuta desde esa
  carpeta; nada se añade a la raíz.
- **Nada de hex.** Lo propio de la app vive en `src/theme/theme.ts`, nunca en
  `tokens.gen.ts` (`gen:check` lo compara byte a byte).
- **Nunca opacidad sobre un `GlassView`; nunca vidrio dentro de vidrio.**
- **Los `testID` de Maestro no cambian**: `composer-input`, `send`,
  `take-over`, `waiting-card`.
- **`docs/app-movil.md` se actualiza en el mismo commit** que lo que describe.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.

## Format: `[ID] [P?] [Story] Descripción`

- **[P]**: puede ir en paralelo (ficheros distintos, sin dependencias abiertas).
- **[Story]**: la historia de la spec a la que sirve.
- Cada descripción lleva la ruta exacta.

---

## Phase 1: Setup

**Propósito**: poder ver iOS 26 sin tocar el Xcode de la máquina, y tener dónde
dejar la evidencia.

- [X] T001 Añadir el perfil `development-simulator` a `apps/mobile/eas.json`
      (`extends: "development"`, `ios: { simulator: true }`), y documentar en
      `docs/app-movil.md` §Builds que es el build de simulador en la nube
      (research D16). _Requisitos: 1.1_
- [X] T002 [P] Crear los simuladores de referencia con `xcrun simctl create`:
      «13 26» (iPhone SE 3.ª generación, iOS 26.0) y «13 26» (iPhone 17,
      iOS 26.0), y dejar los comandos en `quickstart.md` §Requisitos previos
      tal como quedaron. _Requisitos: 5.6_
      > 2026-10-21: los dos se sustituyen por **«13 26»** (iPhone 13, iOS
      > 26.0.1) por decisión de Luis, y un solo simulador arrancado a la vez
      > por el disco. Donde las tareas de abajo dicen «13 26» antes decían
      > «SE 26» o «17 26».
- [X] T003 [P] Crear `specs/042-liquid-glass-en-la-app/evidence/` con
      `capturas/`, `a11y.md` (tabla vacía de combinaciones del quickstart §5)
      y `hallazgos.md` (los trece hallazgos de la auditoría, cada uno con su
      requisito y una columna «captura que lo cierra», vacía). §VII
- [X] T004 [P] Comprobar que las skills de revisión están en
      `apps/mobile/.claude/skills/` (`npx skills experimental_install` desde
      `apps/mobile` si faltan) y anotar la versión de cada una en
      `evidence/hallazgos.md`. §IX

---

## Phase 2: Foundational

**Propósito**: lo que todas las historias comparten. Se divide en lo que sirve
al contenido (2a) y lo que sirve al material (2b, 2c). US2 y US5 solo
necesitan 2a.

### 2a · Primitivas de lista y forma (iteración 1)

#### Tests

- [X] T005 [P] Test de `Group` y `Row` en `apps/mobile/__tests__/group.test.tsx`:
      `kind="push"` pinta el chevrón y responde; `kind="external"` pinta el
      icono de enlace externo y exige `hint`; sin `kind` no hay indicador ni
      `onPress`; con el texto al 200 % `label` y `value` se apilan sin cortar.
      _Requisitos: 6.1, 6.2, 6.4, 4.7_
- [X] T006 [P] Test de `concentric()` y `CARD_RADIUS` en
      `apps/mobile/__tests__/states.test.tsx`: `concentric(24, 8) === 16`, nunca
      por debajo de 4; `CARD_RADIUS === 12`. _Requisitos: 7.1_

#### Implementación

- [X] T007 Añadir `CARD_RADIUS = 12` y `concentric(outer, padding)` a
      `apps/mobile/src/theme/theme.ts`, junto a `TOUCH` y `SHEET_RADIUS`, con
      el comentario de por qué no van en los tokens generados (research D12).
      _Requisitos: 7.1_
- [X] T008 Crear `Group` y `Row` en `apps/mobile/src/ui/group.tsx` según
      [contracts/ui.md §2](contracts/ui.md): fondo `colors.card`, `CARD_RADIUS`,
      separadores, `kind: "push" | "external" | "none"`, `onPress` solo con
      `kind` (tipo discriminado), pulsación por fondo `colors.muted` en iOS y
      `android_ripple` en Android. _Requisitos: 6.1, 6.2, 6.4_
- [X] T009 Dar a `RowButton` (`apps/mobile/src/ui/bits.tsx`) el mismo `kind`
      que `Row`, con el icono de enlace externo y el subtítulo obligatorio para
      `external`; quitar la opacidad 0,6 al pulsar y usar la misma pulsación
      que `Row`. _Requisitos: 6.1, 6.2, 7.2_
- [X] T010 Pasar `Card` (`apps/mobile/src/ui/card.tsx`) a `CARD_RADIUS`.
      _Requisitos: 7.1_

**Checkpoint**: T005 y T006 en verde. Hay una sola forma de hacer una fila que
lleva a otro sitio.

### 2b · Spike S2: el vidrio en el simulador (iteración 0)

Va por el flujo `assess` y **su código no se fusiona**. Bloquea 2c, US1, US4,
US3 y US6; no bloquea US2 ni US5.

- [X] T011 Abrir `.specify/assessments/042-s2-vidrio-en-el-pie/intake.md` con
      la tabla de seis comprobaciones de research D18 y, por cada fila, qué
      decisión cierra y cuál es su respaldo. §II
- [X] T012 En una rama de spike, instalar `expo-glass-effect` con `npx expo
      install expo-glass-effect` desde `apps/mobile`, hacer el build
      `development-simulator` (T001) e instalarlo en «13 26». Guardar en
      `.specify/assessments/042-s2-vidrio-en-el-pie/evidence/` el log del
      build con la imagen usada («Spin up build environment»). §VIII
- [X] T013 Comprobación 1 (D3): un `GlassView` cuyo hijo cambia de altura con
      `LinearTransition.duration(240)`; grabar la pantalla y contar fotogramas.
      Resultado en `…/evidence/01-vidrio-sigue-altura.md` con el vídeo.
      _Requisitos: 2.5_
- [X] T014 Comprobación 2 (D4): `KeyboardChatScrollView` + `KeyboardStickyView`
      con una lista invertida bajo una cabecera sin fondo, al tamaño de texto
      por defecto y en `accessibility-extra-extra-extra-large`. Capturas en
      `…/evidence/02-teclado-*.png`. _Requisitos: 2.2, 2.7, 4.7_
- [X] T015 [P] Comprobación 3 (D6): `headerSearchBarOptions.placement:
      "automatic"` dentro de las pestañas; dónde cae y si se usa con una mano.
      Captura en `…/evidence/03-busqueda-automatic.png`. _Requisitos: 1.8_
- [X] T016 [P] Comprobación 4 (D7): una `formSheet` a `[0.6, 1]` con el
      contenedor sin fondo; si UIKit la pinta de vidrio y si las filas se leen.
      Captura en `…/evidence/04-hoja-06.png`. _Requisitos: 1.7_
- [X] T017 [P] Comprobación 5 (D2): `Stack.Toolbar.Button` con SF Symbol;
      agrupación en cápsula y lectura del tinte `primaryText` sobre una
      Bandeja clara y una oscura. Capturas en `…/evidence/05-barra-*.png`.
      _Requisitos: 1.4, 1.6_
- [X] T018 [P] Comprobación 6 (D5): un `GlassView`, la barra superior, la de
      pestañas y una hoja con «Reducir transparencia» activado en Ajustes del
      simulador; qué hace UIKit con cada una (la spec espera opacas o
      esmeriladas, Historia 3 esc. 1). Capturas en
      `…/evidence/06-reducir-transparencia-*.png`. _Requisitos: 4.2_
- [X] T019 Escribir `…/decision.md`: una línea por comprobación con «se
      sostiene» o «respaldo», y **actualizar research.md** (D3, D4, D6, D7) con
      lo decidido. Si la comprobación 1 falla, reescribir D3 con `@expo/ui`,
      su licencia (MIT, citando el `LICENSE` de la raíz de expo/expo porque el
      paquete no lleva uno) y rehacer las tareas de US1 antes de seguir. §VIII

**Checkpoint**: las seis dudas tienen respuesta escrita. La rama del spike no
se fusiona.

### 2c · Base del material (iteración 2)

#### Tests

- [X] T020 [P] Test de `useSystemAppearance()` en
      `apps/mobile/__tests__/system-appearance.test.ts`, con
      `AccessibilityInfo` simulado: lee `isReduceTransparencyEnabled`,
      `isDarkerSystemColorsEnabled` (iOS), `isHighTextContrastEnabled`
      (Android) e `isReduceMotionEnabled`; se actualiza al emitir
      `reduceTransparencyChanged`, `darkerSystemColorsChanged`,
      `highTextContrastChanged` y `reduceMotionChanged`; se desuscribe al
      desmontar. _Requisitos: 4.5_
- [X] T021 [P] Test de `FloatingSurface` en
      `apps/mobile/__tests__/floating-surface.test.tsx`, con
      `isLiquidGlassAvailable` simulado: con vidrio renderiza `GlassView`
      `regular` flotante (márgenes y radio); sin vidrio, `View` anclada con
      `colors.card`, ancho completo, sin radio y borde superior `colors.border`;
      con vidrio **y** «Reducir transparencia», `View` opaca; con «Aumentar
      contraste» o contraste alto, `borderWidth` 1 en `colors.border`;
      `tone="warning"` tiñe el borde, nunca el fondo; nunca aplica `opacity`.
      _Requisitos: 2.1, 3.1, 3.3, 4.2, 4.3_
- [X] T022 [P] Test de `motionFor(reduced)` en
      `apps/mobile/__tests__/states.test.tsx`: con `reduced` pasa
      `ReduceMotion.Always` y sin `layout`; sin él, `ReduceMotion.Never` y
      `LinearTransition` de `durations.state`; el presupuesto sigue en 300 ms.
      _Requisitos: 2.6, 4.5, 10.3_

#### Implementación

- [X] T023 Instalar `expo-glass-effect` con `npx expo install expo-glass-effect`
      desde `apps/mobile` (queda `~58.0.4` en `package.json` y en el lockfile
      de la app), pasar `npx expo-doctor`, y añadir la fila a la tabla de
      licencias de `docs/app-movil.md` §Arquitectura con el párrafo citado en
      [research §Licencias](research.md#licencias-de-lo-que-entra-constitución-viii).
      §VIII
- [X] T024 [P] Crear `useSystemAppearance()` en
      `apps/mobile/src/theme/system-appearance.ts` según
      [contracts/ui.md §2](contracts/ui.md): estado inicial con los `is*`,
      suscripciones por plataforma, limpieza al desmontar. _Requisitos: 4.5_
- [X] T025 Crear `FloatingSurface` en `apps/mobile/src/ui/floating-surface.tsx`
      (depende de T023 y T024): `GlassView` de `expo-glass-effect` cuando
      `isLiquidGlassAvailable()` y no hay «Reducir transparencia»; si no, la
      tarjeta opaca **anclada** (ancho completo, sin radio, borde superior
      hairline: el pie de la 031); borde con contraste alto; `tone`, `radius`,
      `onLayout`, `testID`. Las dos presentaciones comparten código
      ([contracts/ui.md §2](contracts/ui.md)). Sin `opacity` en ningún caso.
      _Requisitos: 2.1, 3.1, 3.2, 3.3, 4.2, 4.3_
- [X] T026 Pasar `motionFor()` (`apps/mobile/src/motion/use-motion.ts`) a
      recibir `reduced` de `useSystemAppearance().reduceMotion` y a usar
      `ReduceMotion.Always` / `ReduceMotion.Never` explícitos; `useMotion()`
      deja de llamar a `useReducedMotion()` de Reanimated. Actualizar el
      párrafo «Movimiento» de `docs/app-movil.md`. _Requisitos: 2.6, 4.5_

**Checkpoint**: T020, T021 y T022 en verde. Hay una superficie que sabe de qué
material es, y el movimiento reacciona en vivo.

---

## Phase 2b: Las puertas de la constitución

- **Aislamiento (§I)**: la spec declara **ninguna garantía tocada** y el plan no
  toca datos, rutas ni permisos. No hay tarea en `tests/isolation/`; la suite
  de la 031 sigue siendo la que bloquea. Es una decisión, no un descuido.
- [X] T027 Dejar escrita la licencia de `expo-glass-effect` (MIT) con el
      párrafo citado: ya está en [research §Licencias](research.md#licencias-de-lo-que-entra-constitución-viii);
      T023 la copia a `docs/app-movil.md`. Si el spike (T019) hace entrar
      `@expo/ui`, esta tarea se reabre con su párrafo. §VIII
- **Medidor**: nada gasta modelo, reloj de máquina ni herramienta de pago. Sin
  tarea.

**Checkpoint**: las puertas tienen dueño.

---

## Phase 3: US2. Inicio dice cada cosa una vez (P1) · Iteración 1 🎯

**Goal**: tres bloques (atención, dinero, conversaciones); cada dato una vez;
ningún número contradice a otro. Cierra H1, H2, H3 y H13.

**Independent Test**: `pnpm test --ci -- inicio` en verde, y en «13 26» al
tamaño por defecto se ven la atención y el dinero sin desplazar (CE-002).

### Tests

- [X] T028 [P] [US2] En `apps/mobile/__tests__/inicio.test.tsx`: con dos
      conversaciones esperando, el texto «2 conversaciones esperan a una
      persona» aparece **una** vez en el árbol, no existe ninguna cifra aparte
      de «esperan» ni ningún `Badge` dentro del bloque de atención (CE-001).
      _Requisitos: 5.1, 5.2_
- [X] T029 [P] [US2] En `apps/mobile/__tests__/inicio.test.tsx`: sin nada pendiente, existe la línea
      tranquila y no existe ningún texto «esperan» ni ninguna cifra «0».
      _Requisitos: 5.3_
- [X] T030 [P] [US2] En `apps/mobile/__tests__/inicio.test.tsx`: con saldo asignado hay un solo grupo
      de dinero con las filas «Saldo disponible», «Alcanza» (con el `Meter`) y
      «Gasto del mes»; no existe ninguna tarjeta `Metric` ni `SpendCard`; con
      módulo `usage` hay una fila `kind="push"` a Consumo; sin él, ninguna
      fila del grupo tiene `onPress`. _Requisitos: 5.4, 5.5, 6.4_
- [X] T031 [P] [US2] En `apps/mobile/__tests__/inicio.test.tsx`: con espera y saldo bajo, el bloque de
      atención tiene dos filas y cada dato aparece una sola vez; con saldo sin
      asignar, el grupo de dinero lo dice y no inventa cifras.
      _Requisitos: 5.1, 5.4_
- [X] T032 [P] [US2] En `apps/mobile/__tests__/inicio.test.tsx`: el bloque de conversaciones tiene una
      sola cifra protagonista (`figure`) con su tendencia y las barras debajo;
      los cinco estados de la 031 (carga, vacío, error, parcial, ideal) siguen
      pasando. _Requisitos: 5.5, 10.2_

### Implementación

- [X] T033 [US2] Quitar la insignia del bloque de atención en
      `apps/mobile/src/features/home/attention.tsx` y dejar el número solo en
      la fila de espera, junto al botón; la fila de saldo pasa de `Button` a
      `RowButton kind="push"` cuando hay módulo de Consumo. _Requisitos: 5.1, 5.2, 6.1_
- [X] T034 [US2] Reescribir `apps/mobile/src/features/home/home-view.tsx`
      según [contracts/ui.md §3 Inicio](contracts/ui.md): sin la métrica
      «Esperan a una persona»; grupo de dinero con `Group`/`Row` (saldo, días
      con `Meter`, gasto del mes, fila de avance solo con módulo `usage`);
      bloque de conversaciones con `figure` + tendencia + `DayBars`.
      _Requisitos: 5.1, 5.3, 5.4, 5.5, 5.6, 6.4_
- [X] T035 [US2] Retirar `apps/mobile/src/features/home/metric.tsx` y
      `spend-card.tsx`, y sus importaciones; `grep` de `Metric` y `SpendCard`
      vacío. _Requisitos: 5.5_
- [X] T036 [P] [US2] La fila de avance a Consumo usa la clave compartida
      `lite.spend.see` («Ver consumo» / «See usage»), que ya existe en
      `apps/mobile/src/i18n/lite.gen.ts`; en `apps/mobile/src/i18n/app.es.ts`
      y `app.en.ts` solo entra lo que no tenga clave compartida (el pie del
      saldo sin asignar, si hiciera falta). `grep` de cada texto nuevo en
      `lite.gen.ts` antes de añadirlo. _Requisitos: 5.4_
- [X] T037 [US2] Captura de Inicio en «13 26» al tamaño por defecto, claro y
      oscuro, con dos conversaciones esperando:
      `evidence/capturas/ios26-se-inicio-{claro,oscuro}.png`; anotar en
      `evidence/hallazgos.md` que H1, H2, H3 y H13 quedan cerrados con ellas y
      que la atención y el dinero se ven sin desplazar (CE-002).
      _Requisitos: 5.6_

**Checkpoint**: T028 a T032 en verde. Inicio dice cada cosa una vez.

---

## Phase 4: US5. Saber a dónde lleva cada cosa (P2) · Iteración 1

**Goal**: una sola forma de navegar; salir a la web se reconoce; Ajustes separa
cerrar sesión de borrar la cuenta; Consumo sin frase de entrada ni selector
vacío; «Atender ahora». Cierra H5, H7, H10, H11 y H12.

**Independent Test**: `pnpm test --ci -- consumo ajustes-avisos` en verde, y en
Android se cuentan dos formas de ir a otro sitio en Inicio, Consumo y Ajustes.

### Tests

- [X] T038 [P] [US5] En `apps/mobile/__tests__/consumo.test.tsx`: no existe el
      texto de `lite.usage.intro`; las cifras son filas de un grupo (ningún
      `Metric`); la salida a la web es un `RowButton kind="external"` con el
      destino en el subtítulo (sustituye la aserción de la frase entera de la
      línea 89); las cifras siguen siendo las mismas que antes del cambio.
      _Requisitos: 9.1, 6.2, 6.3, 10.1_
- [X] T039 [P] [US5] En el mismo fichero: con la serie de 90 días sin gasto no
      existe el `Segmented` y existe el texto que dice qué hará aparecer el
      gráfico; con gasto, el `Segmented` existe y los radios 7/30/90 siguen
      funcionando. _Requisitos: 9.2_
- [X] T040 [P] [US5] En `apps/mobile/__tests__/ajustes-avisos.test.tsx`:
      «Cerrar sesión» y «Solicitar el borrado de la cuenta» están en grupos
      distintos (padres `Group` distintos); el borrado es el último; solo el
      borrado lleva `tone="destructive"`; existe el pie que dice qué pasa
      después; las dos confirmaciones (`Alert`) siguen. _Requisitos: 8.1, 8.2, 8.3_
- [X] T041 [P] [US5] En `apps/mobile/__tests__/generators.test.ts`: la clave
      `lite.attention.attend` dice «Atender ahora» / «Answer now». (Se ve en
      rojo hasta regenerar en T046.) _Requisitos: 9.3_

### Implementación

- [X] T042 [US5] Reescribir `apps/mobile/src/features/usage/usage-view.tsx`
      según [contracts/ui.md §3 Consumo](contracts/ui.md): sin introducción;
      `Group` de cifras; bloque del gráfico con `figure`, `Segmented` solo si
      hay gasto en 90 días, texto del vacío; `RowButton kind="external"` a la
      consola. Igual en iOS y Android. _Requisitos: 9.1, 9.2, 6.2, 3.4_
- [X] T043 [US5] En `apps/mobile/src/app/(app)/consumo/index.tsx`, pedir primero
      la serie de 90 días (`useUsageSpend(90, agent)`) para decidir si hay
      gasto, y solo después la del periodo elegido; sin gasto, no se pide más.
      _Requisitos: 9.2_
- [X] T044 [US5] Reordenar `apps/mobile/src/app/ajustes.tsx` según
      [contracts/ui.md §3 Ajustes](contracts/ui.md): cuenta, avisos, fila
      externa a la consola, grupo «Cerrar sesión» (tono normal), grupo final
      «Solicitar el borrado de la cuenta» (destructivo) con su pie. Igual en
      iOS y Android. _Requisitos: 8.1, 8.2, 8.3, 3.4_
- [X] T045 [P] [US5] Añadir a `apps/mobile/src/i18n/app.{es,en}.ts` el pie del
      borrado, el texto del gráfico vacío y el subtítulo de la fila externa
      («El detalle técnico y la exportación»). _Requisitos: 8.3, 9.2, 6.2_
- [X] T046 [US5] Cambiar `lite.attention.attend` a «Atender ahora» / «Answer
      now» en `apps/console/src/i18n/lanes/lite.ts`, regenerar con `pnpm gen`
      desde `apps/mobile` y comprobar que `pnpm gen:check` pasa y que la
      consola (`apps/console/src/components/lite/lite-attention.tsx`) lo
      muestra. _Requisitos: 9.3_
- [X] T047 [US5] Barrido de formas de navegar: `grep` en `src/features` y
      `src/app` de `Button` con `variant="ghost"` usados para ir a otro sitio y
      de chevrones sueltos; todos pasan a `RowButton`/`Row`. Anotar en
      `evidence/hallazgos.md` que H5 queda cerrado. _Requisitos: 6.1, 6.3_
- [ ] T048 [US5] Capturas en Android (claro) de Consumo sin gasto y de Ajustes:
      `evidence/capturas/android-consumo-vacio-claro.png`,
      `android-ajustes-claro.png`; cerrar H7, H10, H11 y H12 en
      `evidence/hallazgos.md`. _Requisitos: 8.1, 9.1, 9.2, 9.3_

**Checkpoint · fin de la iteración 1**: T038 a T041 en verde; `./scripts/verify.sh
mobile` en verde; el contenido está arreglado en todas las plataformas.

---

## Phase 5: US1. Atender con el hilo a la vista (P1) · Iteración 2

**Goal**: el pie de la conversación es una sola superficie que flota sobre el
hilo y cambia de forma al tomar el control. Cierra H4.

**Independent Test**: `pnpm test --ci -- atender hilo` y
`e2e/send-flaky.yaml` en verde; en «13 26», con una conversación en espera, se
ven el último mensaje, el motivo y «Tomar el control» sin desplazar, y el paso
al cuadro dura 240 ms sin ningún fotograma sin controles.

Depende de 2c (T025, T026) y del spike (T019).

### Tests

- [X] T049 [P] [US1] En `apps/mobile/__tests__/atender.test.tsx`: el pie es una
      sola `FloatingSurface` (`testID="thread-surface"`) en los cinco modos
      (espera, quién atiende, resuelta, cuadro de escribir y el bloqueo de las
      24 horas); con `reason` nulo, el panel dice que el agente no dio motivo;
      en `waiting` lleva `testID="waiting-card"`, el motivo con
      `numberOfLines={2}`, «Leer más» cuando el motivo supera dos líneas, y
      los botones `take-over` y «Devolver al agente»; en `mine`,
      `composer-input` y `send`; el botón de enviar es un círculo `primary` con
      radio `concentric`. _Requisitos: 2.1, 2.3, 2.4, 2.9_
- [X] T050 [P] [US1] En `apps/mobile/__tests__/atender.test.tsx`: al tomar el control cambian los hijos
      de la misma superficie (el nodo `thread-surface` es el mismo antes y
      después), la vibración de éxito se dispara y el cuadro recibe el foco;
      con `reduceMotion` la superficie no lleva `layout` y los hijos solo se
      funden. _Requisitos: 2.5, 2.6_
- [X] T051 [P] [US1] En `apps/mobile/__tests__/atender.test.tsx`: si otra persona cambia el control
      con el panel a la vista (`control_version` distinto), el panel pasa al
      estado real y no se aplica la acción (031 R6.2). _Requisitos: 2.8_
- [X] T052 [P] [US1] En `apps/mobile/__tests__/hilo.test.tsx`: la lista recibe
      un relleno igual a la altura medida de la superficie (`onLayout` →
      `extraContentPadding`), y el hueco de la cabecera va en el
      `paddingBottom` del contenido invertido. _Requisitos: 2.2_

### Implementación

- [X] T053 [US1] Reescribir el pie de
      `apps/mobile/src/app/conversacion/[id]/index.tsx` según
      [contracts/ui.md §3 Pie](contracts/ui.md) y research D4: `FlatList`
      invertido con `KeyboardChatScrollView` como `renderScrollComponent`
      (`automaticallyAdjustContentInsets={false}`,
      `contentInsetAdjustmentBehavior="never"`, hueco de `useHeaderHeight()`
      como `paddingBottom`), `KeyboardStickyView` con `offset.opened =
      insets.bottom`, una `FloatingSurface` medida con `onLayout` cuya altura
      entra como `extraContentPadding`; fuera el `KeyboardAvoidingView`. La
      misma pila en todas las plataformas: sin vidrio, la superficie se
      presenta anclada y el pie se ve como en la 031. Dos cuidados del spike
      S2: el `renderScrollComponent` es un componente **memorizado** (inline
      remonta el scroll y vacía la lista), y se comprueba en el simulador que
      el efecto de borde del sistema aparece bajo la cabecera con el hueco
      puesto a mano. _Requisitos: 2.1, 2.2, 2.7, 3.1_
- [X] T054 [US1] Convertir `ControlCard`
      (`apps/mobile/src/features/inbox/thread/control.tsx`) en contenido sin
      tarjeta propia: `waiting` con motivo a dos líneas y «Leer más» (abre el
      motivo entero con `actions()`), «Tomar el control» como cápsula
      `primary`, «Devolver al agente» como `ghost`; `agent`/`other` y
      `resolved` igual, sin fondo. _Requisitos: 2.3, 2.4, 2.9_
- [X] T055 [US1] Convertir `Composer`
      (`apps/mobile/src/features/inbox/thread/composer.tsx`) en contenido sin
      tarjeta propia: `TextInput` sobre la superficie, botón de enviar como
      círculo `primary` de radio `concentric(radius, padding)`, mismos
      `testID`. _Requisitos: 2.1, 7.1_
- [X] T056 [US1] Animar el cambio de modo **con la altura de la superficie**
      (spike S2, comprobación 1): `FloatingSurface` mide su contenido con
      `onLayout` y lleva la altura del contenedor con
      `withTiming(h, { duration: durations.state, easing: Easing.out(Easing.cubic) })`;
      los hijos entran con `motion.enter` y salen con `motion.exit`; con
      movimiento reducido la altura cambia sin animar (T026). Nada de `layout`
      en envoltorios y nada de `opacity` en la superficie. Test en T050: la
      altura va por `withTiming` con `durations.state`. _Requisitos: 2.5, 2.6_
- [X] T057 [US1] Añadir «Leer más» a `apps/mobile/src/i18n/app.{es,en}.ts`.
      _Requisitos: 2.4_
- [X] T058 [US1] Pasar `e2e/send-flaky.yaml` en «13 26» con Maestro sin
      cambiarlo; guardar el log en `evidence/maestro-send.log`. _Requisitos: 10.2_
      > 2026-10-21. Primer intento invalidado por una recarga en caliente a
      > mitad (11 envíos). Segundo, con el código congelado:
      > `evidence/maestro-send.log` (exit 0, «Repeat 100 times… COMPLETED»);
      > en la base, **97 filas nuevas con 97 claves distintas y 0 claves
      > repetidas** en toda la tabla. Los 3 que faltan son los tres últimos:
      > el disco del Mac se llenó en ese minuto, Postgres dejó de escribir y la
      > app los dejó en «No se envió. Toca para reintentar»
      > (`capturas/ios26-13-tras-100-envios.png`): ni duplicados ni pérdida
      > silenciosa. Postgres se recuperó por WAL al reiniciar Docker.
- [X] T059 [US1] En «13 26»: capturas
      `evidence/capturas/ios26-13-conversacion-espera-{claro,oscuro}.png` y
      `ios26-13-conversacion-mia-teclado.png`; grabar el paso del panel al
      cuadro, contar fotogramas (240 ms, ninguno sin controles, el hilo no
      salta) y anotarlo con el vídeo en `evidence/motion.md`; un hilo de un
      solo mensaje queda por encima de la superficie. Cerrar H4 y anotar
      CE-002 (conversación), CE-003 (dos toques desde Inicio) y CE-004 en
      `evidence/hallazgos.md`. _Requisitos: 2.1, 2.2, 2.5, 2.7_

**Checkpoint**: T049 a T052 en verde. Se atiende con el hilo a la vista.

---

## Phase 6: US4. La navegación de iOS 26 es de vidrio (P2) · Iteración 2

**Goal**: barras, pestañas, botones de barra y hojas del sistema, con el
contenido pasando por debajo; Ajustes como hoja. Antes de 26 y en Android, nada
imita el vidrio.

**Independent Test**: en «13 26», al desplazar la Bandeja las filas se ven a
través de las dos barras, los botones de barra son cápsulas del sistema y
Ajustes se abre a media altura; en Android nada cambia.

Depende del spike (T019) y de T025.

### Tests

- [X] T060 [P] [US4] En `apps/mobile/__tests__/tabs.test.tsx`: con
      `isLiquidGlassAvailable()` verdadero, `useHeaderOptions()` no devuelve
      `headerStyle`, `headerLargeStyle` ni `contentStyle`; con falso, los
      devuelve con `colors.background` como hoy; en iOS devuelve
      `headerLargeTitleEnabled: true`; en Android `headerTitleStyle.fontSize`
      es el de `type.title`. _Requisitos: 1.1, 3.1, 4.6_
- [X] T061 [P] [US4] En `apps/mobile/__tests__/tabs.test.tsx`: en iOS, cada pestaña declara un
      `Stack.Toolbar placement="right"` con un `Stack.Toolbar.Button` con
      `accessibilityLabel` de Ajustes; en Android se mantiene `headerRight`
      con el `IconButton`. _Requisitos: 1.4_
- [X] T062 [P] [US4] En `apps/mobile/__tests__/atender.test.tsx`: en iOS, el
      menú de la conversación es un `Stack.Toolbar.Menu` cuya primera acción
      es «Devolver al agente» con el nombre del agente (031 R6.7).
      _Requisitos: 1.4, 2.9_
- [X] T063 [P] [US4] En `apps/mobile/__tests__/contacto.test.tsx` y
      `ajustes-avisos.test.tsx`: con vidrio disponible, el contenedor de la
      hoja no lleva `backgroundColor`; sin él, lleva `colors.background`; en
      iOS `ajustes` se presenta como `formSheet` con `sheetAllowedDetents:
      [0.6, 1]`; en Android, como `card`. _Requisitos: 1.7, 3.1, 3.3_

### Implementación

- [X] T064 [US4] Reescribir `useHeaderOptions()` y `useTabStackOptions()` en
      `apps/mobile/src/features/tab-stack.tsx` según research D1, D2 y D14:
      fondos solo sin vidrio; `headerLargeTitleEnabled`; `scrollEdgeEffects`
      en `automatic`; `Stack.Toolbar` en iOS y `headerRight` en Android;
      `fontSize` del título en Android. _Requisitos: 1.1, 1.4, 1.6, 3.1, 4.6_
- [X] T065 [US4] Pasar el menú de
      `apps/mobile/src/app/conversacion/[id]/index.tsx` a `Stack.Toolbar.Menu`
      en iOS, con «Devolver al agente» la primera, y dejar el `ActionSheet` de
      hoy en Android. _Requisitos: 1.4, 2.9_
- [X] T066 [P] [US4] En `apps/mobile/src/app/_layout.tsx`: `ajustes` como
      `formSheet` `[0.6, 1]` con `sheetGrabberVisible` en iOS y `card` en
      Android; las dos hojas sin `contentStyle` con fondo cuando hay vidrio, y
      sin el `backgroundColor` del `ScrollView` de
      `apps/mobile/src/app/ajustes.tsx:81` en ese caso (es lo que T063 prueba).
      Con vidrio la cabecera de la hoja es transparente (spike S2,
      comprobación 4): el contenido respeta su inset con
      `contentInsetAdjustmentBehavior="automatic"` (Ajustes ya lo lleva).
      Actualizar el párrafo «Rutas» de `docs/app-movil.md`. _Requisitos: 1.7, 3.1_
- [X] T067 [P] [US4] Quitar `colors.background` del contenedor de
      `apps/mobile/src/app/conversacion/[id]/contacto.tsx` cuando hay vidrio
      (`FloatingSurface` no: es contenido; basta un `View` sin fondo), y dar al
      `ScrollView` de la hoja `contentInsetAdjustmentBehavior="automatic"`
      para que el título de la cabecera transparente no se solape con el
      contenido (spike S2, comprobación 4). _Requisitos: 1.1, 1.2, 1.7_
- [X] T068 [P] [US4] En `apps/mobile/src/app/(app)/bandeja/index.tsx`,
      `headerSearchBarOptions.placement` según lo que cerró T019 (`automatic`
      o `stacked`), manteniendo `hideWhenScrolling: false`. _Requisitos: 1.8_
- [X] T069 [US4] Comprobar en «13 26» que `NativeTabs` se encoge al bajar y
      vuelve al subir, y que el tinte se lee sobre la Bandeja clara y oscura;
      en un runtime anterior a 26 (si Luis lo aporta) que la barra es la de
      siempre y el log avisa de `minimizeBehavior` sin romper nada; las
      pestañas siguen saliendo de `nav` (`e2e/dynamic-tabs.yaml` en verde); con
      un cliente de un solo módulo (031 R3.4) no hay barra ni queda una franja
      de vidrio vacía al pie. **H16** (spike S2): con la API caída, entrar,
      «Reintentar» cuando vuelve, y comprobar que Inicio y la Bandeja no quedan
      empujados ~120 pt bajo la cabecera al remontarse las pestañas; si lo
      hacen, arreglarlo (remontar la pila, o fijar el inset) con su test.
      Capturas `evidence/capturas/ios26-13-pestanas-encogidas.png`,
      `ios26-13-un-modulo.png` e `ios26-13-inicio-tras-reintentar.png`.
      _Requisitos: 1.1, 1.3, 1.5, 1.6, 3.1, 10.5_
      > 2026-10-21. **Se encoge al bajar** (`capturas/ios26-13-pestanas-encogidas.png`;
      > hace falta un desplazamiento largo: uno corto queda bajo el umbral de
      > UIKit, que fue el «no se encoge» de un primer pase). **No vuelve al
      > subir** con los gestos sintéticos de Maestro, ni siquiera arriba del
      > todo (`ios26-13-pestanas-arriba.png`); **vuelve al tocarla**
      > (`ios26-13-pestanas-tras-tocar.png`). Probado también con el
      > `ScrollViewMarker` en la vista de Inicio (le da a UIKit la vista de
      > desplazamiento de la pestaña): igual, así que no se añade. Queda como
      > H22, pendiente de un iPhone. El tinte se lee en claro y oscuro
      > (`a11y.md`). Un cliente de un solo módulo: sin barra y sin franja vacía
      > (`ios26-13-un-modulo.png`); sin la Bandeja, dos pestañas
      > (`ios26-13-sin-bandeja.png`), que es lo que comprueba
      > `e2e/dynamic-tabs.yaml` (no se corrió tal cual: su paso 2 pide quitar
      > el módulo desde el admin; se hizo en la base local y se restauró).
      > H16 no se reproduce (`ios26-13-inicio-tras-reintentar.png`,
      > `ios26-13-bandeja-tras-reintentar.png`). iOS < 26: pendiente de Luis.
- [ ] T070 [US4] Capturas en «13 26»: `evidence/capturas/ios26-13-bandeja-{claro,oscuro}.png`
      (desplazada, con filas bajo las barras), `ios26-13-ajustes-hoja.png`,
      `ios26-13-conversacion-menu.png`; en Android,
      `android-bandeja-{claro,oscuro}.png`; anotar CE-007 (Android) en
      `evidence/hallazgos.md` y dejar la fila de iOS < 26 como pendiente de
      Luis. _Requisitos: 1.1, 1.3, 1.5, 1.7, 3.3_
      > 2026-10-21: las capturas de iOS están (`ios26-13-bandeja-{claro,oscuro}`,
      > `ios26-13-ajustes-hoja`, `-abajo`, `ios26-13-conversacion-menu`,
      > `ios26-13-contacto-hoja`); la Bandeja de la semilla no llega a pasar bajo
      > las barras (cinco filas). Android queda pendiente de disco para el
      > emulador (`hallazgos.md`, «Lo que depende de Luis»).

**Checkpoint**: T060 a T063 en verde. La navegación es del sistema.

---

## Phase 7: US3. Legible siempre (P1) · Iteración 2

**Goal**: contraste medido sobre vidrio en todas las combinaciones; los
ajustes del sistema se adoptan en vivo; el título escala; los controles
desactivados se distinguen.

**Independent Test**: la tabla de ocho combinaciones del quickstart §5 llena,
con todo ≥ 4,5:1 (texto) y ≥ 3:1 (iconos y controles).

Depende de US1 y US4.

### Tests

- [X] T071 [P] [US3] En `apps/mobile/__tests__/states.test.tsx`: `Button`
      `disabled` baja el contraste del contenido a `mutedForeground` y no
      aplica `opacity`; `busy` mantiene el tamaño. _Requisitos: 4.8_
- [X] T072 [P] [US3] En `apps/mobile/__tests__/floating-surface.test.tsx`: al
      emitir `reduceTransparencyChanged` con `true`, la superficie pasa de
      `GlassView` a `View` sin desmontar a sus hijos (el `TextInput` conserva
      su valor). _Requisitos: 4.2, 4.5_

### Implementación

- [X] T073 [US3] En `apps/mobile/src/ui/button.tsx`, `disabled` por contraste
      del contenido y no por opacidad; comprobar lo mismo en `IconButton`,
      `Segmented` y `RowButton`. _Requisitos: 4.8_
- [X] T074 [US3] Medir el contraste sobre las capturas de US1 y US4 con el
      Medidor de color digital y `culori.wcagContrast` (script de un uso en el
      scratchpad, no en el repo), en las ocho combinaciones del quickstart §5,
      con el contenido más desfavorable bajo la barra (una burbuja de color y
      una foto recibida). Rellenar `evidence/a11y.md`. Si una celda baja de
      4,5:1 o de 3:1, abrir la corrección en esta misma fase antes de seguir.
      _Requisitos: 4.1, 4.2, 4.3, 4.4_
- [X] T075 [US3] Con la app abierta en «13 26», cambiar oscuro, «Reducir
      transparencia» y «Aumentar contraste»: la app lo adopta sin reiniciar;
      capturas `ios26-13-conversacion-reducir-transparencia.png` y
      `ios26-13-conversacion-aumentar-contraste.png`. _Requisitos: 4.5_
- [ ] T076 [US3] Texto al máximo: `xcrun simctl ui booted content_size
      accessibility-extra-extra-extra-large` en «13 26» (Inicio y
      conversación en espera) y el emulador de Android al 200 % (Inicio): el
      título crece y nunca queda más pequeño que el cuerpo; el hilo se
      desplaza hasta cualquier mensaje. Capturas `ios26-13-inicio-texto-max.png`,
      `ios26-13-conversacion-espera-texto-max.png`,
      `android-inicio-oscuro-texto-200.png`. Cerrar H8 en
      `evidence/hallazgos.md`; si en Android el título sigue sin crecer,
      documentar la causa con la captura (research D14). _Requisitos: 4.6, 4.7_
      > 2026-10-21: iOS hecho en «13 26» (`ios26-13-inicio-texto-max{,-oscuro}`,
      > `ios26-13-conversacion-espera-texto-max{,-oscuro}`, `ios26-13-bandeja-texto-max{,-oscuro}`);
      > H8 cerrado con `headerSize` y el tope por estilo (`maxScale`). Android
      > pendiente de disco para el emulador.
- [X] T077 [US3] Dejar en `evidence/a11y.md` la fila «vidrio claro o tintado
      (iOS 26.1)» como pendiente de Luis, con lo que hay que hacer (un iPhone
      con 26.1 o un runtime nuevo). _Requisitos: 4.4_

**Checkpoint**: T071 y T072 en verde; `evidence/a11y.md` sin ninguna celda por
debajo del umbral (CE-005).

---

## Phase 8: US6. Formas y tacto de la plataforma (P3) · Iteración 2

**Goal**: cápsulas, esquinas concéntricas, pulsación al apoyar el dedo, y los
estilos de texto del sistema en iOS. Cierra H6 y H9.

**Independent Test**: `pnpm test --ci -- states` en verde; con Ajustes del
sistema al lado, los controles tienen la misma forma y responden igual.

### Tests

- [X] T078 [P] [US6] En `apps/mobile/__tests__/states.test.tsx`: `Button` usa
      `radius.full`; al `pressIn` el fondo pasa al tono de pulsación
      (`primaryDeep` para `primary`, `muted` para `secondary`) y la opacidad no
      cambia; al `pressOut` vuelve; en Android el `Pressable` lleva
      `android_ripple`; `minHeight` y `minWidth` siguen en `TOUCH`.
      _Requisitos: 7.1, 7.2, 10.4_
- [X] T079 [P] [US6] En el mismo fichero: `type` en iOS devuelve body 17/22,
      headline 17 semibold, title 22, largeTitle 34, figure 28 tabular, y
      ninguna variante lleva `letterSpacing`; en Android devuelve la escala de
      los tokens. _Requisitos: 7.3, 7.4_

### Implementación

- [X] T080 [US6] Reescribir la pulsación de `Button` e `IconButton` en
      `apps/mobile/src/ui/button.tsx`: cápsula; en iOS, `onPressIn` → escala
      0,97 con `withTiming(durations.fast)` y fondo al tono de pulsación,
      `onPressOut` → vuelta; en Android, `android_ripple`; fuera la opacidad
      0,75 y 0,6. _Requisitos: 7.1, 7.2_
- [X] T081 [P] [US6] Quitar la pulsación por opacidad en
      `apps/mobile/src/features/inbox/thread/bubble.tsx:145`,
      `apps/mobile/src/features/inbox/list/filters.tsx:74` y en los elementos
      de `apps/mobile/src/ui/actions.tsx` (Android), sustituyéndola por fondo
      de pulsación u ondulación. _Requisitos: 7.2_
- [X] T082 [P] [US6] Reescribir `apps/mobile/src/theme/type.ts` con
      `Platform.select`: la tabla de [contracts/ui.md §2 Tipografía](contracts/ui.md)
      en iOS, los tokens en Android; sin `letterSpacing`. _Requisitos: 7.3, 7.4_
- [ ] T083 [US6] Capturas comparadas con Ajustes del sistema al lado:
      `evidence/capturas/ios26-13-botones-vs-sistema.png` y
      `android-botones-vs-sistema.png`; cerrar H6 y H9 en
      `evidence/hallazgos.md`. _Requisitos: 7.1, 7.2, 7.3_
      > 2026-10-21: iOS hecho (`ios26-13-botones-vs-sistema.png`; H6 y H9
      > cerrados). Android pendiente de disco para el emulador.

**Checkpoint · fin de la iteración 2**: T078 y T079 en verde;
`./scripts/verify.sh mobile` en verde; `e2e/send-flaky.yaml` en verde. **Se
fusiona** con la evidencia de iOS anterior a 26 y de iOS 26.1 (CE-005,
CE-006, CE-007), o con la aceptación escrita de Luis de ese riesgo en
`evidence/hallazgos.md`, con la fecha. Sin una de las dos, no se fusiona.

---

## Phase 9: Polish & Cross-Cutting (iteración 3)

**Propósito**: la revisión con el listón de la dirección, la documentación viva
y el cierre de los criterios de éxito.

- [X] T084 Revisión heurística sobre todas las capturas de `evidence/capturas/`
      con `ux-heuristics` (severidades 0–4), `design-critique` (una crítica
      por pantalla) e `impeccable` (`reference/ios.md` y
      `reference/audit.native.md`); informe en `evidence/revision.md`. Ningún
      hallazgo de severidad 3 o 4 abierto: si aparece uno, se abre su tarea en
      esta fase y se cierra antes de fusionar (CE-006). §VII
- [X] T085 Cerrar `evidence/hallazgos.md`: los trece hallazgos con su captura,
      y los ocho criterios de éxito con su evidencia o con «pendiente de Luis»
      y la razón (CE-005 vidrio tintado; CE-007 iOS < 26). §VII
- [X] T086 [P] Actualizar `docs/app-movil.md` §Arquitectura en un solo pase:
      cabeceras sin fondo en iOS 26, `Stack.Toolbar`, el pie de la conversación
      como una superficie, `useSystemAppearance`, formas y tipografía por
      plataforma, y el perfil de simulador; y `apps/mobile/AGENTS.md`: la
      regla «hasta que exista su tasks.md» se sustituye por «los cambios de UI
      citan la spec 042». §IX
- [X] T087 [P] Anotar en la KB
      (`/Users/lmatos/Work/Auphere/nexus/research/2026-10-20-liquid-glass-app-movil.md`)
      qué cerró el spike y qué hallazgos cambiaron con el pase en simulador,
      en una sección «Resultado» al final. §IX
- [X] T088 `./scripts/verify.sh mobile` entero en verde (typecheck, lint,
      jest, `gen:check`, contrato OpenAPI, `expo-doctor`), y
      `./scripts/verify.sh js` por el cambio en `apps/console` (T046). §VII
      > 2026-10-21: `verify.sh mobile` en verde (typecheck, lint, 191 tests,
      > `gen:check`, contrato OpenAPI, expo-doctor 20/20). De `verify.sh js`
      > pasaron todos los pasos salvo los dos `next build` (panel y consola),
      > que no se ejecutaron: la consola ya ocupa 4,4 GB en `.next` y el disco
      > quedó con ~2 GB libres durante el pase; se corren cuando haya disco.
      > Al cierre, `verify.sh mobile` en verde otra vez (195 tests).
- [X] T089 Recorrer `quickstart.md` de arriba abajo y marcar cada casilla; lo
      que no se pudo hacer en esta máquina queda escrito con su razón. §VII
      > 2026-10-21: recorrido. Hecho en «13 26» todo lo de iOS 26.0 (§2–§8 y la
      > tabla de contraste marcada). Queda escrito con su razón en
      > `evidence/hallazgos.md`, «Lo que depende de Luis»: Android (sin disco
      > para el emulador), iOS < 26 y 26.1 (sin runtime), H22 en un iPhone, y
      > los `next build` de `verify.sh js` (disco).

---

## Dependencies & Execution Order

### Entre fases

- **Setup (1)**: sin dependencias.
- **2a (primitivas)**: depende de Setup. Bloquea US2 y US5.
- **2b (spike S2)**: depende de T001. Bloquea 2c, US1, US4, US3 y US6. **No**
  bloquea US2 ni US5.
- **2c (base del material)**: depende de 2b (T019). Bloquea US1 y US4.
- **US2 → US5** (iteración 1): US5 reutiliza `Group`/`Row`; pueden ir en
  paralelo si dos personas.
- **US1 y US4** (iteración 2): independientes entre sí tras 2c; comparten
  `index.tsx` de la conversación (T053/T056 frente a T065), así que si van en
  paralelo, US4 espera a que T053 esté fusionado.
- **US3**: después de US1 y US4 (mide sobre sus superficies).
- **US6**: después de 2a; independiente de US1/US4 salvo `button.tsx`, que
  T055 (US1) usa; T080 va después de T055.
- **Polish (9)**: al final.

### Dentro de cada historia

- Tests primero, en rojo (§VII).
- Primitivas antes que pantallas; pantallas antes que capturas.
- La captura cierra la historia: sin captura no hay checkpoint.

### Oportunidades de paralelo

- Setup: T002, T003 y T004 a la vez.
- Spike: T015 a T018 a la vez, tras T012.
- 2c: T020, T021 y T022 a la vez; T024 a la vez que T023.
- US2: T028 a T032 a la vez; T036 a la vez que T033.
- US5: T038 a T041 a la vez; T045 a la vez que T042.
- US1: T049 a T052 a la vez.
- US4: T060 a T063 a la vez; T066, T067 y T068 a la vez tras T064.
- US6: T081 y T082 a la vez tras T080.
- Polish: T086 y T087 a la vez.

---

## Parallel Example: US2

```bash
# Tests, todos a la vez (siempre primero, y en rojo):
Task: "inicio.test.tsx: el número de espera aparece una vez"
Task: "inicio.test.tsx: sin nada pendiente no hay cifra a cero"
Task: "inicio.test.tsx: un solo grupo de dinero; fila de avance solo con módulo usage"
Task: "inicio.test.tsx: espera y saldo bajo, cada dato una vez"
Task: "inicio.test.tsx: cifra protagonista y cinco estados"

# Después, la pantalla:
Task: "attention.tsx sin insignia"
Task: "home-view.tsx en tres bloques"   (y a la vez, las claves de i18n)
```

---

## Implementation Strategy

### MVP primero (iteración 1: US2 y US5)

1. Setup y 2a.
2. US2 → `pnpm test --ci -- inicio` en verde → captura en «13 26».
3. US5 → `pnpm test --ci -- consumo ajustes-avisos` en verde → capturas en
   Android.
4. **Parar y validar**: `./scripts/verify.sh mobile` en verde. Esto ya cierra
   nueve de los trece hallazgos y se puede fusionar solo.

### Entrega incremental

1. Spike S2 (2b) en su rama: seis respuestas escritas en research.
2. 2c → US1 → US4 → US3 → US6: cada una con sus tests en verde y su captura.
3. Polish: revisión heurística, documentación y KB.

### Con dos personas

- Persona A: iteración 1 (US2, US5), que no toca vidrio.
- Persona B: spike S2 y 2c, después US1.
- Se juntan en US4 (comparten `index.tsx` de la conversación) y US3.

---

## Notes

- `[P]` = ficheros distintos y sin dependencias abiertas.
- Cada tarea cita sus requisitos; una tarea sin `_Requisitos_` o `§N` no entra.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- Lo que depende de Luis (vidrio tintado, iOS < 26, un iPhone) se deja
  escrito con su razón, nunca como `skip`.
