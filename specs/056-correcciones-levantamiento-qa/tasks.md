---
description: "Tareas de la spec 056: correcciones del levantamiento QA de la consola del cliente"
---

# Tareas: Correcciones del levantamiento QA de la consola del cliente

**Entrada**: `specs/056-correcciones-levantamiento-qa/` (spec, plan, research, data-model, contracts, quickstart)

**Pruebas**: obligatorias (constitución §VII). Cada bloque empieza por su prueba, que se ve en rojo antes de implementar. Ninguna hace `skip`. La de staging (T019) es `manual_only` y no cuenta como cubierta en CI.

**Reglas de este repo**:
- Cada tarea termina con `_Requisitos: n.m_`.
- Al entregarla se anota `Entregado: commit <sha> (rama 056-correcciones-levantamiento-qa)`.
- Las pruebas de API y worker van **una suite cada vez**, con una base propia (`NEXUS_DATABASE_URL=…/nexus_test_056`), y solo las de lo tocado ([[suites-completas-solo-al-final]]).
- Textos de la consola sin punto y coma (`words.test.ts`).

**Paquetes** (plan, «Orden de trabajo»):
- **A**: el freno.
- **B**: módulos y Acceso.
- **C**: horario, servicios y pulido de Reservas.
- **D**: Bandeja y transversales.

Los archivos de cada paquete son suyos. `i18n/messages.ts` y `lib/backend.ts` son de B.

## Formato: `[ID] [P?] [Historia] Descripción`

---

## Fase 1: Preparación

- [x] T001 Comprobar la base antes de tocar nada:
  - la rama es `056-correcciones-levantamiento-qa`;
  - `cd apps/api && uv run alembic heads` da solo `0222_merge_0220_heads`;
  - crear la base `nexus_test_056`.

  Si la cabeza no es esa, parar y avisar.
  _Requisitos: —_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

---

## Fase 2: Base (bloquea todo lo demás; la hace una sola mano)

**⚠️ Ninguna historia empieza hasta que esta fase esté en verde.** Las migraciones van en este orden exacto (`data-model.md`).

- [x] T002 Migración `apps/api/alembic/versions/0223_booking_unbacked_reason.py` (`down_revision = "0222_merge_0220_heads"`):
  - rehace `ck_conversations_waiting_reason` añadiendo `booking_unbacked`;
  - añade `booking_unbacked` a `WAITING_REASONS` en `apps/api/src/nexus_api/db/models/conversation.py:67`, **no** a `GATE_REASONS`.

  Prueba primero: `apps/api/tests/integration/test_migration_0223_booking_unbacked_reason.py`. El CHECK acepta el motivo nuevo y rechaza uno inventado.
  _Requisitos: 1.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T003 Migración `0224_client_modules_retire.py` (`down_revision = "0223_booking_unbacked_reason"`):
  - `UPDATE client_access SET modules = array_remove(array_remove(modules,'agents'),'business'), updated_at = now(), updated_by = 'system:spec_056' WHERE modules && ARRAY['agents','business']::varchar[]`;
  - después, `enabled = false` donde quede `modules = '{}'`;
  - rehace `ck_client_access_modules` con `panel`, `inbox`, `reservas` y `usage`, como en `0198_lite_and_corrections.py:120-126`.

  En `apps/api/src/nexus_api/db/models/client_access.py`:
  - `CLIENT_MODULES = ("panel","inbox","reservas","usage")`;
  - se añade `RETIRED_CLIENT_MODULES = ("agents","business")`;
  - se borra `CONSOLE_V2_MODULES`.

  Prueba primero: `tests/integration/test_migration_0224_client_modules_retire.py`, con el patrón de `test_migration_0204…`:
  - `{panel,agents,business}` queda en `{panel}`;
  - `{agents}` queda apagado y vacío;
  - el CHECK rechaza `agents`.
  _Requisitos: 2.1, 2.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T004 Migración `0225_client_access_audit_actor.py` (`down_revision = "0224_client_modules_retire"`):
  - reescribe `summary_es`/`summary_en` de `client_access.updated`, `client_member.invited`, `client_member.resent` y `client_member.revoked` (sembradas en `0148_client_audience_vocab.py:30-66`) de «Auphere …» a «{actor} …»;
  - siembra `agent.booking_brake`, `correction.batch_accepted` y `correction.batch_discarded` con frase es/en.

  Prueba: ampliar `apps/api/tests/unit/test_console_audit_words.py`.
  _Requisitos: 3.8, 1.5, 9.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T005 Migración `0226_correction_batches.py` (`down_revision = "0225_client_access_audit_actor"`):
  - `inbox_corrections.batch_id uuid NULL`;
  - **FK compuesta** `(tenant_id, batch_id) → inbox_corrections(tenant_id, id)` ([[fk-no-pasa-por-rls]]);
  - índice `(tenant_id, batch_id) WHERE batch_id IS NOT NULL`;
  - el campo en `apps/api/src/nexus_api/db/models/inbox_correction.py`.

  Prueba: `tests/integration/test_migration_0226_correction_batches.py`. Un `batch_id` de otro tenant viola la FK.
  _Requisitos: 9.1_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T006 Migración `0227_notice_handled.py` (`down_revision = "0226_correction_batches"`):
  - `console_notifications.handled_at timestamptz NULL`;
  - índice parcial `((payload->>'conversation_id')) WHERE kind = 'inbox.waiting' AND handled_at IS NULL`;
  - el campo en `apps/api/src/nexus_api/db/models/console_notification.py`.

  Prueba: `tests/integration/test_migration_0227_notice_handled.py`.
  _Requisitos: 8.1_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T007 Permiso `client_access:manage = ["owner","admin"]`:
  - en `PERMISSIONS` de `apps/api/src/nexus_api/core/console_auth.py:97-150`;
  - en su copia de `apps/console/src/lib/permissions.ts`;
  - en `API_MAP` de `apps/console/src/lib/__tests__/permissions.test.ts:10-41`;
  - una fila en `apps/console/src/components/team/roles-table.tsx` con su clave de texto y su prueba.
  _Requisitos: 3.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T008 [P] Reglas compartidas en Python: `apps/api/src/nexus_api/services/business/rules.py`.
  - Turnos de 0 a 6 por día (`MAX_SHIFTS_PER_DAY`).
  - Paso de 5 minutos, con 24:00 válido como cierre.
  - Nocturnos sin solape, tampoco con el día siguiente.
  - Duración de 5 a 480 en pasos de 5.
  - `PRICE_KINDS` none, free y amount.
  - Importe en unidades menores, de 0 a 10¹² (`AMOUNT_MAX_MINOR = 10**12`).
  - Categoría de 40 como máximo.
  - Nombre de 1 a 120.

  Reexporta las constantes de los modelos. Prueba primero: `apps/api/tests/unit/test_business_rules.py`. Los límites de `reservas_schemas` y `schemas_business_sections` salen de este módulo, de modo que importarlos y comparar da igual.
  _Requisitos: 5.1, 5.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T009 [P] Las mismas reglas en TypeScript: `apps/console/src/lib/business-rules.ts`, con prueba en `apps/console/src/lib/__tests__/business-rules.test.ts`. Mismos valores que T008. Un comentario en cada archivo apunta al otro.
  _Requisitos: 5.1, 5.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T010 [P] Mover `REASONS` y `reasonKey` (`apps/console/src/components/builder/improve-model.ts:54-76`) a `apps/console/src/lib/waiting-reasons.ts`, y añadir `inboxReasonText(raw, t)`:
  - un código conocido da el texto de la tabla;
  - un código desconocido o `escalated` da `inbox.event.escalated` («El agente pidió ayuda»);
  - el texto libre sale tal cual.

  Añadir las claves `waiting.reason.booking_unbacked` («El agente dio por hecha una cita que no existe») y `waiting.reason.out_of_audience` en `apps/console/src/i18n/lanes/agent-improve.ts`. Prueba: `apps/console/src/lib/__tests__/waiting-reasons.test.ts`. `improve-model.ts` reimporta de la nueva ubicación.
  _Requisitos: 7.1, 7.2, 7.3_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T011 [P] `apps/console/src/lib/amount.ts`:
  - `minorDigits`;
  - `formatAmount({amount_minor, currency}, locale)` con Intl `style: "currency"`, que da «10,00 US$» en español;
  - `parseAmount(text, currency)`, que acepta coma o punto y «1.234,56», con el tope 10¹² → `amount_too_large`;
  - `amountInput(minor, currency, locale)`.

  `apps/console/src/lib/money.ts:formatMoney` delega en `formatAmount`. Prueba: `apps/console/src/lib/__tests__/amount.test.ts`, con es, en, EUR, USD, COP y CLP.
  _Requisitos: 13.1, 13.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

**Punto de control**: `alembic heads` da `0227_notice_handled` sola. Las pruebas de T002–T011 están en verde.

---

## Fase 3: Historia 1, el freno de citas (P1) 🎯 MVP · Paquete A

**Objetivo**: ninguna respuesta da por hecha una reserva sin una reserva real en la conversación.

**Prueba independiente**: con la herramienta de reservar fallando, el agente no confirma (`quickstart.md` §1).

### Pruebas (en rojo primero)

- [x] T012 [P] [US1] `apps/worker/tests/unit/test_booking_brake.py`, con funciones puras:
  - el filtro en es, en y pt detecta las afirmaciones, y no «¿quieres que te reserve?» ni «no pude reservar»;
  - el predicado de respaldo, con todos los casos de la tabla de `research.md` R1: un `reservas.create` con `status: ok` y `refused` **no** respalda; `answer_offer` solo con `booked`; un error de Composio y el enlace de Calendly no respaldan; `dry_run` y `replayed` sí; `approval_*` no.
  _Requisitos: 1.1, 1.3_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T013 [P] [US1] `apps/worker/tests/unit/test_pipeline_booking_brake.py`, con el patrón de `test_pipeline_router.py` (`InMemoryProvider` + `tool_responder`):
  - una afirmación sin respaldo lleva `BOOKING_BRAKE_NOTE` en la segunda llamada;
  - dos afirmaciones dan `turn_failure.reason == "booking_unbacked"` y `_handoff_line`;
  - con una reserva `ok` hay cero llamadas de clasificación;
  - un fallo del clasificador cuenta como afirmación;
  - se comprueban `interactive_payload` y el borrador que reescribe el revisor;
  - vale igual para un agente legado y para uno estructurado.
  _Requisitos: 1.1, 1.2, 1.4_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T014 [US1] `apps/api/tests/integration/test_booking_brake_turn.py`, con el patrón de `test_react_final_answer.py:106-162` (`_turn_world`, `process_inbound`):
  - `conversations.waiting_reason == "booking_unbacked"`;
  - una fila `agent.booking_brake` con `outcome`, sin texto;
  - **el cobro de la llamada `classify` dentro del turno** (patrón `worker/tests/unit/test_multimodal_metering.py`, `drain_for_tests`);
  - con Bandeja, el agente se pausa en esa conversación.
  _Requisitos: 1.2, 1.5, 1.6_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T015 [P] [US1] Aislamiento (garantía 8): `apps/api/tests/isolation/test_056_booking_brake_same_conversation.py`. Una reserva viva de **otra** conversación del mismo tenant, o de otro tenant, no respalda la afirmación.
  _Requisitos: 1.1_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

### Implementación

- [x] T016 [US1] En `apps/api/src/nexus_api/api/console/capability_names.py:969-1015`, añadir `GOOGLECALENDAR_QUICK_ADD` y `GOOGLECALENDAR_UPDATE_EVENT`. Crear `apps/worker/src/nexus_worker/runtime/booking_brake.py` con:
  - el filtro regex sin tildes;
  - `is_backed(envelopes)` por herramienta;
  - `load_conversation_backing(session, conversation_id, since)`, con las salidas desde `attended_at` y las `reservations` con ese `conversation_id` en `LIVE_STATUSES`;
  - `claims_booking(llm, bundle, text)`, que llama a `llm.classify` con `chain_for(..., "classify", ...)`, con el borrador como `user` y falla cerrado.

  El medidor entra solo, por el rol `classify` dentro del `usage_turn`.
  _Requisitos: 1.1, 1.3, 1.6_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T017 [US1] Integrar en `make_handler_node` (`apps/worker/src/nexus_worker/runtime/pipeline.py`, tras `:2153`):
  - el bucle de `:1921-2151` pasa a dos intentos, el segundo con el borrador como `assistant` y `BOOKING_BRAKE_NOTE` como `system`;
  - si el segundo también afirma, texto `_handoff_line(state)`, sin `interactive_payload` y con `turn_failure = {"kind":"handoff","reason":"booking_unbacked","detail":None}`;
  - se salta con `turn_failure`, `reception_handoff` o sin texto;
  - se vuelve a comprobar tras la reescritura del revisor (`:2617`) y, si afirma, sale `GRADER_FALLBACK_RESPONSE`.
  _Requisitos: 1.2, 1.4_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T018 [US1] En `apps/worker/src/nexus_worker/runtime/dispatcher.py`:
  - `_ROUTER_REASONS` (`:481`) acepta `booking_unbacked`, que sigue a `mark_waiting_reason` por `_apply_gate(fresh=False)`;
  - con Bandeja, pausar al agente en la conversación como `reception.py:229-232`;
  - una fila de auditoría `agent.booking_brake` en sesión propia y de mejor esfuerzo, como `_record_router_anomaly` (`:857`), con `after = {agent_id, turn_id, outcome}`;
  - un evento de log `booking.brake` (sin campo `result`).
  _Requisitos: 1.2, 1.5_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T019 [US1] Punta a punta: `apps/api/tests/release/test_booking_brake_staging.py`, marcada `manual_only` y con las fixtures de `release/conftest.py`.
  - Webhook de Meta firmado a staging (`docs/qa-canales-meta-2026-10-30/07-webhooks-a-staging.md`).
  - Agente de pruebas con Reservas sin horario, así que `refused: hours_missing`.
  - 20 intentos sin una confirmación en el saliente.

  Se ejecuta tras desplegar a staging, no en CI.
  _Requisitos: 1.7_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T020 [US1] Documentos:
  - `specs/047-la-fabrica-de-agentes/contracts/events.md`: §2 `booking_unbacked`, §4 `agent.booking_brake` y §5 `booking.brake`, como en `contracts/events.md` de esta spec;
  - `docs/agentes.md`, sección del freno;
  - `docs/modelos-y-router.md`, la llamada `classify` extra.
  _Requisitos: 1.5, 17.1_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

**Punto de control**: T012–T015 en verde. `quickstart.md` §1 (unidad e integración).

---

## Fase 4: Historia 2, Agentes y Negocio fuera del cliente (P1) · Paquete B

**Objetivo**: ninguna persona de cliente ve ni alcanza Agentes ni Negocio.

**Prueba independiente**: `quickstart.md` §2.

- [x] T021 [US2] Pruebas en rojo:
  - pasar a afirmar la retirada:
    - `apps/api/tests/integration/lite/test_lite_agents_business.py` (las 16 rutas dan el 403 de módulo ausente);
    - `tests/unit/test_console_identity_client.py:92`;
    - `tests/unit/test_lite_me_nav.py:36-39`;
    - `tests/isolation/test_lite_client_vs_client.py:70,300-306`;
    - `tests/integration/test_dev_seed_fabrica.py:204,244`;
  - añadir que `PUT /admin/tenants/{id}/client-access` con `agents` da 422 `unknown_module`;
  - las pruebas del partner sobre agentes y ficha no se tocan y siguen en verde: pausar y reanudar, y editar horario, servicios y sedes (`tests/integration/business/*` y las de agentes del partner). Se corren en T059.
  _Requisitos: 2.1, 2.3, 2.5, 2.9_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T022 [US2] API:
  - quitar los `also=CONSOLE_V2_MODULES` de `apps/api/src/nexus_api/core/client_auth.py:197-202` y `services/console_identity.py:333-338`;
  - `require_client_principal` (`core/client_auth.py:336-346`) acepta `RETIRED_CLIENT_MODULES` y responde siempre `_forbidden()`;
  - `services/client_access.py:262` rechaza los retirados con `unknown_module`;
  - el seed `apps/api/scripts/dev_seed_fabrica.py:90` deja de guardarlos.

  Las rutas del partner no cambian.
  _Requisitos: 2.1, 2.3, 2.5, 2.9_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T023 [US2] Avisos:
  - `LITE_LINKS` (`apps/api/src/nexus_api/api/console/notifications.py:150-156`) pierde `agent.*` y `channel.*`;
  - el push `agents.state` enlaza a `auphere-customers://home` (`services/push_payloads.py:97-100`, `push_fanout.py:373`) y sigue saliendo.

  Pruebas: las de push existentes, más una que fije el enlace.
  _Requisitos: 2.6, 2.7_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T024 [US2] Consola:
  - quitar `agents` y `business` de:
    - `apps/console/src/components/shell/lite-nav.ts`;
    - `src/lib/principal-access.ts` (`ClientModule`, `CLIENT_MODULE_PATH`, `clientModuleOfPath`);
    - `components/shell/lite-notifications-bell.tsx:56`;
  - borrar `src/app/(console)/agentes/`, `src/app/(console)/negocio/`, `components/lite/lite-agents.tsx` y `components/lite/lite-business.tsx`, con sus pruebas;
  - **antes de borrar** `i18n/lanes/lite-agents.ts`, mover sus claves de «Corregir esta respuesta» a la lane de la Bandeja y borrar las huérfanas.

  Actualizar `lite-nav.test.ts`, `lite-bell-links.test.ts`, `app/__tests__/page-guards.test.ts:61` y `inbox/__tests__/design-045.test.tsx`. Pasar `src/i18n` entero (`no-orphan-keys`, `words`).
  _Requisitos: 2.1, 2.4_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T025 [P] [US2] Panel: `apps/admin/src/app/(dashboard)/tenants/[id]/access/access-form.tsx:31,64-68` deja de conservar `agents` y `business` (fuera la lógica `kept`). También `messages.ts:38-39`, `apps/admin/src/lib/backend.ts:36` y `__tests__/access-form.test.tsx:68-69`.

  El panel conserva su pestaña. Sus reglas son las del servicio compartido, las mismas que usa el partner (T031): `no_modules`, `inbox_requires_whatsapp`, el modo de Reservas y `unknown_module`.
  _Requisitos: 2.3, 3.9_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T026 [P] [US2] App:
  - `apps/mobile/src/app/+native-intent.tsx:19` manda `agents/*` a `"/"`;
  - borrar `app/agente`, `app/negocio`, `features/agents` y `features/business`;
  - quitar las invalidaciones de `keys.business` en `app/conversacion/[id]/corregir.tsx:110-133`.

  Pruebas: `__tests__/{agentes,negocio}.test.tsx` se borran; `inicio`, `push` y `fabrica-avisos` se actualizan. Sale en la próxima versión. Lo demás ya lo hace la API.
  _Requisitos: 2.6_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T027 [US2] Documentos: `docs/consola-lite.md` («Lo que la spec 047 cambió aquí (ola 8)» → enmendado por la 056, y el apartado «Acceso desde el admin»), `docs/app-movil.md` y `docs/admin.md`.
  _Requisitos: 17.1_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

**Punto de control**: T021 en verde. `quickstart.md` §2.

---

## Fase 5: Historia 3, el Acceso desde la consola de partners (P1) · Paquete B

**Objetivo**: owner y admin del partner encienden la consola de su cliente, eligen módulos e invitan, como el panel (D3).

**Prueba independiente**: `quickstart.md` §3.

### Pruebas (en rojo primero)

- [x] T028 [P] [US3] Aislamiento (garantía 1 y C8):
  - nuevo `apps/api/tests/isolation/test_console_client_access_scope.py`:
    - el `member_id` de un cliente de otro partner pedido con el `ref` propio da 404;
    - builder, analyst y billing reciben 403;
    - ninguna respuesta trae conversaciones, contactos ni texto de avisos;
  - en `tests/isolation/test_console_scope.py`, `_minimal_body` (`:430-486`) gana PUT `{"enabled": false, "modules": []}` y POST `{"email": "x@example.com"}`.
  _Requisitos: 3.10, 4.1, 4.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T029 [P] [US3] Integración: `apps/api/tests/integration/console/test_client_access_partner.py`.
  - El owner enciende Panel y Reservas con su modo, y la auditoría dice `console:<correo>` y la frase «{actor} cambió…».
  - `agents` da 422.
  - La Bandeja sin WhatsApp da 422.
  - Un cambio de modo con reservas futuras da 409 `live_reservations`.
  - Invitar devuelve `accept_url` y `email_sent`.
  - Un correo de un miembro del partner da 409 `account_is_partner_member`.
  - Revocar cierra sesiones y teléfonos.
  - Por encima de `console_client_invites_per_minute`, 429.
  _Requisitos: 3.3, 3.4, 3.6, 3.7, 3.8_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T030 [P] [US3] Consola:
  - `apps/console/src/app/(console)/clients/[ref]/access/__tests__/actions.test.ts`, con `actionHarness`: owner y admin pueden; builder, analyst, billing y cliente reciben `h.denied()`;
  - `components/clients/v2/__tests__/client-header-v2.test.tsx`: la pestaña existe con `canManageAccess` y no existe sin él;
  - la página da `notFound()` sin permiso;
  - las filas tienen una sola acción a la vista, el resto en «⋯» y «Revocar» al final, en rojo y con confirmación.
  _Requisitos: 3.1, 3.2, 3.5_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

### Implementación

- [x] T031 [US3] API:
  - los esquemas de `apps/api/src/nexus_api/api/admin/client_access.py:52-162` pasan a un módulo compartido (`api/schemas_client_access.py`), con una salida de partner sin `partner`;
  - router nuevo `apps/api/src/nexus_api/api/console/client_access.py`, montado en `api/console/__init__.py` como `client_bags`, con las cinco rutas de `contracts/api.md`;
  - en cada ruta: `require_console_principal("client_access:manage")`, `resolve_mapping`, `async with session.begin(): await declare_tenant(...)` y la comprobación de que el partner del acceso es el del principal, si no `unknown_client()`;
  - `actor = principal.actor`, y `_send` tras el commit, como el panel;
  - el límite `core.rate_limit.allow(... key=f"console:client_invite:{partner_id}", per_minute=settings.console_client_invites_per_minute ...)`, con su setting en `apps/api/src/nexus_api/config.py` (por defecto 5).
  _Requisitos: 3.3, 3.4, 3.6, 3.7, 3.8, 3.10, 4.1, 4.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T032 [US3] Pestaña:
  - `apps/console/src/components/shell/routes-v2.ts:7` añade `"access"`;
  - `components/clients/v2/client-header-v2.tsx` (`TABS`, `activeTab`) recibe `canManageAccess`;
  - `app/(console)/clients/[ref]/layout.tsx:48` se lo pasa con `can(principal.role, "client_access:manage")`;
  - `components/shell/crumbs-v2.ts`;
  - clave `clients.v2.tab.access` («Acceso» / «Access») en `i18n/lanes/business.ts:305-307`.
  _Requisitos: 3.1, 3.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T033 [US3] Página y acciones:
  - `app/(console)/clients/[ref]/access/{page,actions}.ts(x)`: la página copia `business/page.tsx:35-68`, con `notFound()` sin permiso; las acciones usan `backendFor(principal)`, con los métodos nuevos en `lib/backend.ts`;
  - componentes en `components/clients/access/`:
    - `client-console-card.tsx`: interruptor, módulos, modo de Reservas y el diálogo de reservas vivas, portados de `apps/admin/.../access-form.tsx`;
    - `client-people-card.tsx`: lista con estado; acción principal por estado (Reenviar para invitada o caducada); «⋯» con `DropdownMenuItem variant="destructive"` «Revocar» al final; `ConfirmDialog returnFocus`; aviso con `accept_url` una sola vez. Patrón `connector-model.rowLayout`;
  - lane nueva `i18n/lanes/client-access.ts`, registrada en `i18n/messages.ts`;
  - los cinco estados de cada tarjeta: cargando, vacío, error, parcial e ideal.
  _Requisitos: 3.3, 3.4, 3.5, 3.6, 3.7_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T034 [US3] Documentos:
  - `docs/console.md`, sección nueva «Acceso del cliente»;
  - `docs/consola-lite.md`: «Acceso desde el admin» pasa a «Acceso, desde el panel o desde la consola de partners», con el **riesgo aceptado en D3** dicho tal cual;
  - `docs/admin.md`.
  _Requisitos: 4.3, 17.1_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

**Punto de control**: T028–T030 en verde. `quickstart.md` §3.

---

## Fase 6: Historia 4, horario y servicios con las mismas reglas (P2) · Paquete C

**Objetivo**: ficha y Reservas aceptan lo mismo y no pisan lo que no se tocó.

**Prueba independiente**: `quickstart.md` §4 (CE-005).

- [x] T035 [P] [US4] API en rojo: ampliar `apps/api/tests/integration/reservas/test_api_services.py` (`:275` CRUD, `:330` horario).
  - Un lunes con tres turnos y un nocturno sobrevive a un PATCH del martes.
  - El horario propio de una sede no cambia.
  - Un servicio de 50 minutos cambia de precio.
  - «Gratis» se conserva.
  - Renombrar da 422 `rename_not_allowed`.
  - 10¹² + 1 da `amount_too_large`.
  - Una categoría de 41 caracteres da `category_too_long`.
  - Un conflicto de revisión da 409.

  Más un `tests/unit/test_reservas_rules_parity.py` con los esquemas contra `rules.py`.
  _Requisitos: 5.1, 5.2, 5.3, 5.4, 5.6_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T036 [P] [US4] Consola en rojo:
  - `components/reservas/model/__tests__/hours.test.ts`: `changedDays`, y que el «Revísalo» sale con minutos no múltiplo de 5;
  - `components/reservas/__tests__/waitlist-and-settings.test.tsx`:
    - solo se envían los días tocados;
    - el nombre no se puede editar al editar;
    - los tres tipos de precio;
    - duraciones de 5 a 480;
    - un 422 se pinta en su campo, nunca «No se pudo hablar con el servidor»;
  - `app/(console)/reservas/__tests__/actions.test.ts`.
  _Requisitos: 5.3, 5.4, 5.5, 5.6_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T037 [US4] API, `apps/api/src/nexus_api/api/console/lite/reservas.py` y `reservas_schemas.py`:
  - `SettingsOut.hours` con la forma de la ficha (`hours_view`) y `location_hours`;
  - `PATCH /business-hours` con solo los días tocados y `revision`, que sustituye esos días, recalcula el layout (blocks o daily) y llama a `save_week(expected_revision=…)`; las reglas estrictas solo en esos días;
  - los servicios se crean y se editan por `services_catalog.create_service`/`update_service`;
  - `ServiceOut.price` y `PriceIn`;
  - `rename_not_allowed`;
  - los límites salen de `rules.py`; la categoría pasa a 40 en `reservas_schemas.py:168,180` y en `schemas_business_sections.py`.
  _Requisitos: 5.1, 5.2, 5.3, 5.4_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T038 [US4] Consola:
  - sacar el editor de turnos de la ficha (`components/business/sections/shift-editor.tsx` + `hours-model.ts`) a un componente puro;
  - `components/reservas/settings/hours-editor.tsx` lo usa, con `changedDays`, la sede con horario propio solo de lectura y «Revísalo»;
  - `services-settings.tsx`: precio Sin precio, Gratis o Importe; duraciones de `business-rules.ts`; solo lo cambiado; nombre de solo lectura al editar;
  - `app/(console)/reservas/actions.ts`: `safeParse` → `{status: 422, code, field}` y errores traducidos en `business.services.error.*`.
  _Requisitos: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T039 [US4] Documentos: `docs/reservas.md` y `docs/ficha-del-negocio.md` (las reglas compartidas y el PATCH por días).
  _Requisitos: 17.1_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

**Punto de control**: T035–T036 en verde. `quickstart.md` §4.

---

## Fase 7: Historia 5, la Bandeja dice la verdad (P2) · Paquete D

**Objetivo**: «Abiertas», motivos legibles, avisos que se cierran y correcciones con el alcance real.

**Prueba independiente**: `quickstart.md` §5.

### Pruebas (en rojo primero)

- [x] T040 [P] [US5] API:
  - `apps/api/tests/unit/test_lite_inbox_list.py`: con 2 cerradas y 0 abiertas, `resolved == 2`;
  - nuevo `tests/integration/lite/test_lite_waiting_notice_handled.py`, parametrizado por `take_over`, `give_back`, `resolve`, `archive`, `release_reason` y `release_escalated_for_tenant`:
    - `unread-count` pasa de 1 a 0;
    - un escalado nuevo abre un aviso pendiente;
    - otro cliente del mismo partner no se toca.
  _Requisitos: 6.2, 8.1, 8.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T041 [P] [US5] Correcciones (C8 en el lote):
  - ampliar `apps/api/tests/integration/improvement/test_corrections.py`: «Todo el negocio» con dos agentes `published` y uno `paused` da tres correcciones con el mismo `batch_id`; un borrador no entra; «Solo este agente» da una;
  - nuevo `test_correction_batch_accept.py`: aceptar el lote aplica las tres en una transacción;
  - ampliar `tests/isolation/test_52_partner_never_sees_bodies.py` con el lote;
  - una corrección de **dato** con «Todo el negocio» se sigue guardando como pregunta frecuente de la ficha aunque el cliente ya no tenga Negocio.
  _Requisitos: 2.8, 9.1, 9.2, 9.3_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T042 [P] [US5] Consola:
  - `components/inbox/__tests__/inbox-list.test.tsx`: estado vacío con resueltas y botón a Resueltas; sin ninguna, sin botón;
  - pruebas de `thread`, `composer`, `conversation-row` y la actividad con `agent_unpublished` → «Agente sin publicar» y con un código desconocido → genérico;
  - `builder/__tests__/agent-improve.test.tsx`: el lote.
  _Requisitos: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 9.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

### Implementación

- [x] T043 [US5] API: `resolved: int` en `ListPage` (`apps/api/src/nexus_api/services/inbox_view.py`) y en `ConversationPageOut` (`api/console/lite/inbox.py:128-133,494`). Se calcula solo con `flt == "all"`, sin búsqueda ni filtro y con la página vacía. `has_any` se queda.
  _Requisitos: 6.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T044 [US5] API:
  - `mark_waiting_handled(...)`, llamado tras el commit:
    - en `take_over` y `give_back` (`lite/inbox.py:639-712`, `scope.after_commit`);
    - en `inbox_lifecycle.resolve` (`:327-344`) y `release_reason` (`:255-273`);
    - en `release_escalated_for_tenant` (`:385-417`);
    - en el worker (`dispatcher.py:929`) y en `client_access.py:304`;
  - en `api/console/notifications.py:79-90,203-209`, `_read_expr` y `_unread_count` excluyen lo atendido;
  - `NotificationOut.handled`.
  _Requisitos: 8.1, 8.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T045 [US5] API, lotes de corrección:
  - `services/improvement/corrections.py:283,354-425`: con alcance `business`, una hermana por cada agente `published` o `paused`, sin mirar el papel; las que no validan se saltan y quedan en `after_json` de `correction.proposed`; un solo aviso por lote;
  - `api/console/agent_improvement.py`: `ImprovementOut.batch {id, agents_count}` y `POST /console/clients/{ref}/corrections/{batch_id}/accept|discard` en una transacción, auditadas con `correction.batch_*`.
  _Requisitos: 9.1, 9.2, 9.3_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T046 [US5] Consola:
  - `inbox.filter.all` = «Abiertas» / «Open» e `inbox.empty.clear` nuevo (`i18n/lanes/inbox.ts`);
  - el estado vacío en `components/inbox/conversation-list.tsx:171-187`, con `resolved` y `onFilter("resolved")`;
  - `inboxReasonText` en `event-text.ts:26`, `thread.tsx:112`, `composer.tsx:74` y `conversation-row.tsx:105`, con el código de la columna primero;
  - la UI del lote en `components/builder/agent-improve*.tsx`;
  - el texto de los dos alcances del diálogo de corrección dice lo que pasa.
  _Requisitos: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 9.2, 9.4_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T047 [P] [US5] App:
  - estado vacío con resueltas en `apps/mobile/src/app/(app)/bandeja/index.tsx:116`;
  - motivos legibles en `features/inbox/model.ts:180-193` y `conversation-row.tsx:39`.

  Pruebas: `__tests__/bandeja.test.tsx`. La regeneración del contrato va en T058.
  _Requisitos: 6.2, 7.1, 7.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T048 [US5] Documentos: `docs/consola-lite.md`, «La Bandeja de entrada» (Abiertas, motivos, avisos atendidos, lotes).
  _Requisitos: 17.1_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

**Punto de control**: T040–T042 en verde. `quickstart.md` §5.

---

## Fase 8: Historia 6, pulido (P3) · Paquetes C y D

**Objetivo**: sin texto técnico, validación igual, confirmación de lo que no se deshace, un formato por cosa, acceso en un idioma, una 404 con salida y el aviso de la sesión.

Cada tarea lleva su prueba en rojo primero.

- [x] T049 [P] [US6] (D) Errores:
  - `ViewerKindProvider` en `ConsoleShellV1`;
  - `RouteError` (`apps/console/src/components/error-boundary.tsx:17-33`) no pinta `error.message` con un cliente, ni con nadie si hay `digest`;
  - nuevo `apps/console/src/app/error.tsx`.

  Prueba: `components/__tests__/error-boundary.test.tsx`.
  _Requisitos: 10.1_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T050 [US6] (D) Fallo de Reservas:
  - `apps/console/src/instrumentation.ts` con `onRequestError`, que registra en JSON `console.request_error` con `digest`, `route`, `route_type` y `cause_code`, sin `message`;
  - `session()` (`lib/backend.ts:809-820`) con un reintento y un tiempo límite;
  - Playwright `apps/console/e2e/reservas-period-switch.spec.ts`, de ejecución manual contra staging, con diez repeticiones.

  Si la causa aparece en el registro, se corrige en esta tarea.
  _Requisitos: 10.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T051 [P] [US6] (C) Validación:
  - `components/reservas/waitlist/add-waitlist-dialog.tsx`: `onBlur` y `disabled={!ready}`, como `booking-dialog.tsx`;
  - `EmailStr`, con 254 como máximo, en `api/console/lite/reservas_schemas.py:128,134`, y la consola a 254;
  - `date_past` en `services/business/special_dates.py:106,152` (`to < hoy` en la zona del negocio) y en `special-dates-section.tsx:166-180`;
  - `noValidate` en `business-sources.tsx:209`, `services-section.tsx:507` e `inbox/saved-replies.tsx:158`.

  Pruebas: `waitlist-and-settings.test.tsx`, `integration/business/test_hours_and_locations.py:303`, `special-dates-section.test.tsx` y `test_api_services.py`.
  _Requisitos: 11.1, 11.2, 11.3, 11.4, 11.5_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T052 [P] [US6] (C) Confirmaciones:
  - `ConfirmDialog` de `@nexus/ui` al archivar en `components/business/sections/services-section.tsx:152,168,239`, `locations-section.tsx:126` y `special-dates-section.tsx:112`;
  - confirmación en `components/business/history/section-history.tsx:143` («¿Deshacer “{kind}”?» con quién y cuándo);
  - `src/components/use-discard-guard.tsx`, aplicado en los nueve diálogos de Reservas de `research.md` R12.

  Pruebas junto a cada componente, más un `locations-section.test.tsx` nuevo.
  _Requisitos: 12.1, 12.2, 12.3_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T053 [P] [US6] (C y D) Formatos:
  - (C) llevar a `lib/amount.ts` las llamadas de `booking-detail.tsx:113`, `services-settings.tsx:315,370,376,456`, `services-section.tsx:36,126,322,337`, `services-model.ts:14-70` y `lite-spend-card.tsx:14,92`;
  - (D) `display_handle(identifier, channel)` con «+» en WhatsApp, en `services/inbox_view.py:409-410,695-696`.

  Pruebas: `services-model.test.ts`, `money.test.ts`, `tests/unit/test_lite_inbox_contact.py` y `test_lite_inbox_list.py`.
  _Requisitos: 13.1, 13.2, 13.3_
  Entregado (C): sin commit (rama 056-correcciones-levantamiento-qa).
  Entregado (D): sin commit (rama 056-correcciones-levantamiento-qa).
- [x] T054 [P] [US6] (D) Idioma y 404:
  - `getT()` en `apps/console/src/app/(auth)/layout.tsx:6`;
  - `src/i18n/__tests__/auth-pages-locale.test.ts:42-47` revisa todos los `.tsx` de `(auth)`;
  - nuevo `app/(console)/not-found.tsx` con menú y enlace a `firstModulePath`/`firstPartnerModulePath`;
  - `app/not-found.tsx` asíncrono con `resolvePrincipal()`: con sesión, un `ConsoleFrame` sacado de `(console)/layout.tsx:36-73`; sin sesión, «Entrar»;
  - claves traducidas, con «No existe o no es tuyo».

  Prueba: `app/__tests__/not-found.test.tsx`.
  _Requisitos: 14.1, 14.2, 14.3, 14.4_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T055 [P] [US6] (D) Sesión:
  - `resolve_session` (`services/console_identity.py:465-490`) devuelve `expires_at`, y `SessionOut.expires_at` (`schemas_auth.py:95`);
  - `PrincipalBase.sessionExpiresAt` (`apps/console/src/lib/principal-access.ts:118-146`);
  - `components/shell/session-expiry-notice.tsx`, montado en el layout raíz: toast con «Volver a entrar», una sola vez por `expiresAt` (localStorage en try/catch).

  Pruebas: `tests/unit/test_console_identity.py` (`expires_at` no se mueve) y el componente con temporizadores falsos (23 h: aviso; 3 días: nada; al volver a montar: no repite).
  _Requisitos: 15.1, 15.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T056 [P] [US6] (D) Vaciar y Eliminar: ampliar `apps/api/tests/integration/lite/test_lite_inbox_clear_archive.py`.
  - Eliminar → el contacto escribe por `worker/persistence/messages.py:144` y `dispatcher._mark_attended` → conversación nueva en «Abiertas» con solo el mensaje nuevo.
  - El actor de la auditoría es `client:<correo>`.
  - Los otros dos criterios ya los cubren `resolve.test.tsx:46-103` y `:49-87`.
  _Requisitos: 16.1, 16.2, 16.3, 16.4_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)

---

## Fase 9: Cierre

- [x] T057 Documentos que falten, revisados contra 17.1, y comprobar que la enmienda de ADR-041 en la KB enlaza `specs/056-correcciones-levantamiento-qa/` (17.2).
  _Requisitos: 17.1, 17.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T058 App: `cd apps/mobile && pnpm gen && pnpm gen:check`, con el contrato de `lite.gen.ts` (`resolved`, `handled`, `price`, `expires_at`). Después `pnpm test`.
  _Requisitos: 2.6, 6.2_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
- [x] T059 Verificación:
  - `./scripts/verify.sh lint`;
  - los archivos de prueba tocados o nuevos de la API y del worker, una suite cada vez y en la base propia;
  - `cd apps/console && pnpm typecheck && pnpm test` sobre lo tocado más `src/i18n` y los barridos de rutas lite;
  - `cd apps/admin && pnpm typecheck && pnpm test -- access`;
  - `next build` de la consola;
  - un grep de pruebas no tocadas que usen nombres quitados: `CONSOLE_V2_MODULES`, `lite-agents`, `lite-business`, `price_minor` en Reservas, `clear_price`.
  _Requisitos: todos_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa)
  Queda en rojo, y también en `develop` (no es de la 056): `tests/integration/clients/test_client_read_job.py::test_what_was_read_is_proposed_for_review` (el «Corte de pelo» leído de la web queda con `price_kind = 'none'` en vez de `amount` 1500; sin diagnosticar).
- [x] T060 Comprobar en local lo que se pueda de `quickstart.md`, marcar el checklist y entregar a Luis los mensajes de commit por paquete.
  _Requisitos: —_
  Entregado: sin commit (rama 056-correcciones-levantamiento-qa). Quedan para staging T019 y el Playwright de 10.2.

---

## Dependencias y orden

- **Fase 1 → Fase 2 → Fases 3 a 8 → Fase 9.**
- **Dentro de la Fase 2**: T002 → T003 → T004 → T005 → T006, en serie por la cadena de Alembic. T007 a T011 van en paralelo con ellas.
- **Historias**:
  - US1 (A), US2 + US3 (B), US4 (C) y US5 (D) son independientes entre sí tras la Fase 2.
  - US3 depende de T007 y T004.
  - US5 depende de T005, T006 y T010.
  - US6 se reparte entre C y D y solo depende de la Fase 2 (T011 para T053).
- **Archivos compartidos**:
  - `i18n/messages.ts` y `lib/backend.ts` solo los edita B; D y C usan `lib/backend/*.ts` por módulo.
  - `inbox_view.py` es de D, también para T053-D.
  - `services-section.tsx` es de C.
  - `notifications.py`: `LITE_LINKS` es de B (T023) y `_read_expr` es de D (T044). Son regiones distintas: el que llegue segundo vuelve a leer el archivo.

## Paralelismo

- **Paquete A**: T012, T013 y T015 juntas → T014 → T016 → T017 → T018 → T019 → T020.
- **Paquete B**: T021 → T022 y T023 → T024, más T025 y T026 en paralelo → T027; luego T028, T029 y T030 juntas → T031 → T032 → T033 → T034.
- **Paquete C**: T035 y T036 juntas → T037 → T038 → T039; luego T051, T052 y T053-C.
- **Paquete D**: T040, T041 y T042 juntas → T043 → T044 → T045 → T046 → T047 → T048; luego T049, T050, T053-D, T054, T055 y T056.

## Estrategia

- **MVP**: Fase 2 + Historia 1 (el freno). Es lo único que engaña a un cliente final.
- **Después**: Historias 2 y 3 (lo que pidió el owner), luego la 4 (pérdida de datos), la 5 y por último la 6.
- Cada historia se puede desplegar sola en staging: ninguna depende de otra salvo por la Fase 2.
