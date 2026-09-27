# Tasks: la ficha adelgaza y sus catálogos se navegan

**Input**: Design documents from `/specs/018-ficha-ligera-y-catalogos/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: NO son opcionales (constitución §VII): cada bloque de tests se escribe primero, se ve en rojo, y solo entonces se implementa.

**Organization**: por **iteración**, y dentro de cada una por historia. US1 = Resumen · US2 = dos pestañas menos · US3 = catálogos navegables · US4 = las palabras dicen lo que son · US5 = puesta en marcha ligera.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: termina con `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: rama, YYYY-MM-DD`.
- **Test primero (§VII)**; **aislamiento (§I)** con tarea propia (T-ISO); **licencias (§VIII)**: ninguna dependencia nueva (T-LIC); **medidor**: nada nuevo, solo lectura (T-MET).
- **Cada iteración cierra igual**: prototipo aprobado → tests rojos → código → suites en verde → paridad completa → evidencia → log de sesión en la KB → merge a `develop` → staging.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

Consola en `apps/console/src/` con tests junto al código (`__tests__/`) y e2e en `apps/console/e2e/`; DS en `packages/ui/src/{components,stories}/` con tests en `packages/ui/src/components/__tests__/`; API solo `apps/api/tests/isolation/`; KB en `/Users/matos/workspace/kb/Auphere/nexus/`.

---

## Phase 1: Setup

**Purpose**: lo compartido, sin cambiar comportamiento.

- [ ] T001 Crear `specs/018-ficha-ligera-y-catalogos/parity.md` con el inventario **antes de tocar una línea**: qué enseña y qué permite hoy el Resumen (`clients/[ref]/page.tsx`), «Datos del cliente» (`settings/page.tsx`), «Ajustes» del agente (`agent/settings/`), la tarjeta de puesta en marcha, y las tres pantallas de catálogo (`capabilities/`, `integrations/`, `channels/`). Una fila por cosa, con su destino. _Requisitos: 2.4, 3.4, 6.3_
- [ ] T002 [P] Crear `specs/018-ficha-ligera-y-catalogos/evidence/README.md` con una entrada por iteración (prototipo, aprobación del owner con fecha, capturas, suites, paridad), siguiendo el precedente de la spec 017. _Requisitos: ninguno — ritual de cierre_
- [ ] T003 [P] T-LIC · Comprobar con `scripts/verify.sh locks` que `pnpm-lock.yaml` y `uv.lock` no cambian en toda la spec, y dejarlo anotado en `plan.md` §Puertas. _Requisitos: ninguno — puerta §VIII_

---

## Phase 2: Foundational

**Purpose**: lo que la iteración 1 necesita y no es una pantalla.

- [ ] T004 T-ISO · Añadir a `apps/api/tests/isolation/test_console_scope.py` el caso del Resumen compuesto: un partner que pide la ficha de un cliente de otro recibe **404 opaco**, byte a byte igual al de un cliente que no existe, y ninguna de las cuatro lecturas que el Resumen compone (ficha, consumo acotado a ese cliente, estadísticas de conversación, canales y conectores) responde distinto ni tarda distinto. _Requisitos: 12 §I del plan_
- [ ] T005 [P] T-MET · Test en `apps/api/tests/integration/` de que componer el Resumen **no escribe ningún `UsageRecord`**: se cuentan las filas antes y después de las cuatro lecturas. La pantalla lee el medidor; nunca lo alimenta. _Requisitos: ninguno — puerta del medidor_
- [ ] T006 [P] Tipos en `apps/console/src/lib/backend/`: la forma que el Resumen consume de cada una de las cuatro lecturas, sin inventar campos que la API no devuelve. `pnpm typecheck` es el criterio. _Requisitos: 1.1, 1.3, 1.4, 1.5_

---

## Iteración 1 · El Resumen contesta (US1 + US2 + US5) 🎯 MVP

**Goal**: la ficha contesta «¿cómo va este cliente?» sin abrir nada, con dos pestañas menos.

**Independent Test**: quickstart §Iteración 1, con los cuatro roles.

### Prototipo

- [ ] T007 [US1] Prototipo `packages/ui/src/stories/prototypes/client-summary.stories.tsx` (`Prototipos/Resumen del cliente`) con los estados que hay que decidir mirando: atendiendo con datos · recién creado sin actividad · una lectura caída · sin crédito · analista (sin controles de escritura) · a medio configurar (con puesta en marcha) · móvil. Revisado con el addon a11y. **Aprobación del owner antes de escribir código**, anotada en `evidence/iteracion-1.md`. _Requisitos: 1.1, 1.2, 1.6, 1.7, 6.1, 6.2_

### Tests primero

- [ ] T008 [P] [US1] Tests `apps/console/src/components/clients/summary/__tests__/summary.test.tsx`: los cuatro bloques con sus cifras y sus enlaces; sin actividad dice que no hay datos y **no** enseña ceros; una lectura caída pinta su bloque en error con reintento y los otros tres siguen; el analista no ve controles de escritura. _Requisitos: 1.1–1.7_
- [ ] T009 [P] [US2] Tests en el arnés de server actions para editar nombre y zona horaria desde el Resumen, incluido el caso que importa: **no crea ni toca el borrador del agente**. _Requisitos: 2.1, 2.4_
- [ ] T010 [P] [US2] Tests `apps/console/src/components/clients/__tests__/client-nav.test.tsx`: la ficha tiene **nueve** pestañas, «Datos del cliente» y «Ajustes» ya no están, y el punto de borrador de los ajustes del agente señala «Agente». _Requisitos: 2.2, 3.1, 3.2_

### Implementación

- [ ] T011 [US1] Implementar `apps/console/src/components/clients/summary/` (los cuatro bloques) y rehacer `app/(console)/clients/[ref]/page.tsx` para pedir las cuatro lecturas **en paralelo**, cada una con su fallo propio. _Requisitos: 1.1–1.8_
- [ ] T012 [US2] Bloque editable de nombre y zona horaria dentro del Resumen, con su server action (`can()` + test). _Requisitos: 2.1, 2.4_
- [ ] T013 [US2] `settings/page.tsx` y `agent/settings/page.tsx` pasan a `permanentRedirect`; los ajustes del agente se montan dentro de `agent/page.tsx`; `client-nav-model.ts` baja a nueve pestañas y el mapa del punto de borrador apunta a «Agente». _Requisitos: 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_
- [ ] T014 [US5] Repartir la tarjeta de puesta en marcha: «qué falta» se queda como cabecera de la ficha mientras falte algo; el crédito pasa a ser bloque del Resumen y sobrevive cuando la puesta en marcha desaparece. _Requisitos: 6.1, 6.2, 6.3_

### Cierre

- [ ] T015 [US1] E2E: `a11y.spec.ts` audita la ficha rehecha; `record.spec.ts` comprueba las nueve pestañas, las dos redirecciones y que editar el nombre **no** levanta la barra de borrador. _Requisitos: 2.2, 2.3, 3.1, 3.3_
- [ ] T016 [US1] Paridad §Iteración 1 al 100 %, `evidence/iteracion-1.md`, log de sesión en la KB, merge a `develop` y staging. _Requisitos: 2.4, 3.4, 6.3_

---

## Iteración 2 · Los catálogos se navegan (US3)

**Goal**: un patrón, tres pantallas, y encontrar algo entre veinte cuesta tres gestos.

**Independent Test**: quickstart §Iteración 2, con los tres catálogos comparados entre sí.

### Prototipo

- [ ] T017 [US3] Prototipo `packages/ui/src/stories/prototypes/catalog.stories.tsx` con los estados: lleno · buscando · filtrado · filtro sin resultados · catálogo vacío · solo lo activo · solo lectura · móvil. **Aprobación del owner**, anotada en `evidence/iteracion-2.md`. _Requisitos: 4.1–4.7_

### Tests primero

- [ ] T018 [P] [US3] Tests `packages/ui/src/components/__tests__/catalog-browser.test.tsx`: buscar reduce y el contador lo dice; la pestaña de activos enseña solo lo activo y se puede volver; filtrar sin resultados dice con qué se filtró y ofrece quitarlo, con un mensaje **distinto** del catálogo vacío; un elemento sin categoría cae en un grupo con nombre propio; el componente **no sabe** qué es una habilidad, un conector ni un canal. _Requisitos: 4.1, 4.2, 4.3, 4.5_
- [ ] T019 [P] [US3] Tests de que el estado (búsqueda, pestaña, filtro) viaja en la dirección de la página y que volver atrás restituye lo que se veía. _Requisitos: 4.4_

### Implementación

- [ ] T020 [US3] Implementar `packages/ui/src/components/catalog-browser.tsx`, extraído de lo que la pantalla de Capacidades ya hace, más las pestañas y el filtro por categoría que le faltan. Exportarlo en el índice del paquete. _Requisitos: 4.1–4.6_
- [ ] T021 [US3] `capabilities/page.tsx` pasa a usarlo, con la función como categoría; el filtro por sector de la spec 017 se conserva dentro del patrón nuevo. _Requisitos: 4.1, 4.4, 4.6_
- [ ] T022 [US3] `integrations/page.tsx` pasa a usarlo, con la categoría del conector; el orden por lo que necesita atención se conserva dentro de cada grupo. _Requisitos: 4.1, 4.6_
- [ ] T023 [US3] `channels/page.tsx` pasa a usarlo, **sin enseñar canales que todavía no se pueden conectar** (§V: la ausencia se diseña; Messenger, Instagram o Telegram no aparecen apagados ni prometidos). _Requisitos: 4.1, 4.6, 4.7_
- [ ] T024 [P] [US3] Tests de componente de las tres pantallas: los tres llaman igual a lo mismo y lo colocan en el mismo sitio. _Requisitos: 4.6_

### Cierre

- [ ] T025 [US3] E2E: `a11y.spec.ts` audita los tres catálogos con filtro puesto; un recorrido de «buscar → filtrar → compartir el enlace» en `record.spec.ts`. _Requisitos: 4.1–4.4_
- [ ] T026 [US3] Paridad §Iteración 2, `evidence/iteracion-2.md`, log de sesión, merge y staging. _Requisitos: 4.6_

---

## Iteración 3 · Las palabras dicen lo que son (US4)

**Goal**: nadie tiene que aprender el vocabulario interno de Auphere.

**Independent Test**: quickstart §Iteración 3, incluida la prueba con alguien que no conoce el producto.

### Tests primero

- [ ] T027 [P] [US4] Test de que en el diccionario de la consola no queda visible «Capacidades» ni «Integraciones» en ninguno de los dos idiomas, y de que existen «Habilidades» y «Conectores». _Requisitos: 5.1_
- [ ] T028 [P] [US4] Tests de las dos cabeceras: Conocimiento dice que lo lee el agente de **ese** cliente; Guía del partner dice que lo lee el asistente de la consola y que el agente **no** lo ve. _Requisitos: 5.2, 5.3_

### Implementación

- [ ] T029 [US4] Renombrar en el copy: «Capacidades» → **Habilidades**, «Integraciones» → **Conectores**, ES y EN, incluida la navegación de la ficha y los títulos de página. Rutas y claves internas **no** cambian (decisión 3 de la Fase 0). _Requisitos: 5.1, 5.4_
- [ ] T030 [P] [US4] Reescribir las cabeceras de `knowledge/` (cliente) y `/knowledge` (partner) para que digan quién las lee. _Requisitos: 5.2, 5.3_

### Cierre

- [ ] T031 [US4] Paridad §Iteración 3, `evidence/iteracion-3.md`, log de sesión, merge y staging. _Requisitos: 5.1–5.4_

---

## Phase Final: Polish

- [ ] T032 [P] Comprobar CE-007 de punta a punta: recorrer todas las direcciones que la consola tenía antes de esta spec y confirmar que ninguna responde «no existe». _Requisitos: CE-007_
- [ ] T033 [P] Barrido de claves de i18n huérfanas en los carriles que esta spec toca, con el precedente de la spec 017: al mover y renombrar pantallas, el copy que se queda sin dueño describe un producto que ya no existe. _Requisitos: 5.1_
- [ ] T034 Actualizar `architecture/console-map.md` en la KB: la ficha tiene nueve pestañas, el Resumen compone cuatro lecturas, y los tres catálogos comparten patrón. _Requisitos: ninguno — §IX_

---

## Dependencias

- **Phase 1 → Phase 2 → Iteración 1.** T001 (paridad) va antes que cualquier código: es el inventario de lo que no puede desaparecer.
- **Iteración 1** entrega el MVP y se puede parar ahí: el Resumen y las dos pestañas menos valen por sí solos.
- **Iteración 2** no depende de la 1: `CatalogBrowser` se puede construir en paralelo. Lo que no se puede es renombrar antes (iteración 3), o el copy se toca dos veces.
- **Iteración 3** va al final a propósito.
- Dentro de cada iteración: prototipo → tests en rojo → código → cierre.

## Paralelismo

- T002 ∥ T003 tras T001.
- T005 ∥ T006 tras T004.
- T008 ∥ T009 ∥ T010 tras T007.
- T018 ∥ T019 tras T017; T024 tras T021–T023.
- T027 ∥ T028; T030 ∥ T029.
- T032 ∥ T033 al final.

## Estrategia

**MVP = iteración 1.** Si solo se entrega eso, el partner ya contesta «¿cómo va
este cliente?» sin recorrer la ficha, y la ficha tiene dos sitios menos donde
mirar. Las otras dos iteraciones mejoran lo que ya funciona.
