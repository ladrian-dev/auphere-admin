# Tasks: el alta deja de pesar

**Input**: documentos de diseño de `/specs/019-alta-deja-pesar/`

**Prerequisites**: spec.md, plan.md, research.md

**Tests**: NO son opcionales (constitución §VII): cada bloque se escribe
primero, se ve en rojo, y solo entonces se implementa.

**Organization**: por **iteración**, y dentro de cada una por historia.
H1 = crear cabe en una pantalla · H2 = la plantilla se elige · H3 = el Companion
redacta · H4 = publicar se decide con la plantilla.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: termina con `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: rama, YYYY-MM-DD`.
- **Test primero (§VII)**; **aislamiento (§I)** con tarea propia (T-ISO);
  **licencias (§VIII)**: ninguna dependencia nueva (T-LIC); **medidor**: lo que
  gaste se mide (T-MET).
- **Cada iteración cierra igual**: prototipo aprobado → tests rojos → código →
  suites en verde → paridad completa → evidencia → log de sesión en la KB →
  merge a `develop` → staging.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

Consola en `apps/console/src/` con tests junto al código (`__tests__/`) y e2e en
`apps/console/e2e/`; DS en `packages/ui/src/{components,stories}/`; API solo
`apps/api/tests/isolation/`; KB en `/Users/matos/workspace/kb/Auphere/nexus/`.

---

## Phase 1: Setup

- [ ] T001 Crear `specs/019-alta-deja-pesar/parity.md` con el inventario **antes de tocar una línea**: qué pide, qué enseña y qué permite hoy el alta (`clients/new/wizard.tsx`, `wizard-state.ts`, `actions.ts`), una fila por cosa y su destino. Incluye las once opcionales de `aesthetic_clinic_v1` y los doce imprescindibles, con su número. _Requisitos: 1.2, 1.3_
- [ ] T002 [P] Crear `specs/019-alta-deja-pesar/evidence/README.md` con una entrada por iteración, siguiendo el precedente de las specs 017 y 018. _Requisitos: ninguno — ritual de cierre_
- [ ] T003 [P] T-LIC · `scripts/verify.sh locks`: `pnpm-lock.yaml` y `uv.lock` no cambian en toda la spec. Se corre al abrir y al cerrar cada iteración. _Requisitos: ninguno — puerta §VIII_

---

## Phase 2: Foundational

- [ ] T004 T-ISO · Test en `apps/api/tests/isolation/` de que **ninguna ruta que el alta usa acepta un `tenant_id` del llamante**, y de que la creación queda dentro del partner autenticado. No es una ruta nueva, pero esta spec la reordena y la barrida deja constancia de que sigue siendo así. _Requisitos: ninguno — puerta §I_
- [ ] T005 T-ISO · Test de que **el camino que el Companion usa para proponer no puede escribir**: recorrer el catálogo desde el ángulo de esta spec y afirmar que ninguna herramienta alcanzable crea, publica o activa un cliente. Es la capa 2, y R5.4 la declara intacta: sin este test la declaración es una intención. _Requisitos: 5.4_
- [ ] T006 [P] T-MET · Comprobar que la propuesta del Companion **pasa por el medidor que ya existe**: pedirla consume modelo, y el partner tiene que verlo en su consumo como cualquier otra conversación con el Companion. Si no lo hiciera, sería gasto invisible. _Requisitos: ninguno — puerta del medidor_
- [ ] T007 [P] Función pura `requiredPlaceholders(template)` en `wizard-state.ts`: qué campos exige una plantilla, **derivado de la plantilla** y no de una lista escrita a mano. El dato **ya viaja** en `SeedTemplate.placeholders[].required` y el asistente ya lo usa para validar: lo que hace falta es **dejar de pintar los opcionales**, no pedir información nueva. La función lo expone y se prueba contra los trece casos medidos en la Fase 0. _Requisitos: 1.1, 1.2_

---

## Iteración 1 · El alta cabe en tres pasos (H1 + H2 + H4) 🎯 MVP

**Goal**: crear un cliente pasa de 23 campos a 4, y la plantilla se elige a
conciencia.

**Independent Test**: un partner crea una barbería de principio a fin sin ver
un solo campo de medicina estética.

### Prototipo

- [X] T008 [US1] Prototipo `packages/ui/src/stories/prototypes/new-client.stories.tsx` con los estados que hay que decidir mirando: elegir plantilla (vacío, buscando, sin resultados) · el negocio con dos campos · el negocio con doce (`aesthetic_clinic_v1`) · confirmar · ejecutando · una etapa fallida · cupo lleno · móvil. **Aprobación del owner antes de escribir código**, anotada en `evidence/iteracion-1.md`. _Requisitos: 1.1–1.6, 2.1–2.5, 4.1–4.4_ Entregado: rama 019, 2026-09-28 — **aprobado por el owner el 2026-09-28** tras siete rondas. Las siete cambiaron la spec, no solo la pantalla, y quedan en `evidence/iteracion-1.md`.

### Tests primero

- [ ] T009 [P] [US2] Tests de `requiredPlaceholders` contra las trece plantillas: diez piden dos, tres no piden ninguno, `aesthetic_clinic_v1` pide doce. **Los números son los de la Fase 0** y el test falla si una semilla cambia sin que nadie lo note. _Requisitos: 1.1, 1.2_
- [ ] T010 [P] [US2] Tests del selector de plantilla: nada preseleccionado, no se puede continuar sin elegir, buscar reduce y dice cuántas quedan, y «sin plantilla» existe como opción nombrada que dice qué implica. _Requisitos: 2.1–2.4_
- [ ] T011 [P] [US1] Tests del alta: **tres pasos**, ninguno de canal, y el paso del negocio enseña exactamente los campos que la plantilla exige — ni uno opcional. _Requisitos: 1.2, 1.3, 3.1, 3.3_
- [ ] T012 [P] [US1] Tests de la referencia: se deriva del nombre, vive plegada, y un duplicado se dice **antes** de intentar crear proponiendo una libre. _Requisitos: 4.1–4.3_
- [ ] T013 [P] [US1] Test de que **el alta no pregunta si publicar**: el agente nace en borrador y la ficha lo pide. Se queda como guardia para que la pregunta no vuelva sin decisión escrita. _Requisitos: 6.4_
- [ ] T013c [P] [US1] Tests del crédito: un cliente nace con **cero**, su fila de cupo **sí se crea** —la ausencia de fila es el silencio del 31-ago— y el alta dice dónde se asigna. _Requisitos: 8.1–8.3 · CE-008_
- [ ] T013d [P] Test de que ninguna cadena visible del alta mezcla idiomas, incluidos los nombres de plantilla que vienen de la semilla. Un nombre de marca no cuenta. _Requisitos: 9.1–9.3 · CE-009_

### Implementación

- [ ] T013b [P] [US1] Tests del horario: se elige con controles de hora, **no hay campo «Sábados» aparte**, y el detalle por día se abre solo si se pide. _Requisitos: 7.1–7.3_
- [ ] T014 [US2] `template-picker.tsx`: catálogo buscable, nada marcado, «sin plantilla» nombrada, y qué trae cada una (para qué sirve y cuántas habilidades enciende). _Requisitos: 2.1–2.5_
- [ ] T014b [US1] El control de horario y el campo de dirección, con la salida en el formato que la plantilla espera (`tenant.business_hours_label`). _Requisitos: 7.1–7.4_
- [ ] T015 [US1] Rehacer `wizard.tsx` a tres pasos y `wizard-state.ts` en consecuencia: fuera `ChannelChoice` y su etapa, dentro `requiredPlaceholders`. _Requisitos: 1.1–1.6, 3.1–3.3_
- [ ] T016 [US1] La referencia, derivada y plegada, con la comprobación de duplicado antes de crear. _Requisitos: 4.1–4.4_
- [ ] T017 [US1] La ejecución por etapas con su reintento por etapa, que ya existe y se conserva. Sin etapa de publicar. _Requisitos: 6.1–6.4_
- [ ] T017b Crédito inicial a **cero**: `partner_default_client_allocation_tokens` pasa de 50 000 a 0. La fila se sigue sembrando. _Requisitos: 8.1, 8.2_
- [ ] T017c Nombres de plantilla sin inglés en la semilla («wellness» → «bienestar», «medspa» → «con cirugía») y en la KB. _Requisitos: 9.1, 9.2_
- [ ] T017d Icono por rubro en las trece plantillas. _Requisitos: 10.1, 10.2_

### Cierre

- [ ] T018 [US1] E2E: `a11y.spec.ts` audita los tres pasos en ES y EN; `record.spec.ts` crea un cliente de punta a punta sin rellenar campos opcionales y comprueba que la ficha lo recibe. _Requisitos: 1.1, 1.2, 3.2 · CE-002, CE-003_
- [ ] T019 [US1] Paridad §Iteración 1 al 100 %, `evidence/iteracion-1.md`, log de sesión en la KB, merge a `develop` y staging. **Incluye recorrer `quickstart.md` §Iteración 1**, con las tres plantillas que da el número (barbería 4 campos · cobranza 2 · clínica estética 14) y **CE-004 con alguien ajeno al producto**, anotando qué dijo en voz alta. _Requisitos: 1.3, 2.5 · CE-001, CE-004_

---

## Iteración 2 · Lo que el alta dejó de pedir, se pide en su sitio (H1, cola)

**Goal**: los campos que salieron del alta no se pierden — los pide la ficha.

**Independent Test**: un cliente creado sin datos del negocio enseña un paso
nuevo que los pide, y el paso desaparece al completarlo.

### Tests primero

- [ ] T020 [P] [US1] Tests del paso «Datos del negocio» en `client-setup.tsx`: aparece **solo mientras falte algo**, su barra dice cuántos van, y desaparece entero al completarse — como los otros tres. La tarjeta no crece para siempre. _Requisitos: 1.5_
- [ ] T021 [P] [US1] Test de que el paso cuenta **los campos de la plantilla del cliente**, no una lista fija, y de que un cliente sin plantilla no lo ve. _Requisitos: 1.5_

### Implementación

- [ ] T022 [US1] El paso nuevo en la tarjeta, con su enlace a donde se rellenan. _Requisitos: 1.5_
- [ ] T023 [US1] La pantalla donde se rellenan, reutilizando los campos que el alta dejó de enseñar: mismos nombres, misma validación, en su sitio nuevo. Es paridad, no rehacerlo. _Requisitos: 1.4, 1.5_

### Cierre

- [ ] T024 [US1] Paridad §Iteración 2, evidencia, log de sesión, merge y staging, recorriendo `quickstart.md` §Iteración 2. _Requisitos: 1.4_

---

## Iteración 3 · El Companion redacta el borrador (H3)

**Goal**: el partner describe el negocio en una frase y llega a confirmar con
los campos propuestos.

**Independent Test**: con el Companion apagado el alta se recorre igual; con él
encendido, ningún campo llega en blanco y se distingue quién escribió cada uno.

### Prototipo

- [ ] T025 [US3] Prototipo de la caja: vacía · pensando · con propuesta (y **lo propuesto marcado**) · propuesta descartada · Companion caído · Companion no disponible (la caja **no está**). **Aprobación del owner.** _Requisitos: 5.1–5.5_

### Tests primero

- [ ] T026 [P] [US3] Tests de que lo propuesto se distingue de lo escrito, y de que se puede cambiar o descartar uno a uno y todo a la vez. **Si no se distingue, está roto** (R5.2). _Requisitos: 5.2, 5.3_
- [ ] T027 [P] [US3] Tests de la ausencia: sin Companion disponible la caja **no se pinta** —ni apagada ni explicada— y el alta se completa igual (§V). _Requisitos: 5.5_
- [ ] T028 [P] [US3] Test de que no se envía al Companion nada que el partner no haya escrito o elegido en esta pantalla. _Requisitos: 5.6_

### Implementación

- [ ] T029 [US3] `business-brief.tsx`: la caja, la petición de propuesta y la aplicación al formulario marcando cada valor. _Requisitos: 5.1–5.3_
- [ ] T030 [US3] El camino de la propuesta, leyendo `console.list_templates`. **Ninguna herramienta de escritura**, y T005 lo vigila. _Requisitos: 5.1, 5.4_

### Cierre

- [ ] T031 [US3] E2E: el recorrido con propuesta, y el recorrido sin Companion. _Requisitos: 5.1, 5.5 · CE-005, CE-006_
- [ ] T032 [US3] Paridad §Iteración 3, evidencia, log de sesión, merge y staging. _Requisitos: 5.1–5.6_

---

## Phase Final: Polish

- [ ] T033 [P] Barrido de claves de i18n huérfanas: el paso del canal se lleva las suyas, y los campos que se mueven a la ficha cambian de dueño, no de idioma. _Requisitos: ninguno_
- [ ] T034 [P] CE-007: recorrer las direcciones que la consola tenía antes de esta spec y confirmar que ninguna responde «no existe». _Requisitos: CE-007_
- [ ] T035 Actualizar `architecture/console-map.md` en la KB: el alta tiene tres pasos y la tarjeta de la ficha tiene cuatro. _Requisitos: ninguno — §IX_
- [ ] T035b **Retirar el límite de clientes por partner** (owner, 2026-09-28). Toca tres sitios y por eso es tarea propia: la comprobación de `provision_partner_client`, el contador «{used} de {max}» de la lista de clientes y `/console/me`, y las claves de i18n que se quedan sin dueño (`clients.quota`, `clients.quota.full`, `wizard.quota.blocked`). **Conservar la guarda**: la comprobación corre bajo bloqueo de fila antes de crear nada y hoy acota el daño de una clave filtrada, así que el techo sube a un número que ningún partner real alcanza en vez de desaparecer. _Requisitos: 1.6_
- [ ] T036 **Entra en alcance (owner, 2026-09-28)**: valores por defecto **seguros** para los campos avanzados de `aesthetic_clinic_v1` en su semilla y en la KB — una respuesta que un agente bien educado daría mientras no se lo hayan dicho («consúltalo con recepción»), no un hueco vacío. Sin esto, «lo avanzado no se pide en el alta» no se puede cumplir: el renderizador levanta `SeedTemplatePlaceholderMissing`. **Bloquea T015.** _Requisitos: 1.2, 1.3_

---

## Dependencias

- **Phase 1 → Phase 2 → Iteración 1.** T001 (paridad) va antes que cualquier
  código: es el inventario de lo que no puede desaparecer.
- **Iteración 1 es el MVP y se puede parar ahí**: lleva el alta de 23 campos a 4.
- **Iteración 2 depende de la 1**: recoge lo que la 1 dejó de pedir. Entregar la
  1 sin la 2 deja esos campos sin sitio — aceptable durante una iteración, no
  para siempre.
- **Iteración 3 no depende de la 2**, pero va después porque es la que menos
  duele si se retrasa.
- Dentro de cada iteración: prototipo → tests en rojo → código → cierre.

## Paralelismo

- T002 ∥ T003 tras T001.
- T005 ∥ T006 ∥ T007 tras T004.
- T009 ∥ T010 ∥ T011 ∥ T012 ∥ T013 tras T008.
- T020 ∥ T021; T026 ∥ T027 ∥ T028 tras T025.
- T033 ∥ T034 al final.

## Estrategia

**MVP = iteración 1.** Si solo se entrega eso, crear un cliente pasa de
veintitrés campos a cuatro y nadie vuelve a empezar en la plantilla equivocada.
Las otras dos cierran el círculo y lo hacen cómodo.
