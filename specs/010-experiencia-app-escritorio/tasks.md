---
description: "Plan de ejecución — spec 010, la experiencia de la aplicación de escritorio"
---

# Tasks: la experiencia de la aplicación de escritorio

**Input**: `/specs/010-experiencia-app-escritorio/` · **Rama**: `010-experiencia-app-escritorio`

**Prerequisites**: [plan.md](./plan.md) · [spec.md](./spec.md) · [research.md](./research.md) · [data-model.md](./data-model.md) · [contracts/](./contracts) · [quickstart.md](./quickstart.md)

**Tests**: no son opcionales (constitución §VII). Cada criterio de aceptación
nace como test, se ve en rojo, y solo entonces se implementa.

**Organization**: por historia, para que cada una se pueda entregar y probar
sola. Cada tarea cita sus requisitos.

## Reglas de este plan

- **Nada de «lo ajustamos luego»**: toda tarea que rompa un test existente lo
  **dice en su descripción**, con el nombre del fichero. Esta spec cambia a
  propósito comportamiento que hoy está fijado por test.
- **Documentos vivos en el mismo commit** que el cambio que describen.
- **`./scripts/verify.sh` entero antes de fusionar.** Lo que se olvida no son las
  pruebas de la API: son el worker, el tipado estricto, el paquete compartido y
  la compilación de la consola.
- El `git commit` lo ejecuta la persona; las tareas nunca commitean.

---

## Phase 1: Setup (infraestructura compartida)

- [X] T001 Instalar dependencias de producción nuevas en `apps/desktop/package.json` y `packages/ui/package.json`: `@fontsource-variable/inter-tight`, `@fontsource-variable/jetbrains-mono`, `react-resizable-panels`, `@tanstack/react-virtual`, `electron-context-menu`; y `use-stick-to-bottom` en `packages/companion-ui/package.json` — _Requisitos: 2.1_
- [X] T002 Leer el `LICENSE` de cada paquete instalado y dejar el párrafo citado en `apps/desktop/THIRD-PARTY-LICENSES.md`, verificando que ninguna es AGPL (§VIII) — _Requisitos: 2.1_
- [X] T003 [P] Añadir `@playwright/test` (fijado a **1.62.1**, la misma versión que la consola) en `apps/desktop/package.json` con el guion `test:smoke`. **`@axe-core/playwright` se aplaza a T132**, que es donde se usa: añadirlo ahora subió el par compartido `playwright-core` a 1.63 en el lockfile único del monorepo y dejó en rojo el typecheck de la consola — _Requisitos: 11.9_
- [X] T004 [P] Crear `apps/desktop/vitest.config.ts` que **excluya** `tests/smoke/**` y `tests/a11y/**` del `include` por defecto: sin eso, un fichero de Playwright dentro de `tests/` hace rojo `pnpm --filter @nexus/desktop test`, que es el paso que corre la tubería — _Requisitos: 11.9_
- [X] T005 [P] Crear `apps/desktop/eslint.config.js` extendiendo las reglas de `@nexus/ui` (sin color suelto, sin valor fuera de escala), **añadir el guion `lint` al paquete** y **añadir el paso de escritorio a `scripts/verify.sh`** (hoy no existe ninguno de los tres) — _Requisitos: 2.2_
- [X] T006 [P] Servir las fuentes empaquetadas desde `apps/desktop/src/app/styles.css` y declarar la política de contenido de la vista de la aplicación en `apps/desktop/src/app/index.html`, con `font-src 'self'` y sin orígenes remotos — _Requisitos: 2.1_
- [X] T007 Test en `apps/desktop/tests/app-csp.test.ts`: la vista de la aplicación declara política de contenido y no referencia ningún origen remoto de estilos, fuentes ni iconos — _Requisitos: 2.1_
- [X] T008 [P] Banco de humo del binario en `apps/desktop/tests/smoke/launch.spec.ts` (Playwright + Electron): abre, la ventana pinta, cero violaciones de política en consola — _Requisitos: 2.7, 3.1_

---

## Phase 2: Foundational (prerequisitos que bloquean todo)

**⚠️ CRITICAL**: ninguna historia empieza hasta que esta fase esté completa.

### Contratos y aislamiento

- [X] T009 Fijar la lista canónica de secciones en `apps/desktop/src/app-ipc.ts` con **las diez** entradas que la consola ya declara en `apps/console/src/components/shell/nav.ts` (inicio, clientes, conocimiento, puesto, consumo, auditoría, notificaciones, equipo, claves, facturación) y sus permisos — _Requisitos: 1.2, 1.3_
- [X] T010 Test en `apps/desktop/tests/nav-parity.test.ts` (vive en escritorio, no en la consola: `apps/console` no es dependencia de este paquete y no debe serlo — la aplicación sigue a la consola, así que lee su fichero de navegación): coinciden entrada por entrada y con el mismo permiso; si la consola añade una sección y la aplicación no, falla — _Requisitos: 1.2_
- [X] T011 Enmendar `apps/desktop/src/app-ipc.ts` con los canales de [`contracts/desktop-app-ipc-v2.md`](./contracts/desktop-app-ipc-v2.md): invocaciones `app:shell.showSection`, `app:shell.contentBounds`, `app:shell.prefs`, `app:signIn.start`, `app:signIn.cancel`, `app:workstation.state`, `app:workstation.pair`, `app:workstation.unpair`, `app:workstation.pickDirectory`, `app:setup.status`, `app:update.install`, `app:handoff.done`; empujes `app:console.location`, `app:workstation`, `app:signIn`, `app:update`, `app:waiting`, `app:connectivity` — _Requisitos: 1.3, 3.6, 7.1, 8.2_
- [X] T012 Ampliar la validación de entrada en `apps/desktop/src/app-ipc.ts`: sección contra la lista canónica cerrada, rectángulo como cuatro enteros ≥0, código de emparejamiento contra el alfabeto `ABCDEFGHJKMNPQRSTVWXYZ23456789` de 8 símbolos; valor desconocido lanza antes de tocar la red — _Requisitos: 1.3, 8.2_
- [X] T013 Actualizar `apps/desktop/tests/app-ipc.test.ts`: el `preload` expone una función por canal y ninguna genérica, y la validación rechaza sección inventada, rectángulo negativo y código mal formado — _Requisitos: 1.3, 8.2_
- [X] T014 Actualizar `apps/desktop/tests/no-credentials-over-ipc.test.ts` con cuerpos envenenados en los canales nuevos (estado del puesto, puesta en marcha, traspaso): ninguna clave de sesión, cookie, token ni credencial sale a ninguna profundidad — _Requisitos: 1.3_
- [ ] T015 ⏳ **Se ejecuta junto a T139** (la retirada de la barra), no antes: el test no puede pasar mientras la vista siga existiendo, y un rojo largo no es test primero, es un test roto. **Cambia `apps/desktop/tests/session-isolation.test.ts`**: retirar el bloque `describe` de la partición del puesto y pasar el recuento de cuatro a **tres**, **conservando explícitamente** las dos aserciones de que la vista de la consola sigue **sin `preload`** y que el arranque aborta si dos particiones se igualan — _Requisitos: 8.1_
- [ ] T016 ⏳ **Se ejecuta junto a T139**, por lo mismo. **Cambia `apps/desktop/tests/no-own-auth.test.ts`**: trasladar a la vista de la aplicación la prohibición **de R8.7**, que es *formulario de credenciales* —sin `type="password"`, sin ruta de inicio de sesión propia, sin canje de credenciales en el renderer—, manteniendo la prohibición léxica **solo** para el `preload`. La pantalla sí dirá «tu sesión terminó» y «entrar», y eso es correcto — _Requisitos: 8.7, 3.4, 7.1_
- [X] T017 [P] Escribir las enmiendas en los contratos de origen: nota en `specs/002-identidad-app-escritorio/contracts/desktop-bar.md` y en `specs/003-teammates-app-escritorio/contracts/desktop-app-ipc.md` apuntando a los contratos de esta spec — _Requisitos: 8.1_

### Módulos puros (test primero)

- [X] T018 [P] Test en `apps/desktop/tests/shell-layout.test.ts`: el rectángulo del panel nunca invade la franja superior, se acota al tamaño de la ventana, y la lista lateral se colapsa por debajo del ancho umbral — _Requisitos: 1.1, 1.4_
- [X] T019 [P] Implementar `apps/desktop/src/electron/shell-layout.ts` (puro) — _Requisitos: 1.1, 1.4_
- [X] T020 [P] Test en `apps/desktop/tests/waiting.test.ts`: el derivado de «lo que te espera» produce **una sola** cifra, con su presentación (tope visual) como decoración, y baja al decidir — _Requisitos: 5.4_
- [X] T021 [P] Implementar `apps/desktop/src/waiting.ts` — _Requisitos: 5.4_
- [X] T022 Conectar el derivado como única fuente en las cuatro superficies y retirar los tres recuentos actuales de `apps/desktop/src/app/App.tsx`, `src/tray-badge.ts` y `src/notifications-policy.ts`. **Cambia `apps/desktop/tests/tray-badge.test.ts` y `tests/notifications-policy.test.ts`**, que hoy fijan tres reglas distintas de recuento — _Requisitos: 5.4_
- [X] T023 Renombrar `apps/desktop/src/bar-state.ts` a `workstation-state.ts` conservando sus ocho estados y transiciones, trasladar `tests/bar-state.test.ts` y `tests/bar-update-state.test.ts` sin perder ningún caso, y **corregir la cabecera del módulo, que dice «siete estados» y tiene ocho** desde la spec 008 — _Requisitos: 3.6, 8.1_
- [X] T024 Test en `apps/desktop/tests/workstation-state.test.ts` para lo nuevo: estado `comprobando` antes del primer veredicto, `since` en todos los estados, `cause` con `sin_red`, `sin_ejecutor`, `sesion_perdida`, y `required_version` en `version_no_admitida` (que vive **solo** aquí, no en el estado de actualización) — _Requisitos: 3.6, 3.7, 6.4_
- [X] T025 Implementar `comprobando`, `since`, `cause` y `required_version` en `apps/desktop/src/workstation-state.ts` — _Requisitos: 3.6, 3.7, 6.4_
- [X] T026 [P] Test en `apps/desktop/tests/feedback.test.ts`: la función que elige mecanismo cumple la tabla de [`contracts/feedback-taxonomia.md`](./contracts/feedback-taxonomia.md), incluida la regla de que ningún error va en aviso efímero y de que con foco no se emite aviso del sistema — _Requisitos: 5.1, 5.2, 5.5_
- [X] T027 [P] Implementar la API de avisos en `apps/desktop/src/app/feedback/notify.ts` y el `Toaster` sin `next-themes` en `packages/ui/src/components/sonner.tsx`, importando la hoja de estilos del paquete en vez de depender de su inyección — _Requisitos: 5.1, 5.2_
- [X] T028 [P] Test en `apps/desktop/tests/connectivity.test.ts`: `offline` y `unconfirmed` son estados distintos, y `unconfirmed` **conserva** el último veredicto de sesión — _Requisitos: 3.1, 3.2_
- [X] T029 [P] Implementar `apps/desktop/src/connectivity.ts` y usarlo en `apps/desktop/src/session-gate.ts`, sustituyendo la conversión actual de excepción en «nadie ha iniciado sesión» — _Requisitos: 3.2_
- [X] T030 Añadir `section` y `sidebarWidth` a la lista cerrada de claves persistibles en `apps/desktop/src/shell-state.ts` y a `apps/desktop/tests/shell-credentials.test.ts`: sin esto, la última sección no sobrevive al reinicio y T053 no puede cumplirse — _Requisitos: 1.10_

### Sistema visual compartido

- [X] T031 Test en `packages/ui/src/components/__tests__/contrast.test.ts`: recorre los pares de `data-model.md` §4 en ambos temas y **falla** por debajo de 4,5:1 (texto) y 3:1 (no textual y foco) — _Requisitos: 2.4_
- [X] T032 Reescribir el modo oscuro de `packages/ui/src/styles/tokens.css` a superficies de tinta neutra cálida con el verde como acento, y añadir el token de foco con ≥3:1 en ambos temas — _Requisitos: 2.3, 2.4, 2.5_
- [X] T033 Añadir la capa de densidad de escritorio en `packages/ui/src/styles/tokens.css` (texto de interfaz 13 px, fila de lista 28 px y 32 con avatar, control 28 px, objetivo mínimo 24 px, radios concéntricos) — _Requisitos: 2.2_
- [X] T034 Retirar de `apps/desktop/src` y `packages/companion-ui/src` las sobrescrituras del anillo de foco y las opacidades de texto por debajo del umbral, y revisar que ningún estado normal de trabajo se pinte con el color de peligro (hoy lo usan el medidor agotado y el turno fallido) — _Requisitos: 2.5, 2.4, 2.9_
- [X] T035 [P] Revisar consola y panel de operador contra los tokens nuevos: `./scripts/verify.sh js` en verde y una pasada visual de sus pantallas principales — _Requisitos: 2.3_

**Checkpoint**: contratos, módulos puros y sistema visual listos.

---

## Phase 3: US1 — Una sola aplicación, con armazón de escritorio (P1)

**Goal**: que la ventana sea una aplicación y no tres superficies.
**Independent test**: recorrer operar y administrar sin menú de cambio de superficie, con la lista lateral marcando siempre dónde se está.

- [X] T036 [P] [US1] Test en `apps/desktop/tests/shell-chrome.test.tsx`: la franja superior existe, es la única con región de arrastre, reserva el hueco de los controles del sistema y sus controles internos son no arrastrables — _Requisitos: 1.1_
- [X] T037 [US1] Crear la ventana con barra de título oculta, posición explícita de los controles del sistema y color de fondo del tema en `apps/desktop/src/electron/main.ts`, mostrándola solo cuando la vista del armazón está lista — _Requisitos: 1.1, 2.7_
- [X] T038 [US1] Montar el armazón en `apps/desktop/src/app/shell/` (franja, lista lateral redimensionable, panel) y reportar el rectángulo del panel por `app:shell.contentBounds` — _Requisitos: 1.1, 1.2_
- [X] T039 [US1] Lista lateral con las diez secciones de administrar **filtradas por el permiso de la persona**, más operar y el pie de identidad, plan y máquina — _Requisitos: 1.2, 9.2_
- [X] T040 [P] [US1] Test en `apps/desktop/tests/shell-sections.test.tsx`: elegir una sección pide mostrarla, la lista lateral la marca, el empuje de ruta desde el principal actualiza la marca, y una sección sin permiso **no se ofrece** — _Requisitos: 1.3, 1.4, 9.2_
- [X] T041 [US1] Colocar la vista de la consola en el rectángulo del panel y observar su navegación en `apps/desktop/src/electron/main.ts`, empujando `app:console.location` acotado a la lista canónica — _Requisitos: 1.3, 1.4_
- [X] T042 [US1] Retirar el menú «Ver → Equipo/Consola», sus atajos y la recarga de la consola al volver: mostrar sin recargar — _Requisitos: 1.5, 1.6_
- [X] T043 [P] [US1] Modo embebido en `apps/console/src/app/(console)/layout.tsx` según [`contracts/console-modo-embebido.md`](./contracts/console-modo-embebido.md): sin barra lateral, sin cabecera, sin menú de usuario, sin sus tarjetas de puesta en marcha. **Cambia `apps/console/src/lib/__tests__/shell-detect.test.ts`**, que hoy fija que `@/lib/shell` se importa **exactamente una vez** — _Requisitos: 1.3_
- [X] T044 [P] [US1] Ampliar la detección en `apps/console/src/lib/shell.ts` y `lib/shell-ua.ts` con su test: con la marca de la cáscara, modo embebido; sin ella, armazón completo — _Requisitos: 1.3_
- [X] T045 [P] [US1] Test en `apps/desktop/tests/theme.test.ts`: hay **una sola** fuente de tema, el cambio alcanza a la vista de la consola y la preferencia sobrevive al reinicio — _Requisitos: 2.3_
- [X] T046 [US1] Implementar el tema en `apps/desktop/src/electron/main.ts` y `src/shell-state.ts`: preferencia de la cáscara aplicada con el mecanismo del sistema, que arrastra a la consola embebida, con «Sistema» por defecto (transversal T-5 de la evaluación) — _Requisitos: 2.3_
- [X] T047 [US1] Menú de aplicación completo en `apps/desktop/src/electron/main.ts` según [`contracts/shell-armazon.md`](./contracts/shell-armazon.md), con Ajustes, Buscar actualizaciones, Ir, zoom, mostrar/ocultar lista lateral y Ayuda, todo en el idioma de la cuenta — _Requisitos: 1.7, 1.9, 12.2_
- [X] T048 [P] [US1] Test en `apps/desktop/tests/shortcuts.test.ts`: los atajos estándar del sistema no se reutilizan y cada acción del armazón tiene orden de menú — _Requisitos: 1.7, 1.9_
- [X] T049 [US1] Búsqueda de acciones y objetos (⌘K) en `apps/desktop/src/app/shell/palette.tsx`, sobre el primitivo que ya usa `@nexus/ui`, mostrando el atajo de cada acción — _Requisitos: 1.8_
- [X] T050 [P] [US1] Test en `apps/desktop/tests/navigation.test.ts`: la ruta canónica gobierna lista lateral, historial e inicio, y la última sección se restaura al reabrir — _Requisitos: 1.6, 1.10_
- [X] T051 [US1] Historial atrás/adelante y ruta canónica interna en `apps/desktop/src/app/shell/navigation.ts` — _Requisitos: 1.6, 1.10_
- [X] T052 [P] [US1] Iconografía y densidad: sustituir el «+» de texto y los avatares improvisados por iconos de la librería a 16/20 px en `apps/desktop/src/app/routes/`, y acompañar de texto o forma todo estado que hoy se comunica solo con color — _Requisitos: 2.8, 2.6_
- [ ] T053 ⏳ **Se ejecuta con T072-T073** (US3), que es cuando los avisos se montan de verdad: comprobar «con avisos encendidos» sin avisos encendidos no comprueba nada. El humo ya vigila que no haya **ninguna** violación de la política, así que el día que se enciendan, si bloquea, se verá. Verificar en el humo que con avisos encendidos **no hay violación** de la política de contenido; si la hubiera, sustituir por el primitivo de aviso de la librería de primitivas — _Requisitos: 5.1_
- [X] T054 [US1] Humo del binario: la franja arrastra la ventana con la consola en el panel, y pulsar dentro de la consola no la mueve (el caso que el spike validó) — _Requisitos: 1.1_

**Checkpoint**: la ventana ya es una aplicación. **MVP.**

---

## Phase 4: US2 — La pantalla no miente (P2)

- [X] T055 [P] [US2] Test en `apps/desktop/tests/bootstrap-offline.test.ts`: sin red, la puesta en marcha **no aborta** y la ventana queda en «sin conexión» con reintento — _Requisitos: 3.1_
- [X] T056 [US2] Desacoplar la carga de la consola del arranque en `apps/desktop/src/electron/main.ts`: veredicto de sesión, vigilante de pendientes y latido arrancan en paralelo y un fallo de red no tumba nada — _Requisitos: 3.1_
- [X] T057 [US2] Banner de conectividad en el armazón con reintento manual y recuperación automática, conservando el borrador del hilo — _Requisitos: 3.1, 3.3_
- [X] T058 [P] [US2] Test en `apps/desktop/tests/session-expired.test.tsx`: la sesión caducada se dice **en la pantalla actual**, conserva el borrador y ofrece entrar; no salta a la consola sin avisar — _Requisitos: 3.4_
- [X] T059 [US2] Implementar ese estado en `apps/desktop/src/app/App.tsx` y retirar el salto automático a la consola de `apps/desktop/src/electron/main.ts` — _Requisitos: 3.4_
- [X] T060 [P] [US2] Test en `apps/desktop/tests/thread-open-error.test.tsx`: si abrir el hilo falla, se pinta error con motivo y reintento, **nunca** «vacío» — _Requisitos: 4.2_
- [X] T061 [US2] Implementar la rama de error en `apps/desktop/src/app/routes/thread.tsx` y distinguir «vacío de verdad» de «no se pudo leer» — _Requisitos: 4.2_
- [X] T062 [P] [US2] Test de los estados del turno en `apps/desktop/tests/turn-states.test.tsx`: enviando, esperando, razonando, herramienta, esperando decisión, terminado, detenido, fallido; detener siempre visible; el indicador de espera no aparece en respuestas inmediatas y dice qué se está haciendo — _Requisitos: 4.3, 4.4, 4.8_
- [X] T063 [US2] Implementar en `apps/desktop/src/app/routes/thread.tsx` y `packages/companion-ui/src/components/` lo que falte de esos estados: botón de detener siempre visible mientras trabaja y texto del indicador de espera — _Requisitos: 4.3, 4.4, 4.8_
- [X] T064 [US2] Conservar el texto al fallar el envío en `apps/desktop/src/app/routes/thread.tsx` (hoy se vacía antes de saber el resultado) — _Requisitos: 4.5_
- [X] T065 [P] [US2] Test en `apps/desktop/tests/window-lifecycle.test.ts`: cerrar la ventana **oculta**, el icono de la barra y los avisos siguen vivos, y salir advierte si hay trabajo vivo — _Requisitos: 3.5_
- [X] T066 [US2] Implementar cierre = ocultar, reapertura desde icono y Dock, y orden explícita de salir en `apps/desktop/src/electron/main.ts` — _Requisitos: 3.5_
- [X] T067 [US2] Estado del puesto en el pie de la lista lateral y en Hoy, con estado, desde cuándo, causa y acción, alimentado por `app:workstation` — _Requisitos: 3.6, 3.7, 8.1_
- [X] T068 [P] [US2] Test de estados por pantalla, parte 1 — Hoy, lista lateral, Pendientes y Cuenta, contra la tabla de `data-model.md` §5 — _Requisitos: 4.1, 4.9_
- [X] T069 [P] [US2] Test de estados por pantalla, parte 2 — hilo, entorno, notas de cambio, ajustes del teammate y secciones de administrar — _Requisitos: 4.1, 4.9_
- [X] T070 [US2] Implementar los estados que esos dos tests dejen en rojo, pantalla por pantalla — _Requisitos: 4.1, 4.9_
- [X] T071 [P] [US2] Estados de «parcial» y «bloqueado»: el alcance acotado se dice en la respuesta y un teammate esperando a otro no se pinta como ocioso — _Requisitos: 4.6, 4.7_

---

## Phase 5: US3 — Avisos que se entienden y un solo número (P3)

- [ ] T072 [US3] Cablear la API de avisos, parte 1 — Pendientes y hilo: decidir, enviar, política local y entorno dejan de fallar en silencio — _Requisitos: 5.2, 5.3_
- [ ] T073 [US3] Cablear la API de avisos, parte 2 — Cuenta, formulario de teammate, ajustes, puesta en marcha y salidas al navegador — _Requisitos: 5.2, 5.3_
- [ ] T074 [P] [US3] Test en `apps/desktop/tests/no-silent-failures.test.tsx`: toda acción termina en resultado visible o fallo explicado (los siete silencios documentados) — _Requisitos: 5.3_
- [ ] T075 [P] [US3] Test en `apps/desktop/tests/waiting-surfaces.test.ts`: las cuatro superficies muestran la misma cifra y bajan a la vez al decidir — _Requisitos: 5.4_
- [ ] T076 [US3] Avisos del sistema con motivo y sin contenido sensible en `apps/desktop/src/electron/adapters.ts`, agrupados por teammate y en el idioma de la cuenta (hoy el resumen está solo en español) — _Requisitos: 5.6, 12.2_
- [ ] T077 [US3] Al pulsar un aviso, traer la ventana al frente sobre el objeto que lo produjo en `apps/desktop/src/electron/main.ts` (hoy no restaura la ventana) — _Requisitos: 5.6, 10.4_
- [ ] T078 [P] [US3] Test en `apps/desktop/tests/notifications-focus.test.ts`: con la ventana enfocada no se emiten avisos del sistema de lo ya visible — _Requisitos: 5.5_
- [ ] T079 [US3] Pantalla de preferencia de avisos en Cuenta, conectada al canal que ya existe, dejando claro que no silencia lo que espera decisión — _Requisitos: 5.8_
- [ ] T080 [P] [US3] Test en `apps/desktop/tests/updater-wiring.test.ts`: la versión descargada **emite** estado y llega al armazón; con trabajo vivo no instala y lo dice; y la aplicación no se reinicia por su cuenta en ningún otro caso — _Requisitos: 6.1, 6.3, 6.6_
- [ ] T081 [US3] Cablear `apps/desktop/src/electron/updater.ts` con el runtime y el armazón — _Requisitos: 6.1, 6.3, 6.6_
- [ ] T082 [US3] Acción de instalar («volver al mismo sitio») e ítem de menú «Buscar actualizaciones» con la versión instalada, con test — _Requisitos: 6.2, 6.5_
- [ ] T083 [US3] Versión no admitida: nombrar la versión mínima y llevar la acción a una página útil, no al directorio crudo del canal, con test — _Requisitos: 6.4_
- [ ] T084 [P] [US3] Revisión de anuncios a tecnologías de apoyo: una región educada y una urgente por vista, sin dobles anuncios (hoy el puesto anuncia dos veces y el composer duplica) — _Requisitos: 5.7_

---

## Phase 6: US4 — De instalar a la primera respuesta (P4)

**Depende de US1.** Cierra `009-T029`.

- [ ] T085 [P] [US4] Test en `apps/desktop/tests/sign-in-entry.test.tsx`: sin sesión, la aplicación ofrece entrar desde su propia pantalla, incluida la entrada con proveedor externo — _Requisitos: 7.1_
- [ ] T086 [US4] Pantalla de entrada en `apps/desktop/src/app/routes/sign-in.tsx` que dispara `app:signIn.start` (el flujo por navegador ya existe y hoy **no tiene quien lo llame**) — _Requisitos: 7.1, 7.2_
- [ ] T087 [US4] Estado de espera con «Abrir de nuevo», «Copiar enlace» y «Cancelar», alimentado por `app:signIn` — _Requisitos: 7.2_
- [ ] T088 [US4] Traer la ventana al frente al volver del navegador y continuar donde estaba, en `apps/desktop/src/electron/main.ts` — _Requisitos: 7.3_
- [ ] T089 [P] [US4] Test en `apps/desktop/tests/sign-in-outcomes.test.ts`: cancelado, caducado y error tienen mensaje y reintento; nunca espera en silencio — _Requisitos: 7.4_
- [ ] T090 [US4] Sustituir la página de vuelta del navegador por una con marca y bilingüe en `apps/desktop/src/loopback-login.ts` — _Requisitos: 7.3, 12.2_
- [ ] T091 [P] [US4] Test en `apps/desktop/tests/no-partner.test.tsx`: sin pertenencia a partner hay dos salidas (invitación y entrar con otra cuenta) y **ningún bucle** — _Requisitos: 7.5_
- [ ] T092 [US4] Implementar esa pantalla y coordinar con la consola para que no devuelva al mismo punto de partida — _Requisitos: 7.5_
- [ ] T093 [P] [US4] Test en `apps/desktop/tests/setup-checklist.test.tsx`: la lista de puesta en marcha deriva de lo que ya existe, no bloquea, y cada paso lleva a su acción o dice por qué está bloqueado — _Requisitos: 7.6, 7.7_
- [ ] T094 [US4] Implementar `apps/desktop/src/setup-checklist.ts` y la sección «Puesta en marcha» — _Requisitos: 7.6, 7.7_
- [ ] T095 [US4] Diálogo de emparejamiento en la aplicación: pedir el código y teclearlo sin salir, con el recorrido **entero visible** y alcanzable con teclado (sustituye a la hoja que no cabía) — _Requisitos: 8.2, 11.1_
- [ ] T096 [P] [US4] Test en `apps/desktop/tests/pairing-flow.test.tsx`: al completar, todas las superficies lo reflejan sin recargar; código inválido y demasiados intentos tienen mensaje propio — _Requisitos: 8.3_
- [ ] T097 [US4] Implementar la propagación del emparejamiento a todas las superficies sin recarga — _Requisitos: 8.3_
- [ ] T098 [P] [US4] Test en `apps/desktop/tests/directories.test.tsx`: declarar directorio dice el motivo cuando no vale (hoy se pierde) — _Requisitos: 8.4_
- [ ] T099 [US4] Declarar directorios desde la aplicación, con su motivo de rechazo — _Requisitos: 8.4_
- [ ] T100 [US4] Desemparejar con diálogo propio que explique qué deja de funcionar, retirando la confirmación nativa, con test — _Requisitos: 8.5_
- [ ] T101 [P] [US4] Unificar el guion de puesta en marcha en las tres superficies, retirar de la consola embebida el «Instala la aplicación de escritorio», con test de que ningún texto pide algo ya hecho — _Requisitos: 8.6_
- [ ] T102 [US4] Permisos del sistema pedidos al usarlos por primera vez, con su porqué, con test — _Requisitos: 7.8_
- [ ] T103 [US4] Permiso denegado: decir qué deja de funcionar y cómo concederlo, con enlace a Ajustes del sistema, con test — _Requisitos: 7.10_
- [ ] T104 [US4] Primera pantalla con sesión: «Hoy» con lo siguiente que tiene sentido hacer, nunca vacía, con test — _Requisitos: 7.9_
- [ ] T105 [US4] Recorrido cronometrado de CE-001 documentado en `specs/010-experiencia-app-escritorio/evidence/` — _Requisitos: 7.1, 7.9_

---

## Phase 7: US5 — Todo tope lleva a la acción (P5)

**Depende de US1.**

- [ ] T106 [P] [US5] Test en `apps/desktop/tests/gating.test.tsx`: sin plan, plan lleno, consumo agotado, cobro degradado y versión no admitida **terminan en acción o en el rol** — _Requisitos: 9.1, 9.2_
- [ ] T107 [US5] Decir el tope de plan **antes** del formulario de teammate y retirar el control de ejecución local cuando el plan no lo incluye — _Requisitos: 9.3, 4.9_
- [ ] T108 [US5] Acciones con destino exacto a las secciones de administrar, respetando el permiso de la persona — _Requisitos: 9.1, 9.2_
- [ ] T109 [P] [US5] Test en `apps/desktop/tests/handoff.test.ts`: al salir al navegador la ventana lo dice y espera; al volver, plan y consumo se releen sin reiniciar — _Requisitos: 9.4, 9.5_
- [ ] T110 [US5] Implementar el traspaso en `apps/desktop/src/handoff-state.ts` y detectar la salida a proveedor de pago en `apps/desktop/src/window-open-policy.ts`. **Cambia `apps/desktop/tests/window-open.test.ts`**, que hoy fija exactamente dos salidas — _Requisitos: 9.4_
- [ ] T111 [US5] Releer plan y consumo al recuperar el foco (`app:handoff.done`) y devolver a la persona a lo que estaba haciendo — _Requisitos: 9.5_
- [ ] T112 [P] [US5] Cuenta enseña plan, estado del cobro, saldo y reinicio, con proporción y **sin cifra absoluta del pool**; y «Cerrar sesión» deja de mentir. **Cambia `apps/desktop/tests/account-usage.test.tsx`**, que hoy fija que «cerrar sesión» abre la consola — _Requisitos: 9.6_
- [ ] T113 [P] [US5] Aviso de consumo cercano **al 80 %**, el umbral que el producto ya usa, con la fecha de reinicio — _Requisitos: 9.7_
- [ ] T114 [US5] Una sola explicación de la pausa por consumo: retirar la duplicidad entre el banner del hilo y el composer — _Requisitos: 9.8_
- [ ] T115 [P] [US5] Test en `apps/desktop/tests/resume-after-pause.test.tsx`: resuelta la causa, lo pausado se reanuda sin empezar de nuevo — _Requisitos: 9.11_
- [ ] T116 [US5] Implementar la reanudación apoyándose en la tarea durable que ya existe — _Requisitos: 9.11_
- [ ] T117 [P] [US5] Estados de cobro degradado anunciados **antes** de que se noten en el trabajo, con test — _Requisitos: 9.9_

---

## Phase 8: US6 — Decidir sabiendo qué se decide (P6)

- [ ] T118 [P] [US6] Test en `apps/desktop/tests/inbox-context.test.tsx`: cada pendiente muestra qué se hará, cliente y máquina, desde cuándo y si se deshace, sin abrir nada — _Requisitos: 10.1_
- [ ] T119 [US6] Implementarlo en `apps/desktop/src/app/routes/inbox.tsx` reutilizando las tarjetas del paquete compartido — _Requisitos: 10.1_
- [ ] T120 [P] [US6] Test en `apps/desktop/tests/decide-keyboard.test.tsx`: aprobar, aprobar siempre (donde aplique) y rechazar con teclado — _Requisitos: 10.2_
- [ ] T121 [US6] Implementar el teclado en las tarjetas de `packages/companion-ui/src/components/` — _Requisitos: 10.2_
- [ ] T122 [US6] Protección anti-pulsación al aparecer la tarjeta. **Cambia `packages/companion-ui/tests/confirm-card.test.tsx`**, que hoy tabula y pulsa Enter nada más renderizar: decidir en esa tarea si la guarda aplica también al teclado o solo al ratón, y dejarlo escrito — _Requisitos: 10.3_
- [ ] T123 [P] [US6] Test en `apps/desktop/tests/notification-focus-target.test.tsx`: al llegar desde un aviso, la tarjeta está a la vista y con el foco — _Requisitos: 10.4_
- [ ] T124 [US6] Implementar el desplazamiento y el foco a la tarjeta que produjo el aviso — _Requisitos: 10.4_
- [ ] T125 [P] [US6] Decir el fallo al decidir y permitir reintentar, con test — _Requisitos: 10.5_
- [ ] T126 [P] [US6] Sin permiso para decidir: a quién pedírselo, con el hilo accesible igualmente, con test — _Requisitos: 10.6_
- [ ] T127 [US6] Mostrar la atribución de la decisión (quién decidió) donde la persona pueda verla después, con test — _Requisitos: 10.7_

---

## Phase 9: Polish & Cross-Cutting

- [ ] T128 [P] Test de teclado en `apps/desktop/tests/keyboard.test.tsx`: toda acción alcanzable, incluido el puesto; salto entre zonas del armazón; foco al encabezado al cambiar de sección; nombres únicos de región (hoy hay tres con el mismo nombre) — _Requisitos: 11.1, 11.2, 11.3, 11.4_
- [ ] T129 Implementar lo que ese test deje en rojo: orden de tabulación, F6 y ⇧F6, foco al encabezado, nombres de región — _Requisitos: 11.1, 11.2, 11.3, 11.4_
- [ ] T130 [P] Grupos de opciones excluyentes como tales (la política local son hoy tres interruptores) y objetivos ≥24 px, con test — _Requisitos: 11.5, 11.6_
- [ ] T131 [P] Movimiento y transparencia reducidos, y zoom del contenido al 200 % con las órdenes de menú, con test — _Requisitos: 11.7, 11.8_
- [ ] T132 `pnpm test:a11y` sobre cada pantalla: cero incidencias graves o críticas — _Requisitos: 11.9_
- [ ] T133 [P] Glosario único en `apps/desktop/src/app/i18n.ts` y `packages/companion-ui/src/messages.ts`: interlocutor por contexto, «pool semanal» en vez de «tope mensual», sin identificadores crudos. **Cambia `packages/companion-ui/tests/ola2-ui.test.tsx`**, que busca la etiqueta «Mensaje al Companion» — _Requisitos: 12.1, 12.3_
- [ ] T134 [P] Idioma de la cuenta en el proceso principal: menús, títulos y mensajes de los diálogos nativos, avisos y la página de vuelta del navegador — _Requisitos: 12.2_
- [ ] T135 [P] Test de guardas de producto en `apps/desktop/tests/product-guards.test.tsx`: ninguna vista pide ni muestra datos de tarjeta, ninguna superficie transcribe texto de cliente final, y cantidades, fechas y proporciones se formatean con el idioma de la cuenta — _Requisitos: 9.10, 12.4, 12.5_
- [ ] T136 [P] Texto largo: prueba con cadenas alemanas en nombre de cliente, teammate y comando; sin desbordes ni cortes que impidan decidir — _Requisitos: 2.2, 10.1_
- [ ] T137 Actualizar los documentos vivos **en este mismo commit**: `docs/desktop-workstation.md` (desaparece la barra; tres particiones), `docs/desktop-teammates.md` (armazón y canales nuevos), `docs/bugs-app-escritorio-2026-09-15.md` (cerrar los fallos que esta spec resuelve) — _Requisitos: 8.1, 1.3_
- [ ] T138 Actualizar los recorridos de evidencia de la spec 003 en `apps/desktop/src/electron/main.ts`: cambian navegación y etiquetas, y uno ya está roto hoy (busca un elemento que Cuenta dejó de pintar) — _Requisitos: 1.2, 9.6_
- [ ] T139 Retirar la barra por completo: `src/bar/`, la entrada de `preload` de `vite.preload.config.ts`, el guion `copy-bar-assets.mjs` del `build`, `barWebPreferences` y su partición en `session-isolation.ts`, y el `BAR_HEIGHT` del `layout()` de `main.ts`. **Cambia `apps/desktop/tests/bar-tokens.test.ts`**, que hoy afirma que `src/bar/` existe: se convierte en el test de tokens del armazón — _Requisitos: 8.1, 2.2_
- [ ] T140 Humo del binario **empaquetado y firmado** siguiendo `quickstart.md`, más la comprobación del recorrido de emparejamiento en una máquina en estado conectada (condición 3 de la evaluación, que quedó abierta) — _Requisitos: 8.2, 8.3_
- [ ] T141 `./scripts/verify.sh` entero en verde y los cuatro gates de interfaz del workspace (estados, accesibilidad, responsive, tokens) — _Requisitos: 11.9, 2.2_

---

## Dependencies

```
Setup (T001-T008)
   └─> Foundational (T009-T035)   ← bloquea todo
          ├─> US1 armazón (T036-T054)          ← MVP
          │      ├─> US4 primer arranque (T085-T105)
          │      └─> US5 llevar a la acción (T106-T117)
          ├─> US2 estados honestos (T055-T071)
          ├─> US3 avisos y contador (T072-T084)
          └─> US6 pendientes (T118-T127)
                 └─> Polish (T128-T141)
```

- **US2, US3 y US6 son independientes entre sí** y pueden ir en paralelo tras la fase 2.
- **US4 y US5 dependen de US1**: su valor es llegar y actuar dentro del armazón.
- Dentro de la fase 2, T009 y T010 (la lista canónica) van **antes** que T011 y T012: la lista es entrada de la validación.
- T053 (avisos bajo política de contenido) depende de que el armazón exista (T038).
- **T015, T016 y T139 se ejecutan juntas**, después de T067: la barra no se puede retirar hasta que el estado de la máquina viva en el armazón, y sus tests no pueden cambiarse antes que el código.

## Parallel opportunities

- Fase 1: T003-T006 en paralelo.
- Fase 2: los pares test/implementación (T018-T019, T020-T021, T026-T027, T028-T029) son independientes entre sí; los tokens (T031-T035) van aparte.
- US1: T043 y T044 (consola) en paralelo con T036-T042 (cáscara).
- Polish: T128, T130, T131, T133-T136 en paralelo; T137-T141 al final y en orden.

## MVP

**US1 completa** (fases 1 y 2 + T036-T054): la ventana deja de ser tres
superficies pegadas y pasa a ser una aplicación con armazón de escritorio, una
navegación y un sistema visual coherente.

**Siguiente incremento recomendado**: US4, porque es el que desbloquea el
autoservicio (hoy entrar con proveedor externo no tiene disparador y emparejar
depende de algo que no se ve).
