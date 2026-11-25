---

description: "Tareas de la spec 076 — conversiones de anuncios de WhatsApp"
---

# Tasks: Conversiones de anuncios de WhatsApp

**Input**: Design documents from `/specs/076-conversiones-whatsapp/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/api-y-eventos.md](contracts/api-y-eventos.md), [quickstart.md](quickstart.md)

**Tests**: obligatorios (constitución §VII). Cada bloque de pruebas se escribe y se ve en rojo antes de su implementación.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero (§VII)**: rojo antes que implementación.
- **Aislamiento (§I)**: garantías 1, 6 y 8.
  - La 8 va en T015 y T040.
  - La 1 va en T038.
  - La 6 va en T039.
  - Los barridos `test_21`, `test_43`, `test_22`, `test_console_scope`, `test_lite_*` y `test_bootstrap_split` se corren en T047.
- **Licencias (§VIII)**: no entra ninguna dependencia.
- **Medidor**: nada nuevo.
- **Suites de una en una**, con base propia (`nexus_test_076`) y Redis 13. Las del worker van aparte de las de la API, con `uv run --with lupa`.
- **Nada se crea ni se cambia en Meta desde el código.** Las tareas marcadas **(Luis)** son pasos suyos en el panel de Meta o en Terraform.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (ficheros distintos, sin dependencias pendientes)
- **[Story]**: US1 origen de anuncio · US2 informe · US3 medición en Meta · US4 el permiso

---

## Phase 1: Setup

**Propósito**: saber que el punto de partida está en verde.

- [x] T001 Correr en la rama (`bfe97215`), de una en una y con la base `nexus_test_076`, las suites que ya cubren lo que se toca, y anotar aquí el resultado:
  - `apps/channels/tests/test_meta_webhook_adapter_2026.py`
  - las pruebas del webhook de Meta en `apps/api/tests` (las que importan `api/webhooks/meta.py`)
  - `apps/api/tests/integration/reservas/test_tools.py` y `test_api_services.py`
  - las de `api/console/channel_config.py`, `api/console/whatsapp.py` y `api/console/lite/inbox.py`
  - `apps/api/tests/isolation/test_console_scope.py`, `test_21_rls_covers_every_tenant_table.py`, `test_43_force_and_composite_fk_sweep.py`
  - `apps/worker/tests/unit/test_bootstrap_split.py`
  - en la consola, `pnpm vitest run src/components/builder src/components/inbox`

  _Requisitos: 1.1, 2.1, 4.6, 5.1_

---

## Phase 2: Foundational

**Propósito**: la migración, los modelos, los ajustes y el contexto de la conversación, que usan las tres historias de código.

- [x] T002 Crear `apps/api/tests/integration/test_migration_0241_ad_conversions.py` (rojo). Comprueba las tres tablas de [data-model.md](data-model.md):
  - `customer_ad_referrals`:
    - `provider_message_id varchar(512) NOT NULL`;
    - `source_type varchar(8)` con CHECK `ad`/`post`;
    - `ctwa_clid varchar(256) NULL`;
    - `UNIQUE (tenant_id, provider_message_id)` y `UNIQUE (tenant_id, id)`;
    - índice `(tenant_id, customer_id, channel_id, clicked_at DESC)`.
  - `channel_ad_measurement`:
    - `UNIQUE (tenant_id, channel_id)`;
    - `enabled boolean NOT NULL DEFAULT false`;
    - `meta_dataset_id varchar(64) NULL`.
  - `ad_conversion_events`:
    - CHECK de `event_name` (`Purchase`, `LeadSubmitted`, `OrderCreated`, `OrderCanceled`), de `status` (`pending`, `sent`, `failed`, `discarded`) y de `source_kind` (`reservation`, `woo_order`);
    - `UNIQUE (tenant_id, event_id)` y `UNIQUE (tenant_id, id)`;
    - `cancels_event_id` con FK compuesta a sí misma;
    - índice parcial `WHERE status = 'pending'`.
  - En las tres: FORCE RLS, política `<tabla>_tenant_isolation`, FK compuestas `(tenant_id, x_id)` y `GRANT` a `nexus_app`.
  - La fila `console.channel.ad_measurement` en `console_audit_vocabulary`.
  - `downgrade` deja la base como estaba.

  _Requisitos: 1.1, 4.2, 4.5, 6.2_
- [x] T003 Escribir `apps/api/alembic/versions/0241_ad_conversions.py` (`down_revision = "0240_respond_bindings_to_agents"`), con el patrón de `0233_quedate_connector.py` y la fila de vocabulario como en la 0233 (:46-68). T002 en verde.
  _Requisitos: 1.1, 4.2, 4.5, 6.2_
- [x] T004 [P] Modelos `CustomerAdReferral`, `ChannelAdMeasurement` y `AdConversionEvent` en `apps/api/src/nexus_api/db/models/ad_conversion.py`, exportados en `db/models/__init__.py`, con `UUIDPrimaryKey`, `TimestampMixin` y `TenantScopedMixin`. Llevan las mismas restricciones que la migración, para que el ORM y la base no diverjan.
  _Requisitos: 1.1, 4.2, 6.2_
- [x] T005 [P] Ajustes:
  - En `apps/api/src/nexus_api/config.py`: `ad_measurement_tenants: list[UUID] = []`, `ad_measurement_general_availability: bool = False`, `meta_capi_test_event_code: str | None = None`, `meta_config_id_wa_events_test_cloud_api: str | None = None`, `meta_config_id_wa_events_test_coexistence: str | None = None`.
  - En `apps/worker/src/nexus_worker/config.py`: `retention_ad_click_days: int = 90`, `conversion_dispatch_tick_seconds: float = 60.0`.
  - Prueba unitaria de valores por defecto y de lectura desde el entorno (`NEXUS_…`).

  _Requisitos: 1.7, 4.1, 4.7, 7.2_
- [x] T006 `conversation_context` y `get_current_conversation()` en `apps/api/src/nexus_api/core/tenant_context.py`, al lado de `customer_context`. El pipeline lo abre junto a `customer_context` (`apps/worker/src/nexus_worker/runtime/pipeline.py:~1985`). Prueba unitaria: dentro del turno se lee la conversación y fuera vale `None`.
  _Requisitos: 5.1, 5.4_

**Checkpoint**: migración y modelos en verde. Las historias pueden empezar.

---

## Phase 3: User Story 1 — El negocio sabe de qué anuncio viene cada cliente (P1) 🎯 MVP

**Goal**: el clic se guarda por contacto y número, el agente lo recibe como dato, la Bandeja lite lo enseña y el identificador del clic se borra a los 90 días.

**Independent Test**: llega un mensaje con origen de anuncio. La conversación lo muestra, el agente lo recibe cercado, y otro contacto del mismo negocio no lo ve.

### Tests for User Story 1 ⚠️ (rojo primero)

- [x] T007 [P] [US1] `apps/api/tests/unit/test_076_referral_whitelist.py`. Prueba la función que arma `referral_json` en `api/webhooks/meta.py`:
  - solo pasan las claves de la lista blanca;
  - los topes de [contracts §1](contracts/api-y-eventos.md) se cumplen;
  - un `source_type` distinto de `ad`/`post` descarta todo;
  - sin claves útiles, no hay campo;
  - el stream lleva `referral_json` cuando el mensaje trae `referral` (fixture `message_with_referral.json`).

  _Requisitos: 1.1_
- [x] T008 [P] [US1] `apps/worker/tests/unit/test_076_inbound_referral.py`:
  - `_to_event` parsea `referral_json`;
  - un JSON roto no tira el mensaje y deja `inbound.referral_unreadable` con `tenant_id`;
  - `accept_inbound` guarda una fila en `customer_ad_referrals` con contacto, conversación, número y `clicked_at`;
  - el mismo `provider_message_id` dos veces deja una sola fila;
  - un segundo clic del mismo contacto añade otra fila.

  _Requisitos: 1.1, 1.2_
- [x] T009 [P] [US1] `apps/worker/tests/unit/test_076_ad_note.py`:
  - la nota sale cuando el último clic del contacto llegó después de `coalesce(context_from, created_at)` de la conversación, y no sale con un clic anterior;
  - lleva el tipo, el titular (hasta 120) y el texto (hasta 280), saneados y cercados con `ad_referral`;
  - nunca lleva `ctwa_clid` ni la URL;
  - un anuncio con «ignora tus instrucciones…», saltos de línea y caracteres de formato llega dentro del cerco, sin romperlo.

  _Requisitos: 1.4, 1.5_
- [x] T010 [P] [US1] `apps/api/tests/integration/test_076_lite_ad_origin.py`:
  - `GET /console/lite/inbox/conversations/{id}` devuelve `ad_origin` con el último clic del contacto (`kind`, `headline`, `url`) y nunca `ctwa_clid`;
  - sin clic, `ad_origin` es `null`;
  - sin titular, `headline` es `null` y `kind` sigue.

  _Requisitos: 1.3, 2.1, 2.2, 2.3_
- [x] T011 [P] [US1] `apps/worker/tests/unit/test_076_ad_click_retention.py`:
  - borra `ctwa_clid` de los clics de hace más de `retention_ad_click_days` y conserva el resto;
  - con 0 no hace nada;
  - trabaja tenant a tenant con `tenant_scoped_session`;
  - no hace E/S al construirse.

  _Requisitos: 1.7_

### Implementation for User Story 1

- [x] T012 [US1] `api/webhooks/meta.py`: la función de lista blanca y topes, y la clave `referral_json` en `fields`. T007 en verde.
  _Requisitos: 1.1_
- [x] T013 [US1] Worker:
  - `InboundEvent.referral` (`runtime/dispatcher.py`);
  - el parseo en `streams/consumer._to_event`;
  - `persistence/ad_referrals.store_referral(session, …)` con `INSERT … ON CONFLICT (tenant_id, provider_message_id) DO NOTHING`, llamado en `accept_inbound` tras `upsert_conversation_for_customer`;
  - log `ad_referral.stored` con `tenant_id`, `channel_id` y `source_type`.

  T008 en verde.
  _Requisitos: 1.1, 1.2_
- [x] T014 [US1] `TAG_AD_REFERRAL = "ad_referral"` en `core/guardrails/untrusted.py`, y `_safe_ad_text` y `_ad_note` en `runtime/pipeline.py`, añadida en `_load_recent_history` igual que `_contact_note`. T009 en verde.
  _Requisitos: 1.3, 1.4, 1.5_
- [x] T015 [US1] `apps/api/tests/isolation/test_076_ad_click_customer_axis.py` (garantía 8, primera parte). Con dos contactos del mismo tenant, el clic de A nunca aparece en:
  - `ad_origin` de la conversación de B;
  - la nota del turno de B.

  La prueba barre las lecturas del clic, no solo estos dos sitios. Se ve en rojo contra una lectura que no filtra por contacto.
  _Requisitos: 1.6_
- [x] T016 [US1] `ConversationDetailOut.ad_origin` (`AdOriginOut`) en `api/console/lite/inbox.py`, leído con el contacto de la conversación. T010 y T015 en verde.
  _Requisitos: 1.3, 1.6, 2.1, 2.2, 2.3_
- [x] T017 [US1] Consola lite:
  - el tipo en `lib/backend/inbox.ts`;
  - la línea «Desde un anuncio: …», con enlace externo `rel="noopener noreferrer"`, en `components/inbox/thread-header.tsx`;
  - la fila «Llegó por» en `components/inbox/contact-panel.tsx`;
  - los textos en `i18n/lanes/inbox.ts`;
  - Vitest: con titular, sin titular («Desde un anuncio» o «Desde una publicación») y sin origen, donde no se pinta nada.

  _Requisitos: 2.1, 2.2, 2.3_
- [x] T018 [US1] Regenerar `apps/mobile/src/api/openapi.json` y `schema.gen.ts` (`scripts/export_openapi.py`), y `lite.gen.ts` si cambian textos compartidos. `export_openapi.py --check` en verde.
  _Requisitos: 2.1_
- [x] T019 [US1] `apps/worker/src/nexus_worker/streams/ad_referral_retention_cron.py`, con el patrón de `meta_social_cron.py`, una vez al día. Se declara en `bootstrap.py` (import, `SCHEDULER_TASK_NAMES` y `_spawn` en `scheduler_tasks()`) **y en `ALL_EXPECTED` de `tests/unit/test_bootstrap_split.py`**. T011 y `test_bootstrap_split.py` en verde.
  _Requisitos: 1.7_
- [x] T020 [US1] Docs, en el mismo commit que el código: el origen de anuncio en `docs/canales.md` y «Desde un anuncio» en `docs/consola-lite.md`.
  _Requisitos: 1.1, 2.1_

**Checkpoint**: la historia 1 se puede fusionar sola. No necesita nada de Meta.

---

## Phase 4: User Story 2 — El partner ve qué anuncios traen reservas (P2)

**Goal**: la pestaña «Anuncios» del cliente: por anuncio, conversaciones, reservas del agente e importe, en 7, 30 o 90 días.

**Independent Test**: con conversaciones de dos anuncios y reservas en una, el informe da los números exactos y no cuenta las canceladas.

### Tests for User Story 2 ⚠️

- [x] T021 [P] [US2] `apps/api/tests/integration/test_076_ads_report.py`:
  - una fila por anuncio, con `conversations` (conversaciones distintas con un clic de ese anuncio en el periodo) y `bookings` (reservas `origin='agent'` no canceladas del periodo, atribuidas al último clic del contacto **en el número de su conversación** anterior a la reserva);
  - una reserva cancelada no cuenta;
  - una reserva sin precio cuenta sin importe;
  - una reserva de la consola no cuenta;
  - `amounts` por moneda;
  - `days` fuera de 7, 30 o 90 da 422;
  - clics sin `source_id` en una fila con `ad_id: null`;
  - orden por `bookings` y después `conversations`;
  - la respuesta no tiene campos `body`, `text`, `message`, `content` ni `reason`, ni nombres o teléfonos.

  _Requisitos: 3.1, 3.2, 3.3, 3.5, 3.6_

### Implementation for User Story 2

- [x] T022 [US2] `ads_report(session, *, days)` en `apps/api/src/nexus_api/services/ad_conversions.py`, y el router `apps/api/src/nexus_api/api/console/ads.py` (`GET /clients/{ref}/ads/report`, `client_scope("conversations:read")`), incluido en `api/console/__init__.py`. T021 en verde y `test_console_scope.py` en verde.
  _Requisitos: 3.1, 3.2, 3.3, 3.6_
- [x] T023 [US2] Consola de partners:
  - `lib/backend/ads.ts` y su `...adsApi(call)` en `lib/backend.ts`;
  - `app/(console)/clients/[ref]/ads/page.tsx`, `loading.tsx` (esqueleto con la forma final) y `error.tsx`;
  - `components/ads/ads-report.tsx`, con el selector 7, 30 o 90, la tabla, el vacío del requisito 3.5 y el error con «Reintentar»;
  - la pestaña en `components/clients/v2/client-header-v2.tsx` (`TABS`) y `components/shell/routes-v2.ts` (`ClientTab`);
  - los textos en `i18n/lanes/ads.ts`, que dicen qué mide cada columna;
  - Vitest: con filas, vacío, cargando y error.

  _Requisitos: 3.1, 3.4, 3.5_
- [x] T024 [US2] La pestaña Anuncios en `docs/console.md`.
  _Requisitos: 3.1_

**Checkpoint**: la historia 2 se puede fusionar sola.

---

## Phase 5: User Story 3 — El negocio mide y optimiza sus anuncios en Meta (P2)

**Goal**: activar la medición por número; encolar los resultados del agente; enviarlos a Meta con el clic o el teléfono cifrado.

**Independent Test**: en staging, con el número de Auphere, un clic de anuncio de prueba y una reserva del agente dan un único `Purchase` en los Eventos de prueba de Meta en menos de una hora.

### Desconocidos primero (staging)

- [ ] T025 [US3] **(Luis)** Crear en Meta las dos configuraciones de registro insertado de pruebas (copias de Cloud API y de Coexistencia con `whatsapp_business_manage_events`) y dar sus ids.
  _Requisitos: 7.2_
- [ ] T026 [US3] Con T025 hecha y el código de esta fase en staging, resolver los desconocidos de [research.md](research.md) y anotar aquí cada resultado y la alternativa aplicada (quickstart, escenarios 3b, 4, 6 y 10):
  - reconectar un número vivo es seguro;
  - crear el conjunto de datos con acceso estándar;
  - evento sin clic (Página);
  - coexistencia;
  - y los códigos de error reales de Meta.

  **Primer resultado (2026-11-24, staging):** `NEXUS_AD_MEASUREMENT_TENANTS` puesto para «Meta Review Demo» (Terraform, workspace `staging`). En su número …1693 (Cloud API, agente Ava), «Activar» respondió **200**: el token del número **ya trae** `whatsapp_business_manage_events`, y el conjunto de datos se creó o se obtuvo y quedó vinculado con el **acceso estándar**. Así que para este número no hizo falta T025 ni volver a conectar. La auditoría lo registró y después se desactivó (el conjunto de datos sigue vinculado). Sigue sin probar: un evento enviado de verdad (hace falta una reserva de Ava en el chat), el evento sin clic, la coexistencia y los códigos de error.

  _Requisitos: 4.2, 4.3, 5.7, 7.1_

### Tests for User Story 3 ⚠️

- [x] T027 [P] [US3] `apps/api/tests/unit/test_076_phone_hash.py`:
  - `(650)555-1212` con el prefijo de EE. UU. se normaliza a `16505551212` y da `e323ec626319ca94ee8bff2e4c87cf613be6ea19919ed1364124e16807ab3176`;
  - quita símbolos, letras y ceros iniciales;
  - un teléfono sin dígitos suficientes da `None`.

  _Requisitos: 5.7, 6.4_
- [x] T028 [P] [US3] `apps/api/tests/unit/test_076_event_rules.py`:
  - reserva con precio → `Purchase` con `value_minor` y `currency`;
  - sin precio → `LeadSubmitted` sin importe;
  - pedido → `OrderCreated`, con el total pasado a unidades menores con `ZERO_DECIMALS` (CLP 15000 → 15000; EUR 12.50 → 1250);
  - `event_id` es `"{source_kind}:{source_id}:{event_name}"`;
  - `value` a Meta en unidades mayores (CLP 15000 → 15000; EUR 1250 → 12.5).

  _Requisitos: 5.1, 5.2, 5.4, 6.2_
- [x] T029 [P] [US3] `apps/channels/tests/test_076_meta_conversions_client.py`, con `httpx.MockTransport`:
  - `token_scopes` lee `data.scopes` y `data.granular_scopes[].scope`;
  - `ensure_dataset` hace `POST /{waba_id}/dataset` y devuelve el `id`;
  - `send_conversion_event` hace `POST /{dataset_id}/events` con el cuerpo de [contracts §4.3](contracts/api-y-eventos.md), `partner_agent` y `test_event_code` solo si se pasa;
  - los errores se clasifican como hoy (transitorio, límite de ritmo, token, 4xx).

  _Requisitos: 4.2, 4.3, 6.3, 6.4_
- [x] T030 [P] [US3] `apps/api/tests/integration/test_076_ad_measurement_endpoint.py`:
  - número que no admite la medición (tenant fuera de la lista, apertura cerrada, coexistencia, canal que no es WhatsApp) → sin bloque y `PUT` 404;
  - activar sin `confirm_data_sharing` → 422 `confirm_required`;
  - token sin el permiso → 409 `reauthorize` y sigue apagada;
  - activar → `ensure_dataset`, `meta_dataset_id` guardado, `enabled_by` y auditoría `console.channel.ad_measurement` con la confirmación;
  - fallo de Meta → 502 y nada activado;
  - desactivar → los pendientes del número pasan a `discarded` y queda en la auditoría;
  - el bloque trae `state`, `sent_7d`, `last_error` y `reconnect_config_id` (el de pruebas del modo si está puesto, y si no el normal).

  _Requisitos: 4.1–4.8, 7.2, 7.4_
- [x] T031 [P] [US3] `apps/api/tests/integration/test_076_whatsapp_reconnect_quota.py`: un cliente en su tope que reconecta el mismo `phone_number_id` no recibe 409; uno que añade un número nuevo, sí.
  _Requisitos: 4.3_
- [x] T032 [P] [US3] `apps/api/tests/integration/test_076_enqueue.py`:
  - reserva del agente con precio → `Purchase`, y sin precio → `LeadSubmitted`;
  - no encolan: reserva de la consola, de la lista de espera (con `agent_id`) o de llegada sin reserva, ni nada con la medición apagada;
  - baja activa del contacto en ese número (por `customer_id` o por `recipient_phone`, cualquier `scope`, `opted_in_at IS NULL`) → nada; una baja levantada o de otro número no bloquea;
  - atribuye el último clic **del mismo número**, y un clic en otro número no cuenta;
  - sin clic y sin teléfono → nada;
  - un reintento del turno deja un solo evento;
  - cancelar una reserva con evento → `OrderCanceled` con `cancels_event_id`, el mismo `referral_id`, `value_minor` y `currency`, aunque haya un clic más nuevo;
  - cancelar sin evento → nada;
  - cancelar desde la consola también encola;
  - `woocommerce.create_order` y `build_checkout_link` con la medición activa encolan un `OrderCreated` con la conversación del turno, y sin conversación del turno no encolan.

  _Requisitos: 5.1–5.9, 6.2, 6.6_
- [x] T033 [P] [US3] `apps/worker/tests/unit/test_076_conversion_dispatcher.py`:
  - reserva filas `pending` con plazo (`SKIP LOCKED`) y envía fuera de la transacción;
  - cuerpo con clic `{whatsapp_business_account_id, ctwa_clid}` y sin clic `{…, whatsapp_phone_number_id, ph}`;
  - evento de más de 6 d 23 h → `failed` (`too_old`) sin llamar a Meta;
  - transitorio → reintento con espera de 1 min × 2^n, hasta 6;
  - token o permiso → `failed` y `last_error_code = reauthorize` en la medición;
  - otro 4xx → `failed` con `meta_<code>`;
  - la medición apagada o una baja nueva al enviar → `discarded`;
  - un `OrderCanceled` espera sin gastar intentos a que su original sea final: sale si el original queda `sent`, y queda `discarded` si queda `failed` o `discarded`;
  - `test_event_code` solo si el ajuste está puesto;
  - un envío correcto limpia `last_error_*`;
  - el conjunto de datos y el token salen de la medición y las credenciales del tenant del evento;
  - no hace E/S al construirse.

  _Requisitos: 6.1–6.5, 5.3, 5.9_

### Implementation for User Story 3

- [x] T034 [US3] Funciones de normalización y cifrado del teléfono y reglas de evento en `apps/api/src/nexus_api/services/ad_conversions.py`. T027 y T028 en verde.
  _Requisitos: 5.1, 5.2, 5.4, 5.7, 6.4_
- [x] T035 [US3] `token_scopes`, `ensure_dataset` y `send_conversion_event` en `apps/channels/src/nexus_channels/whatsapp_meta/meta_client.py`, sin cambiar lo que ya hace el cliente. T029 en verde.
  _Requisitos: 4.2, 4.3, 6.3_
- [x] T036 [US3] Medición y reconexión:
  - `apps/api/src/nexus_api/services/ad_measurement.py`: disponibilidad (D10), permiso, conjunto de datos, activar y desactivar, bloque de estado y `reconnect_config_id`;
  - en `api/console/channel_config.py`: el bloque `ad_measurement` en `ChannelPageOut` y `PUT /clients/{ref}/channels/{channel_id}/ad-measurement` con `client_scope("channels:write")` y `_audit(…, "console.channel.ad_measurement", …)`;
  - la etiqueta en `api/console/audit_words.py`;
  - la cuota de `api/console/whatsapp.py` no cuenta el número que se reconecta.

  T030, T031 y `test_console_scope.py` en verde.
  _Requisitos: 4.1–4.8, 7.2, 7.4_
- [x] T037 [US3] Encolar:
  - `enqueue_for_booking`, `enqueue_cancellation` y `enqueue_for_order` en `services/ad_conversions.py`, llamados desde `services/reservations/core.create_booking` (solo `origin == "agent"`) y `cancel_booking` (cualquier actor), en la misma transacción;
  - `reservas._turn` (`apps/mcp/src/nexus_mcp/servers/reservas/tools.py`) usa primero `get_current_conversation()`;
  - `woocommerce.create_order` y `build_checkout_link` (`apps/mcp/src/nexus_mcp/servers/woocommerce/tools.py`) encolan tras crear el pedido.

  Logs `ad_conversion.enqueued`. T032 en verde, y `test_51_new_tools_take_no_end_customer.py` sigue en verde sin cambios.
  _Requisitos: 5.1–5.9, 6.2, 6.6_
- [x] T038 [US3] `apps/api/tests/isolation/test_076_conversion_events_tenant.py` (garantía 1). Con dos tenants con la medición activa:
  - cada evento sale con el `meta_dataset_id` y el token de su tenant;
  - un evento cuyo `channel_id` no tiene medición en su tenant no sale;
  - ninguna ruta acepta un `dataset_id` o un `tenant_id` del llamante.

  Se ve en rojo contra un despachador que busca la medición sin el tenant.
  _Requisitos: 6.5_
- [x] T039 [US3] `apps/api/tests/isolation/test_076_logs_carry_no_click.py` (garantía 6). Captura los logs de encolar, enviar, fallar y descartar, y comprueba:
  - todos llevan `tenant_id`;
  - ninguno contiene el `ctwa_clid`, el teléfono ni su hash.

  _Requisitos: 6.7_
- [x] T040 [US3] Ampliar `test_076_ad_click_customer_axis.py` (garantía 8, segunda parte): el clic o el teléfono de un evento son siempre los del contacto del resultado, aunque otro contacto del mismo negocio tenga un clic más reciente.
  _Requisitos: 6.6_
- [x] T041 [US3] `apps/worker/src/nexus_worker/conversions/dispatcher.py`, con el patrón de `push/dispatcher.py` y su recorrido propio de tenants con medición activa y eventos pendientes. Se declara en `bootstrap.py` (import, el conjunto de `egress` y `_spawn`) **y en `ALL_EXPECTED`**. Logs `ad_conversion.sent`, `.failed` y `.discarded`. T033, T038, T039, T040 y `test_bootstrap_split.py` en verde.
  _Requisitos: 6.1–6.7_
- [x] T042 [US3] Consola de partners:
  - `components/builder/ad-measurement-section.tsx`: interruptor, diálogo que dice qué sale a Meta y pide confirmar, estado, último error con qué hacer, y «Volver a conectar» con `reconnect_config_id` por `loginWithMeta`;
  - montada en `components/builder/channel-page.tsx` solo si llega el bloque;
  - la acción en `app/(console)/clients/[ref]/agents/channel-actions.ts` y la llamada en `lib/backend/channel-config.ts`;
  - los textos en `i18n/lanes/builder.ts`;
  - Vitest: sin bloque no hay sección, la confirmación es obligatoria, `reauthorize` lleva a reconectar, y se ve el estado con y sin error.

  _Requisitos: 4.1, 4.3, 4.6, 4.7, 4.8_
- [x] T043 [US3] Docs: la medición en `docs/canales.md`, la sección del número en `docs/console.md` y los eventos al crear y cancelar en `docs/reservas.md`.
  _Requisitos: 4.1, 5.1, 5.3_

**Checkpoint**: la historia 3 se puede fusionar con la medición cerrada (lista vacía y sin apertura general). Solo se enciende en staging para el tenant de Auphere.

---

## Phase 6: User Story 4 — Auphere pide el permiso con un uso real (P3)

- [ ] T044 [US4] **(Luis)** Con T026 resuelta y los escenarios 1 a 9 del quickstart en verde:
  - grabar el vídeo;
  - cambiar la descripción del borrador `submission_id=1125440307039671`;
  - revisar el tratamiento de datos, marcar las certificaciones y enviar.

  _Requisitos: 7.1, 7.3_
- [ ] T045 [US4] **(Luis)** Con el acceso avanzado concedido, añadir el permiso a las configuraciones normales de Cloud API y Coexistencia en Meta, y quitar los dos ajustes de pruebas de staging.
  _Requisitos: 7.4, 7.5_
- [ ] T046 [US4] **(Luis)** Con el nivel completo de la API de marketing, poner `NEXUS_AD_MEASUREMENT_GENERAL_AVAILABILITY=true` en producción por Terraform.
  _Requisitos: 7.6_

---

## Phase 7: Polish & Cross-Cutting

- [x] T047 Verificar antes de pasar a `develop`:
  - `./scripts/verify.sh lint`;
  - de una en una, las suites de todo lo tocado y los barridos de aislamiento (`test_21`, `test_43`, `test_22`, `test_console_scope`, `test_lite_route_scope`, `test_lite_bodies_only_in_inbox`, `test_51`);
  - `test_bootstrap_split.py`;
  - `pnpm build` de la consola y `./scripts/verify.sh mobile`.

  Anotar aquí el resultado.
  _Requisitos: todos_
- [x] T048 Actualizar el estado de la nota de la KB `research/2026-11-24-conversiones-whatsapp.md` y de la spec.
  _Requisitos: —_


### Resultado de la implementación (2026-11-24)

**Punto de partida (T001)**, en `bfe97215` con `nexus_test_076`: 77 pruebas unitarias de la API, 1701 de reservas y aislamiento, 6 del contrato del worker y 15 de canales, en verde. La consola no se corrió aparte en ese momento.

**Verificación (T047)**, al cerrar:
- `./scripts/verify.sh lint`: todo verde (ruff y `mypy --strict` de API, worker, canales, MCP y renderer).
- De una en una, con `nexus_test_076`: 70 archivos de la API (los de la 076, los barridos `test_21`, `test_22`, `test_43`, `test_51`, `test_console_scope`, `test_lite_route_scope`, `test_lite_bodies_only_in_inbox` y los que tocan el webhook, la página del canal, el alta de WhatsApp, la Bandeja lite y las reservas) → **2917 en verde**. 40 del worker, con `test_bootstrap_split` → **505 en verde**. MCP (WooCommerce y reservas) → 44. Canales → 120.
- Consola: sin token de admin, `tsc`, ESLint, **2555 pruebas de Vitest** y `next build`, en verde. `./scripts/verify.sh mobile`: todo verde.
- Las pruebas de aislamiento de la 076 se vieron en rojo al romper lo que guardan: el filtro por contacto del clic (garantía 8) y un log con el cuerpo del evento (garantía 6).

**Sin comprobar:** la sección de la consola en un navegador; nada contra Meta de verdad (eso es T026). Los códigos de Graph que se leen como «falta un permiso» (10 y 200–299) son provisionales hasta verlos en staging.

**Desviaciones del plan:**
- Las pruebas que el plan ponía en `apps/worker/tests/unit` (T008, T009, T011 y T033) están en `apps/api/tests/integration` (`test_076_inbound_referral.py`, `test_076_ad_note.py`, `test_076_ad_click_retention.py` y `test_076_conversion_dispatch.py`): necesitan la base y el `conftest` de la API, y el del worker no puede ir en la misma ejecución. T010 está en `apps/api/tests/unit/test_076_lite_ad_origin.py`.
- T027 no tiene archivo propio: la normalización y el cifrado del teléfono, con el vector de Meta, están en `test_076_event_rules.py`.
- T022: el informe vive en `services/ad_report.py`, no en `ad_conversions.py`.
- T029, último punto: los pedidos de WooCommerce se prueban en `test_076_enqueue.py`, por `enqueue_for_order` y por el enganche de las herramientas (`_measure_order`), no en la prueba del cliente de Meta.
- T036: `api/console/audit_words.py` no hizo falta. La frase de `console.channel.ad_measurement` entra por la migración 0241.
- T042: los textos están en `i18n/lanes/builder-channels.ts`, donde viven los de la página del canal, no en `builder.ts`.
- El bloque `ad_measurement` lleva además `enabled` (contrato §2.1): con `reauthorize`, la consola necesita saber si ofrecer «Desactivar».
- `page_required` está en el contrato, en la consola y en los textos, pero **nada lo produce todavía**: no sabemos qué código de Graph lo dice. Hasta T026, ese error sale como `meta_<código>` con el texto general.
- `no_identity` (sin clic ni teléfono) también queda como último error del número, por el requisito 6.3 (`test_076_conversion_dispatch.py`).
- «Volver a conectar» no se ofrece con el número en pausa. El alta de Meta deja el número activo y lo reanudaría sin decirlo, así que la sección pide reanudarlo antes. Que el alta reutiliza el mismo canal, guarda el token nuevo y conserva la configuración ya lo prueban `test_endpoint_console_whatsapp.py` y `test_endpoint_meta_signup.py`.
- La garantía 6 se prueba también por el envío de verdad (`deliver` y el cliente de Meta con `respx`), con un error de Meta que repite el clic y el teléfono: ningún log lleva el clic, el teléfono, su hash ni el token.
- **Sin pasar como skills**: `ui-states-checklist`, `a11y-audit`, `responsive-audit`, `design-tokens` y `/cso`. Sí hay axe en las pruebas de la sección, los cinco estados del informe y una revisión a mano sin colores fijos ni estilos en línea. `/cso` y la revisión de seguridad quedan para antes del PR a `main`.
- **Para encenderlo en staging** hay que poner `NEXUS_AD_MEASUREMENT_TENANTS` (y, si se usan, `NEXUS_META_CONFIG_ID_WA_EVENTS_TEST_*` y `NEXUS_META_CAPI_TEST_EVENT_CODE`). Ninguno está en Terraform todavía: sin ellos, la sección no se ofrece en ningún número.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T006)** → historias.
- **US1 (T007–T020)** no depende de las otras. Es el MVP.
- **US2 (T021–T024)** lee las tablas de la US1 y las reservas. Puede ir en paralelo con la US1 una vez hecha la fase 2, pero su prueba necesita clics guardados: más cómodo después de T013.
- **US3 (T025–T043)**:
  - necesita T013 (clics guardados) y T006 (contexto de conversación);
  - T025 y T026 necesitan a Luis y staging, y no bloquean escribir ni probar en local T027–T043;
  - T026 puede cambiar T036 (reconexión) y los códigos de error de T041.
- **US4 (T044–T046)** necesita la US3 en staging y a Luis.
- **T047** al final de cada historia que se vaya a fusionar, y entero antes de `main`.

## Parallel Opportunities

- Fase 2: T004 y T005 en paralelo tras T003.
- US1: T007–T011 en paralelo; después T012 (API), T013 (worker) y T017 (consola, sobre el contrato) por separado.
- US3: T027–T033 en paralelo; T035 (canales) y T042 (consola) en paralelo con T036 y T037.

## Implementation Strategy

1. **MVP**: fase 2 y US1. El negocio ve de qué anuncio viene cada cliente y el agente lo sabe. Sin Meta.
2. **US2**: el informe para el partner.
3. **US3** en local hasta T043, con la medición cerrada. Después, staging con el tenant de Auphere y T026.
4. **US4**: la solicitud a Meta y la apertura, que son pasos de Luis.
