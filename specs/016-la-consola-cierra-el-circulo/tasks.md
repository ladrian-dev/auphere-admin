# Tasks: la consola cierra el círculo

**Input**: Design documents from `/specs/016-la-consola-cierra-el-circulo/`

**Prerequisites**: plan.md, spec.md (Clarificada), research.md, data-model.md, contracts/, quickstart.md

**Tests**: NO son opcionales en este repo (constitución §VII): cada bloque de tests se escribe primero, se ve en rojo, y solo entonces se implementa.

**Organization**: por historia de usuario. US1 = Historia 1 (WhatsApp) · US2 = Historia 2 (sin cupo + mover cupo) · US3 = Historia 3 (alta por etapas) · US4 = Historia 4 (modelo) · US5 = Historia 5 (AgendaPro + conectores por clave). R8 (rol y pruebas en cada acción) es transversal: su cimiento va en la Fase 2 y su cierre en la última.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: termina con `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero (§VII)**; **aislamiento (§I)** con una tarea por garantía; **licencias (§VIII)**: ninguna dependencia nueva; **medidor**: el coste relativo del modelo se enseña antes de elegir.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

Monorepo: API en `apps/api/src/nexus_api/`, tests en `apps/api/tests/{unit,integration,isolation}/`; worker en `apps/worker/src/nexus_worker/` con tests en `apps/worker/tests/unit/`; consola en `apps/console/src/` con tests junto al código (`__tests__/`) y e2e en `apps/console/e2e/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: lo que todas las historias comparten y no cambia comportamiento.

- [ ] T001 Crear la migración de datos `apps/api/alembic/versions/0128_console_audit_vocab_016.py` (siguiendo `0105_console_audit_vocab_auth.py`) con las cuatro acciones y sus plantillas ES/EN de `contracts/console-api.md` §Auditoría: `console.allocation.move`, `console.model.update`, `console.integration.agendapro_url`, `console.connector.connect`. Test primero: ampliar el test de vocabulario que ya vigila que toda acción `console.*` escrita en `api/console/**` esté sembrada (`apps/api/tests/unit/test_endpoint_console_home_usage.py`, bloque «every console.* action…»). _Requisitos: 3.3, 5.2, 6.2, 7.1_
- [ ] T002 [P] Añadir a `apps/console/src/i18n/lanes/*.ts` las claves que usan todas las historias, con ES y EN: `clients.detail.missing.quota`, `clients.health.outOfQuota`, `notif.kind.client.out_of_quota`, `notif.kind.client.model_reset`, `wizard.stage.activate`, `ch.connect.byAuphere.*`, `hu.usage.allocations.move.*` (errores del sistema), `agent.model.*`, `connectors.agendapro.*`, `connectors.lastSync.*`, `connectors.field.{woocommerce,amigable_cobro,amigable_venta}.*` y `audit.action.console.{allocation.move,model.update,integration.agendapro_url,connector.connect}`. El test `apps/console/src/i18n/__tests__/messages.test.ts` (paridad ES/EN) y el de claves huérfanas fijan que ninguna sobre. _Requisitos: 1.3, 2.1, 4.1, 5.1, 6.1, 7.2_
- [ ] T003 [P] Corregir en `infra/README-console.md` los nombres de las variables de Meta que la consola lee de verdad (`NEXUS_META_CONFIG_ID_WA_CLOUD_API`, `NEXUS_META_CONFIG_ID_WA_COEXISTENCE`, `NEXUS_META_GRAPH_API_VERSION`, según `apps/console/src/lib/env.ts:32-35`). _Requisitos: 1.3_

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: el estado «sin cupo» y el arnés de pruebas de acciones de servidor los usan varias historias.

- [ ] T004 Test primero en `apps/api/tests/integration/test_console_wallet.py`: `quota_state(partner_id, [tenant_ids])` devuelve `out_of_quota=True` sin wallet, sin fila de asignación y con `remaining <= 0`; `False` con restante > 0; y coincide con `allow_channel_turn` en los cuatro casos. _Requisitos: 2.1, 2.5_
- [ ] T005 Implementar `quota_state` (lote, sesión de partner con `apply_partner_to_session`, misma semántica que `allow_channel_turn`) en `apps/api/src/nexus_api/metering/wallet.py` junto a `allow_channel_turn`; hacer que `clients_without_quota` de `apps/api/src/nexus_api/services/wallet_alerts.py` la use y devuelva `external_client_ref` uniendo `PartnerTenant`. _Requisitos: 2.1, 2.5_
- [ ] T006 [P] Crear el arnés de pruebas de acciones de servidor `apps/console/src/test/actions.ts`: `mockPrincipal(role)` sobre `@/lib/principal` (con `redirect` de `next/navigation` neutralizado), `mockBackend(overrides)` sobre `@/lib/backend`, `vi.mock("next/cache")`; patrón de `apps/console/src/app/api/desktop/__tests__/register-machine.test.ts:29-33`. Documentarlo en `apps/console/README.md` §Comprobaciones. _Requisitos: 8.2_
- [ ] T007 Añadir `"quota"` a `ClientHealth.missing` en `apps/console/src/lib/backend.ts` y el tipo `issues: "out_of_quota"` en `apps/console/src/lib/backend/home-usage.ts` (solo tipos; sin UI aún). _Requisitos: 2.1_

**Checkpoint**: `quota_state` probada; arnés de acciones listo.

---

## Phase 2b: Las puertas de la constitución

- [ ] T008 Test de aislamiento en `apps/api/tests/isolation/test_24_partner_wallet_rls.py`: mover cupo entre un tenant propio y uno de **otro** partner responde 404 opaco y la suma de topes de ambos partners no cambia; y `quota_state` con un `tenant_id` ajeno lo omite (garantía 1). Bloquea el merge. _Requisitos: 3.2, 2.1_
- [ ] T009 [P] Ampliar la barrida de 404 opaco de `apps/api/tests/isolation/test_console_scope.py` con los endpoints nuevos: `POST /console/wallet/allocations/move`, `PUT /console/clients/{ref}/integrations/agendapro/public-url`, y el `signup` de WhatsApp con un ref ajeno (garantía 1). _Requisitos: 1.5, 3.2, 6.2_
- [ ] T010 [P] Test en `apps/api/tests/isolation/test_16_model_binding_scoped.py`: `PUT /clients/{ref}/model` de un partner no toca el binding de un tenant de otro partner, y la reconciliación de allowlist de un partner no borra bindings de otro (garantía 1). _Requisitos: 5.2, 5.3_
- [ ] T011 [P] Test en `apps/api/tests/unit/test_endpoint_console_tools.py`: conectar AgendaPro o un conector por clave enciende herramientas **solo** para ese tenant (`agent_configs.tools` del otro tenant intacto) (garantía 2). _Requisitos: 6.2, 7.1_
- [ ] T012 [P] Test de rastro en `apps/api/tests/unit/test_endpoint_console_home_usage.py` (bloque de auditoría): las cinco acciones nuevas escriben `audit_log` con `actor = console:{email}` y **sin** tokens, claves ni URLs con secretos en `after` (garantías 4 y 6). _Requisitos: 1.6, 3.3, 5.2, 6.2, 7.1_
- Licencias (§VIII): **no aplica** — el plan no instala ninguna dependencia; `pnpm-lock.yaml` y `uv.lock` no cambian (se comprueba en T060).
- Medidor: cubierto por T037 (el coste relativo del modelo se enseña antes de elegir); nada nuevo gasta.

**Checkpoint**: las puertas tienen dueño.

---

## Phase 3: User Story 1 — Conectar WhatsApp desde la consola (Priority: P1) 🎯 MVP

**Goal**: el botón real de Embedded Signup en Canales, activación del cliente al volver, y ausencia diseñada cuando el entorno no tiene Meta.

**Independent Test**: en staging con claves de Meta, conectar un número de prueba deja la ficha en «listo» y el onboarding con «Conecta un canal» hecho; en local (sin claves) Canales muestra la nota sin botón.

### Tests for User Story 1 (OBLIGATORIO — §VII) ⚠️

- [ ] T013 [P] [US1] Ampliar `apps/api/tests/unit/test_endpoint_console_channels.py`: tras un signup correcto (orquestador stubbed) el tenant en `provisioning` con agente activo y `partner.auto_activate` pasa a `active`, y la respuesta trae `client_status` y `health.ready=true`; sin agente activo se queda en `provisioning`. _Requisitos: 1.2_
- [ ] T014 [P] [US1] Test en el mismo fichero: un `provider_identifier` ya usado por otro tenant → 409 `number_in_use` y el otro tenant no cambia (stub del orquestador que lanza la `IntegrityError` de `UNIQUE(type, provider_identifier)`). _Requisitos: 1.5_
- [ ] T015 [P] [US1] Test de la página en `apps/console/src/components/channels/__tests__/whatsapp-connect.test.tsx`: con `meta` configurado renderiza el botón «Conectar WhatsApp»; sin `appId` o sin `configId` renderiza `WhatsAppConnectByAuphere` (nota, **sin** `button`); sin `channels:write` no renderiza nada de conectar. _Requisitos: 1.1, 1.3_
- [ ] T016 [P] [US1] Test de acción con el arnés de T006 en `apps/console/src/app/(console)/clients/[ref]/channels/__tests__/actions.test.ts`: `whatsappSignupAction` permitido con `channels:write` (llama al backend y revalida) y denegado sin él (403 sin llamar). _Requisitos: 1.1, 8.2_
- [ ] T017 [US1] Ampliar `apps/console/src/lib/__tests__/shell-detect.test.ts` para que la única importación de `@/lib/shell` siga siendo `channels/page.tsx` y que la ruta de «continuar en el navegador» apunte a la misma página (donde ahora vive el botón real). _Requisitos: 1.7_

### Implementation for User Story 1

- [ ] T018 [US1] En `apps/api/src/nexus_api/api/console/whatsapp.py` tras `complete_meta_signup`: llamar a `activate_tenant_if_ready` (`services/partner_provisioning.py`), recalcular `client_health` y devolver `client_status` y `health` en `WhatsAppSignupOut` (`schemas` del módulo); mapear la `IntegrityError` de `channels` a 409 `{"code": "number_in_use"}` sin efectos. _Requisitos: 1.2, 1.5, 1.6_
- [ ] T019 [P] [US1] Crear `apps/console/src/components/channels/whatsapp-connect-by-auphere.tsx`: nota sin botón con `ch.connect.byAuphere.title/body/contact` (a quién escribir y qué datos mandar); borrar `whatsapp-connect-unavailable.tsx` y sus claves `ch.connect.unavailable`/`ch.connect.notConfigured`. _Requisitos: 1.3_
- [ ] T020 [US1] En `apps/console/src/app/(console)/clients/[ref]/channels/page.tsx`: construir `MetaSignupConfig` con `env()` y renderizar `WhatsAppConnect` (con `canConnect = manage && cupo`) o `WhatsAppConnectByAuphere` cuando falten claves; mantener la bifurcación de escritorio con `WhatsAppContinueInBrowser`. En `whatsapp-connect.tsx`, `disabledReason` de «no configurado» deja de existir (la página ya no lo renderiza). _Requisitos: 1.1, 1.3, 1.7_
- [ ] T021 [P] [US1] Actualizar `apps/console/src/lib/backend/channels.ts` (`WhatsAppSignupOut` con `client_status`, `health`) y, en `whatsapp-connect.tsx`, tras el éxito: toast «WhatsApp conectado» y `router.refresh()` (la ficha y el onboarding se recalculan en el servidor). _Requisitos: 1.1, 1.2_
- [ ] T022 [P] [US1] Copy honesto: `wizard.channel.whatsapp.body` en `apps/console/src/i18n/lanes/onboarding.ts` («se conecta desde la pestaña Canales del cliente; si tu entorno no lo permite, te decimos cómo pedirlo») y `diag.todo.connect_whatsapp` en `lanes/channels.ts` sin prometer un botón. _Requisitos: 1.8_
- [ ] T023 [US1] Recorrido en staging documentado en `specs/016-la-consola-cierra-el-circulo/evidence/us1-whatsapp-staging.md` (capturas: botón, ventana de Meta, tarjeta activa, ficha «listo», onboarding); en local, captura de la nota sin botón. _Requisitos: 1.1, 1.2, 1.3_

**Checkpoint**: un partner conecta WhatsApp sin Auphere; sin claves, la ausencia está diseñada.

---

## Phase 4: User Story 2 — Ver y resolver «sin cupo» sin que nadie llame (Priority: P1)

**Goal**: «sin cupo» visible en ficha, lista y portada en < 60 s; aviso en consola y correo una vez por cliente y día; mover cupo en una transacción.

**Independent Test**: bajar el tope a 0, provocar un turno, ver el estado en las tres pantallas y el aviso; mover cupo y comprobar la suma constante, también cuando falla.

### Tests for User Story 2 (OBLIGATORIO — §VII) ⚠️

- [ ] T024 [P] [US2] Tests en `apps/api/tests/integration/test_console_wallet.py`: `POST /wallet/allocations/move` baja y sube en la misma operación (suma de `cap` constante), recorta `remaining` del origen si supera el cap nuevo, 422 `same_client`, 422 `insufficient_cap` con `{cap, qty}`, 422 con `qty <= 0`, 403 sin `usage:write`, y auditoría `console.allocation.move`. _Requisitos: 3.1, 3.2, 3.3_
- [ ] T025 [P] [US2] `test_move_allocation_is_atomic` en el mismo fichero: con `monkeypatch` que hace fallar el `UPDATE` del destino tras bloquear el origen, la transacción se deshace y la suma de topes no cambia (CE-003). _Requisitos: 3.1_
- [ ] T026 [P] [US2] Tests en `apps/api/tests/unit/test_endpoint_console_home_usage.py`: `GET /console/clients` y `GET /console/clients/{ref}` traen `health.missing` con `"quota"` (después de `"whatsapp"`) cuando `quota_state` lo dice, y `GET /console/home` lo cuenta en `incidents` con `issues: ["out_of_quota"]`; `health.ready` no depende del cupo. _Requisitos: 2.1, 2.7_
- [ ] T027 [P] [US2] Tests en `apps/api/tests/integration/test_wallet_alerts.py`: `notify_client_out_of_quota_detached(tenant_id)` crea **una** notificación `client.out_of_quota` (`severity=warning`, `external_client_ref`, `dedupe_key` por cliente y día), no crea otra el mismo día, **no** la crea si al recomprobar el cliente ya tiene cupo (R2.5), y manda correo a `usage_alert_recipients` cuando existen. _Requisitos: 2.2, 2.3, 2.5_
- [ ] T028 [P] [US2] Test del worker en `apps/worker/tests/unit/test_dispatcher_out_of_quota.py`: cuando `allow_channel_turn` devuelve `False`, el despachador llama al notificador con el `tenant_id` y sigue devolviendo `{"skipped": "wallet_empty"}`; el mensaje al cliente final no cambia (R2.6). _Requisitos: 2.2, 2.6_
- [ ] T029 [P] [US2] Tests de consola: `apps/console/src/app/(console)/usage/__tests__/actions.test.ts` (`moveAllocationAction` hace **una** llamada `moveAllocation`, permitido/denegado; `saveAllocationAction` permitido/denegado), `apps/console/src/components/notifications/__tests__/render.test.ts` (texto de `client.out_of_quota` con nombre del cliente y enlace a Consumo; `client.model_reset`), y `apps/console/src/components/clients/__tests__/health.test.ts` (nuevo: `missingItems(health)` devuelve etiqueta y enlace por elemento, con `quota` → `/usage`). _Requisitos: 2.1, 2.4, 3.4, 8.2_

### Implementation for User Story 2

- [ ] T030 [US2] `move_allocation(partner_id, from_tenant, to_tenant, qty)` en `apps/api/src/nexus_api/metering/wallet.py`: una `session.begin()`, `apply_partner_to_session`, `_load_wallet_for_update`, dos `PartnerAllocation` con `with_for_update()` en orden de `tenant_id`, `from.cap -= qty; from.remaining = min(from.remaining, from.cap); to.cap += qty; to.remaining += qty`; errores `SameClient`, `InsufficientCap(cap, qty)`. _Requisitos: 3.1, 3.2_
- [ ] T031 [US2] `POST /console/wallet/allocations/move` en `apps/api/src/nexus_api/api/console/wallet.py` (`usage:write`): resolver los dos refs con `resolve_mapping` antes de la transacción (404 opaco), body `{from_ref, to_ref, qty}` con `extra="forbid"`, respuesta `{from, to}` (`AllocationOut`), 422 por código, auditoría `console.allocation.move {from, to, qty}`; actualizar el comentario de `:179`. _Requisitos: 3.1, 3.2, 3.3_
- [ ] T032 [US2] Salud con cupo: `client_health(..., out_of_quota: bool)` en `apps/api/src/nexus_api/api/console/deps.py` (`"quota"` tras `"whatsapp"`); `GET /console/clients` en `tenants.py` calcula `quota_state` una vez por página y lo pasa; `GET /console/clients/{ref}` igual; `services/console_home.py` + `api/console/home.py` añaden `out_of_quota` a `issues` con el mismo lote. _Requisitos: 2.1, 2.7_
- [ ] T033 [US2] Aviso: `NotificationKind.CLIENT_OUT_OF_QUOTA` en `apps/api/src/nexus_api/db/models/console_notification.py`; `notify_client_out_of_quota_detached(tenant_id)` en `services/wallet_alerts.py` (sesión propia, resuelve partner y ref por `PartnerTenant`, recomprueba `allow_channel_turn`, `emit_detached` con `dedupe_key=partner:{id}:client.out_of_quota:{ref}:{YYYY-MM-DD}`, correo con `_notify_by_email` a `usage_alert_recipients`); `evaluate_partner_wallet_alerts` emite lo mismo por cada cliente de `clients_without_quota` (red de seguridad). _Requisitos: 2.2, 2.3, 2.5_
- [ ] T034 [US2] Worker: en `apps/worker/src/nexus_worker/runtime/dispatcher.py`, en la rama `skipped: wallet_empty`, `await notify_client_out_of_quota_detached(tenant_id)` con `contextlib.suppress` + log (el aviso nunca tumba el turno); nada cambia para el cliente final. _Requisitos: 2.2, 2.6_
- [ ] T035 [US2] Consola, estado: `apps/console/src/components/clients/health.ts` (nuevo, `missingItems`: etiqueta + `href` por elemento — agente → `…/agent`, WhatsApp → `…/channels`, cupo → `/usage?client={ref}`, activación → acción); `clients/[ref]/page.tsx` pinta cada elemento como enlace y «sin cupo» con tono aviso; `components/clients/clients-table.tsx` añade el punto «sin cupo» con `title`; `(console)/page.tsx` cuenta y nombra `out_of_quota` en incidencias con enlace a Consumo; `components/notifications/render.ts` con los dos tipos nuevos. _Requisitos: 2.1, 2.4, 2.7_
- [ ] T036 [US2] Consola, mover: `moveAllocation(from_ref, to_ref, qty)` en `apps/console/src/lib/backend/home-usage.ts`; `moveAllocationAction` en `usage/actions.ts` con una sola llamada y sin `from_cap`/`to_cap`; `usage/move-allocation.tsx` con confirmación única, un solo resultado («{qty} créditos movidos de {from} a {to}») y errores por código (`same_client`, `insufficient_cap` con la cifra); fila «sin cupo» con acción «Asignar» en `usage/page.tsx`. _Requisitos: 3.1, 3.2, 3.4, 2.4_

**Checkpoint**: sin cupo se ve y se avisa; mover cupo es atómico.

---

## Phase 5: User Story 3 — El alta termina con la verdad a la vista (Priority: P2)

**Goal**: cuatro etapas separadas con reintento propio; la ficha nombra lo que falta con la acción a un clic.

**Independent Test**: forzar el fallo de «activar» y comprobar que publicar no se repite y que solo esa etapa se reintenta.

### Tests for User Story 3 (OBLIGATORIO — §VII) ⚠️

- [ ] T037 [P] [US3] Ampliar `apps/console/src/app/(console)/clients/new/__tests__/wizard-state.test.ts`: `planStages` con `publishNow=true` produce `create → seed → publish → activate`; `retry("activate")` no vuelve a `pending` ninguna anterior; `runOutcome` con `activate` fallida = `partial`. _Requisitos: 4.1, 4.2_
- [ ] T038 [P] [US3] Tests de acciones con el arnés en `apps/console/src/app/(console)/clients/new/__tests__/actions.test.ts`: `wizardPublishAction` publica solo si no hay activa (idempotente: con activa no llama a `publish`), `wizardActivateAction` llama a `setClientStatus("active")`; cada una permitido/denegado. _Requisitos: 4.2, 4.3, 8.2_

### Implementation for User Story 3

- [ ] T039 [US3] `StageKey` con `"activate"` en `apps/console/src/app/(console)/clients/new/wizard-state.ts` (`planStages`, `initialStages`, `STAGE_LABEL`); dividir `wizardPublishAndActivateAction` en `wizardPublishAction` y `wizardActivateAction` en `actions.ts` (permisos `agents:write` y `clients:write` respectivamente); `runStage` en `wizard.tsx` con las dos etapas y su reintento; etiqueta `wizard.stage.activate`. _Requisitos: 4.1, 4.2, 4.3_
- [ ] T040 [US3] La ficha nombra lo que falta con acción a un clic (reutiliza `missingItems` de T035) y el wizard aterriza en ella con el foco en la tarjeta de estado (`wizard.tsx` redirección con `#setup`). _Requisitos: 4.4_

**Checkpoint**: cuatro etapas, reintento por etapa, ficha con lo que falta.

---

## Phase 6: User Story 4 — Elegir el modelo del agente (Priority: P2)

**Goal**: tarjeta «Modelo» en los ajustes del agente con los permitidos por plan y su coste relativo en créditos; auditoría; aviso si el plan deja de permitir el elegido.

**Independent Test**: cambiar el modelo, enviar un turno en el Playground y ver el modelo nuevo en el inspector.

### Tests for User Story 4 (OBLIGATORIO — §VII) ⚠️

- [ ] T041 [P] [US4] Ampliar `apps/api/tests/integration/test_console_models.py`: `GET /console/models` devuelve `display_name`, `weights` y `relative_cost` (entero, el menor = 1) leídos de `model_profiles`; `GET /clients/{ref}/model` devuelve `allowed`; `PUT` escribe `console.model.update` con `{model_id, previous}`. _Requisitos: 5.1, 5.2_
- [ ] T042 [P] [US4] Test de reconciliación en `apps/api/tests/integration/test_admin_partner_models.py`: al reescribir la allowlist sin el modelo elegido, el binding `respond` del tenant se borra y se emite `client.model_reset` con `{from_model, to_model}`; con el modelo aún permitido, nada cambia. _Requisitos: 5.3_
- [ ] T043 [P] [US4] Tests de consola: `apps/console/src/components/agent-tools/__tests__/model-picker.test.tsx` (lista con «×N créditos», el actual marcado, aviso cuando `allowed=false`, guardar llama a `saveModelAction`), y `apps/console/src/app/(console)/clients/[ref]/agent/__tests__/actions.test.ts` (`saveModelAction` permitido/denegado). _Requisitos: 5.1, 5.3, 8.2_

### Implementation for User Story 4

- [ ] T044 [US4] API: `GET /console/models` une `respond_catalog.RESPOND_MODELS` con `model_profiles` (`display_name`, `quota_weight_input/cache_read/output`) y calcula `relative_cost = round(weight_output / min_weight_output)`; `GET /clients/{ref}/model` añade `allowed`; `PUT` escribe `AuditLog` `console.model.update`; en `apps/api/src/nexus_api/api/console/models.py` y `schemas_models.py`. _Requisitos: 5.1, 5.2_
- [ ] T045 [US4] Reconciliación: en el endpoint de admin que reescribe la allowlist de un partner (`apps/api/src/nexus_api/api/admin/model_bindings.py` o donde viva `PartnerModelAllowlist` write), borrar los bindings `respond` fuera de la allowlist y emitir `client.model_reset` (`NotificationKind` nuevo en `console_notification.py`). _Requisitos: 5.3_
- [ ] T046 [US4] Consola: `apps/console/src/lib/backend/models.ts` (`listModels`, `getClientModel`, `setClientModel`), `saveModelAction` en `clients/[ref]/agent/actions.ts` (`agents:write`), `components/agent-tools/model-picker.tsx` (tarjeta fuera del `<form>` de ajustes: actual, lista con «×N créditos», aviso `allowed=false` con el modelo por defecto, guardar → toast «El siguiente mensaje lo atiende {modelo}»), montada en `clients/[ref]/agent/settings/page.tsx`. _Requisitos: 5.1, 5.2, 5.3, 5.4_

**Checkpoint**: el modelo se elige, se audita y se explica en créditos.

---

## Phase 7: User Story 5 — AgendaPro enlazada y conectores por clave sin fricción (Priority: P3)

**Goal**: enlazar la agenda pública de AgendaPro desde la consola; guardar una clave sincroniza solo y muestra el resultado; campos traducidos.

**Independent Test**: enlazar una URL pública de AgendaPro y ver `booking.*` activables; conectar WooCommerce y no tener que pulsar «Sincronizar».

### Tests for User Story 5 (OBLIGATORIO — §VII) ⚠️

- [ ] T047 [P] [US5] Tests en `apps/api/tests/unit/test_endpoint_console_tools.py` (o nuevo `test_endpoint_console_integrations.py`): `PUT /clients/{ref}/integrations/agendapro/public-url` guarda, `""`/`null` borra, 422 si no es `https` o no es dominio de AgendaPro, 403 sin `agents:write`, auditoría `console.integration.agendapro_url {set}`; `GET …/connectors` muestra AgendaPro con `auth_kind: "public_url"`, `public_url` y `status: connected` cuando hay URL. _Requisitos: 6.1, 6.2, 6.3, 6.4_
- [ ] T048 [P] [US5] Tests en el mismo fichero: `POST …/connectors/{slug}/api-key` sincroniza en la misma petición y devuelve `last_sync {status: ok, added, deprecated}`; si `sync_tools_for` lanza `ComposioUnavailable`, la credencial queda guardada, `status = connected`, `last_sync.status = error` con `reason = provider_unavailable`; auditoría `console.connector.connect {slug, sync_status}`. _Requisitos: 7.1, 7.3_
- [ ] T049 [P] [US5] Tests de consola: `apps/console/src/components/agent-tools/__tests__/tools-catalog.test.tsx` (nuevo: AgendaPro renderiza «Enlazar la agenda» con campo URL y no un formulario de credenciales; conector por clave muestra `last_sync` ok/error y «Reintentar» solo en error; etiquetas de campos traducidas por `connectors.field.*`), `apps/console/src/app/(console)/clients/[ref]/tools/__tests__/actions.test.ts` (`setAgendaProUrlAction`, `connectApiKeyAction`, `syncConnectorAction` permitido/denegado). _Requisitos: 6.1, 6.5, 7.1, 7.2, 7.3, 8.2_

### Implementation for User Story 5

- [ ] T050 [US5] API AgendaPro: `apps/api/src/nexus_api/api/console/integrations.py` (nuevo router bajo `/console`) con `PUT /clients/{ref}/integrations/agendapro/public-url` (`agents:write`, validación `https` + dominio `agendapro.com`, mismo servicio que `api/admin/integrations.py`, auditoría); en `api/console/tools.py::_connectors` AgendaPro sale con `auth_kind: "public_url"`, `public_url` y `status` derivado de `tenants.agendapro_public_url`; registrar el router en `api/console/__init__.py`. _Requisitos: 6.1, 6.2, 6.3, 6.4_
- [ ] T051 [US5] API conectores por clave: en `api/console/tools.py::connect_api_key`, tras `bootstrap_api_key`, ejecutar la misma lógica de `sync_connector` y devolver `ConnectorOut` con `last_sync {status, added, deprecated, reason, at}` (`ConnectorOut` en `schemas` del módulo); errores de proveedor no deshacen la credencial; auditoría `console.connector.connect`. _Requisitos: 7.1, 7.3_
- [ ] T052 [US5] Consola AgendaPro: `setAgendaProUrlAction` en `clients/[ref]/tools/actions.ts`, `setAgendaProUrl` en `lib/backend/agent-tools.ts`, tarjeta en `tools-catalog.tsx` («Enlazar la agenda» con campo URL, ejemplo y ayuda de dónde se obtiene; «Desenlazar» con `ConfirmDialog`); `ConnectorOut` con `public_url` en `agent-tools-types.ts`; **ningún** formulario de credenciales para `browser_credentials`. _Requisitos: 6.1, 6.2, 6.4, 6.5_
- [ ] T053 [US5] Consola conectores por clave: `tools-catalog.tsx` muestra `last_sync` en la tarjeta («Conectado · N herramientas» / «Guardado, pero no se pudo sincronizar: {motivo} · Reintentar»), «Sincronizar» permanente desaparece, etiquetas por `connectors.field.{slug}.{field}` con `f.label` de reserva; `connectApiKeyAction` devuelve el `ConnectorOut` nuevo. _Requisitos: 7.1, 7.2, 7.3_

**Checkpoint**: AgendaPro enlazada; clave = un clic; todo en el idioma del partner.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: R8 completo, documentación viva y verificación del bloque.

- [ ] T054 Añadir `can()` a las 16 acciones que no lo tienen, con el permiso exacto que la API exige: `keys/actions.ts` (`keys:manage`), `team/actions.ts` (`team:manage`; techo → `teammates:policy`), `billing/actions.ts` (`billing:manage`), `notifications/actions.ts` (`partner:read`); `invite/[token]/actions.ts` queda documentado como preautenticación. _Requisitos: 8.1, 8.3_
- [ ] T055 [P] Tests permitido/denegado con el arnés para el resto de acciones (las que no cubren T016, T029, T038, T043, T049): `keys`, `team`, `billing`, `notifications`, `knowledge` (cliente y playbook), `skills`, `playground`, `workstation` (cliente y partner), `usage/alerts`, `clients/actions.ts` (siete) y `wizardCheckRefAction`; un fichero `__tests__/actions.test.ts` por carpeta. CE-008: las 69 acciones cubiertas. _Requisitos: 8.2_
- [ ] T056 [P] Los controles de acción no se muestran sin permiso (R8.3): revisar `keys/page.tsx`, `team/page.tsx`, `billing/page.tsx` y las pestañas de cliente para que el botón no exista cuando `can()` es falso (no deshabilitado). _Requisitos: 8.3_
- [ ] T057 [P] Documentación viva en el mismo commit que la cambia: `docs/console.md` (nuevo, spec viva de la consola: qué existe hoy, en línea con `kb/Auphere/nexus/architecture/console-map.md`), `apps/console/README.md` (arnés de acciones, Node), `infra/README-console.md` (T003). _Requisitos: 1.3, 8.2_
- [ ] T058 [P] KB (`/Users/matos/workspace/kb/Auphere/nexus/`): anotar en `PLAN-ACCION-CONSOLA-2026-09-22.md` la desviación de R6 (URL pública en vez de credenciales) con la decisión del owner; ADR corto `decisions/ADR-039-la-consola-cierra-el-circulo.md` con las decisiones R1–R8; session log. _Requisitos: 6.5_
- [ ] T059 Suite e2e: añadir a `apps/console/e2e/a11y.spec.ts` la tarjeta de modelo y el diálogo de mover cupo abiertos (axe con diálogo abierto), y a `quickstart.md` los resultados. _Requisitos: 2.1, 5.1_
- [ ] T060 Verificación del bloque: `./scripts/verify.sh` completo, `pnpm check`, `pnpm test:e2e`, `git diff --stat pnpm-lock.yaml uv.lock` vacío (licencias: nada nuevo), y los ocho CE de la spec con su evidencia en `specs/016-la-consola-cierra-el-circulo/evidence/`. _Requisitos: todos_

---

## Dependencies & Execution Order

- **Setup (T001–T003)** → **Foundational (T004–T007)** → **Puertas (T008–T012)** pueden empezar en paralelo con las historias que tocan, pero **bloquean el merge**.
- **US1** (T013–T023) depende solo de T002/T003. **US2** (T024–T036) depende de T004/T005/T007. **US3** (T037–T040) depende de T035 (`missingItems`). **US4** (T041–T046) depende de T001. **US5** (T047–T053) depende de T001/T002.
- **Polish (T054–T060)** al final; T055 puede ir en paralelo desde que existe T006.

```
T001 ─┬─► US4, US5
T002 ─┼─► US1, US5
T004 ─► T005 ─► US2 (T032, T033) ─► T035 ─► US3 (T040)
T006 ─► todos los *actions.test.ts (T016, T029, T038, T043, T049, T055)
```

## Parallel Execution Examples

- Tras la Fase 2: un agente en **US1** (consola + `whatsapp.py`), otro en **US2 API** (T024–T028, T030–T034), otro en **US4** (T041–T046): ficheros disjuntos.
- Dentro de US2: T030+T031 (wallet) en paralelo con T032 (salud) y T033+T034 (aviso); T035+T036 (consola) después.
- Tests de acciones (T055) en paralelo por carpeta.

## Implementation Strategy

- **MVP** = Fase 1 + Fase 2 + **US1** + **US2**: con eso un partner conecta WhatsApp y se entera de que un cliente se quedó sin cupo. Es lo que cierra el círculo; el resto lo pule.
- Cada historia se entrega con sus tests en verde, `./scripts/verify.sh lint`, y un commit por tarea o grupo de tareas de un mismo carril (`feat(console)`, `feat(api)`, `test(…)`).
- Staging obligatorio antes de fusionar a `develop` para US1 (Meta) y US2 (worker en producción con tráfico real).
