# Análisis de consistencia: spec 069 (`/speckit-analyze`)

**Fecha**: 2026-11-21 · **Artefactos**: `spec.md` (469 líneas), `plan.md` (206), `tasks.md` (100), contra `.specify/memory/constitution.md` 1.1.0. También se han leído `log.md`, `checklists/requirements.md`, `docs/spec-driven-development.md`, el contrato `apps/mobile/src/api/openapi.json` y el estado del árbol de trabajo.

**Cómo se ha corrido:**
- Solo lectura. No se ha tocado `spec.md`, `plan.md` ni `tasks.md`.
- Los ganchos `before_analyze` y `after_analyze` son commits opcionales y se han saltado, porque aquí no se commitea.
- La oferta de remediación del paso 8 no se ha aplicado. Las correcciones van propuestas en la columna «Corrección», y las aplica quien decida.
- `check-prerequisites.sh` solo listó `tasks.md` en `AVAILABLE_DOCS`. No existen `research.md`, `quickstart.md` ni `contracts/` (ver M9).

**Veredicto: no está en verde.** Hay 2 CRITICAL y 3 HIGH. Por la puerta de la constitución, `/speckit-implement` no debería seguir hasta resolverlos.

## Resumen: CRITICAL y HIGH

- **C1 — Helvena sin licencia (§VIII, y contradice R1.5).** El plan marca ☑ la fila VIII, pero de Helvena dice «Ninguno todavía», y D3 y T004 la incrustan en el build `development`.
  - **Corrección:** `extra.helvena` queda falso en todas las variantes hasta tener el EULA, y la fila VIII y D3 se corrigen.
- **C2 — Se implementó antes de la puerta de `/speckit-analyze`.** T003 y T005 están `[x]`, y la Fase 2 está en curso en el árbol (`gen-tokens.mts`, `theme.ts`, `type.ts`, `fonts.ts`).
  - **Corrección:** congelar sin revertir, anotarlo en `log.md` y volver a correr `/speckit-analyze` cuando no queden CRITICAL ni HIGH.
- **H1 — El umbral de D8 no es el de R22.4.** «30 cuadros > 50 ms» son unos 20 fps, y R22.4 pide 50 fps.
  - **Corrección:** el umbral pasa a 20 ms por cuadro, con un test de Jest de la función que decide el cuadro quieto.
- **H2 — El rendimiento no es medible.** «Un 10 % de lo que tarda» se puede leer de dos formas, «sin saltos» no tiene métrica, el Android de gama media no tiene nombre, y T056 no bloquea nada.
  - **Corrección:** «mediana de 5 arranques en frío ≤ 1,10 × la de la 1.2.0» y «≤ 1 % de cuadros > 16,7 ms con 1.000 filas», un modelo Android con nombre, y T056 como puerta de la 070.
- **H3 — Las dos plataformas no se comprueban.** Jest corre en iOS, T050 no pide Android en cada función, y T052 no ve iOS.
  - **Corrección:** `describe.each(["ios", "android"])` en los tests del Requisito 20, y el simulador de iOS 26 en T052, o SC-001 en iOS como pendiente que bloquea la 070.

## Hallazgos

| ID | Categoría | Severidad | Dónde | Resumen | Corrección propuesta |
|----|-----------|-----------|-------|---------|----------------------|
| C1 | Constitución (§VIII) + conflicto | CRITICAL | plan.md:53, 61, 100–103, 164 · spec.md:53, 196 · tasks.md:16 | El plan marca ☑ la fila VIII, pero su tabla de licencias dice de Helvena «**Ninguno todavía**». D3 y T004 incrustan Helvena en el binario `development` sin licencia leída. Eso choca con §VIII (licencia leída y citada antes de instalar) y con R1.5 («IF la licencia de Helvena no está confirmada THEN … la fuente del sistema»), que no exceptúa desarrollo. El interruptor ya existe (`src/theme/fonts.ts:14` lee `extra.helvena`), pero `app.config.ts` todavía no lo enciende. | No hacer la parte de T004 que enciende `extra.helvena` en `development`: queda falso en **todas** las variantes hasta tener el EULA, y `DISPLAY_FONT` = fuente del sistema. La fila VIII del plan pasa a «☐ Helvena pendiente de EULA, fuera de todo binario», y D3 cambia en consecuencia. El token sigue listo, así que se cumple R1.5. |
| C2 | Constitución (§Flujo de trabajo, puerta «`/speckit-analyze` en verde antes de `/speckit-implement`») | CRITICAL | tasks.md:15, 17 · spec.md:3 · árbol de trabajo | La implementación empezó antes de esta puerta: T003 y T005 están `[x]` y la spec se declara «implementada de noche». Además, `git status` muestra la Fase 2 en curso: `scripts/gen-tokens.mts`, `src/theme/{theme,type,tokens.gen}.ts` y `src/theme/fonts.ts` nuevo, más tres dependencias añadidas a `package.json`. T001 (rama) sí es legítimo. | Congelar la implementación, sin revertir, hasta que este informe quede sin CRITICAL ni HIGH, y volver a correr `/speckit-analyze`. En `log.md`, anotar que T003, T005 y la Fase 2 empezaron antes de la puerta. |
| H1 | Conflicto (rendimiento) | HIGH | plan.md:134 vs spec.md:431 y plan.md:33 | D8 pasa al cuadro quieto «si 30 cuadros seguidos pasan de **50 ms**», que son unos **20 fps**. R22.4 y los Performance Goals exigen **≥ 50 fps**, es decir, 20 ms por cuadro. Entre 20 y 50 fps el plan sigue animando y la spec obliga a parar. | En D8, cambiar el umbral a «30 cuadros seguidos por encima de 20 ms (menos de 50 fps)». Añadir a T041 un test de Jest de la función que decide el cuadro quieto, con tiempos sintéticos: 19 ms sigue y 30 × 21 ms se queda quieto. |
| H2 | Ambigüedad (rendimiento) + §VII | HIGH | spec.md:176, 429–431, 462 · tasks.md:100 · checklists/requirements.md («Success criteria are measurable [x]») | Hay tres problemas. (1) R22.2 y SC-006, leídos al pie de la letra («no tardar más de un 10 % de lo que tarda»), piden ≤ 10 % del tiempo, cuando el plan entiende «no empeora más de un 10 %». (2) «Sin saltos» (R22.3 y SC-006) y «no se traba» (caso límite, spec.md:176) no tienen métrica. (3) «Un Android de gama media» no nombra el dispositivo. Además, T056 lo deja todo «para Luis», sin protocolo y sin bloquear nada: ningún criterio de R22.2–22.4 nace como prueba (§VII). | Reescribir R22.2–22.4 y SC-006 así: «la mediana de 5 arranques en frío hasta Inicio NO DEBE superar en más de un 10 % la de la 1.2.0 en el mismo teléfono»; «sin saltos = ≤ 1 % de cuadros por encima de 16,7 ms al desplazar 1.000 filas»; y nombrar el modelo Android. T056 pasa a puerta que bloquea la spec 070. |
| H3 | Cobertura (criterio no comprobable) | HIGH | spec.md:237, 408, 414, 457–458 · plan.md:18 · tasks.md:94, 96 · `apps/mobile/jest.config.js` (`preset: "jest-expo"`, el de iOS) | R4.2, R20.1 y SC-002 piden comprobar cada función del Requisito 20 en **iOS y Android**. El preset corre con `Platform.OS = "ios"`, y solo 12 de los 38 archivos de test cambian a Android, caso a caso (`jest.replaceProperty`). T050 no exige que cada función pase por las dos plataformas. Además, T052 verifica solo en el emulador Android («iOS queda pendiente»), mientras que el Summary del plan promete el simulador de iOS 26, así que SC-001 queda sin verificar en iOS. | En T050, parametrizar cada test del Requisito 20 con `describe.each(["ios", "android"])` y `jest.replaceProperty(Platform, "OS", os)`, como ya hacen `tabs.test.tsx` y `states.test.tsx`. En T052, o se exige el simulador de iOS 26, o SC-001 en iOS queda como pendiente que bloquea la 070, y el Summary del plan se alinea con eso. |
| M1 | Inconsistencia | MEDIUM | tasks.md:15 | T003 está `[x]` y promete una «Nota en `docs/licenses/`», pero ahí no hay ninguna para `react-native-svg`, `@shopify/react-native-skia` ni `lucide-react-native`. Las citas sí están en plan.md:161–163, que es lo que pide §VIII. | Escribir la nota o quitar esa frase de T003. Mientras tanto, desmarcarla. |
| M2 | Conflicto spec/plan | MEDIUM | spec.md:194 vs plan.md:72–78 | R1.3 dice «una sola familia de iconos (Lucide) en contenido y **controles**». D1 deja símbolos del sistema en `NativeTabs`, `Stack.Toolbar`, los menús nativos y `ActionSheetIOS`, que también son controles. La tabla «Lo que enmienda» (spec.md:20) lo insinúa, pero el criterio no lo dice. | Enmendar R1.3: «… salvo el cromo nativo (pestañas, botones de cabecera y menús del sistema), que usa los símbolos del sistema». |
| M3 | Cobertura (criterio no comprobado) | MEDIUM | spec.md:440 · plan.md:119–123 · tasks.md:36 | R23.2 dice «NO DEBE **incluir**», pero el test de T017 solo comprueba que el modo «nunca está activo». D6 confía en que Metro deje fuera `api/demo/`, y eso solo ocurre si cada `require` va tras un `__DEV__` literal, como en `src/api/reservas.ts:548`. Un `DEMO` importado no se pliega entre módulos. | En D6, exigir `__DEV__ && …` literal en cada sitio de `require`. En T017, exportar el bundle de producción (`expo export`) y buscar una cadena centinela de los datos de ejemplo: si aparece, el test falla. |
| M4 | Inconsistencia (orden y `[P]`) | MEDIUM | tasks.md:9, 41–45, 47, 50–87 · plan.md:141–155 | `[P]` se define como «toca archivos de otra área», pero T031–T034 comparten el área Bandeja, T035–T038 el área Reservas y T039–T040 el área Consumo y Ajustes. T032 toca `app/(app)/_layout.tsx`, que según D11 es de una sola mano. Las Fases 3 y 4 citan los mismos criterios sobre los mismos archivos (12.1, 14.4, 15.1/16.1 y 11.5/11.7), y la Fase 4 solo espera a la Fase 2. | Quitar `[P]` dentro de cada área. Que la Fase 4 dependa también de la Fase 3, o fundir cada arreglo de la Fase 3 en su tarea de pantalla. T032 pide el cambio de `_layout.tsx` a su dueño. |
| M5 | Cobertura | MEDIUM | spec.md:199–200, 182 · tasks.md:90 | Ninguna tarea cita R1.8 (vidrio solo en barras y controles, sin vidrio sobre vidrio) ni R1.9 (opaco con «Reducir transparencia» o en iOS anterior a 26). No hay una pieza de superficie en la Fase 2 (vidrio, opaco, tonal), y T043 (Android tonal) va al final. | Añadir a la Fase 2 una tarea «`ui/surface`: vidrio, opaco y tonal según plataforma, versión y Reducir transparencia (tests)» con `_Requisitos: 1.8, 1.9, 4.1, 4.3_`. |
| M6 | Cobertura | MEDIUM | spec.md:219 | Ninguna tarea cita R2.6 (mapa de hápticos), aunque `motion/haptics.ts` aparece en plan.md:192. | Añadir 2.6 a T014 o T016, con un test que compruebe que cada acción usa un háptico del mapa. |
| M7 | Cobertura | MEDIUM | spec.md:422 | Ninguna tarea cita R21.3 («Leído» solo si la API lo dice). | Añadir 21.3 a T033, con un test que pinte un mensaje sin estado de lectura y no encuentre «Leído». |
| M8 | Cobertura (criterio de éxito) | MEDIUM | spec.md:460 · tasks.md:97 | SC-004 exige `ux-heuristics`, `design-critique` e `impeccable`, pero T053 corre otras cuatro puertas. Esas tres skills viven en `apps/mobile/.claude/skills/` del checkout principal, fuera de git, y en el worktree solo está `skills-lock.json`. | Añadir a T053 la restauración de las tres skills desde `skills-lock.json` y su ejecución, con el umbral de SC-004 (sin severidad 3 ni 4). |
| M9 | Artefacto ausente | MEDIUM | plan.md:126, 174–175 | El plan lista `research.md` («las respuestas de los spikes») y D7 depende de él para la pestaña de búsqueda de `NativeTabs` en SDK 58. No existe y ninguna tarea lo produce. `quickstart.md` sí está en T055. | Crear una tarea en la Fase 1: «Spike D7: confirmar en la documentación de SDK 58 la pestaña de búsqueda → `research.md`», que bloquee T032. |
| M10 | Cobertura | MEDIUM | spec.md:413 · tasks.md:47–90 | R20.1 conserva «Actualizar», «Sin acceso» y «No es cliente» «con el aspecto nuevo». Ninguna tarea de la Fase 4 viste `update-required.tsx`, `no-access.tsx` ni `not-a-client.tsx`: solo T050 las prueba. | Añadir esas tres rutas a T041 (área Entrar) o crear una tarea propia con `_Requisitos: 20.1, 3.1_`. |
| M11 | Duplicación | MEDIUM | spec.md:317 vs 410 | R11.8 y R20.1 («Conversación») repiten la lista de lo que se conserva, y cada uno tiene elementos que el otro no: «baja por palabra» y «ventana de 24 h» frente a «corrección de respuestas» y «motivos de espera». R20.2 pide un test por función, así que hacen falta una sola lista. | Hacer de R20.1 la lista canónica (unión de las dos) y que R11.8 la cite. |
| M12 | Subespecificación (§IV) | MEDIUM | spec.md:312–313 · plan.md:49 | R11.4 pide confirmación solo para «Eliminar chat». «Vaciar chat» no la lleva, aunque la web la pide («¿Vaciar este chat?», `lite.gen.ts:285`). | En R11.4: «Vaciar chat y Eliminar chat, cada uno con su confirmación». |
| M13 | Mapeo con §V | MEDIUM | spec.md:225 · constitución §V | §V nombra el estado `reconectando`, y R3.1 no lo nombra. «Sin conexión» lo cubre en parte, pero la llegada en vivo de R9.5 depende del flujo SSE, y no está dicho qué enseña la Bandeja mientras se reconecta. No es un conflicto: `parcial` y `bloqueado` son de teammates. | Añadir a R3.1 o R9.5 el estado «reconectando» de la Bandeja en vivo (sin aviso hasta X s, y luego «Lo guardado a las HH:MM»). |
| L1 | Inconsistencia | LOW | tasks.md:14 vs spec.md:11, 466 | T002 compara `openapi.json` con `develop`, mientras que la spec y sus supuestos hablan de `main`. Hoy `apps/api` es idéntico en `origin/main` y en `origin/develop`. | T002: comparar también con `origin/main`. |
| L2 | §IX (puente KB) | LOW | plan.md:54 | El plan promete «al cerrar, la KB enlaza esta carpeta», pero no hay tarea para ello. El README de la KB nombra la 069, pero no enlaza `specs/069-*/`. | Añadirlo a T055. |
| L3 | Trazabilidad | LOW | tasks.md:37, 99 | T018 (textos por área) cita 1.1 (color), y T055 cita «—». | T018 → 21.2 o «soporte de 8–19»; T055 → «encabezado (IX)». |
| L4 | Terminología | LOW | spec.md:330 vs plan.md:80–88 | «Hoy en turquesa» (R13.1) no corresponde a ningún rol de D2 (menta, destacado, selección). | Decir qué rol es (¿`highlight`?) en la spec o en D2. |
| L5 | Ambigüedad | LOW | spec.md:216–217 | La coreografía de «Tomar el control» suma 400 ms, y R2.4 pone un tope de 300 ms por transición. | Precisar en R2.4 «por transición; la coreografía de 2.3 suma 400 ms por diseño». |
| L6 | Redacción | LOW | spec.md:428 · package.json | R22.1 habla de «un módulo nativo nuevo», pero entran dos (Skia y SVG). `lucide-react-native` va con `^1.77.0` y las otras dos dependencias van fijadas. | Corregir el texto y fijar la versión. |
| L7 | Cobertura | LOW | spec.md:461 | SC-005 (encontrar una conversación en menos de 10 s) no tiene tarea. | Añadir una prueba guiada a T052 o T056. |
| L8 | Subespecificación | LOW | spec.md:343, 354, 362 | El «Deshacer» de cancelar, crear y quitar no dice cómo se deshace. Existe `POST /reservas/bookings/{id}/undo` (044), pero no está dicho qué pasa con el aviso ya enviado al cliente. | Citar `…/undo` y el comportamiento de la 044 en R14.2 y R15.4. |
| L9 | Suposición de datos | LOW | spec.md:298, 323, 336 | R10.2 (búsqueda por texto de mensajes, incluidas las resueltas), R12.1 («primera vez» y «próxima reserva») y R13.7 (estados de Google) suponen datos que nadie ha comprobado en el contrato. `q` existe, pero su alcance no está descrito. La regla 6 de la spec lo ampara. | Comprobarlo en el spike de M9 y anotarlo en `research.md`. |
| L10 | Ambigüedad | LOW | spec.md:272–273 | No está dicho cuándo se muestra «N meses» y cuándo «N días», ni qué es «Conversaciones: lo que da la API». | Fijar el umbral (p. ej., < 60 días → días) y nombrar el campo. |
| L11 | Cobertura | LOW | spec.md:215, 230 | Ninguna tarea cita R2.2 (lente del sistema, sin trabajo) ni R3.6 (estado no solo por color; queda implícito en T053). | Citar 2.2 en T031 y 3.6 en T053. |

## Lo que pasa (comprobado, sin hallazgo)

- **§I y §II.** No hay rutas nuevas. Los ajustes que pide la spec ya existen en el contrato:
  - antelación: `AgentSettings.min_notice_minutes`;
  - recordatorios: `reminder_enabled`;
  - cierre por inactividad: `InboxSettings.autoclose_hours`;
  - parar ofertas: `/reservas/offers/{id}/stop`;
  - deshacer reservas: `/bookings/{id}/undo`.

  Además, `apps/api` no difiere entre `main` y `develop`.
- **§IV.** «Eliminar chat» llama a `POST …/conversations/{id}/archive`, no borra. Cumple «Borrar no existe: se archiva».
- **R18.2 frente a R20.1.** «Ver en la web» de Consumo abre `${CONSOLE_URL}/usage`, que para el cliente es la vista lite de solo lectura, sin «Comprar saldo» (`lite-usage-view.tsx:18`). No contradice la guía 3.1.3(f).
- **§VIII, para las tres dependencias de código.** Licencia, versión y párrafo citados en plan.md:161–163.
- **§IX, ida.** La spec cita `[[research/2026-11-21-app-movil-a-tiendas]]`, y la nota existe.
- **Cero `[NEEDS CLARIFICATION]`.**

## Cobertura

| Requisito | ¿Tarea? | Tareas | Notas |
|---|---|---|---|
| R1 Sistema visual | Parcial | T003, T004, T010–T013, T018 | Falta 1.8 y 1.9 (M5); 1.4 y 1.5 en conflicto (C1) |
| R2 Movimiento | Parcial | T014–T016, T033 | Falta 2.6 (M6) y 2.2 (L11); 2.3 está en T033 sin citarse |
| R3 Estados y a11y | Parcial | T010, T015, T016, T031, T053 | 3.6 implícito (L11); `reconectando` (M13) |
| R4 Android M3 | Sí | T043 | Las dos plataformas, sin comprobar (H3) |
| R5 Entrar | Sí | T003, T041 | Umbral de fps (H1) |
| R6 Recuperar | Sí | T042 | |
| R7 Preaviso | Sí | T042 | |
| R8 Inicio | Sí | T021, T030 | L10 |
| R9 Bandeja | Sí | T031 | `[P]` (M4) |
| R10 Búsqueda | Sí | T032 | Spike sin tarea (M9) |
| R11 Conversación | Sí | T024, T033 | Duplica R20.1 (M11); vaciar sin confirmación (M12) |
| R12 Contacto | Sí | T020, T034 | |
| R13 Reservas | Sí | T035 | L4 |
| R14 Una reserva | Sí | T022, T036 | L8 |
| R15 Nueva reserva | Sí | T023, T037 | |
| R16 Lista de espera | Sí | T023, T037 | |
| R17 Ajustes de reservas y Bandeja | Sí | T038 | |
| R18 Consumo | Sí | T039 | |
| R19 Ajustes | Sí | T040 | |
| R20 Nada se pierde | Sí | T001, T050 | Tres rutas sin vestir (M10); Android solo caso a caso en Jest (H3) |
| R21 Lo que se ve es verdad | Parcial | T020–T022 | Falta 21.3 (M7) |
| R22 Versión y rendimiento | Sí | T005, T056 | 22.2–22.4 sin métrica ni puerta (H1, H2) |
| R23 Datos de ejemplo | Sí | T017 | 23.2 sin comprobar inclusión (M3) |
| SC-001 | Parcial | T052 | Solo Android (H3) |
| SC-002 | Parcial | T050 | Android solo caso a caso en Jest (H3) |
| SC-003 | Sí | T016, T053 | |
| SC-004 | **No** | — | M8 |
| SC-005 | **No** | — | L7 (es de uso, no de código) |
| SC-006 | Sí | T056 | H2 |

**Tareas sin requisito:** T055 («—»). T018 está mal citada (L3).

## Alineación con la constitución

- **§VIII:** C1 (Helvena).
- **§Flujo de trabajo (puertas):** C2.
- **§VII:** H2 y H3 lo rozan: los criterios de rendimiento y de plataforma no nacen como prueba ejecutable. Quedan en HIGH porque tienen tarea (T050 y T056); lo que falla es cómo se verifican.
- **§V:** M13 es un hueco de mapeo, no un conflicto.
- **§I, §II, §III, §IV, §VI y §IX (ida):** sin conflicto (ver «Lo que pasa»).

## Métricas

- **Requisitos:** 23, con 101 criterios de aceptación. Además, 6 criterios de éxito (5 con trabajo construible).
- **Tareas:** 40. Están marcadas `[x]` T001, T003 y T005.
- **Cobertura:** 100 % de los requisitos tiene al menos una tarea. Por criterio, 95 de 101 (94 %). Sin citar: 1.8, 1.9, 2.2, 2.6, 3.6 y 21.3.
- **Ambigüedades:** 4 (H2, L5, L8, L10).
- **Duplicaciones:** 1 (M11).
- **Por severidad:** CRITICAL 2 · HIGH 3 · MEDIUM 13 · LOW 11 (29 hallazgos).

## Siguientes pasos

1. **Antes de seguir con `/speckit-implement`**, resolver C1 y C2: Helvena fuera de todo binario hasta tener el EULA, y la implementación congelada con la nota en `log.md`.
2. **Enmendar la spec a mano o con `/speckit-specify`:** R22.2–22.4 y SC-006 (H2), R1.3 (M2), R11.4 (M12), R20.1 como lista canónica (M11) y R3.1 o R9.5 (M13).
3. **Ajustar el plan:** el umbral de D8 (H1), la fila VIII y D3 (C1), el patrón `__DEV__` de D6 (M3) y el Summary frente a T052 (H3).
4. **Editar `tasks.md`:**
   - cada test del Requisito 20 en las dos plataformas, en T050 (H3);
   - la tarea `ui/surface` (M5);
   - el spike de `research.md` (M9);
   - las tres rutas de R20.1 (M10);
   - las skills de SC-004 en T053 (M8);
   - citar 2.6 y 21.3 (M6 y M7);
   - corregir los `[P]` y la dependencia de la Fase 4 (M4);
   - desmarcar o completar T003 (M1).
5. **Volver a correr `/speckit-analyze`.**

No se ha aplicado ninguna de estas correcciones.

## Segunda pasada (cierre, 2026-11-21)

**Artefactos:** `spec.md` (470 líneas), `plan.md` (207), `tasks.md` (105) y `log.md` (187), contra la constitución 1.1.0. Los hallazgos de `revision.md` se han cruzado con la tabla de `log.md`.

**Cómo se ha corrido:**
- Solo lectura. Este apartado es lo único que se ha escrito.
- Los ganchos `before_analyze` y `after_analyze` son commits opcionales (`.specify/extensions.yml:71-75, 152-156`) y se han saltado.
- Para cada tarea marcada que promete un test, se ha buscado el test en `apps/mobile/__tests__/` con grep. Las suites no se han ejecutado: el «verde, 740 tests» es lo que dice `log.md:90`.
- Los IDs nuevos llevan el prefijo `S`, para no confundirlos con H1–H3 (primera pasada) ni con H01–H23 (`revision.md`).

**Veredicto: 0 CRITICAL y 2 HIGH, así que todavía no está en verde.** Los dos HIGH son tareas marcadas cuyo test no aparece. Ninguno cambia el comportamiento: se cierran escribiendo el test, o desmarcando la tarea y declarando el hueco.

### Hallazgos nuevos

| ID | Categoría | Sev. | Dónde | Resumen | Corrección |
|----|-----------|------|-------|---------|------------|
| S1 | Tarea marcada sin respaldo (resto de H3) | HIGH | tasks.md:94 · spec.md:237, 414, 459 | T050 está `[x]` y dice «un test por cada función del Requisito 20». R4.2 y SC-002 piden esas funciones en iOS **y** Android, pero no hay ningún mapa de función a test. Solo 12 de los 65 archivos de test pasan a Android, y ninguno de ellos toca el filtro por agente, los adjuntos, los motivos de espera o de envío fallido, Llegó, No vino, bloqueos, «Sin acceso», «No es cliente» ni Entrar con Google. La pasada del emulador (`log.md:94-102`) ve solo una parte. La mitad de H3 que toca iOS sí quedó resuelta (T052 y R22.5). | Escribir en `log.md` la tabla de cada función de R20.1 con su test, y parametrizar esos tests con `describe.each(["ios", "android"])`. Si no, desmarcar T050 y poner la parte de Android en la puerta de la 070. |
| S2 | Tarea marcada sin respaldo | HIGH | tasks.md:22 · spec.md:197 | T011 dice «ningún peso por encima de 600 (test)», pero no hay ningún test que recorra los pesos. `states.test.tsx:204-213` comprueba pesos sueltos y el interletrado de todos, no el tope de peso. El código cumple: un barrido de `src/` no encuentra ningún 700, 800, 900 ni `bold`. | Añadir en `states.test.tsx` un bucle sobre `Object.values(t)` con `fontWeight ≤ 600`, en iOS y en Android. |
| S3 | Resto de C1 (texto) | MEDIUM | plan.md:61, 165, 186 · `src/theme/fonts.ts:9-10` | Estas líneas siguen diciendo que Helvena va «solo en desarrollo local». Contradicen plan.md:53 y 103 y `log.md:37`, que dicen que ningún build la lleva. El mecanismo está bien: `app.config.ts:46-47` exige `APP_HELVENA=1` y los TTF, y `assets/fonts/` no existe. | Alinear las cuatro líneas con D3: «ningún build hasta tener el EULA». |
| S4 | Contradicción con `log.md` | MEDIUM | tasks.md:26 · spec.md:118 · `src/ui/toast.tsx:26, 28` · log.md:45 | T015 y la Historia 4 dicen que «Deshacer» dura 4 s. El código dura 6 s, y 20 s con lector de pantalla (H10). La decisión 8 de `log.md` lo explica, pero la spec no se enmendó. | Enmendar spec.md:118 y T015: 6 s, y 20 s con VoiceOver o TalkBack. |
| S5 | Contradicción con `log.md` | MEDIUM | tasks.md:33 · log.md:44 | T016 incluye un «diálogo con icono en su tono», y `src/ui/` no tiene ninguno. La decisión 7 de `log.md` usa las alertas del sistema. | Sacarlo de T016 y citar la decisión 7. |
| S6 | Tarea marcada sin respaldo completo | MEDIUM | tasks.md:97, 101 · revision.md:14-16 | T053 nombra cuatro puertas, y `revision.md` corrió tres: `responsive-audit` no está. El texto largo y el texto grande sí se miraron (revision.md:160, 189; log.md:158). Además, las pasadas vivas con TalkBack y VoiceOver siguen pendientes dentro de una tarea marcada. | Correr `responsive-audit`, o quitarlo de T053 con su motivo (solo iPhone y en vertical). Sacar las pasadas con lector a una tarea abierta. |
| S7 | Trabajo pendiente bajo `[x]` | MEDIUM | tasks.md:62 · log.md:47 · spec.md:297 | T032 está marcada, pero la pestaña de búsqueda nativa de iOS 26 (la primera rama de R10.1) depende de expo-router 58.0.26 o posterior, y la app tiene la 58.0.25. Ninguna tarea abierta recoge la subida. | Una tarea abierta, «expo-router ≥ 58.0.26 + pestaña de búsqueda en iOS 26», ligada a T052. |
| S8 | Criterios DEBE incumplidos sin tarea | MEDIUM | log.md:136, 138, 153, 154 · spec.md:193, 201, 227, 236 | Cuatro hallazgos de la revisión quedan «Para Luis» y no tienen tarea abierta, aunque incumplen un criterio de tareas ya marcadas: <ul><li>H03 incumple R1.2 (ámbar fuera del icono), con T010 y T033 marcadas;</li><li>H20 incumple R1.10 (dos escalas de radio), con T012 marcada;</li><li>H21 incumple R3.3 (48 dp en Android), con T015 marcada;</li><li>H05 incumple R4.1 (etiquetas de la barra de Material 3), con T043 marcada.</li></ul> | Una tarea abierta por hallazgo, o enmendar el criterio si Luis acepta la diferencia. |
| S9 | Artefacto no localizado | MEDIUM | tasks.md:7, 103 · quickstart.md:3 | T055 promete los guiones de commit en `.claude/commits/069/`. En el worktree, `.claude/` solo tiene `launch.json`, y la ruta está ignorada (`.gitignore:68`). Puede que estén en el checkout principal; no se ha mirado, porque queda fuera del alcance. | Poner en `quickstart.md:3` la ruta absoluta, o generar los guiones. |
| S10 | Deriva del plan | LOW | plan.md:18, 110-114, 193 | El Summary promete el simulador de iOS 26, que hoy está pendiente (T052). D5 nombra `motion/micro.ts` y unos hooks `useDrawCheck` y `useFadeIn`, pero existen `micro.tsx`, `DrawCheck`, `CalmCheck` y `contentFade`. | Alinear el texto. |
| S11 | Trazabilidad | LOW | tasks.md:104-105 | T057 cita R7 (el preaviso), cuando lo que prueba son los enlaces profundos de R20.1 y R8.4. Además, T057 va delante de T056. | Citar `20.1, 8.4` y reordenar. |
| S12 | Lo que se ve es verdad | LOW | spec.md:450 · log.md:155 | La spec deja el rol fuera porque la API no lo da, pero Ajustes enseña un papel fijo (H22), porque lo pide un test de la 031. | Que Luis decida entre quitarlo y enmendar la spec. |

### Estado de la primera pasada

| ID | Estado | Prueba |
|----|--------|--------|
| C1 | **Resuelto** en el mecanismo | `app.config.ts:46-47`; plan.md:53, 103. El texto que queda es S3. |
| C2 | **Registrado**, no reversible | `log.md:23-29`. La congelación no llegó a hacerse, y esta pasada es la puerta que pedía. |
| H1 | **Resuelto** | plan.md:135; `v13-entrar-liquid.test.ts:131-145` (20 ms; 30 cuadros lentos). |
| H2 | **Resuelto** | spec.md:429-432 y 463; T056 como puerta de la 070. |
| H3 | **Parcial**: iOS resuelto y Android abierto | T052 y R22.5 para iOS; lo de Android es S1. |
| M1 | **Resuelto** | `docs/licenses/app-movil-069.md` (sin versionar todavía). |
| M2 | Sigue · MEDIUM | spec.md:194 sin enmendar. |
| M3 | Parcial · LOW | `__DEV__ &&` literal (`client.ts:31`, `sse.ts:121`); `version.test.ts` mira `EXPO_PUBLIC_DEMO`. Falta el centinela en el bundle. |
| M4 | Sin efecto | Las tareas ya están hechas. |
| M5 | Parcial · LOW | T052 cita R1 entero; `reduceTransparency` está en `floating-surface.tsx:71-72`; queda pendiente con iOS. |
| M6 | Sigue · MEDIUM | Ninguna tarea cita 2.6. |
| M7 | Parcial · LOW | Hay test (`v13-bandeja-conversacion.test.tsx`, «Leído» solo si la API lo dice), pero 21.3 no se cita. |
| M8 | **Resuelto** | revision.md:15 corrió `ux-heuristics`, `design-critique` e `impeccable`. |
| M9 | Parcial · LOW | La respuesta de D7 está en `log.md:47`; plan.md:175 sigue listando un `research.md` que no existe. |
| M10 | Parcial · MEDIUM | `no-access.tsx` y `not-a-client.tsx` cambiadas; `update-required.tsx` sin tocar y sin tarea. |
| M11 | Sigue · MEDIUM | |
| M12 | Parcial · LOW | El código confirma las dos acciones (`conversacion/[id]/index.tsx:57`); falta enmendar R11.4. |
| M13 | Sigue · MEDIUM | |
| L1 | **Resuelto** | `apps/api` y `openapi.json` no difieren ni de `origin/develop` ni de `origin/main`. |
| L2 | **Resuelto** | KB `research/2026-11-21-app-movil-a-tiendas/README.md:49` enlaza la carpeta. |
| L3, L5, L7, L10 | Siguen · LOW | |
| L4 | Parcial · LOW | `log.md:46` decide `basil`; spec.md:330 sigue diciendo turquesa. |
| L6 | Sigue · LOW | `package.json:36` `^1.77.0`; spec.md:428. |
| L8 | Parcial · LOW | `log.md:53-54` lo define; la spec no. |
| L9 | Parcial · LOW | `log.md:70` (búsqueda en dos lecturas). |
| L11 | Parcial · LOW | T053 cubre el 3.6; el 2.2 sigue sin citar. |

### Lo que pasa

- **§VIII:** entran exactamente tres dependencias (`git diff origin/develop -- apps/mobile/package.json`), las tres citadas en plan.md:162-164.
- **§I y §II:** no hay rutas nuevas (L1).
- **D2 frente al código:** los roles de plan.md:82-89 existen en `gen-tokens.mts:121-162`.
- **T010:** el test de `controlBorder` existe (`v13-revision-aa.test.tsx:52-56`, umbral de 3,2 en claro y oscuro).
- **Los siete fallos AA de T053:** cada uno tiene su test (`v13-revision-aa`, `toast.test.tsx:60`, `v13-entrar-recuperar.test.tsx:88`).
- **Las Fases 3 y 4:** hay test de cada arreglo (contacto, moneda, precio, teléfono obligatorio, ventana vencida y «Tomar el control»).
- **D11:** de los tests que existían, los únicos cambios que no están en la tabla de `log.md` (`toast` y `reservas-dia`) solo añaden casos.
- **Cero `[NEEDS CLARIFICATION]`** en spec, plan y tareas.

### Métricas

- **Requisitos:** 23, con 102 criterios (la primera pasada contó 101; se añadió el 22.5).
- **Tareas:** 41, de las que 38 están `[x]`. Abiertas: T052 (iOS), T056 y T057, las tres puertas de la 070.
- **Cobertura:** el 100 % de los requisitos tiene tarea. Por criterio, 99 de 102 (97 %). Sin citar: 2.2, 2.6 y 21.3.
- **Por severidad:**
  - CRITICAL 0 · HIGH 2 · MEDIUM 12 · LOW 17.
  - De los MEDIUM, 7 son nuevos (S3–S9) y 5 vienen de la primera pasada (M2, M6, M10, M11 y M13).
  - De los LOW, 3 son nuevos (S10–S12) y 14 vienen de la primera pasada.
  - De la primera pasada quedan resueltos 7: C1, H1, H2, M1, M8, L1 y L2.

### Siguientes pasos

1. **Para cerrar en verde:** S1 y S2, con los tests o desmarcando la tarea.
2. **Antes del PR a `develop`:** S3–S9. Son texto en spec, plan y tareas, más una tarea abierta por cada cosa pendiente.
3. **Lo demás** puede ir con la 070.

## Tercera pasada (cierre, 2026-11-21, 04:50)

**Artefactos:** `spec.md` (470 líneas), `plan.md` (207), `tasks.md` (120), `log.md` (245) y `cso.md` (70), contra la constitución 1.1.0.

**Cómo se ha corrido:**
- Solo lectura. Este apartado es lo único que se ha escrito.
- Para cada test que se cita (el mapa de `log.md:174-195` y `v13-nada-se-pierde`), se ha buscado el archivo y el título con grep, y se ha leído lo que afirma.
- No se ha ejecutado ninguna suite. El verde es el que `log.md:99` da como corrido después de `/cso`: 04:36, 66 suites y 790 tests.
  - Las fechas no confirman el orden. Lo último que se tocó de la app es `eslint.config.js` (04:35:15), `version.test.ts` (04:35:49) y los dos `.gen.ts` (04:36:43), que reescribió un `pnpm gen`, porque `gen:check` no escribe (`scripts/_write.mts`).
  - Lo único que se ha corrido es `gen-tokens.mts --check` y `gen-liquid.mts --check`, que solo leen: los dos `.gen.ts` están al día.
- Los MEDIUM y LOW de las dos primeras pasadas se arrastran sin volver a comprobarlos, salvo M10 y L6.
- Los IDs nuevos llevan el prefijo `N`.

**Veredicto: en verde, con 0 CRITICAL y 0 HIGH.** S1 y S2 están cerrados. Quedan 11 MEDIUM y 19 LOW, y ninguno bloquea.

### Estado de la segunda pasada

| ID | Estado | Prueba |
|----|--------|--------|
| S1 | **Resuelto** el mapa. Android, **abierto con tarea** (T058) | El mapa está en `log.md:170-197`: 20 filas, que cubren cada función de R20.1 (spec.md:404-414). Existen todos los archivos y títulos que cita. Entrar con Google se recorre en `sign-in.test.tsx:38-73` y `:156-186`. T050 ya no promete Android. Lo que queda está en N1 y N2. |
| S2 | **Resuelto** | `v13-nada-se-pierde.test.tsx:30-43` tiene dos pruebas: <ul><li>un bucle sobre la escala (en Jest, la de iOS);</li><li>un barrido de `src` por texto, que también cubre la tabla de Android (`type.ts:74-83`).</li></ul> Un grep propio no encuentra 700, 800, 900 ni `bold`. |
| S3 | **Resuelto** | plan.md:61, 165 y 186, y `fonts.ts:7-12`: «ningún build», salvo encenderla a mano. |
| S4 | **Resuelto** | spec.md:118 y tasks.md:26. `toast.tsx:26` (6 s) y `:28` (20 s). |
| S5 | **Resuelto** | tasks.md:33 cita la decisión 7, y `src/ui/` no tiene diálogo. |
| S6 | **Parcial** · MEDIUM | `responsive-audit` corrió (log.md:166-168; siete `evidence/android-estrecho-grande-*.png`). Pero las pasadas con TalkBack y con VoiceOver siguen «Pendiente» dentro de T053 `[x]` (tasks.md:101), sin tarea abierta. **Corrección:** VoiceOver como línea de T052, y TalkBack como línea de T058. |
| S7 | **Parcial** · MEDIUM | T032 dice «Abierto para la 070» (tasks.md:62), pero sigue `[x]` y T052 no lo nombra. **Corrección:** una línea en T052 con expo-router ≥ 58.0.26 y la pestaña de búsqueda. |
| S8 | **Abierto con tarea** | H03, H05 y H20 están en T059 (tasks.md:114-119). H21 está resuelto: `slopFor` (`theme.ts:36-42`) se usa en `day-grid.tsx:188, 237` y `bubble.tsx:174`, con su test en `v13-revision-aa.test.tsx:159-171`. |
| S9 | **Parcial** · MEDIUM | T055 ya dice «del checkout principal» (tasks.md:103). Pero quickstart.md:3 dice «Todo está en el worktree…» y, justo después, «los guiones están en `.claude/commits/069/`», y eso se lee como dentro del worktree. No se ha comprobado que el guion exista, porque está fuera del worktree y esta pasada no sale de él. **Corrección:** la ruta absoluta en quickstart.md:3. |
| S10 | Sigue · LOW | plan.md:18 y 110-114 no han cambiado, y T014 sigue diciendo `motion/micro.ts`. |
| S11 | Sigue · LOW | T057 sigue citando R7 (tasks.md:104). Además, T056 va ahora la última, detrás de T057–T059 (tasks.md:120). |
| S12 | Sigue · LOW | |

### Hallazgos nuevos

| ID | Categoría | Sev. | Dónde | Resumen | Corrección |
|----|-----------|------|-------|---------|------------|
| N1 | Puerta sin respaldo en la spec | MEDIUM | spec.md:237, 432, 459 · tasks.md:104-105 | T057 y T058 se llaman «puerta de la 070» solo en `tasks.md`. R22.5 da como puerta 22.2–22.4 y el simulador de iOS, pero nada de Android. R4.2 y SC-002 siguen pidiendo Android sin decir cuándo. La mitad Android de S1 la aplaza una tarea, no la spec. | Añadir a R22.5 «el recorrido del Requisito 20 en Android (T058) y el aviso real (T057)». |
| N2 | Cobertura de la puerta | MEDIUM | tasks.md:105-113 · log.md:187-188 | T058 no nombra dos filas que el mapa marca «no» en Android: «Ajustes de reservas» y el mapa de calor de Aforo. Si se sigue al pie de la letra, SC-002 se cerraría sin ellas. | Añadirlas a T058. |
| N3 | Aplazado sin tarea | MEDIUM | cso.md:23, 26, 29, 30 · log.md:209-214 · spec.md:442 | Cuatro hallazgos de `/cso` se aplazan sin tarea en `tasks.md`: <ul><li>L1, «para Luis»: fijar `lucide-react-native` (es el L6 de la primera pasada);</li><li>L4, «para la 070»;</li><li>I2: que `app.config.ts` falle si Helvena va fuera de desarrollo;</li><li>I3, «tarea aparte».</li></ul> L4 toca un DEBE de una tarea marcada: R23.3 pide «sin ningún dato real» y T017 está `[x]`, pero los teléfonos `+34 600 000 0NN` tienen formato de móvil real. Además, los IDs L1–L5 de `cso.md` chocan con los L1–L11 de este archivo. | <ul><li>L4: puerta de la 070 en `tasks.md`, o números de un rango de ficción ya.</li><li>L1 e I3: una tarea abierta.</li><li>IDs de `cso.md` con el prefijo `CSO-`.</li></ul> |
| N4 | El test dice más de lo que prueba | LOW | `v13-nada-se-pierde.test.tsx:68-80` · `routing.ts:25-35` · `notices.ts:18-64` | `routeFor` solo lee `url`, así que la columna `kind` no cuenta. La tabla prueba cuatro formas de enlace, no siete tipos, y un tipo nuevo en `NOTICE_KINDS` no la haría fallar. El enlace de cada tipo lo pone la API (`push_payloads`; `apps/api/tests/unit/test_push_payload_kinds.py`). Los siete tipos de la tabla sí coinciden con `NOTICE_KINDS`. | Recorrer `NOTICE_KINDS` y exigir una fila por tipo. Citar en el mapa el test de la API. |
| N5 | R3.3 en Android | LOW | `features/reservas/header.tsx:155, 271` | El conmutador de lista y cuadrícula tiene `minWidth: 44` y la holgura solo en vertical, así que en Android mide 44 dp de ancho y R3.3 pide 48. No es uno de los puntos de H21, que sí están arreglados. | `minWidth: MIN_TARGET`. |

### Lo que pasa

- **Numeración:** hay 43 tareas, sin IDs repetidos. Existen todas las que citan spec, plan, log, quickstart y cso (T002–T004, T010, T050, T052 y T056–T059). Del orden se ocupa S11.
- **Tareas marcadas:**
  - T011 y T050 tienen ya el respaldo que dicen.
  - La primera cláusula de T050 se sostiene. Han cambiado 14 tests de partida, y los dos que faltan en la tabla de `log.md` (`reservas-dia` y `toast`) no quitan ninguna aserción (`git diff origin/develop`).
  - T051 se apoya en el verde de las 04:36 de `log.md:99`. Las fechas no prueban que se corriera después de los cambios de las 04:35 (ver «Cómo se ha corrido»). Si se corrió antes, T051 sería una tarea marcada sin respaldo, que es un HIGH. Antes del PR, `./scripts/verify.sh mobile` una vez más lo aclara.
- **`/cso`:** sus severidades coinciden con log.md:205 (0 CRITICAL y 0 HIGH). L2 y L3 están arreglados (`eslint.config.js:31-39`; `version.test.ts:48, 50`).
- **Filas «sí» del mapa:** cada una tiene captura en `evidence/` o mención en `log.md`. Contacto solo tiene la mención (log.md:123).
- **M10:** sigue Parcial · MEDIUM. Ya hay test de la pantalla, pero `update-required.tsx` no difiere de `origin/develop`, y vestirla no tiene tarea.
- **L6:** sigue (`package.json:36`, `^1.77.0`). Es el mismo que el L1 de `cso.md`, ver N3.
- **Cero `[NEEDS CLARIFICATION]`** en spec, plan, tareas, log y quickstart.

### Métricas

- **Tareas:** 43, de las que 38 están `[x]`. Las abiertas son T052, T056, T057 y T058, que son puertas de la 070, y T059, que espera la decisión de Luis.
- **Cobertura por criterio:** sin cambios, 99 de 102. Siguen sin citar 2.2, 2.6 y 21.3.
- **Por severidad:** CRITICAL 0 · HIGH 0 · MEDIUM 11 · LOW 19.
  - MEDIUM: S6, S7, S9 y N1–N3, más M2, M6, M10, M11 y M13 (arrastrados).
  - LOW: S10–S12 y N4–N5, más los 14 de la primera pasada (arrastrados).
  - Se cierran en esta pasada S1 (Android queda con tarea), S2, S3, S4, S5 y S8 (con tarea).

### Siguientes pasos

1. **Nada bloquea:** la puerta de `/speckit-analyze` está en verde.
2. **Antes del PR a `develop`:** N1–N3, S6, S7 y S9. Son texto en la spec, en las tareas y en `quickstart.md`.
3. **Lo demás** puede ir con la 070.
