---

description: "Tareas de la spec 058 — la pausa respeta la audiencia"
---

# Tasks: La pausa respeta la audiencia

**Input**: Design documents from `/specs/058-pausa-respeta-audiencia/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/turn-gates.md](contracts/turn-gates.md)

**Tests**: obligatorios (constitución §VII). Cada bloque de tests se escribe y se
ve en rojo antes de su implementación.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero (§VII)**: rojo antes que implementación.
- **Aislamiento (§I)**: la spec declara la garantía 1, rozada por la limpieza. Va en T002.
- **Licencias (§VIII)**: no entra ninguna dependencia.
- **Medidor**: no se gasta nada.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: la historia de la spec (US1, US2, US3)

---

## Phase 1: Setup

**Propósito**: saber que el punto de partida está en verde, para que cualquier
rojo posterior sea de este cambio y no de antes. Suites de una en una: dos a la
vez comparten base y dan rojos falsos.

- [x] T001 Correr en `develop` las suites que ya cubren las puertas y anotar el resultado aquí: `apps/api/tests/integration/test_dispatcher_persist_first.py`, `apps/api/tests/integration/test_dispatcher_reason_notices.py`, `apps/api/tests/integration/lite/test_lite_waiting_notice_handled.py` y `apps/worker/tests/unit/test_dispatcher_out_of_quota.py`
      _Requisitos: 1.4_
      Resultado (2026-11-10, `develop` `10897b90`): 17, 6, 7 y 3 en verde.

---

## Phase 2: Foundational

No aplica. No hay esquema, modelo ni infraestructura compartida que preparar. Cada
historia toca sus propias funciones.

---

## Phase 2b: Las puertas de la constitución

- [x] T002 Test de aislamiento de la limpieza en `apps/api/tests/isolation/test_058_audience_cleanup_per_tenant.py`. Hay dos clientes (`console_world` `a` y `b`) con la misma forma: partner con la consola nueva, número «Solo mi equipo», cliente en pausa y una conversación en espera `paused_client` de un contacto fuera de la audiencia, con su aviso `inbox.waiting`. Lanzar la limpieza de verdad **solo para el tenant A** (`audience_cleanup.release_tenant`) deja la de B en `escalated` y su aviso sin atender, aunque tengan la misma forma. Además, `run(apply=True)` sobre los dos libera cada una en su tenant y no cruza avisos. Rojo hasta T011 (§I).
      _Requisitos: 3.1, 3.3_
- Licencias: **no aplica**. El plan no instala nada (research D7).
- Medidor: **no aplica**. Ni modelo, ni reloj de máquina, ni herramienta de pago (research D7).

**Checkpoint**: las puertas tienen dueño.

---

## Phase 3: User Story 1 — Pausar no llena la Bandeja de contactos a los que el número no responde (Priority: P1) 🎯 MVP

**Goal**: con un contacto fuera de la audiencia, el motivo es `out_of_audience`
aunque haya pausas. No hay Bandeja ni avisos.

**Independent Test**: un cliente en pausa con un número «Solo mi equipo». Un
contacto que no es de prueba no abre espera ni genera aviso. Un número de prueba,
sí.

### Tests for User Story 1 (OBLIGATORIO — rojo antes de implementar) ⚠️

- [x] T003 [P] [US1] Test unitario del orden en `apps/worker/tests/unit/test_gate_order_audience.py`. Con `out_of_audience=True`, `gate_for` devuelve `Gate("not_admin", "out_of_audience")` en todos estos casos:
  - cliente `PAUSED`, `ARCHIVED` y `PROVISIONING`;
  - canal `PAUSED` y `DISCONNECTED`;
  - sin versión publicada (`has_active_agent=False`, con y sin `ever_had_agent`);
  - agente en pausa con cada motivo (`manual`, `no_balance`, `agent_cap`, `client_paused`, `client_archived`).

  Con `out_of_audience=False`, cada caso devuelve su puerta de hoy (requisito 1.4). Con `send_only_channel=True` y `out_of_audience=True`, el resultado es el de hoy: `send_only_channel` con el cliente activo y `tenant_inactive` con el cliente en pausa (requisito 1.7).
      _Requisitos: 1.1, 1.2, 1.4, 1.7_
- [x] T004 [P] [US1] Test de integración del turno en `apps/api/tests/integration/test_dispatcher_058_audience_first.py`, con `process_inbound` y `_turn_world`. Casos:
  - **Cliente `PAUSED` y `ARCHIVED`, canal en pausa y agente pausado por saldo, con un contacto fuera de la audiencia** (agente `admin_only` con otro número de admin). En los cuatro:
    - el entrante se guarda con `skipped_reason == "not_admin"`;
    - `waiting_reason == "out_of_audience"`, `status == open` y `attended_at is None`;
    - no hay `ConsoleNotification` `inbox.waiting` ni `ClientPushEvent` `inbox.waiting`.
  - **La forma de Flor y Encanto**: partner con `console_v2_enabled_at`, canal `audience_mode="team_only"` con un número de prueba distinto del remitente y cliente `PAUSED`. Mismo resultado.
  - **«A todos» con excepciones**: el canal `everyone` con el remitente entre sus excepciones y el agente pausado por saldo (escenario 3 de la historia 1). Mismo resultado. Si escribe otro contacto, espera con `no_balance`.
  - **«Sin configurar»**: el canal `unset` y el cliente `PAUSED`. Mismo resultado (caso límite).
  - **Regresión**: el mismo cliente en pausa con el remitente en la audiencia espera con `paused_client` y deja **un** aviso `inbox.waiting`.
  - **Sin módulo de Bandeja**: agente sin publicar, contacto fuera de la audiencia y `wait_message` en el canal. No hay fila `conversation.escalated` ni mensaje de espera.
  - **Número sin audiencia propia**: agente en pausa con `admin_only` en su versión publicada. Sigue decidiendo la política de esa versión.

  Rojo hasta T005.
      _Requisitos: 1.2, 1.3, 1.4, 1.5, 1.6_

### Implementation for User Story 1

- [x] T005 [US1] En `apps/worker/src/nexus_worker/runtime/dispatcher.py`:
  - `gate_for` mira primero `if facts.out_of_audience and not facts.send_only_channel: return Gate("not_admin", "out_of_audience")`;
  - se quita la comprobación de audiencia que iba detrás del agente en pausa;
  - la tabla de puertas del docstring del módulo pasa a decir el orden nuevo (contrato `turn-gates.md`), con la nota de la spec 058.

  T003 y T004 en verde, y las suites de T001 siguen en verde.
      _Requisitos: 1.1, 1.2, 1.3, 1.7_

**Checkpoint**: la historia 1 funciona sola. Es lo que corta los correos en producción.

---

## Phase 4: User Story 2 — Una espera que ya no es cierta deja de esperar (Priority: P2)

**Goal**: un entrante fuera de la audiencia en una conversación que espera por un
motivo de puerta, y que nadie se asignó, la saca de la espera y cierra su aviso.
Lo demás no se toca.

**Independent Test**: una espera `paused_client` cuyo contacto queda fuera de la
audiencia deja de esperar al siguiente mensaje. Una espera `escalated`, o una
asignada, se queda.

### Tests for User Story 2 (OBLIGATORIO — rojo antes de implementar) ⚠️

- [x] T006 [P] [US2] Test de integración en `apps/api/tests/integration/test_dispatcher_058_release_wait.py`. El cliente está en pausa, con Bandeja y una persona del cliente. Un primer mensaje con el remitente en la audiencia deja la espera `paused_client` y su aviso. Después se cambia la política de la versión (o el número de prueba) para que el remitente quede fuera, y escribe otra vez. Se comprueba:
  - (a) `status == open`, `waiting_reason == "out_of_audience"`, un `ConversationEvent` `released` con `{"why": "out_of_audience", "reason": "paused_client"}` y el aviso `inbox.waiting` con `handled_at` puesto;
  - (b) no se crea ningún aviso ni push nuevo, y no sale ningún mensaje (requisito 2.3);
  - (c) una conversación en `escalated` por `escalated` (con `inbox_lifecycle.mark_waiting`) sigue `escalated` y con su motivo;
  - (d) una espera `paused_client` con `assigned_user_id` puesto sigue `escalated` y con su motivo.

  Rojo hasta T008.
      _Requisitos: 2.1, 2.2, 2.3_

### Implementation for User Story 2

- [x] T007 [US2] En `apps/api/src/nexus_api/services/inbox_lifecycle.py`:
  - **`leave_gate_wait(session, conversation) -> bool`**: libera solo si `status == ESCALATED`, `waiting_reason in GATE_REASONS` y `assigned_user_id is None`. Al liberar pone `status = OPEN`, `waiting_reason = "out_of_audience"` y graba el evento `RELEASED` con actor `SYSTEM` y payload `{"why": "out_of_audience", "reason": <anterior>}`. Después hace `flush` y devuelve `True`.
  - **Guarda en `mark_waiting_reason`**: con `reason == "out_of_audience"` y `status == ESCALATED`, devuelve `None` sin tocar el motivo (como la de `human_takeover`).
  - Añadir `leave_gate_wait` a `__all__`.
      _Requisitos: 2.1, 2.2_
- [x] T008 [US2] En `_apply_gate` (`apps/worker/src/nexus_worker/runtime/dispatcher.py`):
  - con `gate.reason == "out_of_audience"`, llamar a `inbox_lifecycle.leave_gate_wait` antes de `mark_waiting_reason`;
  - tras el commit, si liberó, llamar a `inbox_lifecycle.mark_waiting_handled(ref.tenant_id, [ref.conversation_id])` y publicar `conversation.updated` (`publish_inbox_event`). Ninguna de las dos puede tumbar el turno.

  T006 en verde, y T003, T004 y las suites de T001 siguen en verde.
      _Requisitos: 2.1, 2.3_

**Checkpoint**: las historias 1 y 2 funcionan juntas y cada una por su lado.

---

## Phase 5: User Story 3 — Limpiar lo que el fallo ya dejó en la Bandeja (Priority: P3)

**Goal**: una herramienta de operador, en seco por defecto, que saca las esperas
de puerta de contactos fuera de la audiencia en los números con audiencia propia.

**Independent Test**: datos sembrados. La pasada en seco cuenta y no cambia nada.
`--apply` libera solo lo que toca. Una segunda pasada no cambia nada.

### Tests for User Story 3 (OBLIGATORIO — rojo antes de implementar) ⚠️

- [x] T009 [P] [US3] Test de integración en `apps/api/tests/integration/test_audience_cleanup.py`. Un cliente en pausa, partner con la consola nueva y un número «Solo mi equipo». Hay seis conversaciones, sembradas con `inbox_lifecycle.mark_waiting_reason` o `mark_waiting`, más sus avisos:
  1. espera `paused_client`, contacto fuera;
  2. espera `no_balance`, contacto fuera;
  3. espera `paused_client`, contacto de prueba (dentro);
  4. espera `escalated`, contacto fuera;
  5. espera `paused_client`, contacto fuera y asignada;
  6. resuelta.

  Además, una conversación de un número sin audiencia propia: canal de otro tipo, o tenant de un partner sin la consola nueva.

  Se comprueba:
  - (a) `run(factory, apply=False)` devuelve `would_release == 2` y no cambia ninguna fila;
  - (b) `run(factory, apply=True)` deja la 1 y la 2 en `open` con `out_of_audience`, el evento `released` y sus avisos atendidos. Las demás quedan intactas, y la del número sin audiencia propia cuenta en `skipped_not_strict`;
  - (c) no se crea ningún aviso, push ni mensaje;
  - (d) una segunda pasada con `apply=True` devuelve `released == 0`;
  - (e) los eventos `inbox.audience_cleanup.*` (capturados con `structlog.testing.capture_logs`) no llevan teléfono;
  - (f) `apps/api/scripts/release.sh` no nombra el guion.

  Rojo hasta T010 y T011.
      _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

### Implementation for User Story 3

- [x] T010 [US3] Servicio nuevo `apps/api/src/nexus_api/services/audience_cleanup.py`:
  - `Summary` (dataclass, con `as_log()`);
  - **`release_tenant(factory, tenant_id, *, apply) -> TenantReport`**: una transacción bajo `tenant_scoped_session`. Toma las conversaciones `ESCALATED` con `waiting_reason in GATE_REASONS` y `assigned_user_id IS NULL`. Para cada una, lee `channel_config.gate_audience`; si no es `strict`, cuenta `skipped_not_strict`. Si es `strict`, mira `audience_suppresses(audience, None, customer.identifier)`. Con `apply`, llama a `inbox_lifecycle.leave_gate_wait`. Sin `apply`, revierte. Tras el commit, `mark_waiting_handled`;
  - **`run(factory, *, apply) -> Summary`**: recorre los tenants de uno en uno. Uno que falla se revierte solo y se registra como `inbox.audience_cleanup.tenant_failed`, con el tipo de excepción y sin datos;
  - logs `inbox.audience_cleanup.tenant` y `inbox.audience_cleanup.done` (contrato `turn-gates.md`).
      _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5_
- [x] T011 [US3] Guion nuevo `apps/api/scripts/release_out_of_audience_waits.py`. Copia la forma de `pass_booking_to_reservas.py`: `get_direct_engine` y `dispose_engine`. Va en seco por defecto, con `--apply` para escribir, e imprime el resumen. Sale con 0 aunque falle un cliente, y con 1 solo si revienta fuera de un cliente. **No** se añade a `release.sh`. T009 y T002 en verde.
      _Requisitos: 3.2, 3.4, 3.6_

**Checkpoint**: las tres historias funcionan.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T012 [P] Spec viva en `docs/consola-lite.md`: una sección «Lo que la spec 058 cambió aquí», tras la de la ola 1 de la 047. Dice tres cosas: la audiencia se decide antes que cualquier pausa (salvo un número solo de envío), una espera de puerta se libera cuando el contacto queda fuera, y la limpieza es de operador.
      _Requisitos: 1.2, 2.1, 3.1_
- [x] T013 [P] En `specs/047-la-fabrica-de-agentes/contracts/events.md` §2, una línea bajo la tabla: `out_of_audience` gana a los motivos de puerta cuando se cumplen los dos (spec 058, `specs/058-pausa-respeta-audiencia/contracts/turn-gates.md`).
      _Requisitos: 1.2_
- [x] T014 [P] `apps/api/RUNBOOK.md`: una sección «Limpiar esperas de contactos fuera de la audiencia (spec 058)». Explica cómo lanzarla en seco y de verdad en local, en staging (`ecs exec` en `nexus-staging-api`) y en producción (tarea suelta con la definición del `migrate`, con permiso de Luis). Añade qué mirar en los logs.
      _Requisitos: 3.2, 3.6_
- [x] T015 Verificar: `./scripts/verify.sh lint`, después cada fichero de pruebas tocado de uno en uno y después las suites de T001. Anotar el resultado aquí.
      _Requisitos: 1.1–3.6_
      Resultado (2026-11-10): `verify.sh lint` «Todo verde». De uno en uno, los 36 ficheros de pruebas que usan el despachador o `inbox_lifecycle` más los dos de la limpieza: todos en verde (las suites de T001, 17, 6, 7 y 3, siguen igual). La única excepción es `apps/worker/tests/unit/test_consumer_coalesce.py`, con 3 rojos que no son de este cambio: el entorno local del worker no tiene `lupa` (fakeredis responde `unknown command 'eval'`). Con `uv run --with lupa`, 5 en verde. Esta rama no toca el consumidor, `turns` ni las dependencias.
- [x] T016 [P] KB: en `/Users/lmatos/Work/Auphere/nexus/bugs/2026-11-10-pausa-avisa-fuera-de-audiencia.md`, pasar el estado a `in-progress`, con la rama y lo que falta (fusionar, staging, `main`, limpieza en producción).
      _Requisitos: 3.1_

---

## Dependencies & Execution Order

- **T001** va primero: es la línea base.
- **T002** se puede escribir en cualquier momento. Se pone verde con T010 y T011.
- **US1**: T003 ∥ T004 → T005.
- **US2**: depende de US1 solo en que comparte `_apply_gate`. T006 → T007 → T008.
- **US3**: depende de T007 (`leave_gate_wait`). T009 → T010 → T011.
- **Polish**: T012, T013, T014 y T016 en paralelo cuando su historia está hecha. T015 va el último.

### Parallel Opportunities

- T003 y T004 (ficheros distintos).
- T006 y T009 se pueden escribir mientras se implementa US1.
- T012, T013, T014 y T016.

## Implementation Strategy

1. **MVP = US1** (T001–T005). Basta para que Flor y Encanto deje de mandar correos en cuanto llegue a producción.
2. **US2** (T006–T008) evita que una espera se quede colgada sin motivo visible.
3. **US3** (T009–T011) limpia lo que ya existe. Es separable: si se deja fuera, las tres conversaciones de Flor y Encanto se resuelven a mano.
4. Spec viva y verificación (T012–T016).

Las pruebas de integración corren contra Postgres y Redis locales. **De una en
una**: dos suites a la vez comparten la base y dan rojos que no son del cambio.
