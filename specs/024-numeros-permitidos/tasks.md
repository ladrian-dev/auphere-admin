# Tasks: los números permitidos se editan en Ajustes del agente

**Input**: documentos de diseño de `/specs/024-numeros-permitidos/`

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/audience.md

**Tests**: NO son opcionales (constitución §VII): cada bloque se escribe
primero, se ve en rojo, y solo entonces se implementa.

**Organization**: por historia. H1 = el partner limita a quién responde ·
H2 = la pantalla dice que está limitado · H3 = las plantillas de solo
administradores no se abren. **Orden de entrega** (plan): API y worker →
formulario (H1) → pantalla honesta (H2) → bloqueo (H3).

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: termina con `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: rama, YYYY-MM-DD`.
- **Test primero (§VII)**; **aislamiento (§I)** con tarea propia (T-ISO);
  **licencias (§VIII)**: ninguna dependencia nueva (T-LIC); **medidor**: nada
  nuevo gasta (T-MET).
- **Cierre**: tests rojos → código → suites en verde → paridad → evidencia →
  log de sesión en la KB → merge a `develop` → staging.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

API en `apps/api/src/nexus_api/` con tests en `apps/api/tests/{unit,isolation}/`;
worker en `apps/worker/src/nexus_worker/` (tests con `uv run --directory apps/api pytest <ruta absoluta>`);
consola en `apps/console/src/` con tests junto al código; KB en
`/Users/matos/workspace/kb/Auphere/nexus/`.

---

## Phase 1: Setup

- [ ] T001 [P] T-LIC · hashes de `pnpm-lock.yaml` y `apps/api/uv.lock` en `specs/024-numeros-permitidos/evidence/locks-at-open.sha256`. `parity.md`: qué hace hoy el modo de solo administradores (API de partners, asistente de alta, gate, acuse de lectura) y que **nada se retira**: la API de partners sigue escribiendo la misma lista. _Requisitos: 5.1, 5.2, 5.3 · puerta §VIII_
- [ ] T002 [P] T-MET · En `apps/worker/tests/unit/test_dispatcher_admin_gate.py`, aserción de que un entrante suprimido no escribe ningún evento de consumo (misma comprobación que la 022). _Requisitos: ninguno — puerta del medidor_

---

## Phase 2: Foundational — API y worker

- [ ] T003 [P] Test `apps/api/tests/unit/test_agent_audience.py`: `audience_of(policies, locked)` y `apply_audience(policies, audience, locked)` — `admin_only` ausente → `everyone`; verdadero → `list` con nombres de `admins`; escribir `list` normaliza con `to_e164`, deduplica, conserva `role` previo, pone `full` al nuevo; `everyone` apaga `admin_only` y conserva los números; teléfono inválido → `AudienceInvalidPhone(phone)`; lista vacía → `AudienceEmpty`; `everyone` con `locked` → `AudienceLocked`. _Requisitos: 1.2, 1.3, 2.3, 4.1, 5.3_
- [ ] T004 [P] `apps/api/src/nexus_api/services/agent_audience.py` con esas funciones, las tres excepciones y `is_locked_template(seed_template_ref)` (lee `load_seed_template(...).policies_default.admin_access.admin_only`, `False` si la plantilla no carga). _Requisitos: 1.2, 1.3, 2.3, 4.1_
- [ ] T005 [P] Migración `apps/api/alembic/versions/0136_message_skipped_reason.py` (id ≤ 32 caracteres): `messages.skipped_reason varchar(40) NULL` + índice parcial `ix_messages_skipped_reason` en `(conversation_id) WHERE skipped_reason IS NOT NULL`; `Message.skipped_reason` en `db/models/conversation.py`. Aplicar en local (`alembic upgrade head`). _Requisitos: 3.2_
- [ ] T006 Test en `apps/worker/tests/unit/test_dispatcher_admin_gate.py`: con `admin_only` y remitente fuera de la lista, el entrante persistido queda con `skipped_reason == "not_admin"`; con remitente de la lista, nulo; T002. _Requisitos: 2.1, 3.2_
- [ ] T007 `apps/worker/src/nexus_worker/runtime/dispatcher.py`: al suprimir por `not_admin`, escribir `skipped_reason = "not_admin"` en el entrante recién persistido, en la misma sesión, antes de devolver. _Requisitos: 2.1, 3.2_
- [ ] T008 [P] Tests `apps/api/tests/unit/test_endpoint_console_agent_settings_audience.py`: GET devuelve `audience` derivada del borrador si lo hay; PUT con `audience` normaliza y crea el borrador; PUT sin `audience` no toca `admin_access`; 422 `audience_invalid_phone` con el teléfono; 422 `audience_empty`; 409 `audience_locked`; lo escrito desde la consola lo devuelve `GET /v2/partners/clients/{ref}/admins` (CE-004); publicar y revertir llevan la lista consigo. _Requisitos: 1.1–1.4, 2.2, 4.1, 5.1 · CE-004_
- [ ] T009 `apps/api/src/nexus_api/api/console/schemas_agent_tools.py` (`AudienceNumber`, `AudienceIn`, `AudienceOut`; `AgentSettingsIn.audience: AudienceIn | None`; `AgentSettingsOut.audience`) y `agent_settings.py` (GET deriva; PUT aplica sobre el borrador con las excepciones → 422/409). Contrato en `contracts/audience.md` §1–2. _Requisitos: 1.1–1.4, 4.1_
- [ ] T010 T-ISO · `apps/api/tests/isolation/test_console_agent_settings_audience.py`: el PUT de A no cambia el `admin_access` de B; la ruta de ajustes no acepta `tenant_id` ni `sender` (barrido OpenAPI). _Requisitos: puerta §I_

**Checkpoint**: la lista se fija y se lee desde la consola por API, el worker deja el motivo en el mensaje, y ningún tenant toca a otro.

---

## Phase 3: Historia 1 — la sección del formulario (P1)

**Goal**: en Ajustes del agente, «A quién responde» con las dos opciones, la lista por líneas y los errores por línea; se guarda en el borrador y se publica.

**Independent test**: quickstart, «En la consola local — Historia 1».

- [ ] T011 [P] [US1] Test `apps/console/src/components/agent-tools/__tests__/audience-lines.test.ts`: `parseAudienceLines(text)` acepta «+56 9 9191 9125 · Daniel, ventas», «+34666261967», comas entre números, líneas vacías; devuelve `{numbers, errors: [{line, text}]}`; `formatAudienceLines(numbers)` es la inversa. _Requisitos: 1.2, 1.3_
- [ ] T012 [P] [US1] `apps/console/src/components/agent-tools/audience-lines.ts` (puro) y `settings-schema.ts`: `audience: {mode, numbers}` en el espejo zod, con mensajes inyectables `audienceEmpty` y `audiencePhone`. _Requisitos: 1.2, 1.3_
- [ ] T013 [US1] Tests en `apps/console/src/components/agent-tools/__tests__/agent-settings-form.test.tsx`: la sección aparece entre Escalado y Aviso de IA; elegir «Solo a estos números» enseña el área de texto; guardar con lista vacía o una línea mal señala la línea y no llama a la acción; guardar envía `audience` normalizada; quien solo mira lo ve deshabilitado. _Requisitos: 1.1–1.3, 1.5_
- [ ] T014 [US1] `agent-settings-form.tsx`: sección «A quién responde» (radios + textarea + ayuda con ejemplo); `lib/backend/agent-tools-types.ts` (`Audience`, `AudienceNumber`); la acción de guardar pasa `audience`; claves i18n `agentSettings.section.audience`, `agentSettings.audience.*` en `i18n/lanes/agent-tools.ts` (es/en); `no-orphan-keys` verde. _Requisitos: 1.1–1.5_
- [ ] T015 [US1] Evidencia local: capturas del formulario, del borrador («Cambia: Ajustes») y de la versión publicada en `evidence/iteracion-1.md`. _Requisitos: 1.4 · CE-001_

**Checkpoint**: Historia 1 completa en local.

---

## Phase 4: Historia 2 — la pantalla dice que está limitado (P2)

**Goal**: cabecera, lista de clientes, Conversaciones y Companion dicen que el agente responde solo a N números y cuántos mensajes quedaron sin respuesta.

**Independent test**: quickstart, staging con número real (CE-002, CE-003).

- [ ] T016 [P] [US2] Tests `apps/api/tests/unit/test_endpoint_console_clients_audience.py`: lista y ficha con `audience` de la versión **activa** (no del borrador); nulo sin activa; la lista lo resuelve en una consulta (contador de queries). _Requisitos: 3.1, 3.3_
- [ ] T017 [P] [US2] `schemas.py` (`ClientAudienceOut`; `ClientSummaryOut.audience`) y `tenants.py`: audiencia por cliente en la lista (una consulta por página) y en la ficha. Contrato §3. _Requisitos: 3.1, 3.3_
- [ ] T018 [P] [US2] Tests `apps/api/tests/unit/test_endpoint_console_conversations_unanswered.py`: `unanswered` por conversación y `unanswered_messages` en stats a partir de `skipped_reason`. _Requisitos: 3.2_
- [ ] T019 [P] [US2] `conversations.py` y sus esquemas: `ConversationOut.unanswered`, `ConversationStatsOut.unanswered_messages`. Contrato §4. _Requisitos: 3.2_
- [ ] T020 [US2] Consola: `clients.audience.only` en la cabecera de la ficha (bajo «Atendiendo desde», con enlace a Ajustes), insignia `clients.audience.badge` en `clients-table.tsx`, columna y métrica «sin responder» en `clients/[ref]/conversations/page.tsx`; tipos en `lib/backend`; tests de `clients-table` y `client-header-model`. _Requisitos: 3.1, 3.2_
- [ ] T021 [US2] Companion: test en `apps/api/tests/unit/test_companion_tools_catalog.py` (o el fichero que cubra `console.get_client`) de que la respuesta lleva `audience`; añadir el caso a `services/evals/companion/dataset/known_answer.json` si el dataset lo exige. _Requisitos: 3.3_
- [ ] T022 [US2] Staging con número real: activar la lista en un cliente conectado, escribir desde un número de la lista y desde otro, capturas de cabecera, lista y Conversaciones (`evidence/iteracion-2.md`). _Requisitos: 2.1, 2.2, 3.1, 3.2 · CE-002, CE-003_

**Checkpoint**: Historia 2 cerrada con evidencia real.

---

## Phase 5: Historia 3 — las plantillas de solo administradores (P3)

**Goal**: un cliente de cobranza edita la lista pero no puede elegir «A todo el mundo».

**Independent test**: quickstart, cliente creado con `cobranza_v1`.

- [ ] T023 [US3] Tests (en `test_endpoint_console_agent_settings_audience.py`): con `seed_template_ref = cobranza_v1`, GET devuelve `locked: true` y PUT `everyone` responde 409; con `generic_v1`, `locked: false`. _Requisitos: 4.1_
- [ ] T024 [US3] Consola: con `locked`, radios deshabilitadas y línea `agentSettings.audience.locked`; test en `agent-settings-form.test.tsx`. _Requisitos: 4.1_
- [ ] T025 [US3] Evidencia: Ajustes del agente de un cliente de cobranza en local (`evidence/iteracion-3.md`); en producción, comprobar con Mouna que la lista se ve y el modo no se puede cambiar (CE-005). _Requisitos: 4.1 · CE-005_

---

## Phase 6: Polish & cierre

- [ ] T026 Comparar locks (T-LIC); `parity.md` cerrado; log de sesión en la KB con enlace a esta carpeta; memoria del proyecto; merge a `develop` y CI verde. _Requisitos: ninguno — ritual de cierre · puerta §IX_

---

## Dependencies

- Phase 2 antes que todo: el formulario (H1) necesita el PUT con `audience`; la pantalla (H2) necesita `skipped_reason` y la lectura de la activa.
- Dentro de la Phase 2: T003/T004 ∥ T005; T006/T007 después de T005; T008/T009 después de T004; T010 después de T009.
- H3 (Phase 5) depende de T004 (`is_locked_template`) y de T014 (la sección existe).
- T022 y T025 (CE-005 en prod) exigen staging/producción; todo lo demás se cierra en local.

## Parallel execution

- Phase 2: T003+T004 ∥ T005 ∥ T008 (tests) mientras se escribe T009.
- Phase 3: T011/T012 ∥ T013 (tests) → T014.
- Phase 4: T016/T017 ∥ T018/T019 ∥ T020 (consola) ∥ T021.

## Implementation strategy

MVP = Phase 2 + Phase 3: con eso el partner fija la lista desde la consola
sin clave de API. Phase 4 es lo que evita que un partner crea que el agente
«no funciona»; va en la misma entrega si el tiempo lo permite. Phase 5 es
media jornada.
