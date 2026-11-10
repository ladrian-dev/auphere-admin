---
description: "Tareas de la spec 057 — la agenda desde el agente"
---

# Tareas: La agenda desde el agente

**Entrada**: `specs/057-agenda-desde-el-agente/` — `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`.

**Pruebas**: no son opcionales (constitución §VII). Cada bloque empieza por su prueba, se ve en rojo y solo entonces se implementa. Las frases literales de Spa Jemma (`research.md`, «Lo que se encontró», punto 4) son datos de prueba.

## Reglas de este repo *(constitución)*

- Cada tarea termina con `_Requisitos: N.m_`.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- Aislamiento: T005 (garantía 1) y T006 (garantía 2). Bloquean el merge.
- Licencias: ninguna dependencia nueva.
- Medidor: T024 (la propuesta, dentro de `usage_turn(source=SOURCE_BUILDER)`).
- Una suite de pytest a la vez; las de la API y las del worker, por separado.
- Los commits los hace Luis: cada tarea deja el mensaje en inglés, Conventional Commits, sin firma.

## Formato: `[ID] [P?] [Historia] Descripción`

- **[P]**: puede ir en paralelo (archivos distintos, sin depender de una tarea abierta).
- **[USn]**: la historia de `spec.md` (US1 alta, US2 aviso, US3 Conectores y propuesta, US4 agenda no lista, US5 Acceso).

---

## Fase 1: Preparación

- [x] T001 Migración `apps/api/alembic/versions/0229_agenda_from_agent.py` sobre `0228_staff_calendar_connections`: recrea `ck_jobs_kind` con `agenda_text` y `ck_conversations_waiting_reason` con `agenda_not_ready`; la bajada borra los trabajos `agenda_text`, devuelve esas conversaciones como `escalated` y recrea las restricciones anteriores. Añadir `"agenda_text"` a `JOB_KINDS` (`db/models/jobs.py`) y `"agenda_not_ready"` a `WAITING_REASONS` (`db/models/conversation.py`), con su texto en la Bandeja de la consola (`lib/waiting-reasons.ts`, carril `agent-improve`) y de la app (`features/inbox/model.ts`, `fabrica.{es,en}.ts`). Prueba de la migración (subir y bajar) junto a las de su familia en `apps/api/tests/integration/`.
  _Requisitos: 3.6_
- [x] T002 [P] Carril de textos `apps/console/src/i18n/lanes/agenda.ts`, registrado donde se registran los demás carriles: el interruptor, su línea, el porqué del encendido, los modos, la fila de Conectores y sus estados, la confirmación de encender Reservas, «La agenda aún no está lista» con un texto por cada motivo de `NOT_READY_REASONS`, «Gestionar citas», el aviso «agenda preparada» y los errores `reservas_mode_required`, `reservas_kind_required`, `reservas_kind_forbidden`, `too_many_tools`, `build_budget_exhausted`. Sin punto y coma (`src/i18n/__tests__/words.test.ts`).
  _Requisitos: 1.1, 1.3, 2.1, 2.3, 4.4, 5.3, 6.3_

---

## Fase 2: Lo que todas las historias necesitan

**Bloquea todo lo demás.**

- [x] T003 [P] Prueba en rojo `apps/api/tests/unit/test_057_gives_appointments.py` y `apps/api/tests/integration/reservas/test_057_agenda_ready.py`:
  - `passing.gives_appointments(cfg)`:
    - verdadero con un conector que reserva, con `booking.*`, con un texto estructurado que promete `book` o `modify_booking` (frases de Spa Jemma) y con un agente de instrucciones libres cuyo `legacy_text` promete citas;
    - falso con un agente de cobros.
  - `passing.agenda_ready(session)`: falso apagado, sin modo, sin horario, sin nadie en activo, sin servicio reservable y en aforo sin plazas o franjas; verdadero listo. Sin recorrer días (cuenta de consultas).
  _Requisitos: 4.2, 4.3, 5.1_
- [x] T004 Implementar en `apps/api/src/nexus_api/services/reservations/passing.py`:
  - `gives_appointments` y `agenda_ready`;
  - `pass_to_reservas(..., scope: Literal["booking", "givers"], exclude: frozenset[uuid.UUID] = frozenset())`, que sustituye a `every_agent`;
  - `prepare_agent_versions(..., only: Callable[[AgentConfig], bool] | None, exclude=…)`.

  Actualizar a los llamantes sin cambiar aún su comportamiento: `admin.apply_choice` pasa `scope="givers"` en T039. El paso automático sigue con `only_booking`.
  _Requisitos: 4.2, 4.3, 5.1_
- [x] T005 [P] Aislamiento, **garantía 1**, `apps/api/tests/isolation/test_057_agenda_from_agent.py` (parte A):
  - el partner A, con el `ref` del cliente de B, llama a `PUT …/agenda`, `GET …/agenda`, `GET …/agenda/tools` y `POST …/draft-jobs` con `agenda=true`;
  - recibe el 404 opaco, byte a byte igual que el de un `ref` que no existe;
  - en B no queda rastro: ni `client_access`, ni `reservation_settings`, ni `audit_log`, ni borrador en `agent_configs`, ni `jobs`, ni `proposals`;
  - un cuerpo con `tenant_id` o `partner_id` da 422 (`extra="forbid"`).

  Ampliar `_minimal_body` de `apps/api/tests/isolation/test_console_scope.py` con las tres rutas nuevas.
  _Requisitos: 7.2, 7.3_
- [x] T006 [P] Aislamiento, **garantía 2**:
  - **Parte B, en el mismo archivo:**
    - encender Reservas desde un agente y desde Acceso da `reservas.*` solo al agente de origen y a los que dan citas;
    - el borrador y la versión activa de un agente de cobros siguen sin ninguna.
  - **En `apps/worker/tests/unit/test_057_agenda_whitelist.py`:**
    - con el módulo encendido, un agente sin agenda no tiene `reservas.*` ni en `get_openai_tools` ni en la lista de `registry.dispatch`;
    - con la agenda no lista, `dispatch` rechaza `reservas.create` aunque el modelo la invente.
  - **Barrido** (constitución §I: barre, no enumera): una prueba estructural recorre con `ast` todo `apps/api/src` y `apps/worker/src` buscando quién escribe `RESERVAS_TOOLS` o nombres `reservas.*` en una versión. Cubre `prepare_agent_versions`, `publish_agent_versions`, `_set_spec_tools`, `sanitize`, `draft_from_template` y el en blanco. Cada sitio encontrado tiene que estar en una lista de permitidos con su prueba de que solo escribe en el agente de la ruta o en los que dan citas. Un sitio nuevo sin entrada pone la prueba en rojo.
  _Requisitos: 7.6, 5.1, 4.2_
- [x] T007 [P] Prueba en rojo `apps/api/tests/integration/reservas/test_turn_on_from_agent.py`:
  - añade `reservas` sin tocar `enabled` ni los otros módulos;
  - sin fila de `client_access`, la crea con `enabled=false` y el partner del `PartnerTenant`;
  - `apply_choice` crea `reservation_settings`;
  - errores: sin modo → `reservas_mode_required`; aforo sin tipo y servicios con tipo → error;
  - dos sesiones a la vez → una sola fila de ajustes;
  - auditoría `client_access.updated` con `from_agent`, `mode` y `capacity_kind`;
  - tras la llamada, `current_user` sigue siendo `nexus_app` (sin `RESET ROLE`);
  - el agente de origen no recibe el borrador de R5.
  _Requisitos: 1.4, 1.8, 5.2, 7.3, 7.5_
- [x] T008 Implementar `apps/api/src/nexus_api/services/reservations/turn_on.py: turn_on_from_agent(session, *, tenant_id, partner_id, choice, actor, origin_agent_id, now)`, con `pg_advisory_xact_lock` por cliente.
  - Extraer la parte común (añadir el módulo y auditar) de `auto_pass.turn_on_reservas` (`auto_pass.py:157-217`) y que la usen los dos.
  - Extraer `auto_pass.choose_mode` a `apps/api/src/nexus_api/services/reservations/turn_on.py: suggested_choice(session)` (no en `settings.py`: sería un ciclo de imports) (restaurante → `capacity`/`restaurant`; el resto, `services`).
  - Registro `reservas.turned_on_from_agent`.
  _Requisitos: 1.4, 1.8, 7.1, 7.3, 7.5_
- [x] T009 [P] Prueba en rojo (en `apps/api/tests/integration/builder/test_057_agenda_routes.py` y `tests/integration/test_console_capabilities.py`) para `capabilities_client._set_spec_tools(scope, keys, enabled)`:
  - una validación y una escritura;
  - más de 60 → 422 `too_many_tools` con `max`, y no escribe nada;
  - al quitar, el nombre también sale de `procedures[].tools` y el AgentSpec sigue validando;
  - un agente de instrucciones libres cambia `tools`;
  - `_set_spec_tool` de una sola herramienta sigue igual (pruebas de `test_console_capabilities.py` en verde).
  _Requisitos: 2.2, 2.5, 2.6, 2.7_
- [x] T010 Implementar `_set_spec_tools` en `apps/api/src/nexus_api/api/console/capabilities_client.py`, y que `_set_spec_tool` lo llame con un conjunto de uno. Al apagar la agenda entera no se llama a `_refuse_if_in_use` (`research.md` R3).
  _Requisitos: 2.2, 2.5, 2.6, 2.7_

**Punto de control**: base lista; las historias pueden empezar.

---

## Fase 3: Historia 1 — Crear un agente que da citas (P1) 🎯 MVP

**Objetivo**: «Gestiona citas» en el alta; con él, Reservas se enciende antes de construir y la v1 lleva la agenda.

**Prueba independiente**: cliente sin Reservas → agente con «Gestiona citas» → v1 con las 9, Reservas encendido, el probador reserva.

- [x] T011 [P] [US1] Prueba en rojo `apps/api/tests/integration/builder/test_057_draft_job_with_agenda.py`:
  - `draft-options`:
    - devuelve `agenda`, con `suggested_mode="services"` y `capacity` para restaurante;
    - las plantillas llevan `books`.
  - `draft-jobs` en modo «describir»:
    - con `agenda=true`, el módulo apagado y `reservas` → el módulo queda encendido **antes** de encolar, y `progress.input.agenda=true`;
    - sin `reservas` → 422 `reservas_mode_required`, sin trabajo ni agente;
    - cliente archivado → 409, sin nada escrito;
    - `agenda=null` → como hoy.
  - «Desde una plantilla» con `agenda=false` → sin `reservas.*` ni en `tools` ni en `procedures[].tools`.
  - «En blanco» con `agenda=true` → las 9 y el procedimiento fijo.
  - Permisos: el builder puede (201/202) y el analista no (403).
  _Requisitos: 1.1, 1.3, 1.4, 1.5, 1.7, 7.1_
- [x] T012 [P] [US1] Prueba en rojo `apps/api/tests/unit/test_057_builder_agenda.py`:
  - `build_messages` dice si el agente gestiona citas;
  - `sanitize` con `agenda=True`:
    - añade las 9 disponibles;
    - añade el procedimiento fijo si ninguno usa `reservas.create`;
    - no deja la alternativa «pasar al equipo para que confirme»;
  - `sanitize` con `agenda=False` quita toda `reservas.*`;
  - `offline_output` respeta `agenda`.
  _Requisitos: 1.6, 1.7_
- [x] T013 [US1] Esquemas en `apps/api/src/nexus_api/api/console/schemas_agent_builder.py`:
  - `DraftJobIn.agenda: bool | None = None` y `DraftJobIn.reservas`, con el modo y el tipo de `ClientReservasIn` (`schemas_client_access.py`) sin `on_live`;
  - `DraftOptionsOut.agenda`;
  - `TemplateOptionOut.books`.

  Formas en `contracts/console-api.md` §1 y §2.
  _Requisitos: 1.1, 1.3_
- [x] T014 [US1] `apps/api/src/nexus_api/api/console/agent_builder.py`:
  - `draft_options` rellena `agenda` (`reservas_enabled`, `suggested_choice`) y `books` (`guides/catalog.template_tools`);
  - `start_draft`, con `agenda=true` y el módulo apagado, llama a `turn_on_from_agent(origin_agent_id=None)` antes de encolar (modo «describir») o antes de `draft_from_template` / `_blank_spec` (plantilla y en blanco), en la misma transacción;
  - traduce `ReservasChoiceError` y `ClientAccessError` a 422 y 409;
  - guarda `agenda` en `progress.input`.
  _Requisitos: 1.3, 1.4, 1.5, 1.8, 7.1_
- [x] T015 [US1] Constructor:
  - en `apps/api/src/nexus_api/services/builder/agent_draft.py`:
    - `DraftRequest.agenda: bool | None`;
    - en `build_messages`, un bloque `<agenda>` que dice si gestiona citas;
    - en `sanitize`, hacerlo cumplir;
    - `draft_from_template` y el en blanco aceptan `agenda`;
  - en `apps/worker/src/nexus_worker/jobs/handlers/agent_draft.py`, leer `agenda` de `progress.input`.
  _Requisitos: 1.6, 1.7_
- [x] T016 [P] [US1] Prueba en rojo `apps/console/src/components/builder/__tests__/builder-new.test.tsx`:
  - el interruptor sale si `offered`;
  - se enciende solo con «citas», «reservar» o «turno», enseña el porqué y deja de seguir a la descripción en cuanto alguien lo toca;
  - con el módulo apagado:
    - enseña los modos con el sugerido elegido, y el tipo solo en aforo;
    - avisa de que encenderá Reservas para el cliente;
  - el cuerpo lleva `agenda` y `reservas`;
  - los errores se dicen en su campo y no se navega;
  - una plantilla con `books` enciende el interruptor.

  En `apps/console/src/app/(console)/clients/[ref]/agents/__tests__/builder-actions.test.ts`, `startDraftJobAction` acepta los campos nuevos (permitido) y rechaza un `tenant_id` (denegado).
  _Requisitos: 1.1, 1.2, 1.3_
- [x] T017 [US1] Consola:
  - extraer `ReservasFields` de `apps/console/src/components/clients/access/client-console-card.tsx` a `apps/console/src/components/clients/access/reservas-fields.tsx`; su prueba sigue en verde;
  - en `apps/console/src/components/builder/builder-new.tsx`: interruptor y modo bajo «¿Qué tiene que hacer?», con sus estados de cargando, error y desactivado;
  - `BOOKING_WORDS` y `agendaSuggested()` en `builder-model.ts` (la misma expresión que `agent_draft._BOOKING`, citada en un comentario);
  - tipos en `apps/console/src/lib/backend/builder-types.ts`;
  - esquema de la acción en `builder-actions.ts`.
  _Requisitos: 1.1, 1.2, 1.3_

**Punto de control**: US1 completa y probable sola.

---

## Fase 4: Historia 2 — Los avisos dicen la verdad (P1)

**Objetivo**: «No tenemos herramienta para» se recalcula, y la revisión avisa cuando el texto prohíbe la agenda.

**Prueba independiente**: un agente creado sin agenda que la ganó después ya no la ve en el aviso. Con el texto de Spa Jemma, la revisión señala las seis piezas.

- [x] T018 [P] [US2] Prueba en rojo `apps/api/tests/unit/test_057_still_missing.py` para `missing.still_missing(items, spec, ctx)`:
  - una `action` cubierta por las herramientas sale;
  - un `module_off` de Reservas sale con el módulo encendido;
  - una `integration` conectada sale;
  - un `tool_unknown` se queda;
  - las notas de Spa Jemma («cambiar o cancelar citas», «reservar citas») con las 9 → vacío.

  Integración en `apps/api/tests/integration/builder/test_only_what_we_have.py`:
  - `GET …/draft` de un agente con nota vieja no la devuelve, ni en el borrador ni en lo publicado;
  - `write_spec` no la arrastra al fusionar.
  _Requisitos: 6.1, 6.2, 6.4_
- [x] T019 [US2] Implementar:
  - `still_missing` en `apps/api/src/nexus_api/services/agent_spec/missing.py`;
  - usarlo en `agent_draft_routes._spec_and_missing` (`apps/api/src/nexus_api/api/console/agent_draft_routes.py`) y en `agent_spec_drafts.write_spec` (`agent_spec_drafts.py`).
  _Requisitos: 6.1, 6.2, 6.4_
- [x] T020 [P] [US2] Prueba en rojo en `apps/api/tests/unit/test_agent_spec_compiler.py` y `test_agent_review.py`. `incoherences` da `forbids_agenda`, con el puntero de cada texto, para las frases literales de Spa Jemma:
  - el paso «No ofrezcas huecos ni confirmes la reserva»;
  - el disparador «porque la agenda no está activa»;
  - las dos reglas;
  - la alternativa de las dos habilidades `appointment_*_intake`.

  Y además:
  - no lo da para «si la clienta lo pide, pásala a una persona», ni sin `reservas.create`;
  - `review` lo emite como `warn`, con la acción de pedir la propuesta.
  _Requisitos: 3.8_
- [x] T021 [US2] Implementar en `apps/api/src/nexus_api/services/agent_spec/compiler.py`:
  - `forbids_agenda`, con patrones en español como los de `PROMISES`, sobre `_texts(spec)` más los disparadores `custom` de `escalation` y la alternativa de cada habilidad;
  - el hallazgo en `apps/api/src/nexus_api/services/agent_spec/review.py`.
  _Requisitos: 3.8_
- [x] T022 [P] [US2] Prueba en rojo en `apps/console/src/components/builder/__tests__/missing-capabilities.test.tsx` y `review-panel.test.tsx`:
  - «Gestionar citas» aparece en `book` y `modify_booking` cuando se ofrece Reservas, y lleva a la fila `#agenda` de Conectores;
  - no aparece en otras claves;
  - el panel de revisión pinta `forbids_agenda` con sus punteros.
  _Requisitos: 6.3, 3.8_
- [x] T023 [US2] Implementar en `apps/console/src/components/builder/missing-capabilities.tsx`, `missing-model.ts` y el panel de revisión.
  _Requisitos: 6.3, 3.8_

**Punto de control**: US1 y US2 (las dos P1) completas. Es el MVP.

---

## Fase 5: Historia 3 — La agenda en Conectores y la propuesta de texto (P2)

**Objetivo**: activar o desactivar la agenda de un agente ya creado, con la propuesta del constructor.

**Prueba independiente**: un agente sin agenda → Activar → borrador con las 9 y propuesta con antes y después → aceptar → publicar → reserva.

- [x] T024 [P] [US3] **Medidor**. Prueba en rojo `apps/api/tests/integration/builder/test_057_agenda_text_job.py` (con base: corre el trabajo de verdad):
  - el manejador corre dentro de `usage_turn(source=SOURCE_BUILDER)` y lo medido llega a la partida `build` (`partner_build_budget`), nunca a la bolsa del cliente;
  - la salida del modelo se valida;
  - sin modelo, o si el proveedor falla, usa el respaldo (`fallback=true` en `builder.job`);
  - las operaciones solo tocan `/procedures`, `/rules`, `/escalation`, `/skills`, `/instructions` y `/services/faqs`;
  - `expires_at` queda a 7 días;
  - la propuesta anterior de la agenda del mismo agente pasa a `stale`;
  - si la ficha dice que el equipo confirma las citas (la política de cancelación de Spa Jemma), la propuesta lleva `diff.ficha_links` con la sección y no toca la ficha;
  - el trabajo se corta a los 270 s, como `agent_draft`, y queda en el respaldo.
  _Requisitos: 3.1, 3.2, 3.5, 3.6, 3.7_
- [x] T025 [P] [US3] Prueba en rojo `apps/api/tests/integration/test_057_agenda_routes.py`:
  - `GET …/agenda`:
    - devuelve `state` (`none`, `prepared` u `on`), `ready` y `missing`;
    - `structured=false` en un agente de instrucciones libres.
  - `PUT` con `enabled=true`:
    - con el módulo apagado y sin `reservas` → 422;
    - con `reservas` → módulo encendido, las 9 en el borrador, trabajo `agenda_text` encolado y las dos filas de auditoría;
    - repetirlo no hace nada.
  - `PUT` con `enabled=false`:
    - quita las 9 y su nombre de los procedimientos;
    - el módulo sigue encendido y las reservas, intactas.
  - Más de 60 → 422 sin escribir.
  - Sin presupuesto → las herramientas cambian y `proposal_reason="build_budget_exhausted"`.
  - El analista recibe 403.
  - `GET …/agenda/tools` tiene la forma de `ConnectorToolsOut`.
  - `GET …/proposals` lleva `before` en cada operación.
  _Requisitos: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 3.3, 3.5, 4.4, 7.1, 7.4_
- [x] T026 [US3] `apps/api/src/nexus_api/services/builder/agenda_text.py`:
  - el mensaje al constructor: el AgentSpec ya cambiado, `available_lines(ctx, only=spec.tools)` y la orden de reescribir solo lo que habla de citas, a favor de la agenda o en contra;
  - la validación: `validate_spec`, `missing.strip_doc`, ninguna promesa nueva sin herramienta y ningún `forbids_agenda` restante;
  - el respaldo sin modelo: el procedimiento fijo de `offline_output` y quitar lo que señala `forbids_agenda`;
  - las secciones de la ficha que dicen que el equipo confirma las citas, detectadas con los patrones de `forbids_agenda` sobre las políticas, salen en `diff.ficha_links` (`{"section": "policies.cancellation"}`). Nunca un campo llamado `notes`, que `test_console_scope.py` prohíbe.
  _Requisitos: 3.1, 3.2, 3.4, 3.5, 3.7_
- [x] T027 [US3] Trabajo en el worker:
  - el manejador `apps/worker/src/nexus_worker/jobs/handlers/agenda_text.py`, registrado en `jobs/handlers/__init__.py` y en el reparto del consumidor, dentro de `usage_turn(tenant_id, turn_id=f"job:{job_id}", source=SOURCE_BUILDER)`, con el `role="build"` del constructor y el mismo tope de 270 s que `agent_draft`;
  - en `apps/api/src/nexus_api/services/proposal_state.py`, `propose(..., ttl: timedelta | None = None)`.
  _Requisitos: 3.3, 3.6_
- [x] T028 [US3] Rutas en `apps/api/src/nexus_api/api/console/agenda.py`, montadas en `api/console/__init__.py` (`contracts/console-api.md` §3–§5 y §8):
  - `GET`/`PUT …/agenda` y `GET …/agenda/tools`;
  - `require_build_room` al encolar;
  - auditoría `console.agenda.update`;
  - `before` en `GET …/proposals` (`agent_builder.py:441-457`).
  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.3, 3.5, 4.4, 7.1, 7.5_
- [x] T029 [P] [US3] Prueba en rojo en la consola:
  - `__tests__/agenda-row.test.tsx`: cargando, vacío (no se ofrece → no hay fila), error, parcial (módulo encendido pero no listo) e ideal;
  - `agent-connectors.test.tsx`:
    - la fila va primera;
    - con el módulo apagado, activar pide confirmación con el modo;
    - el diálogo de herramientas usa la carga de la agenda;
  - `proposals.test.tsx`: antes y después por bloque; «Editar» aplica y abre el editor del primer bloque cambiado;
  - en `app/(console)/clients/[ref]/agents/__tests__/agenda-actions.test.ts`, un caso permitido y otro denegado por acción.
  _Requisitos: 2.1, 2.3, 2.4, 2.5, 3.3, 3.5, 4.4_
- [x] T030 [US3] Implementar en la consola, sin hex ni valores fuera de la escala (`@nexus/ui`):
  - `apps/console/src/lib/backend/agenda.ts`;
  - `app/(console)/clients/[ref]/agents/agenda-actions.ts`;
  - `components/builder/agenda-row.tsx`;
  - la fila en `agent-connectors.tsx` (`agent-connectors.tsx:426-450`), con `ConnectorToolsDialog` y su `load`;
  - antes y después y «Editar» en `components/builder/proposals.tsx`;
  - los `ficha_links` de la propuesta, con su enlace a Negocio.
  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 3.3, 3.5, 3.7, 4.4_

**Punto de control**: US3 completa y probable sola.

---

## Fase 6: Historia 4 — Reservas aún no está listo (P2)

**Objetivo**: se publica con aviso; mientras falte algo, el agente pasa las citas a una persona; al estar listo, reserva sin publicar de nuevo.

**Prueba independiente**: cliente sin profesionales → el agente pasa a una persona → al añadir uno, reserva.

- [x] T031 [P] [US4] Prueba en rojo `apps/worker/tests/unit/test_057_agenda_not_ready.py`:
  - **Herramientas con la agenda no lista:**
    - se quitan `find_slots`, `create`, `reschedule`, `join_waitlist` y `answer_offer`;
    - se quedan `services`, `list_mine`, `cancel` y `confirm_attendance`.
  - **La nota:**
    - sale con cualquier intención (también `info`) si el agente tiene `reservas.*`;
    - no sale con la agenda lista;
    - su texto no contiene «tu cita».
  - **Casos límite:**
    - si la lectura falla, el turno sigue con todas y registra `agenda.ready_read_failed`;
    - sin `escalate.escalate_to_human`, el runtime traspasa con `agenda_not_ready`;
    - el freno de citas no salta en un turno que llamó a `escalate` con la agenda no lista.

  Patrones de `test_hand_off_note.py`, `test_intent_tool_filter.py` y `test_booking_brake_simulation.py`.
  _Requisitos: 4.2, 4.3_
- [x] T032 [US4] Implementar:
  - en `apps/worker/src/nexus_worker/runtime/pipeline.py`, entre `allowed_names(...)` y `get_openai_tools(...)` (`pipeline.py:1816-1822`):
    - la lectura de `agenda_ready` por turno, con la RLS del cliente, como `_load_tool_policy`;
    - el filtro;
    - la nota con el patrón de `_HAND_OFF_NOTE`;
    - el registro `agenda.not_ready_turn`;
  - el motivo `agenda_not_ready` en `_ROUTER_REASONS` y `_SILENCES_THE_AGENT` (`runtime/dispatcher.py:482-488`);
  - la excepción del freno en `runtime/booking_brake.py`.
  _Requisitos: 4.2, 4.3_
- [x] T033 [P] [US4] Prueba en rojo `apps/worker/tests/unit/test_057_simulation_readiness.py`:
  - `run_turn(agenda_ready=False)` pasa la cita a una persona;
  - la suite del agente (`jobs/handlers/agent_tests.py`) corre con `agenda_ready=True`: un cliente sin profesionales no suspende las pruebas de reservar;
  - el playground lee la real (`apps/api/tests/integration/builder/test_playground_draft.py`).
  _Requisitos: 4.1, 4.2_
- [x] T034 [US4] Implementar:
  - en `apps/worker/src/nexus_worker/simulation/runner.py`, `run_turn(..., agenda_ready: bool | None)`; el handler lo usa en vez de leerlo;
  - `apps/api/src/nexus_api/api/console/agent_playground.py` pasa la real;
  - `jobs/handlers/agent_tests.py` pasa `True`.
  _Requisitos: 4.1, 4.2_
- [x] T035 [P] [US4] Prueba en rojo en `apps/api/tests/integration/builder/test_publish_gate.py` y `test_review_and_catalog.py`:
  - `no_hours` con un agente que reserva es `warn`;
  - `agenda_not_ready` (`warn`) lleva los motivos y el enlace;
  - publicar un agente con agenda para un cliente sin profesionales sale bien;
  - `bookable_without_duration` sigue bloqueando.
  _Requisitos: 4.1, 4.5_
- [x] T036 [US4] Implementar en `apps/api/src/nexus_api/services/agent_spec/review.py` (y en lo que arma `ReviewInput`): los motivos de `not_ready`; `no_hours` pasa a `warn`; el hallazgo `agenda_not_ready`.
  _Requisitos: 4.1, 4.5_
- [x] T037 [US4] Consola: en la cabecera del agente (`components/builder/agent-builder.tsx`), leído de `GET …/agenda`:
  - «La agenda aún no está lista», con los motivos y el enlace a Reservas;
  - «Tiene la agenda preparada: publica para que reserve», con la acción que lleva a la propuesta de texto (requisito 5.3).

  Prueba primero en `__tests__/agent-builder.test.tsx`.
  _Requisitos: 4.4, 5.3_

**Punto de control**: US4 completa y probable sola.

---

## Fase 7: Historia 5 — Encender Reservas solo toca a quien da citas (P3)

**Objetivo**: desde Acceso (y desde un agente), solo los agentes que dan citas ganan la agenda, en borrador y a la vista.

**Prueba independiente**: tres agentes, uno que promete citas → al encender, solo ese tiene borrador nuevo, y su aviso sale en la lista.

- [x] T038 [P] [US5] Prueba en rojo `apps/api/tests/integration/reservas/test_057_turn_on_only_givers.py`:
  - al encender en Acceso:
    - gana borrador el agente que promete citas y el de Calendly;
    - el de cobros no cambia;
  - un borrador descartado no vuelve con la misma versión activa;
  - `admin_view` cuenta los borradores hechos desde la consola;
  - `GET /clients/{ref}/agents` da `agenda="prepared"`.

  Ajustar a la regla nueva las expectativas de `test_reservas_manda.py` que suponían `every_agent`.
  _Requisitos: 5.1, 5.3, 5.4_
- [x] T039 [US5] Implementar:
  - en `apps/api/src/nexus_api/services/reservations/admin.py`, que `apply_choice` llame a `pass_to_reservas(scope="givers")`;
  - quitar el filtro `created_by LIKE 'operator:%'` de `admin_view` (`admin.py:219`) y comparar el borrador con la versión activa;
  - `AgentOut.agenda` en `apps/api/src/nexus_api/api/console/agents_list.py`.
  _Requisitos: 5.1, 5.3, 5.4_
- [x] T040 [P] [US5] Prueba en rojo `apps/console/src/components/builder/__tests__/agent-cards.test.tsx`: con `prepared`, el aviso y la acción de revisar; con `on` o `none`, nada.
  _Requisitos: 5.3_
- [x] T041 [US5] Implementar el aviso en `apps/console/src/components/builder/agent-cards.tsx` y el tipo en `apps/console/src/lib/backend.ts`.
  _Requisitos: 5.3_

---

## Fase 8: Cierre

- [x] T042 Documentación viva, en el mismo commit que el código que describe:
  - `docs/agentes.md`:
    - §2: la agenda en el alta y la propuesta;
    - §4: `no_hours`, `agenda_not_ready` y `forbids_agenda`;
    - el aviso recalculado;
  - `docs/reservas.md`:
    - «Activarlo», desde el agente y solo para los que dan citas;
    - «El agente», lo que pasa con la agenda no lista;
  - `specs/047-la-fabrica-de-agentes/contracts/events.md`: el motivo `agenda_not_ready` y los registros de `contracts/events.md`.
  _Requisitos: 1.4, 2.1, 3.1, 4.2, 5.1, 6.1_
- [x] T043 Puertas de UI del workspace sobre `builder-new`, `agenda-row`, `proposals`, `agent-cards`, `missing-capabilities` y el aviso de la cabecera: `ui-states-checklist`, `a11y-audit` (WCAG 2.2 AA; foco, objetivos de 24 px, interruptor con nombre accesible), `responsive-audit` (360 px, texto largo, zoom al 200 %) y `design-tokens`. Ningún 🔴 abierto.
  Hecho en estático el 2026-11-09 (Playwright no conectó): 3 🔴 y los 🟡 arreglados (`research.md`, «Revisión de UI»). Queda verlo en vivo con el tema oscuro en staging (T046).
  _Requisitos: 1.1, 2.1, 3.3, 4.4, 5.3_
- [x] T044 `/cso` y `tenant-security-audit`. Cambia quién puede encender un módulo del cliente (`agents:write`), hay un trabajo nuevo que llama al modelo y una lectura nueva por turno. Un 🔴 alto o crítico bloquea.
  _Requisitos: 7.1, 7.2, 7.3, 7.6_
- [x] T045 Verificación de lo tocado, sin las suites completas (se corren de camino a `main`):
  - `./scripts/verify.sh lint`;
  - las suites de los archivos tocados de la API y del worker, por separado;
  - `pnpm --filter console test` de los componentes tocados;
  - `next build` de la consola.
  _Requisitos: todos_
- [ ] T046 Validación en staging, a mano, según `quickstart.md`:
  - en Spa Jemma, el aviso viejo desapareció (CE-003) y `forbids_agenda` señala sus seis piezas;
  - la propuesta las reescribe;
  - un cliente nuevo de prueba recorre el alta con «Gestiona citas» y reserva en su primera conversación (CE-001, CE-002);
  - un barrido de solo lectura sobre los agentes de staging da cero avisos falsos.
  _Requisitos: CE-001, CE-002, CE-003, CE-004, CE-005_

---

## Dependencias

- **Fase 2** bloquea todo. Dentro: T003 → T004; T007 → T008; T009 → T010. T005 y T006 se escriben en rojo al principio y pasan a verde con las historias que cubren (T014, T028, T032, T039).
- **US1** necesita T008 (encender) y T004.
- **US2** no depende de las demás. «Gestionar citas» enlaza a la fila de US3, pero el enlace a la pestaña sirve antes.
- **US3** necesita T001, T008 y T010. T026 → T027 → T028.
- **US4** necesita T004 (`agenda_ready`).
- **US5** necesita T004.
- **Cierre** al final; T042 va dentro del commit de cada tarea que cambia lo documentado.

## En paralelo

- Fase 2: T003, T005, T006, T007 y T009 a la vez (pruebas en archivos distintos).
- US1: T011, T012 y T016 a la vez; luego T013 → T014 → T015, y T017 en paralelo con la API.
- US3: T024, T025 y T029 a la vez; T026 y T030 en paralelo (API y consola).
- US4: T031, T033 y T035 a la vez.
- Historias: tras la Fase 2, US1, US2, US4 y US5 no comparten archivos de implementación, salvo `review.py` (US2 y US4: hacerlas una detrás de otra).

## Estrategia

1. **MVP = Fase 2 + US1 + US2.** Un cliente nuevo crea su agente con agenda en un paso, y la consola deja de mentir. Es lo que habría evitado lo de Spa Jemma.
2. **US3**: los agentes que ya existen y la propuesta de texto.
3. **US4**: publicar sin esperar a que el cliente termine de configurar.
4. **US5**: Acceso deja de tocar a quien no da citas.

Cada historia se fusiona a `develop` por separado, con su parte de documentación, y se prueba en staging antes de la siguiente.
