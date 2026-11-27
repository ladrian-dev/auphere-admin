# Tareas: datos al día en la consola

**Entrada**: `specs/082-datos-al-dia/` (spec.md, plan.md, research.md, data-model.md, contracts/realtime-082.md, quickstart.md)

**Pruebas**: no son opcionales (constitución §VII). Cada bloque de pruebas se escribe y se ve en rojo antes de su implementación.

**Decidido sin Luis**: el orden y las decisiones (D) del plan. Luis lo revisa al final.

## Formato: `[ID] [P?] [Historia] Descripción`

- **[P]**: se puede hacer a la vez (ficheros distintos, sin depender de algo pendiente).
- Cada tarea termina con `_Requisitos: N.m_`.

---

## Fase 1: preparación

- [x] T001 Leer CLAUDE.md, `docs/spec-driven-development.md`, la constitución, la nota de KB (sección 082), `docs/consola-lite.md` (Tiempo real) y `docs/reservas.md` (auto-refresh)
  _Requisitos: todos_
- [x] T002 Escribir `plan.md`, `data-model.md`, `contracts/realtime-082.md` y `quickstart.md` en `specs/082-datos-al-dia/`
  _Requisitos: todos_
- [x] T003 Revisar las pruebas que dejó la sesión anterior (`apps/api/tests/integration/reservas/test_082_datos_al_dia.py`, `apps/console/e2e/datos-al-dia*.e2e.ts`) y verlas en rojo donde toca. Pasar los casos útiles de `datos-al-dia-probe.e2e.ts` (enlace `?booking=` y vista de lista) a `datos-al-dia.e2e.ts` y borrar la sonda (D1)
  _Requisitos: 1.1, 1.4, 3.7, 3.10_
- [x] T004 Añadir `@tanstack/react-query@^5.108.4` a `apps/console/package.json` (lockfile raíz)
  _Requisitos: 1.2, 2.2, 3.11_
- [x] T005 [P] Escribir la licencia leída y su párrafo en `docs/licenses/consola-082.md`
  _Requisitos: 1.2 (§VIII)_

## Fase 2: fundamentos (bloquean las historias)

### Pruebas primero

- [x] T006 [P] Prueba unitaria del aviso en `apps/api/tests/unit/test_082_reservations_live.py`. Debe comprobar cuatro cosas:
  - sale tras el commit, una vez por negocio y transacción, aunque haya varios `add_event`;
  - no sale si la transacción se deshace;
  - lo de un *savepoint* deshecho no sale, pero un `add_event` posterior en la misma transacción sí;
  - el cuerpo es solo `{"event","at"}`.

  _Requisitos: 1.4, 1.5, 1.6_
- [x] T007 [P] Barrido en `apps/api/tests/unit/test_082_add_event_sweep.py`: ningún `ReservationEvent(` se construye en `apps/` fuera de `core.add_event`. El aviso alcanza a todo lo que deja historial
  _Requisitos: 1.4_
- [x] T008 [P] Prueba de aislamiento (garantía 1) en `apps/api/tests/isolation/test_082_reservations_changed_scope.py`. Cubre:
  - la línea de una persona de A solo reenvía `reservations.changed` de A;
  - con `reservas` y sin `inbox`, no reenvía `message.new`;
  - con `inbox` y sin `reservas`, no reenvía `reservations.changed`;
  - sin ninguno de los dos, 403;
  - una cancelación real en A solo publica en `inbox:{A}`.

  _Requisitos: 1.11, 1.4, 1.6_
- [x] T009 [P] Proveedor de pruebas `apps/console/src/test/query.tsx` (un `QueryClient` por prueba, sin reintentos)
  _Requisitos: 1.2_

### Implementación

- [x] T010 `RESERVATIONS_EVENT` y `publish_reservations_changed` en `apps/api/src/nexus_api/services/inbox_stream.py`, más `mark_changed` en `apps/api/src/nexus_api/services/reservations/live.py`. Se registra con `business.writes.after_commit` y se deduplica al publicar
  _Requisitos: 1.4, 1.5, 1.6_
- [x] T011 `core.add_event` llama a `mark_changed(session, res.tenant_id)` en `apps/api/src/nexus_api/services/reservations/core.py`
  _Requisitos: 1.4_
- [x] T012 La línea admite `inbox` o `reservas` y filtra por módulo en `apps/api/src/nexus_api/api/console/lite/inbox_stream.py`. Ajustar `tests/unit/test_lite_inbox_media_and_stream.py` a un principal con módulos
  _Requisitos: 1.11, 3.11_
- [x] T013 BFF: `inbox` o `reservas`, y `export const maxDuration = 300`, en `apps/console/src/app/api/lite/inbox/stream/route.ts`, con su prueba en `apps/console/src/app/api/lite/inbox/stream/__tests__/route.test.ts` (403 sin módulos, 200 con solo `reservas` y `maxDuration === 300`)
  _Requisitos: 1.11, 3.12_
- [x] T014 `lib/query.ts` en `apps/console/src/lib/query.ts`: `makeQueryClient`, `keys`, `ActionError`, `unwrap`. Más `QueryProvider` en `apps/console/src/components/query-provider.tsx`, montado en `apps/console/src/components/shell/console-frame.tsx` alrededor de los dos marcos
  _Requisitos: 1.2, 1.9, 2.2_
- [x] T015 `LiveStreamProvider` en `apps/console/src/components/live/live-stream.tsx`. Hace esto:
  - un `EventSource` por pestaña;
  - invalida `["reservas"]` (300 ms) y `["inbox","counts"]` (400 ms);
  - al volver tras un corte, invalida `["reservas"]` e `["inbox"]` y emite `back`.

  Montado en `console-frame.tsx` para personas de cliente con `inbox` o `reservas`. Prueba en `apps/console/src/components/live/__tests__/live-stream.test.tsx`
  _Requisitos: 1.7, 3.7, 3.10, 3.11_

## Fase 3: Historia 1, la agenda dice lo que hay (P1)

**Objetivo**: la agenda y la ficha leen de una sola fuente que se invalida tras cada escritura y con cada aviso.
**Prueba independiente**: `e2e/datos-al-dia.e2e.ts` › Reservas (cancelar, aviso del agente, enlace y lista).

- [x] T016 [P] [US1] Prueba en `apps/console/src/components/reservas/__tests__/live-data.test.tsx`:
  - tras una escritura, la agenda relee por la acción;
  - un `reservations.changed` relee la agenda;
  - una ráfaga es una sola relectura;
  - la ficha con «No vino» en curso tiene sus botones ocupados y un segundo clic no manda otra orden.

  _Requisitos: 1.1, 1.2, 1.3, 1.7_
- [x] T017 [US1] Sacar la lectura de la página a `apps/console/src/app/(console)/reservas/read.ts` (`server-only`) y añadir `reservasScreenAction` en `apps/console/src/app/(console)/reservas/actions.ts`. `page.tsx` usa `readReservas`
  _Requisitos: 1.1, 1.2_
- [x] T018 [US1] `reservas-view.tsx` con `useQuery(["reservas","screen",urlKey])`:
  - `initialData`, y adopta una lectura del servidor más nueva;
  - 45 s visibles; «puede no estar al día» a los 150 s;
  - `useLastGood` sobre los datos;
  - `ctx.refresh` invalida `["reservas"]`.

  Ajustar `__tests__/auto-refresh.test.tsx` y `__tests__/harness.tsx`
  _Requisitos: 1.1, 1.7, 1.8, 1.9, 1.10_
- [x] T019 [US1] `booking-detail.tsx` con `useQuery(["reservas","booking",id])` y botones ocupados con candado por referencia mientras se guarda
  _Requisitos: 1.2, 1.3_
- [x] T020 [US1] Prueba de navegador: añadir a `e2e/datos-al-dia.e2e.ts` los casos de enlace y lista, y verlo en verde
  _Requisitos: 1.1, 1.4, 1.7_

## Fase 4: Historia 2, el conocimiento del agente se ve al añadirlo (P1)

**Objetivo**: la lista y «Qué sabe» leen la misma consulta, que se relee al añadir y mientras se lee.
**Prueba independiente**: `apps/console/src/components/builder/__tests__/agent-knowledge-live.test.tsx`.

- [x] T021 [P] [US2] Prueba en `agent-knowledge-live.test.tsx`:
  - añadir un archivo relee la lista y llama a `onChanged`;
  - «Qué sabe» cuenta solo las vivas, sin las quitadas;
  - con una fuente en `pending` relee cada 5 s y para a los 10 min;
  - una subida que no responde en 120 s (o una web en 60 s) dice «No respondió a tiempo» y relee.

  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5_
- [x] T022 [US2] `use-agent-knowledge.ts` en `apps/console/src/components/builder/`: `useQuery(["agent",ref,id,"knowledge"])` con sondeo de 5 s mientras hay `pending`, que para a los 10 min
  _Requisitos: 2.1, 2.4_
- [x] T023 [US2] `agent-knowledge.tsx`:
  - lee de la consulta, con carga y error;
  - `onChanged` en añadir, quitar, restaurar y enseñar (D2);
  - plazos de 120 s y 60 s;
  - claves i18n `builder.knowledge.timeout` y `builder.knowledge.loading` en `src/i18n/messages.ts`.

  _Requisitos: 2.1, 2.3, 2.5_
- [x] T024 [US2] `agent-builder.tsx`: `sources` sale de la misma consulta y cuenta las vivas; `onChanged={refreshAll}`. Ajustar `__tests__/agent-builder.test.tsx` y `__tests__/agent-knowledge.test.tsx` al proveedor
  _Requisitos: 2.2, 2.3_

## Fase 5: Historia 3, la Bandeja avisa (P1)

**Objetivo**: sonido, contador y título al día en cualquier pantalla, y relectura al reconectar.
**Prueba independiente**: `e2e/datos-al-dia.e2e.ts` › Bandeja, y las pruebas unitarias de abajo.

- [x] T025 [P] [US3] Pruebas en `apps/console/src/components/live/__tests__/inbox-alerts.test.tsx`:
  - suena con un entrante;
  - no suena con un saliente, ni con la conversación abierta y la pestaña visible;
  - una ráfaga suena una vez cada 3 s;
  - apagado no suena;
  - el título lleva «(N) » y «99+».

  _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.6_
- [x] T026 [P] [US3] Pruebas puras en `apps/console/src/components/live/__tests__/chime-title.test.ts`:
  - `withCount(title, n)` quita y pone el prefijo;
  - el sonido no lanza sin gesto previo (política de reproducción) y suena tras el primero.

  _Requisitos: 3.5, 3.6_
- [x] T027 [P] [US3] Prueba del contador en `apps/console/src/components/shell/__tests__/app-sidebar-lite.test.tsx`:
  - el número llega por la consulta;
  - con la barra plegada se ve en la esquina del icono, con su nombre para lectores de pantalla;
  - el color es primario, no ámbar.

  _Requisitos: 3.7, 3.8, 3.9, 3.13_
- [x] T028 [P] [US3] Prueba de reconexión en `apps/console/src/components/inbox/__tests__/inbox-view.test.tsx`: tras `error` y `ready`, la Bandeja relee la lista y la conversación abierta. Ajustar `view-harness.tsx` al proveedor y a la línea compartida
  _Requisitos: 3.10, 3.11_
- [x] T029 [US3] `chime.ts` y `title-count.ts` en `apps/console/src/components/live/`
  _Requisitos: 3.3, 3.5, 3.6_
- [x] T030 [US3] `inbox-alerts.tsx` en `apps/console/src/components/live/` (sonido y título), montado por `console-frame.tsx` solo con `inbox`
  _Requisitos: 3.1, 3.2, 3.3, 3.6_
- [x] T031 [US3] `use-inbox-unread.ts` con `useQuery(["inbox","counts"])`, que sondea 60 s solo con la línea caída, y `app-sidebar.tsx` con el número en la esquina al plegar
  _Requisitos: 3.7, 3.8, 3.9, 3.13_
- [x] T032 [US3] `use-inbox-stream.ts` sobre la línea compartida con `onBack`, más `inbox-view.tsx`, que relee la lista y la conversación al volver
  _Requisitos: 3.10, 3.11_
- [x] T033 [US3] Interruptor del sonido en `apps/console/src/components/inbox/inbox-settings.tsx`, con las claves `inbox.settings.sound.*`
  _Requisitos: 3.4_

## Fase 6: Historia 4, el resumen del agente no miente (P2)

- [x] T034 [P] [US4] Prueba en `apps/api/tests/integration/test_082_inbox_detail.py`:
  - escalado y luego resuelto, sin resumen;
  - escalado anterior a `context_from`, sin resumen;
  - un nuevo escalado trae el suyo;
  - `contact.username` sale en el detalle.

  _Requisitos: 4.1, 4.2, 4.3, 5.4_
  > Etapa 4: los tres casos del resumen, en rojo y luego en verde. Etapa 4b: el caso `contact.username`, en rojo (`KeyError`) y luego en verde.
- [x] T035 [US4] Regla del resumen en `apps/api/src/nexus_api/services/inbox_view.py` (sin modelo)
  _Requisitos: 4.1, 4.2, 4.3, 4.4_

## Fase 7: Historia 5, cada contacto se reconoce (P2)

- [x] T036 [P] [US5] Prueba en `apps/api/tests/integration/test_082_customer_name.py`:
  - un perfil nuevo actualiza el nombre;
  - `name_by: "person"` no se pisa;
  - un contacto creado desde Reservas con nombre queda `name_by: "person"`;
  - el agente no marca.

  _Requisitos: 5.5_
- [x] T037 [P] [US5] Prueba en `apps/console/src/components/inbox/__tests__/contact-avatar.test.tsx`:
  - el mismo id da el mismo color;
  - sin letras, icono;
  - los seis pares pasan 4,5:1 en claro y oscuro desde `tokens.css`, sin ámbar ni rojo.

  _Requisitos: 5.1, 5.2, 5.3_
- [x] T038 [US5] `contact_username` en `inbox_view.detail` y `ContactDetailOut.username` en `apps/api/src/nexus_api/api/console/lite/inbox.py`. Más `username` en el tipo de la consola (`src/lib/backend/inbox.ts`), y `@usuario` en `contact-panel.tsx` y `thread-header.tsx`
  _Requisitos: 5.4_
- [x] T039 [US5] `upsert_customer(profile_name=…)` en `apps/worker/src/nexus_worker/persistence/messages.py`, más el despachador pasando `profile_name` (`runtime/dispatcher.py`, una línea) y `contact_customer(by_person)` en `core.py`
  _Requisitos: 5.5_
- [x] T040 [US5] `contact-avatar.tsx` con color por contacto e icono sin letras
  _Requisitos: 5.1, 5.2, 5.3_

## Fase 8: cierre

- [x] T041 Puertas de interfaz sobre lo tocado, con hallazgos y arreglos en este fichero (Notas):
  - los cinco estados (carga, vacío, error, parcial e ideal);
  - a11y: foco ≥ 2 px, objetivos ≥ 24 px, lector de pantalla del contador;
  - 360 px y 200 %;
  - tokens sin hex.

  _Requisitos: CE-006, CE-007_
- [x] T042 Actualizar `docs/consola-lite.md` (Tiempo real: Reservas en la línea, línea compartida, sonido, título, resumen, avatar) y `docs/reservas.md` (la pantalla se pone al día sola)
  _Requisitos: 1.4, 1.7, 3.11_
- [x] T043 Pruebas de lo tocado con base propia, `./scripts/verify.sh lint` y `./scripts/verify.sh js` completo (lockfile único)
  _Requisitos: todos_
- [x] T044 Prueba de navegador `pnpm exec playwright test -c e2e/datos-al-dia.config.ts` en verde
  _Requisitos: CE-001, CE-002, CE-004, CE-005_
- [x] T045 Guion de commits en `.claude/commits/2026-11-26-082.sh`
  _Requisitos: —_

## Dependencias

- La fase 1 va antes que todo.
- La fase 2 (T010 a T015) bloquea las historias 1 y 3. La historia 2 solo depende de T014.
- Las historias 4 y 5 son independientes de las demás (backend e interfaz de la Bandeja).
- El cierre va al final.

## A la vez

- T006, T007, T008 y T009.
- T016, T021, T025, T026, T027, T034, T036 y T037: pruebas en ficheros distintos.

## Estrategia

MVP = fases 1 a 3 (la agenda al día con el aviso). Después la historia 3 (la Bandeja avisa), la 2, y las dos P2.

## Notas

### `/speckit-analyze` (2026-11-26, antes de implementar)

- **Cobertura:** 33 de 33 criterios tienen tarea; 45 tareas, todas con `_Requisitos_`.
- **Constitution Check:** sin hallazgos críticos.
- **F1 (alto, resuelto):** el caso límite «Pestaña oculta: no suena» contradecía 3.2. Se corrigió la spec a favor de 3.2: con la pestaña oculta sí suena. Queda en Clarificaciones.
- **C1 (medio, resuelto):** 3.12 (`maxDuration`) no tenía prueba. T013 la añade.
- **C2 (bajo, aceptado):** 4.4 («sin modelo») se cumple por construcción: la regla es una comparación de fechas en `inbox_view`, sin cliente de modelo importado.

Con esto el análisis queda en verde para `/speckit-implement`.

### Parada por etapas (2026-11-26)

- **Verde:** solo las tareas marcadas `[x]`.
- **A medias:**
  - T017: falta `reservasScreenAction`; `read.ts` y `page.tsx` están hechos.
  - T033: el código está hecho; falta su prueba.
- **Sin correr:** `verify.sh js` tras añadir la dependencia.
- **Cómo seguir:** `HANDOFF.md`, en la raíz del worktree.

### Etapa 4 (2026-11-27)

- **En verde:** T016–T024, T033 y T035 (34 de 45). T034 a medias: falta su caso `contact.username`, que va con T038.
- **Pruebas:**
  - consola, vitest: Reservas 218, constructor 619, ajustes de la Bandeja 12;
  - API: `test_082_inbox_detail.py` + `test_lite_inbox_contact.py` y lo que rodea el resumen, 18;
  - navegador `datos-al-dia.config.ts`: 6 de 6;
  - `tsc` y eslint de la consola, limpios.
- **Prueba primero:** T016, T021 y T034 se vieron en rojo. La acción de T017 se escribió antes que su prueba. La prueba de T033 llegó tras el código (de la sesión anterior): se comprobó que falla con el guardado roto.
- **Ajuste por la regla 4.1:** `tests/unit/test_lite_inbox_contact.py` afirmaba que el resumen seguía tras resolver; ahora afirma que no.
- **`verify.sh js` (primera pasada):** dos rojos.
  - Un `any` implícito en `live-stream.test.tsx`: arreglado.
  - El panel sin `@nexus/ucm-*`: es del entorno. `verify.sh` no pasa por `pretypecheck`, y en el worktree no estaban construidos. Al relanzarlo, verde.
- **Segunda pasada, tras T035:** `verify.sh lint` y `verify.sh js` todo verde. En `js`, la consola da 2624 y el panel 861.
- **Queda para la etapa 4b:** T034 (`username`), T036–T045. Detalle en `HANDOFF.md`.

### Etapa 4b (2026-11-27)

- **T034 y T036–T040, en rojo y luego en verde.**
  - API: `test_082_inbox_detail.py` (el caso `contact.username`, `KeyError` antes) y `test_082_customer_name.py` (6: cinco en rojo antes; la del agente ya pasaba, porque el agente no marca hoy tampoco).
  - Consola: `contact-avatar.test.tsx` (de 2 a 19; sin `AVATAR_TONES` ni `contactTone` no compilaba) y `contact-username.test.tsx` (4; tres en rojo).
- **Por el camino (CE-006):** el círculo de cada mensaje del contacto pintaba «·» sobre `accent-soft`. Ahora es `ContactAvatar` con el id de la conversación: `thread.tsx` y `message-bubble.tsx` toman `contactId` (opcional) e `inbox-view.tsx` lo pasa. Prueba en `contact-avatar.test.tsx`, vista en rojo.
- **T041, las cuatro puertas.**
  - *Cinco estados:* el avatar tiene ideal (iniciales), vacío (sin letras: icono), error (la foto que no carga: iniciales) y carga (la foto `lazy`, con el tono de fondo y el tamaño fijo, sin salto). `@usuario` sin dato no pinta nada (§V). Reservas y Conocimiento ya traían carga, error con reintento y parcial («puede no estar al día»), de la etapa 4.
  - *a11y:* axe sin hallazgos graves en la Bandeja abierta (lista, cabecera, hilo y hoja del contacto) y en Reservas, en claro y en oscuro (`e2e/datos-al-dia.e2e.ts`, «Puertas de interfaz»). El contraste del avatar se mide sobre el color calculado (de `lab()` a sRGB con un lienzo), en los dos temas: todos ≥ 4,5:1. Los estados de carga y error del Conocimiento pasan axe (`agent-knowledge-live.test.tsx`). El contador plegado de la barra es `aria-hidden` y el lector lee el número de la insignia, que sigue en el árbol al plegar (`opacity-0`). Nada nuevo es interactivo: sin foco ni objetivos nuevos.
  - *Hallazgo previo, arreglado (CE-007):* en oscuro, la marca «ahora» de la rejilla de Reservas pintaba hueso sobre rojo claro (2,17:1), y axe lo daba como grave. `time-grid.tsx` pasa a `bg-status-danger text-anti-flash` (5,45:1 en los dos temas). Fichero fuera de la propiedad declarada.
  - *Responsive:* 360, 414, 640 (1280 × 900 al 200 %), 1024, 1440 y 1920 px, más el texto un 30 % más largo a 360 px, sin desbordes; la hoja del contacto cabe a 640 px. **Hallazgo previo, sin arreglar:** la Bandeja a 768 px se sale (sin `@usuario` también, mismo `right=854`): la barra lateral abierta y la lista fija de 320 px dejan ~190 px al hilo. Es de maquetación de la Bandeja en tableta, no de esta spec; la prueba lo excluye con un comentario.
  - *Tokens:* sin hex, `rgb()`, `oklch()` en línea, `style={{}}`, valores arbitrarios ni paleta por defecto en lo que añade la 082. 🟡 aceptado: los seis tonos del avatar usan nombres de marca (`pistachio`, `basil`…), como `series-*`, porque son una paleta categórica; la prueba comprueba que cada clase es la de sus tokens.
  - *Otro hallazgo previo, sin arreglar:* la hora de cada mensaje se formatea con la zona del servidor y la del navegador, y no coinciden (aviso de hidratación en `message-bubble.tsx` con el navegador en otra zona). No es de la 082.
- **T042:** `docs/consola-lite.md` (el resumen que desaparece tras Resolver; «La misma línea lleva Reservas»; «La Bandeja avisa en cualquier pantalla»; «Cada contacto se reconoce») y `docs/reservas.md` («La pantalla se pone al día sola», con React Query, el aviso y la ficha ocupada). Van en el mismo commit que su cambio (guion, T045).
- **T043, con base propia (`nexus_test_082`, Redis 12):**
  - API, lo tocado y lo que lo rodea (las pruebas de la 082, `tests/integration/reservas/` entera, las de aislamiento de Reservas y de la consola lite, identidad BSUID, coexistencia, las del despachador de la 076, la Bandeja lite en unidad e integración): **2441 passed** en 6 min.
  - Worker, lo que importa el despachador o `persistence.messages` (con `lupa`): **94 passed**.
  - Consola, vitest de las carpetas tocadas: **1112 passed** (95 ficheros).
  - `./scripts/verify.sh lint`: los 15 pasos en verde. `./scripts/verify.sh js`: los 18 en verde (consola 2645, panel 861, `@nexus/ui` 332, companion-ui 189, desktop 949 y los dos `next build`).
- **T044:** `pnpm exec playwright test -c e2e/datos-al-dia.config.ts`, **10 de 10** (las 6 de la etapa 4 y las 4 de T041). El aviso de hidratación de la hora de los mensajes sale en el registro y no es de la 082 (ver T041).
- **T045:** `.claude/commits/2026-11-26-082.sh`. Entra en el worktree, comprueba la rama y el índice vacío, y hace ocho commits (spec; aviso de Reservas; línea y Bandeja; Reservas; marca «ahora»; Conocimiento; resumen y avatar; prueba de navegador). Cubre los 89 ficheros cambiados; deja fuera, y lo comprueba al final, `HANDOFF.md`, `tsconfig.tsbuildinfo`, `next-env.d.ts` y cualquier `uv.lock`. Sin push.
- **Con `develop` (`ecc06f88`):** solo coincide `docs/reservas.md`, en otra sección. Ni la navegación ni `/usage`.
- **45 de 45.**

