---

description: "Tareas de la spec 044: la app con Reservas"
---

# Tasks: La app con Reservas

**Input**: `specs/044-la-app-con-reservas/`: [spec.md](spec.md), [plan.md](plan.md),
[research.md](research.md), [data-model.md](data-model.md),
[contracts/app-needs.md](contracts/app-needs.md), [quickstart.md](quickstart.md)

**Tests**: no son opcionales (constitución §VII). Cada bloque de tests se
escribe y se ve en rojo antes de su implementación. Lo que solo se ve en un
simulador tiene su captura en `evidence/`; nunca un `skip`.

**Organización**: por historia de la spec y su prioridad. `[USn]` es la
**Historia n**:

| Etiqueta | Historia | Prioridad |
|---|---|---|
| US1 | El día de hoy en Reservas, en los dos modos | P1 |
| US2 | Una reserva: verla, confirmarla, cancelarla | P1 |
| US3 | Llegada sin reserva en Aforo | P1 |
| US4 | Nueva reserva desde el teléfono | P2 |
| US5 | Lo urgente de todos los módulos, en Inicio | P2 |
| US6 | Atender: quién espera, por qué y desde cuándo | P2 |
| US7 | El contacto con su próxima reserva | P3 |
| US8 | Consumo: primero la respuesta | P3 |
| US9 | Lista de espera y ajustes en el teléfono | P3 |
| US10 | Avisos por módulo y fuera de horario | P3 |

## Reglas de este repo *(constitución)*

- Cada tarea termina con `_Requisitos: N.m_` (de **esta** spec; las de otras
  specs se citan como `042 R2.3`) o con `§N` si nace de la constitución.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- Test primero (§VII). El rojo se ve antes de tocar la pantalla.
- **Solo `apps/mobile`, `specs/044-*` y `docs/app-movil.md`.** Nada de
  `apps/api`, `apps/worker`, `apps/mcp` ni `packages/*` (son de `consolas-web`).
- **`apps/mobile` es su propio workspace de pnpm.** Nada de hex (ESLint). Nunca
  vidrio sobre vidrio. Los `testID` de Maestro no cambian.
- **`docs/app-movil.md` en el mismo commit** que lo que describe.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- Durante una tanda de capturas no se edita código.

## Format: `[ID] [P?] [Story] Descripción`

---

## Phase 1: Setup

- [x] T001 Crear `specs/044-la-app-con-reservas/evidence/` con `capturas/`,
      `hallazgos.md` (tabla de capturas por pantalla y estado) y `builds.md`.
      §VII
- [x] T002 [P] Leer `EXPO_PUBLIC_RESERVAS_DEMO` y
      `EXPO_PUBLIC_RESERVAS_DEMO_STATE` en `apps/mobile/src/config.ts` solo con
      `__DEV__` (fuera de desarrollo, `null` siempre), con test en
      `__tests__/reservas-demo.test.ts`. _Requisitos: 18.1, 18.2_

---

## Phase 2: Foundational

**Propósito**: el modelo, el adaptador, la pestaña y las primitivas que todas las
historias usan. Nada de esto se ve solo.

### Tests (en rojo primero)

- [x] T003 [P] `__tests__/reservas-model.test.ts`: «ahora» del negocio desde
      `now` del servidor; día cerrado por `hours`; pasada; «Llega tarde · N min»
      (15 min, dentro de la estancia); resumen del día sin canceladas; dentro
      ahora y próxima hora en Aforo; las tres siguientes de hoy; nivel de
      ocupación en cinco pasos; minutos ↔ «HH:MM»; semana desde el lunes; rejilla
      del mes. _Requisitos: 1.5, 2.5, 2.7, 2.9, 2.10, 3.3, 9.1, 9.4_
- [x] T004 [P] `__tests__/reservas-adapter.test.ts`: el adaptador convierte el
      contrato (§2–§7 de `contracts/app-needs.md`) al modelo de `data-model.md`;
      los errores `slot_taken`, `stale`, `no_room`, `closed`, `blocked`,
      `not_editable` llegan como `ApiError` con su código; las escrituras llevan
      `Idempotency-Key`. _Requisitos: 4.5, 5.6, 5.7, 6.4_
- [x] T005 [P] `__tests__/tabs.test.tsx`: `reservas` es un módulo conocido, con
      su ruta y su icono; sin él no se declara visible. _Requisitos: 1.1, 1.2_

### Implementación

- [x] T006 `apps/mobile/src/lib/reservas-model.ts`: los cálculos puros de
      `data-model.md`. _Requisitos: 1.5, 2.5, 2.7, 2.9, 2.10, 3.3, 9.1, 9.4_
- [x] T007 `apps/mobile/src/api/reservas.ts`: tipos del contrato y del modelo,
      mapeo, la fuente HTTP con `authedFetch` (D1) y `reservasSource()` que elige
      la de ejemplo en desarrollo si se pidió. _Requisitos: 1.3, 4.5, 5.6, 5.7, 18.1_
- [x] T008 `apps/mobile/src/api/reservas-demo.ts`: Barbería Norte (Servicios,
      CLP, Providencia, +56) y Casa Lucía (Aforo, 64), con mutaciones en memoria,
      latencia, errores (`slot_taken`, `no_room`) y los estados forzados de
      `EXPO_PUBLIC_RESERVAS_DEMO_STATE`; añade `reservas` a `/me`; avisos y
      silencio en memoria. Solo se importa con `__DEV__`. _Requisitos: 18.1, 18.2_
- [x] T009 `apps/mobile/src/api/reservas-hooks.ts` y `query.ts`: claves
      (`["reservas", …]`), lecturas (config, rango, ocupación, huecos, lista de
      espera) con `placeholderData`, escrituras que invalidan el día, Inicio y el
      contacto (`invalidateReservas`), y 403 → relee `/me`. _Requisitos: 1.4, 17.1, 17.2_
- [x] T010 `apps/mobile/src/lib/modules.ts` y `src/app/(app)/_layout.tsx`:
      `reservas` → ruta `reservas`, icono `calendar`/`event`; la ruta
      `src/app/(app)/reservas/_layout.tsx` (pila de la pestaña). _Requisitos: 1.1, 1.2_
- [x] T011 [P] `apps/mobile/src/ui/toast.tsx` (proveedor en `_layout.tsx`):
      uno a la vez, opaco, anunciado, 4 s o 6 s con «Deshacer», fundido con
      «Reducir movimiento»; test `__tests__/toast.test.tsx` en rojo primero.
      _Requisitos: 16.5, 16.7_
- [x] T012 [P] `apps/mobile/src/ui/fab.tsx` (vidrio interactivo en iOS 26,
      opaco si no o con «Reducir transparencia»; extendido de Material 3 en
      Android) y `src/ui/pill.tsx` (estado de una reserva en palabras y tono);
      test `__tests__/fab-pill.test.tsx` en rojo primero. _Requisitos: 5.1, 6.1, 16.4, 16.6_
- [x] T013 [P] `__tests__/reservas-no-disk.test.ts`: el adaptador y los hooks
      de Reservas no escriben en el almacén seguro ni en archivos (031: nada de
      clientes finales en disco). §I
- [x] T014 [P] Palabras de Reservas y de las mejoras en
      `apps/mobile/src/i18n/app.es.ts` y `app.en.ts`. _Requisitos: 2, 4, 5, 6, 7, 8_

**Checkpoint**: `pnpm verify` en verde; la pestaña aparece con los datos de
ejemplo y la pantalla está vacía.

---

## Phase 3: US1 — El día de hoy, en los dos modos (P1) 🎯 MVP

### Tests

- [x] T015 [P] [US1] `__tests__/reservas-dia.test.tsx`: abre en Día y hoy;
      tira de días con hoy y cerrados; «Hoy» si no es hoy; Servicios en lista con
      resumen, «Ahora», pasadas atenuadas y filtro por profesional; Cuadrícula
      con un bloque por reserva legible; Aforo con tres cifras (hoy y otro día),
      tira de franjas que filtra y «Ver todo el día», grupos por hora, «Llegó» y
      «No vino» según la hora, «Llega tarde»; cerrado y vacío; la marca de datos
      de ejemplo; carga, error, parcial y sin red. _Requisitos: 1.3, 2.1–2.11, 16.1, 18.1_

### Implementación

- [x] T016 [US1] `src/features/reservas/header.tsx`: periodo
      (`Segmented`), tira de días, título del día, «Hoy», Lista/Cuadrícula en
      Servicios·Día. _Requisitos: 2.2, 2.3, 2.4_
- [x] T017 [US1] `src/features/reservas/day-services.tsx` (lista con filtro por
      profesional) y `day-grid.tsx` (columnas, horas, bloques, línea de ahora, aviso
      con texto grande). _Requisitos: 2.4, 2.5, 2.6, 2.10_
- [x] T018 [US1] `src/features/reservas/day-capacity.tsx`: cifras, tira de
      franjas, grupos por hora, «Llegó»/«No vino», «Llega tarde». _Requisitos: 2.7, 2.8, 2.9, 2.10_
- [x] T019 [US1] `src/app/(app)/reservas/index.tsx`: la pantalla con sus
      estados, barra (iOS: «Nueva reserva» y `⋯`; Android: `⋯` y el flotante),
      el parámetro `date`/`open` y el `SettingsToolbar`. _Requisitos: 1.3, 1.4, 2.1, 2.11, 16.1_

### US1b — Semana y Mes (P2)

- [x] T020 [P] [US1] `__tests__/reservas-semana-mes.test.tsx`: Servicios·Semana
      con tarjetas por día; Aforo·Semana mapa de calor con leyenda y celda que
      lleva al día con la franja; Mes con lunes primero, %, «Cerrado» y día que
      lleva al día; flechas de periodo. _Requisitos: 3.1–3.4_
- [x] T021 [US1] `src/features/reservas/week.tsx` y `month.tsx`. _Requisitos: 3.1–3.4_

---

## Phase 4: US2 — La hoja de una reserva (P1)

- [x] T022 [P] [US2] `__tests__/reserva-hoja.test.tsx`: datos por modo, origen e
      historial; solo las acciones de `actions`; cancelar pide confirmación con
      el WhatsApp; «Llegó»/«No vino»/«Marcar confirmada» sin confirmación; aviso
      breve con «Deshacer»; error en una frase y relectura; sin red, sin acciones.
      _Requisitos: 4.1–4.6, 16.7_
- [x] T023 [US2] `src/app/reserva/[id].tsx` (hoja, `useSheetOptions().reserva`)
      y `src/features/reservas/sheet.tsx`. _Requisitos: 4.1–4.6_

---

## Phase 5: US3 — Llegada sin reserva (P1)

- [x] T024 [P] [US3] `__tests__/llegada.test.tsx`: el «+» solo en Aforo·Día·hoy
      y en el menú; comensales y nombre; «Cabe…», «No cabe…», «Ahora no hay
      servicio»; registrar con aviso breve; si no cabe, apuntar en la lista.
      _Requisitos: 6.1–6.4_
      Nota: el test vive en `__tests__/llegada-nueva.test.tsx`, junto con el de T026 (comparten fixtures).
- [x] T025 [US3] `src/app/reserva/llegada.tsx` y
      `src/features/reservas/walk-in.tsx`; el flotante en `reservas/index.tsx`.
      _Requisitos: 6.1–6.4_

---

## Phase 6: US4 — Nueva reserva (P2)

- [x] T026 [P] [US4] `__tests__/nueva-reserva.test.tsx`: botón en iOS y
      flotante extendido en Android; Servicios con servicio, «Con», días hábiles
      y huecos reales con profesional; Aforo con comensales, «quedan N» y
      «completo» no elegible; aviso por encima del máximo; nombre obligatorio y
      +56; resumen; una sola escritura aunque se toque dos veces; `slot_taken`
      relee y conserva; sin huecos. _Requisitos: 5.1–5.8_
      Nota: en `__tests__/llegada-nueva.test.tsx` (ver T024).
- [x] T027 [US4] `src/app/reserva/nueva.tsx` y
      `src/features/reservas/new-reservation.tsx`. _Requisitos: 5.1–5.8_

---

## Phase 7: US5 — Inicio (P2)

- [x] T028 [P] [US5] `__tests__/inicio.test.tsx`: la atención suma «N reservas
      de hoy sin confirmar» con «Ver reservas»; el saldo sigue; sin insignia;
      conversaciones → Bandeja y saldo → Consumo por fila con chevrón; «Hoy en
      Reservas» por modo; sin módulo, nada de Reservas; el número de espera una
      vez. _Requisitos: 1.2, 9.1–9.5_
- [x] T029 [US5] `src/features/home/{home-view,attention}.tsx`,
      `src/features/home/today-reservas.tsx` y `src/app/(app)/inicio/index.tsx`.
      _Requisitos: 9.1–9.5_

---

## Phase 8: US6 — Bandeja y conversación (P2)

- [x] T030 [P] [US6] `__tests__/bandeja.test.tsx`: grupo «Esperan a una persona
      · N» con «Todas» y sin búsqueda, motivo y «hace N min»; sin
      `waiting_since`, sin tiempo; pie de la regla; búsqueda nativa y filtro por
      agente intactos. _Requisitos: 10.1–10.5_
- [x] T031 [P] [US6] `__tests__/atender.test.tsx`: «Espera hace N min · lo pidió
      el agente de X» (de `waiting_since` o del último `escalated`); subtítulo por
      estado; «Responde el agente… Si entras, deja de responder.»; con el control,
      «Atiendes tú · el agente de X está en pausa», «Devolver» y chips con el
      borrador vacío; sin aviso breve al tomar o devolver. _Requisitos: 11.1–11.5, 16.7_
- [x] T032 [US6] `src/api/endpoints.ts` (campos de la 045 como opcionales),
      `src/features/inbox/list/*` y `src/app/(app)/bandeja/index.tsx`.
      _Requisitos: 10.1–10.5_
- [x] T033 [US6] `src/features/inbox/thread/{control,composer,foot}.tsx`,
      `model.ts` y `src/app/conversacion/[id]/index.tsx`. _Requisitos: 11.1–11.5_

---

## Phase 9: US7, US8 — Contacto y Consumo (P3)

- [x] T034 [P] [US7] `__tests__/contacto.test.tsx`: «Próxima reserva» con el
      módulo y lleva a Reservas en ese día con la hoja; sin módulo o sin reserva,
      nada. _Requisitos: 12.1, 12.2_
- [x] T035 [US7] `src/app/conversacion/[id]/contacto.tsx`. _Requisitos: 12.1, 12.2_
- [x] T036 [P] [US8] `__tests__/consumo.test.tsx`: «Te alcanza hasta el <día>
      <n>» de `runs_out_on` o `days_left`; «Para recargar, habla con…»; sin
      gasto, sin asignar y agotado sin fecha; título de la gráfica con el total;
      sin comprar. _Requisitos: 13.1–13.4_
- [x] T037 [US8] `src/features/usage/usage-view.tsx` y `src/lib/panel-model.ts`.
      _Requisitos: 13.1–13.4_

---

## Phase 10: US9 — Lista de espera, ajustes y bloqueos (P3)

- [x] T038 [P] [US9] `__tests__/reservas-espera-ajustes.test.tsx`: explicación
      por modo, tarjetas con estado y cuenta atrás, «Ofrecer ahora» solo si cabe,
      «Quitar», vacío; Ajustes con el modo, Aforo, horario «Se edita en la web»,
      equipo y servicios en solo lectura, lista de espera y confirmación;
      editable solo si la API lo dice; bloqueos con «Quitar» y «Bloquear horas»
      con motivo obligatorio. _Requisitos: 7.1–7.4, 8.1–8.7_
- [x] T039 [US9] `src/app/(app)/reservas/espera.tsx`,
      `src/app/(app)/reservas/ajustes.tsx`, `src/app/reserva/bloquear.tsx` y
      `src/features/reservas/{waitlist,settings,block}.tsx`; el menú `⋯`.
      _Requisitos: 7.1–7.4, 8.1–8.7_

---

## Phase 11: US10 — Avisos y Entrar (P3)

- [x] T040 [P] [US10] `__tests__/ajustes-avisos.test.tsx` y `push.test.tsx`:
      grupos Bandeja, Reservas y Saldo; tres de Reservas con el módulo, la de la
      lista de espera apagada de partida; silencio con su pista solo si la API lo
      trae; permiso con aviso de ejemplo y grupos, acciones al pie; la ruta de un
      aviso de Reservas abre la reserva; canal y categoría. _Requisitos: 14.1–14.6_
- [x] T041 [US10] `src/features/notices.ts`, `src/app/ajustes.tsx`,
      `src/app/notices-permission.tsx`, `src/push/{routing,channels,categories}.ts`.
      _Requisitos: 14.1–14.6_
- [x] T042 [P] `__tests__/sign-in.test.tsx`: error en una frase; nota bajo
      Google. Implementar en `src/app/sign-in.tsx`. _Requisitos: 15.1, 15.2_

---

## Phase 12: Builds 1.1.0 (R19)

- [x] T043 `apps/mobile/app.config.ts`, `package.json`: versión 1.1.0
      (`runtimeVersion` la sigue); test en `__tests__/version.test.ts`.
      _Requisitos: 19.1_
- [x] T044 `apps/mobile/eas.json`: `preview` con `buildType: "apk"`;
      `staging` Android AAB y `submit.staging.android` con pista interna y la
      cuenta de servicio desde una variable de archivo de EAS; iOS `staging` con
      `ascAppId`. _Requisitos: 19.2_
- [x] T045 `evidence/builds.md` y `docs/app-movil.md` §Builds: lo que crea Luis
      (Play Console, Firebase, `GOOGLE_SERVICES_JSON`, secretos `NEXUS_FCM_*`,
      cuenta de servicio de submit) y los comandos exactos, sin lanzarlos.
      _Requisitos: 19.3_

---

## Phase 13: Polish y cierre

- [x] T046 H25: etiquetas de `NativeTabs` sin recortar con texto grande (D13),
      con test y captura en AX-L. _Requisitos: 16.3_
- [x] T047 Reconciliar con los contratos congelados de la 043 y la 045
      (T-RECONCILIAR): actualizar `contracts/app-needs.md`, el adaptador y los
      tests; si la API local existe, regenerar `openapi.json` y probar contra
      ella. _Requisitos: 1.3, 17.1_
      Nota (2026-10-22): hecho contra `specs/043-reservas/contracts/lite-api.md` y `specs/045-…/contracts/lite-api.md` congelados; tabla al final de `contracts/app-needs.md`. Esquemas comparados uno a uno con el `openapi.json` real de la 043 (export del 2026-10-22, enmiendas incluidas): coinciden. **Probado contra la API de la 043** el mismo día: su código (worktree de `consolas-web`) sobre una base propia, `nexus_app_movil_044`, migrada a 0174 y con su semilla (`dev_seed_reservas_demo.py`); la app entra con las personas de prueba y lee y escribe Reservas en los dos modos (capturas `ios26-13-api043-*`). Lo que queda: pasar el adaptador a `openapi-fetch` tipado. No cabe en esta rama sin copiar un `openapi.json` que su API no produce (`verify` lo rechaza): va cuando la 043 esté en `develop`.
- [x] T048 Gates de UI del workspace sobre cada pantalla nueva o tocada:
      `ui-states-checklist`, `a11y-audit`, `responsive-audit`, `design-tokens`;
      informe en `evidence/revision.md`; ningún 🔴. _Requisitos: 16.1–16.6_
      Nota (2026-10-22): `evidence/revision.md`. Cinco 🔴 encontrados y arreglados con test (G1–G5); los 🟡 también; quedan tres 🟢 y lo no verificado (Android, lectores de pantalla en vivo), dicho allí.
- [x] T049 Capturas en «13 26» (iOS 26) de cada pantalla de Reservas en ideal,
      vacío, carga, error y sin red, claro y oscuro, y AX-L; las mejoras; en
      `evidence/capturas/`. _Requisitos: 16.1–16.3, CE-004_
      Nota: 60 capturas en `evidence/capturas/` (índice en `evidence/hallazgos.md`). Ideal, vacío y error en simulador; carga, parcial y sin red por test (`reservas-dia.test.tsx` «the screen's states»); oscuro y AX-L en las pantallas de Reservas con más riesgo, no en todas. La primera pasada encontró diez fallos (hallazgos R1–R12), arreglados con test y con su «antes» y «después».
- [x] T050 Capturas en el Pixel 9 (Android) de lo mismo, en claro y oscuro.
      _Requisitos: 16.1–16.3, CE-004_
      **Cerrada el 2026-10-22 por decisión de Luis**: Android lo prueba él a mano en un dispositivo físico, con la lista de `evidence/hallazgos.md` §Android. No hay capturas de Android en esta spec: compilar el cliente en este Mac pedía 4–5 GB que no había. Por test: el flotante extendido y el canal `reservations_v1`.
- [x] T051 [P] `docs/app-movil.md`: Reservas, mejoras, avisos, versión y builds;
      quitar «Reservas» de «Lo que no hace en la v1». §IX
      Nota: además, la línea de la barra que no se encoge (042 H22).
- [x] T052 [P] Enlazar `specs/044-la-app-con-reservas/` desde la nota de KB.
      §IX
- [x] T053 `./scripts/verify.sh mobile` en verde y `quickstart.md` recorrido.
      §VII
      Nota (2026-10-22): **en verde**, todo: lockfile, typecheck, lint, jest (36 suites, 409 tests), generados, contrato OpenAPI y `expo-doctor` 20/20. `expo-doctor` fallaba por 11 parches del SDK 58 publicados ese día; con el visto bueno de Luis se aplicaron con `npx expo install --fix` en un commit de dependencias aparte: diez paquetes de Expo y `jest-expo`, todos parches de 58.x. Además, `@expo/metro-runtime` ~58.0.15 pasa a dependencia directa. Ya estaba en el árbol como dependencia par, pero el lockfile la dejaba en 58.0.14 y el `expo-router` nuevo pide ^58.0.15; `expo-doctor` lo marcaba (MIT, de Expo, ya presente: no entra ningún paquete nuevo). `expo install` quiso añadir los plugins de `expo-sharing` y `expo-status-bar` a `app.config.ts` y no se añadieron: no hacen falta para lo que usa la app. El `quickstart.md` se recorrió con los datos de ejemplo y contra la API de la 043.

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → las historias. US1 antes que US2, US3 y US4 (la pantalla
  donde viven sus hojas). US5–US10 dependen solo de Phase 2 y pueden ir en
  paralelo entre sí (archivos distintos). Builds (Phase 12) en cualquier momento.
- T047 en cuanto `consolas-web` mande sus contratos.
- **Al fusionar la 044 detrás de la 043**: la 044 ya no usa
  `lite.usage.balance.runway`, y `apps/console/src/i18n/__tests__/no-orphan-keys.test.ts`
  se pondrá en rojo salvo que esa fusión borre la línea de
  `apps/console/src/i18n/lanes/lite.ts` marcada «La pide la app (spec 031)» (aviso
  de `consolas-web`, 2026-10-22). Si `openapi.json` o los `*.gen.ts` chocan, se
  regeneran con `pnpm gen` en `apps/mobile` sobre lo fusionado.
- Las capturas (T049, T050) al final, sin editar código durante la tanda.
