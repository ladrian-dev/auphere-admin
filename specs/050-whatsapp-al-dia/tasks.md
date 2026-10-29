# Tareas: 050 — WhatsApp al día

**Entrada**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

Test primero (constitución §VII): la prueba se escribe, se ve en rojo y solo entonces se implementa. Las rutas parten de la raíz del repo. `[P]` = paralelizable. Trabajo en `develop`. Cada tarea entregada se anota con su commit.

## Fase 1 — Base de la iteración 1 (bloquea todo)

- [ ] T001 Cargas firmadas de Meta en `apps/channels/tests/fixtures/meta_webhooks/`. Una por campo de [webhook-events.md](contracts/webhook-events.md), con las formas de [research.md](research.md):
  - lote de 5 mensajes y 5 estados;
  - mensaje solo con BSUID (`from_user_id`, sin `from`);
  - mensaje con teléfono y BSUID;
  - `system` `user_changed_number` y `user_changed_user_id`;
  - `button`, `referral`, `contacts`, `errors`;
  - `user_preferences` `stop` y `resume`;
  - los 14 eventos de plantilla, calidad y categoría;
  - `account_update` con `waba_info` sin número (`PARTNER_REMOVED`) y `ACCOUNT_RECONNECTED`;
  - `account_alerts`, `account_review_update`, `business_capability_update`, `phone_number_name_update` y `business_username_updates`;
  - estados con `pricing{billable,type,category}`.

  _Requisitos: 1.1, 1.3_
- [ ] T002 Migración `apps/api/alembic/versions/0206_whatsapp_identity_and_health.py` (encadenada a la cabeza de `develop`):
  - `customers`: `bsuid varchar(160)` con índice único parcial `(tenant_id, bsuid) WHERE bsuid IS NOT NULL`, `phone varchar(32)` con índice `(tenant_id, phone)` y `username varchar(64)`. Relleno: `phone = identifier` cuando `identifier ~ '^[0-9]{6,20}$'`.
  - `whatsapp_opt_outs`:
    - `customer_id` (FK `ON DELETE CASCADE`), `scope varchar(12) NOT NULL DEFAULT 'all'` (CHECK `marketing|all`), `source varchar(12) NOT NULL DEFAULT 'keyword'` (CHECK `meta|keyword|operator`) y `lifted_by`;
    - `recipient_phone` pasa a nulo; unicidad nueva por `(tenant_id, channel_id, customer_id) WHERE opted_in_at IS NULL`;
    - relleno de `customer_id` por teléfono.
  - `whatsapp_template_status`: `previous_category`, `pending_category` y `quality varchar(12)`. Relleno de `tenant_id` por WABA.
  - `ck_channels_problem_reason` admite además `account_review` y `account_alert`.
  - Función `resolve_waba_tenants(text)`: SECURITY DEFINER, `row_security = off`, solo devuelve ids, con `GRANT` al rol de la app.
  - Vocabulario de auditoría: las entradas de [data-model.md](data-model.md).
  - Modelos SQLAlchemy y `PROBLEM_REASONS` en `services/agent_lifecycle.py`.
  - Comprobaciones: `test_21` y `test_22` en verde, y la migración reversible.

  _Requisitos: 2.1, 2.2, 4.2, 5.1, Entidades clave_
- [ ] T003 [P] `NotificationKind`: `template.paused`, `template.disabled`, `template.quality_dropped`, `template.recategorized`, `channel.account_review`, `channel.account_alert` y `channel.name_rejected`. Va en `apps/api/src/nexus_api/db/models/console_notification.py`, con su texto ES/EN en `apps/console/src/i18n/lanes/onboarding.ts` (`notif.kind.*`).
  _Requisitos: 4.1, 4.2, 4.4_

## Fase 2 — Historia 1: nadie se queda sin respuesta (P1)

- [ ] T004 [US1] Pruebas en rojo del parser (`apps/channels/tests/test_meta_webhook_adapter.py`, nuevas):
  - los iteradores devuelven **todos** los mensajes, estados y ecos de cada `change`;
  - un mensaje sin `from` se parsea, con `sender_bsuid`, `sender_phone=None` y `username`;
  - con los dos, se rellenan los dos;
  - `system` da un evento de identidad sin turno;
  - `button`, `contacts` legibles, `referral` y `errors` quedan parseados.

  _Requisitos: 1.1, 1.5, 2.1, 7.1–7.3_
- [ ] T005 [US1] Parser (`apps/channels/src/nexus_channels/whatsapp_meta/webhook_adapter.py`) hasta verde:
  - `iter_inbound_messages`, `iter_status_callbacks`, `iter_message_echoes` e iteradores de coexistencia;
  - `_build_inbound` sin exigir `from`;
  - `InboundMessage` gana `sender_bsuid`, `sender_phone` y `username` (`apps/channels/src/nexus_channels/base.py`, opcionales).

  _Requisitos: 1.1, 2.1_
- [ ] T006 [US1] Pruebas en rojo del router (`apps/api/tests/unit/test_endpoint_webhook_meta_batches.py`):
  - un lote de 5 mensajes da 5 entradas en el stream; uno de 5 estados, 5 estados aplicados;
  - un elemento roto no corta el resto y responde 200;
  - mensaje solo con BSUID: se encola con `user_id` = BSUID y `customer_bsuid`;
  - WhatsApp de hoy sigue igual: `test_endpoint_webhook_meta_inbound.py` en verde.

  _Requisitos: 1.1, 1.2, 1.7, 2.1, CE-002, CE-008_
- [ ] T007 [US1] Router (`apps/api/src/nexus_api/api/webhooks/meta.py`) hasta verde:
  - recorre elementos con fallo aislado (`webhook.meta.element_failed`);
  - el stream lleva `customer_bsuid`, `customer_phone` y `customer_username`;
  - el dedupe es por elemento.

  _Requisitos: 1.1, 1.2, 1.7_
- [ ] T008 [US1] Pruebas en rojo de identidad (`apps/worker/tests/unit/test_customer_identity.py`):
  - las reglas 1 a 4 de [data-model.md](data-model.md): por BSUID, por teléfono con BSUID añadido, alta con `identifier = phone ?? bsuid`;
  - conflicto: gana el BSUID, no se funde nada y se escribe el log;
  - `user_changed_number` y `user_changed_user_id`;
  - `identifier` nunca cambia.

  _Requisitos: 2.1–2.3, 2.6_
- [ ] T009 [US1] `upsert_customer_identity` en `apps/worker/src/nexus_worker/persistence/messages.py`, usado por `runtime/dispatcher.py` (`accept_inbound`) y por los consumidores de coexistencia (`streams/meta_echoes_consumer.py`, `meta_history_consumer.py`, `meta_state_sync_consumer.py`). Los eventos `system` actualizan la identidad sin turno.
  _Requisitos: 2.1–2.3, 2.6, 1.5_
- [ ] T010 [US1] Pruebas en rojo del despachador (`apps/api/tests/integration/channels/test_outbound_bsuid.py`):
  - cliente con teléfono: sale con `to`;
  - sin teléfono: sale con `recipient`;
  - plantilla de autenticación a un cliente sin teléfono: `failed` con `needs_phone` y sin llamar a Meta.

  _Requisitos: 2.4_
- [ ] T011 [US1] Despachador (`apps/worker/src/nexus_worker/streams/outbound.py`) y `MetaClient`/adapter (`whatsapp_meta/meta_client.py`, `adapter.py`): `to` o `recipient` según la identidad. `send_*` aceptan `recipient_kind`.
  _Requisitos: 2.4_
- [ ] T012 [US1] Prueba de aislamiento `apps/api/tests/isolation/test_whatsapp_identity_bsuid.py`:
  - el mismo BSUID en dos tenants son dos personas;
  - un BSUID nunca resuelve a otro tenant;
  - dos personas de un mismo tenant no se funden aunque compartan un dato parcial;
  - el `user_id` del hilo no cambia al añadir un BSUID.

  _Requisitos: 2.3, Garantías 1, 4 y 8, CE-007_

## Fase 3 — Historia 2: conexión vigente (P1, antes del 2026-11-16)

- [ ] T013 [P] [US2] Pruebas en rojo de `signupExtras(mode, version)` y de `parseSignupMessage` (`apps/console/src/lib/__tests__/meta-fb-sdk.test.ts` y su espejo en el panel):
  - v4 en Cloud API: `{setup:{}}`; en coexistencia: `{setup:{}, featureType:"whatsapp_business_app_onboarding"}`; sin `sessionInfoVersion`;
  - v5: `{version:"v5"}`, y en Cloud API además `features:[{name:"whatsapp_business_app_onboarding",enabled:false}]`;
  - se aceptan los seis eventos de v4 y el `FINISH` de v5 (`messaging_account_ids` → WABA).

  _Requisitos: 3.1, 3.4_
- [ ] T014 [US2] `signupExtras` y `parseSignupMessage` en `apps/console/src/lib/meta-fb-sdk.ts` y `apps/admin/src/lib/meta-fb-sdk.ts`, con prueba de paridad entre los dos. Callers: `components/builder/connect-whatsapp-dialog.tsx`, `components/channels/whatsapp-connect.tsx`, `app/connect/whatsapp/*` (enlace del dueño y beta de inicio de sesión con WhatsApp) y `admin/.../meta-signup-dialog.tsx`. `FINISH_ONLY_WABA` y `FINISH_GRANT_ONLY_API_ACCESS` dicen qué falta.
  _Requisitos: 3.1, 3.4_
- [ ] T015 [US2] Interruptor `meta_embedded_signup_version` (por defecto `v4`) en `apps/api/src/nexus_api/config.py`. Se entrega a los navegadores en el overview, en el enlace del dueño (`api/console/channel_signup.py`) y en `partners_clients.py`, junto a `graph_version`.
  _Requisitos: 3.1, 3.5_
- [ ] T016 [US2] Pruebas en rojo de la versión única (`apps/api/tests/unit/test_meta_graph_version.py`):
  - `MetaClient` sin `base_url` usa `settings.meta_graph_api_version`;
  - un barrido del código falla si aparece `v2X.0` escrito a mano fuera de `config.py` y las pruebas;
  - la configuración por defecto es `v26.0`.

  _Requisitos: 3.5_
- [ ] T017 [US2] `MetaClient(version=…)` en `whatsapp_meta/meta_client.py`: se quitan `META_GRAPH_VERSION`/`META_GRAPH_BASE_URL` como constantes de uso. Construcciones en `meta_signup_service.py`, `admin/meta_signup.py`, `whatsapp_templates.py`, `owner_channel_flow.py`, `worker/bootstrap.py`, `owner_outbox.py`, `operator_alerts.py`, `whatsapp_health_cron.py` y `console/channels.py`. Defaults `v26.0` en la consola (`lib/env.ts`, `.env.example`) y en el panel.
  _Requisitos: 3.5_
- [ ] T018 [US2] Pruebas en rojo del alta (`apps/api/tests/unit/test_endpoint_meta_signup.py`):
  - el PIN queda en `MetaCredentials.two_step_pin` (Cloud API y `connect_with_token`) y no sale en ninguna respuesta;
  - reconectar un número conserva `catalog_id`, `history_import`, audiencia y escalado.

  _Requisitos: 3.2, 3.3_
- [ ] T019 [US2] `MetaCredentials.two_step_pin` (`whatsapp_meta/credentials.py`), guardado en `signup.py`. `_upsert_channel` fusiona `config`. Endpoint `POST /admin/tenants/{tenant_id}/channels/{channel_id}/two-step-pin` (`apps/api/src/nexus_api/api/admin/whatsapp_pin.py`): genera, envía `POST /{phone} {pin}`, guarda y audita `channel.whatsapp.pin_rotated`. Botón en el panel, en la ficha del canal.
  _Requisitos: 3.2, 3.3_
- [ ] T020 [US2] Aviso de caducidad de versión: tabla de fechas en `config.py`. `whatsapp_health_cron` avisa al operador (`operator_alerts`) cuando falten 60 días o menos.
  _Requisitos: 3.6_
- [ ] T021 [US2] Verificación en staging: las cinco vías de [quickstart.md](quickstart.md) (escenarios 5 a 7), con evidencia en `specs/050-whatsapp-al-dia/evidence/`.
  _Requisitos: 3.1, CE-004_

## Fase 4 — Historia 3: la cuenta avisa antes de romperse (P1)

- [ ] T022 [US3] Pruebas en rojo (`apps/api/tests/integration/channels/test_whatsapp_account_events.py`):
  - plantillas:
    - los 14 eventos de estado actualizan estado, motivo y categoría con `tenant_id`;
    - `PAUSED`, `DISABLED`, `REJECTED`, `LOCKED` y `DELETED` avisan e invalidan la caché;
    - calidad a `YELLOW`/`RED` avisa;
    - recategorización: aviso (`pending_category`) y aplicada (`previous_category`).
  - cuenta:
    - `account_update` con solo `waba_info` se aplica a los números de esa WABA del negocio, y a ningún otro negocio;
    - `ACCOUNT_RECONNECTED` limpia el problema;
    - `account_alerts` `CRITICAL` + `ACTIVE` da `account_alert`, y la informativa solo va a `config.alerts`;
    - `account_review_update` `REJECTED` da `account_review`;
    - `business_capability_update` y `phone_number_quality_update` escriben `messaging_limit`;
    - `phone_number_name_update` `REJECTED` avisa con el motivo;
    - `business_username_updates` escribe `username`.

  _Requisitos: 4.1–4.4, 2.5, 8.4_
- [ ] T023 [US3] `apps/api/src/nexus_api/services/whatsapp_account_events.py` (atribución por `resolve_waba_tenants` y aplicación bajo RLS de cada negocio). El router despacha ahí. Avisos con `channel_config.announce` / `console_notifications.emit`.
  _Requisitos: 4.1–4.4, 2.5_
- [ ] T024 [US3] Pruebas en rojo del cron (`apps/worker/tests/unit/test_whatsapp_health_cron.py`, nuevo):
  - con un problema de cuenta, la calidad `GREEN` no lo limpia;
  - con uno de calidad, `GREEN` sí lo limpia;
  - lee `whatsapp_business_manager_messaging_limit` y `name_status`.

  _Requisitos: 4.2, 8.4_
- [ ] T025 [US3] `apps/worker/src/nexus_worker/streams/whatsapp_health_cron.py` con `config.problem_source`.
  _Requisitos: 4.2, 8.4_
- [ ] T026 [US3] Prueba de aislamiento `apps/api/tests/isolation/test_waba_event_attribution.py`:
  - un evento de la WABA de A nunca toca canales de B;
  - `resolve_waba_tenants` no devuelve filas ni datos;
  - una WABA sin dueño no se aplica.

  _Requisitos: 4.3, Garantía 1_
- [ ] T027 [US3] Consola: la página del canal (spec 047, `components/builder/channel-page.tsx` y `api/console/channel_config.py` `page()`) enseña nombre de usuario, nombre visible y su decisión, límite, revisión y alertas. Las plantillas (`components/channels/templates-section.tsx`) enseñan calidad y categoría pendiente. Vitest de los estados.
  _Requisitos: 4.1, 4.2, 4.4, 8.4_

## Fase 5 — Historia 4: una baja se respeta siempre (P1)

- [ ] T028 [US4] Pruebas en rojo (`apps/api/tests/integration/channels/test_whatsapp_opt_outs.py`):
  - `user_preferences` `stop` crea una baja `scope=marketing`, `source=meta`, por `customer_id` (con o sin teléfono);
  - `resume` la levanta y deja constancia;
  - la palabra «baja» crea `scope=marketing`, `source=keyword` y **llega a la bandeja** sin turno;
  - con baja de marketing, la difusión y la plantilla `MARKETING` se bloquean y la de `UTILITY` sale;
  - una fila antigua `scope=all` sigue bloqueándolo todo;
  - el operador levanta una baja de palabra clave con motivo; una de Meta da 409 `lifted_by_person_only`.

  _Requisitos: 5.1–5.5, CE-005_
- [ ] T029 [US4] `apps/api/src/nexus_api/services/whatsapp_opt_outs.py`. Router (`user_preferences` y palabra clave). Despachador (`streams/outbound.py`, por `scope` y categoría de plantilla). Difusiones (`services/broadcasts.py`).
  _Requisitos: 5.1–5.4_
- [ ] T030 [US4] Panel: `GET /admin/tenants/{tenant_id}/opt-outs` y `POST …/opt-outs/{id}/lift` (`apps/api/src/nexus_api/api/admin/opt_outs.py`), con la lista en la ficha del cliente del panel y su auditoría `customer.opt_out.lifted`.
  _Requisitos: 5.5_

## Fase 6 — Cierre de la iteración 1

- [ ] T031 `NODE_OPTIONS=--experimental-require-module ./scripts/verify.sh lint` y las suites de las fases 1 a 5, por fichero. Subir a `develop`, CI en verde y staging: escenarios 1 a 14 de [quickstart.md](quickstart.md).
  _Requisitos: CE-001–CE-008_
- [ ] T032 KB: nota de sesión y actualización de `kb/Auphere/nexus/whatsapp-connector/04-webhooks.md` y `02-embedded-signup.md` (v4/v5, BSUID, eventos).
  _Requisitos: §IX_

## Iteración 2 — Historias 5 y 6 (P2) *(por bloques; se detalla al empezarla)*

- [ ] T040 [US5] **Primero, riesgo D7.3**: probar en staging la Resumable Upload API con el token del negocio. Si falla, decidir la alternativa (token del operador) y anotarla en research.
  _Requisitos: 6.1_
- [ ] T041 [US5] Plantillas completas:
  - pruebas en rojo de `TemplateCreateIn` (cabecera multimedia, autenticación con `COPY_CODE`, carrusel de 2 a 10, validaciones de [console-api.md](contracts/console-api.md)) y de `_build_template_components` (multimedia, código, carrusel);
  - `services/whatsapp_media_upload.py`;
  - compositor de la consola (`template-composer.tsx`, `template-rules.ts`) con vitest.

  _Requisitos: 6.1–6.5_
- [ ] T042 [US5] Entrantes:
  - `button` va al agente con su plantilla;
  - `referral` se guarda en `conversations.ad_referral` (migración `0207`) y va como contexto de datos;
  - `contacts` legibles.

  Pruebas de webhook y de turno.
  _Requisitos: 7.1–7.3_
- [ ] T043 [US5] Salientes:
  - indicador de escritura junto al acuse (`runtime/read_receipts.py`);
  - ramas `location` y `location_request` en el despachador;
  - `notification.request_location` en el MCP;
  - perfil de capacidades de WhatsApp corregido.

  Con sus pruebas.
  _Requisitos: 7.4–7.6_
- [ ] T044 [US6] Precio y límites:
  - `messages.pricing_billable` / `pricing_type` (migración `0207`) desde el estado;
  - `GET /usage/meta-messages`;
  - bloque «Mensajes de Meta» en Consumo, separado de las líneas de Auphere.

  Con sus pruebas.
  _Requisitos: 8.1–8.4_

## Iteración 3 — Historias 8 y 9 (P2, catálogo) *(por bloques)*

- [ ] T050 [US9] `MetaClient`: `create_catalog`, `create_product`, `update_product`, `delete_product`, `list_products`, `product_feeds` y `commerce_settings`, con pruebas sobre `MockTransport`.
  _Requisitos: 11.3, 11.4_
- [ ] T051 [US9] API `api/console/channel_catalog.py` según [console-api.md](contracts/console-api.md): `If-Match`, `read_only_source` y auditoría. Pruebas de integración en rojo primero.
  _Requisitos: 11.2–11.8, 11.11_
- [ ] T052 [US9] Sección «Catálogo» en `components/builder/channel-page.tsx`: entrada en `SECTIONS`; crear o enlazar, lista con buscador y filtro, panel lateral, borrar con confirmación, solo lectura y coexistencia, y los estados de vacío, carga, error y parcial. Vitest y axe.
  _Requisitos: 11.1, 11.2, 11.5–11.10_
- [ ] T053 [US9] Herramientas de catálogo derivadas del canal en el cargador del turno, filtrando agotado, oculto y rechazado. Prueba de aislamiento `apps/api/tests/isolation/test_catalog_tools_per_channel.py`.
  _Requisitos: 11.9, 11.12, Garantía 1_
- [ ] T054 [US9] Revisión de diseño sobre la pantalla real (`design:design-critique` / `impeccable`) y corrección de lo que salga.
  _Requisitos: 11.2_
- [ ] T055 [US8] Kit de revisión de `catalog_management` y `business_management`:
  - número de demo por Cloud API;
  - guion y descripciones;
  - instrucciones del revisor unificadas con Instagram y Messenger (`specs/049-meta-instagram-messenger/app-review-instructions-instagram-messenger.md`);
  - comprobar que las configuraciones de inicio de sesión de WhatsApp piden `business_management` (cambio del owner en el Dashboard).

  _Requisitos: 10.1–10.4_

## Iteración 4 — Historia 7 (P3, perfil) *(por bloques)*

- [ ] T060 [US7] `GET/PUT /channels/{id}/whatsapp-profile` con sus límites y coexistencia (409). Foto por Resumable Upload. Sección «Perfil» en la página del canal. Auditoría con los nombres de los campos cambiados. Con sus pruebas.
  _Requisitos: 9.1–9.3_

## Dependencias y orden

- La fase 1 bloquea las fases 2 a 5. Dentro de la iteración 1:
  - las fases 2 (identidad) y 3 (conexión) son independientes y se pueden hacer en paralelo;
  - la 4 y la 5 dependen de la fase 1 y de la identidad (T009) para atar las bajas a `customer_id`.
- **La fase 3 tiene fecha**: debe estar en producción antes del **2026-11-16**.
- La iteración 2 depende de T040. La iteración 3 depende de la base de la iteración 1 (identidad y salud) y de T040 para las imágenes de producto.

## Paralelizable

- T003 con T002.
- T013–T015 (frontend del alta) con T004–T012 (parser e identidad).
- T016–T017 (versión) en paralelo con la fase 2.

## Estrategia

Lo mínimo entregable es la **iteración 1**: nada se pierde, la conexión sobrevive al 16 de noviembre, la cuenta avisa y las bajas se respetan. Se promueve a producción en cuanto pase staging. Las iteraciones 2 a 4 se detallan al empezar cada una.
