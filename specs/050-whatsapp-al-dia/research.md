# Investigación (Fase 0): 050 — WhatsApp al día

Fecha: 2026-10-29. Fuentes:

- **Documentación oficial de Meta.** Raíz: `developers.facebook.com/documentation/business-messaging/whatsapp/`, abreviada `D/`. Para cada decisión se cita la página.
- **Lectura del código de `develop`.** Rutas relativas al repo.

Lo marcado **SIN CONFIRMAR** se prueba en staging antes de cerrar su tarea.

## D1 — Lotes completos del webhook

**Hallazgo.** Cada handler vuelve a leer el payload entero y toma solo el primer elemento:

- `parse_inbound` (`webhook_adapter.py:258`), `parse_status_callback`, `parse_message_echo` y los de coexistencia;
- en `meta.py:294-324` el bucle recorre los cambios, pero cada vuelta procesa el mismo primer elemento.

Con N mensajes en un lote, el primero se procesa N veces (el dedupe lo frena) y el resto se pierde.

**Decisión.**
1. Los parsers devuelven **listas por `change`** (`iter_inbound_messages` ya existe). El router itera elemento a elemento.
2. Cada elemento se procesa en su propio bloque: un fallo se registra (`webhook.meta.element_failed`, sin datos personales) y no corta el lote.
3. El ack sigue siendo 200 salvo por firma inválida.

**Alternativas descartadas.** Encolar el payload entero para que lo trocee el worker: retrasa el dedupe y la atribución, y el ack ya es barato.

## D2 — Identidad: BSUID, teléfono y nombre de usuario

**Contrato de Meta** (`D/business-scoped-user-ids/`, `D/webhooks/reference/messages/system.md`):

- `messages[].from_user_id` y `contacts[].user_id` (BSUID, `CC.<hasta 128 alfanuméricos>`) **siempre** vienen.
- `from` y `wa_id` (teléfono) son **opcionales**. Faltan cuando la persona adoptó nombre de usuario y no hubo contacto con ese número en 30 días, ni está en la agenda del negocio.
- `profile.username` es opcional.
- Mensajes `system`:
  - `user_changed_number`: trae el `wa_id` nuevo y `user_id`;
  - `user_changed_user_id`: trae `user_id` y `previous_user_id`.
- Estados: `recipient_user_id` siempre; `recipient_id` puede faltar.
- Enviar a un BSUID: campo `recipient` (si van `to` y `recipient`, gana `to`).
- Las plantillas de autenticación (copiar código, un toque, cero toques) **no** se pueden enviar a un BSUID (error `131062`).

**Código hoy.**

- `customers.identifier` es único por tenant y guarda el `from` de Meta (dígitos).
- `_build_inbound` exige `from` (`webhook_adapter.py:491`): un mensaje solo con BSUID se descarta.
- Más de 15 sitios tratan `identifier` como teléfono: bajas, audiencia de prueba, envíos, cobranza, reservas, pagos, alertas, bandeja.
- El hilo del agente es `make_thread_id(tenant, channel, user_id)`.

**Decisión.**

1. `customers.identifier` **no cambia de significado ni de valor una vez creado**: sigue siendo la clave del hilo y de todo lo que ya existe.
   - Persona nueva con teléfono: `identifier` = teléfono (como hoy).
   - Persona nueva sin teléfono: `identifier` = BSUID.
2. Columnas nuevas en `customers`: `bsuid` (único por tenant cuando no es nulo), `phone` (dígitos E.164, índice por tenant) y `username`.
3. Resolución en el worker, en este orden: por `bsuid` → por `phone` / `identifier` = teléfono → crear. Si el evento trae los dos y el cliente existe por teléfono sin BSUID, se le **añade** el BSUID: es la misma persona porque Meta los da juntos.
   - Nunca se funden dos clientes existentes. Si el BSUID y el teléfono apuntan a dos filas distintas, gana la del BSUID y queda un aviso de log (`customer.identity_conflict`) para revisión.
4. Mensajes `system`: `user_changed_number` actualiza `phone`; `user_changed_user_id` actualiza `bsuid`. No disparan al agente.
5. **Envío:** teléfono si lo hay (`to`); si no, `recipient` = BSUID. Una plantilla de autenticación a alguien sin teléfono se rechaza antes de llegar a Meta, con motivo `needs_phone`.
6. Las columnas `phone`/`bsuid` se rellenan para las filas existentes: `phone = identifier` cuando `identifier` son solo dígitos.
7. Las bajas (D6) se atan a `customer_id`. La audiencia «Solo mi equipo» sigue comparando por teléfono, y además acepta BSUID.

**Alternativas descartadas.**
- Cambiar `identifier` a BSUID para todos: rompe hilos, búsquedas y los más de 15 sitios que esperan teléfono.
- Una tabla de alias aparte: más uniones en el camino caliente del webhook, para el mismo resultado.

## D3 — Registro integrado (Embedded Signup) vigente

**Contrato** (`D/embedded-signup/versions/`, `D/embedded-signup/version-5`, `D/embedded-signup/implementation/`):

- v2 y v3 retiradas el 2026-10-15: hoy se sirven como v4. `featureType:"only_waba_sharing"` muere el 2026-11-16.
- **v4.**
  - Extras: `setup:{}` y, en coexistencia, `featureType:"whatsapp_business_app_onboarding"`. `sessionInfoVersion` se ignora.
  - Eventos: `FINISH`, `FINISH_ONLY_WABA`, `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING`, `FINISH_GRANT_ONLY_API_ACCESS`, `CANCEL` y `ERROR`.
  - `FINISH` trae `waba_id`, `phone_number_id`, `business_id` y listas de activos (`catalog_ids`…).
- **v5** (2026-10-20).
  - Extras: `version:"v5"`; la coexistencia viene encendida por defecto y se apaga con `features:[{name:"whatsapp_business_app_onboarding",enabled:false}]`.
  - `FINISH` **no trae `waba_id`**: trae `messaging_account_ids`, `is_on_biz_app` y `primary_waac_ids`.
- El código dura 30 s y se canjea con `GET /oauth/access_token`.

**Código hoy.** Consola y panel envían `sessionInfoVersion:"3"` (`apps/console/src/lib/meta-fb-sdk.ts:120-126`, `apps/admin/src/lib/meta-fb-sdk.ts:258-265`). Se aceptan `FINISH` y `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING`.

**Decisión.**

1. **v4 explícita en todas las vías antes del 2026-11-16.** Un solo constructor de extras (`signupExtras(mode)`), compartido por consola, panel, enlace del dueño y beta de inicio de sesión con WhatsApp, y probado con su tabla.
2. Se aceptan los seis eventos de v4. `FINISH_ONLY_WABA` y `FINISH_GRANT_ONLY_API_ACCESS` dicen qué falta (sin número, sin permiso) en vez de fallar mudos.
3. El parser del evento acepta también la forma v5 (`messaging_account_ids` → WABA): adelantarse no cuesta nada.
4. **v5 detrás de un interruptor** (`meta_embedded_signup_version`, por defecto `v4`). Se enciende en staging cuando pasen las cinco vías. Mientras tanto, v5 no se activa en producción.
5. Coexistencia: después del alta se piden `smb_app_data` (`smb_app_state_sync` y luego `history`) dentro de las 24 h, si el código actual no lo hace ya. **Comprobar primero** en `meta_history_consumer`.

## D4 — Una sola versión de la API de Meta

**Contrato** (`docs/graph-api/changelog/versions`): v21 caduca el 2027-01-21, v22 el 2027-05-20, v25 el 2028-07-29; v26 es la vigente (2026-07-29). Desde v24, el estado ya no trae `conversation` (salvo entrada gratuita) y `messaging_limit_tier` está deprecado.

**Código hoy.** `META_GRAPH_VERSION="v22.0"` fijo en `meta_client.py:71`, y ningún constructor pasa `base_url`. `meta_graph_api_version` solo llega a los navegadores. Instagram y Messenger usan `v26.0` y los webhooks están suscritos en v26.0.

**Decisión.**
1. **v26.0 para todo**. `MetaClient` toma la versión de la configuración, y la consola, el panel y el enlace del dueño reciben la misma desde la API.
2. El código ya tolera la ausencia de `conversation`: `conversation_provider_id` queda nulo.
3. Una prueba falla si aparece una versión escrita a mano en el código.
4. Aviso de caducidad (Req. 3.6): tabla de fechas en la configuración. El cron de salud avisa al operador con 60 días de margen.

**Alternativa descartada:** v25. Es más conservadora, pero deja dos versiones vivas, y los webhooks ya están en v26.

## D5 — Salud de la cuenta y de las plantillas

**Contratos** (`D/webhooks/reference/<campo>.md`):

- **`message_template_status_update`.**
  - Eventos: `APPROVED`, `REJECTED`, `PENDING`, `PAUSED`, `DISABLED`, `PENDING_DELETION`, `DELETED`, `ARCHIVED`, `UNARCHIVED`, `FLAGGED`, `IN_APPEAL`, `LIMIT_EXCEEDED`, `LOCKED`, `REINSTATED`.
  - Opcionales: `reason`, `other_info.title` (`FIRST_PAUSE`…), `rejection_info` y `message_template_category`.
- **`message_template_quality_update`:** `previous_quality_score` y `new_quality_score` (`GREEN`/`YELLOW`/`RED`/`UNKNOWN`).
- **`template_category_update`:** aviso unas 24 h antes (`correct_category`) y confirmación (`previous_category` → `new_category`).
- **`account_alerts`:** `entity_type`, `entity_id`, `alert_info{alert_severity, alert_status, alert_type, alert_description}`.
- **`account_review_update`:** `decision` (`APPROVED`/`REJECTED`/`PENDING`/`DEFERRED`).
- **`business_capability_update`:** `max_daily_conversations_per_business` (`TIER_250`…`TIER_UNLIMITED`) y `max_phone_numbers_per_waba`.
- **`phone_number_name_update`:** `decision`, `requested_verified_name`, `rejection_reason`.
- **`phone_number_quality_update`:** `event` y `max_daily_conversations_per_business`.
- **`account_update`.** Una veintena de eventos; los de socio traen **solo `waba_info{waba_id, owner_business_id}`**, sin `phone_number`. Incluye `VOLUME_BASED_PRICING_TIER_UPDATE`, `ACCOUNT_VIOLATION`, `ACCOUNT_RESTRICTION`, `DISABLED_UPDATE` y `ACCOUNT_RECONNECTED`.

**Código hoy.**
- El estado de plantilla se guarda tal cual; no se escribe `category` ni la calidad, y no se avisa.
- `tenant_id` queda nulo en `whatsapp_template_status`.
- `account_update` exige `phone_number` (`meta.py:1016`).
- El cron de salud pone `ACTIVE` en verde y borra el problema de un `account_update` (`whatsapp_health_cron.py:179-184`).
- `problem_reason` admite cuatro valores (CHECK `ck_channels_problem_reason`).

**Decisión.**

1. **Atribución por WABA.** Una función `SECURITY DEFINER` `resolve_waba_tenants(waba_id)` devuelve los negocios con números vivos en esa WABA. Cada evento de cuenta o plantilla se aplica **bajo la RLS de cada negocio**, solo a sus números. Una WABA que nadie tiene se ignora.
2. Plantillas:
   - se guardan estado, motivo, calidad, categoría y categoría anterior;
   - `tenant_id` se rellena;
   - cada cambio que impide enviar (pausa, deshabilitada, rechazada, bloqueada, borrada) avisa al partner con un tipo de notificación nuevo, y la caché de plantillas se invalida;
   - el agente compara sin distinguir mayúsculas (ya corregido en `c3bffbee`).
3. **Cuenta:** `problem_reason` gana `account_review` (revisión rechazada o diferida) y `account_alert` (alerta crítica activa), con migración del CHECK y de `PROBLEM_REASONS`.
   - Las alertas informativas se guardan en `channels.config.alerts` sin degradar el canal.
   - Límites y tramo en `channels.config` (`messaging_limit`, `pricing_tier`).
   - Nombre visible en `channels.config` (`name_decision`, `requested_name`, `name_rejection_reason`).
4. **Origen del problema.** El cron de salud solo limpia los problemas que él mismo puso (`problem_source = "quality"` en `config`). Los de cuenta se limpian con su evento contrario (`ACCOUNT_RECONNECTED`, revisión `APPROVED`, alerta `NONE`).

## D6 — Bajas de marketing

**Contrato** (`D/webhooks/reference/user_preferences.md`): `user_preferences[]{wa_id?, user_id?, category:"marketing_messages", value:"stop"|"resume", timestamp}`. Se respeta por persona, y nunca por BSUID padre.

**Código hoy.**
- `whatsapp_opt_outs` tiene la clave por teléfono (`recipient_phone`), bloquea **todos** los envíos y nada escribe `opted_in_at`.
- La palabra «STOP» descarta el entrante sin encolarlo (`meta.py:554-565`), así que no llega a la bandeja.

**Decisión.**
1. `whatsapp_opt_outs` gana `customer_id`, `scope` (`marketing` | `all`), `source` (`meta` | `keyword` | `operator`) y `lifted_by`.
   - Las filas existentes quedan en `scope='all'`: no se relaja un consentimiento ya dado.
   - Las nuevas por palabra clave y las de Meta quedan en `marketing`.
2. **Despachador:** con `scope='marketing'` bloquea solo las plantillas `MARKETING` y las difusiones. Con `scope='all'` bloquea todo salvo la confirmación de baja.
3. `resume` levanta la baja de Meta. El operador puede levantar la de palabra clave con motivo, con auditoría (`customer.opt_out.lifted`).
4. La palabra «STOP» **sí** llega a la bandeja como entrante (marcado como baja), sin turno del agente.

## D7 — Plantillas completas

**Contratos** (`D/templates/components.md`, `authentication-templates/*`, `marketing-templates/*`, `docs/graph-api/guides/upload`):

- **Cabecera multimedia:** `format: IMAGE|VIDEO|DOCUMENT` con `example.header_handle`, obtenido con la Resumable Upload API:
  1. `POST /{app-id}/uploads` → `upload:<SID>`;
  2. `POST /upload:<SID>` con los bytes → `h`.
- **Autenticación:** botón `{type:"otp", otp_type:"copy_code"}`, `add_security_recommendation` y `code_expiration_minutes` (1–90). Se envía con el código en el cuerpo y en el botón `sub_type:"url"`. Máximo 15 caracteres.
- **Carrusel:** de 2 a 10 tarjetas con los mismos componentes, solo `MARKETING`; al enviar van todas las tarjetas, con `card_index`.

**Decisión.**
1. El esquema de autoría (`TemplateCreateIn`) gana la cabecera multimedia (subida en el servidor), el botón de copiar código, la plantilla de autenticación y el carrusel. El compositor de la consola los ofrece con sus reglas (`template-rules.ts`).
2. `_build_template_components` gana cabecera multimedia, botón de copiar código y carrusel.
3. **SIN CONFIRMAR:** si la Resumable Upload API acepta el token de usuario del sistema del negocio o exige un token de usuario. **Primera tarea de la iteración**, en staging. Si exige token de usuario, se usa el del operador de Auphere con rol en la app, y queda anotado como limitación.
4. La oferta por tiempo limitado queda fuera de esta spec: el formato de envío está **SIN CONFIRMAR** y no hay pedido de cliente.

## D8 — Mensajes entrantes y salientes completos

**Contratos** (`D/webhooks/reference/messages/*`, `D/typing-indicators.md`, `D/messages/*`):

- `type:"button"` → `button{payload, text}` con `context.id` de la plantilla.
- `referral{source_type, source_id, source_url, headline, body, media_type, ctwa_clid…}`.
- Errores en `value.errors[]` y en `messages[].errors[]` (tipo `unsupported`).
- **Indicador de escritura:** `{status:"read", message_id, typing_indicator:{type:"text"}}`. Se apaga al responder o a los 25 s.
- **Ubicación:** `type:"location"`.
- **Petición de ubicación:** `interactive.type:"location_request_message"`; la respuesta llega como `location` con `context.id`.
- **Contactos:** `type:"contacts"`.

**Decisión.**
1. **Parser:**
   - `button` → `INTERACTIVE` con `kind="template_button"` y el id de la plantilla de origen;
   - `referral` → campo del evento que el worker guarda en `conversations.ad_referral` (la primera vez) y pasa al agente como contexto de sistema, nunca como instrucción (§III);
   - `contacts` se convierte en texto legible;
   - `errors` y `system` se registran.
2. **Acuse más escritura:** el runner envía `typing_indicator` junto al acuse cuando el turno va a responder. Con las mismas excepciones que el acuse de hoy: audiencia, solo-envío, pausado.
3. **Despachador:** rama `location` (desde `tool_calls` de `notification.send_location`) y rama `location_request`, que es un tipo nuevo del bloque interactivo.
4. El perfil de capacidades de WhatsApp (`packages/ucm-schema/.../capabilities.py`) se corrige para que diga lo que de verdad sale.

## D9 — Precio y límites

**Contrato** (`D/pricing.md`, estado de mensajes).

- `pricing{billable, pricing_model:"PMP", type, category, subtype?}` llega en `sent` y en uno de `delivered`/`read`.
- **`type`:**
  - `regular`;
  - `free_customer_service`;
  - `free_entry_point`;
  - `free_group_customer_service`.
- **`category`:**
  - `authentication`, `authentication-international`;
  - `marketing`, `marketing_lite`;
  - `utility`, `service`;
  - `referral_conversion`;
  - las de grupo.
- **Desde el 2026-10-01:**
  - el servicio por encima de 1000 al mes por número es `regular` y `billable:true`;
  - la utilidad dentro de la ventana, también.
- **Límite:** `GET /{phone}?fields=whatsapp_business_manager_messaging_limit`, o el webhook `business_capability_update`.

**Decisión.**
1. `messages` gana `pricing_billable` (bool) y `pricing_type`; `pricing_category` ya existe.
2. La consola (Consumo y ficha del cliente) muestra un bloque «Mensajes de Meta» por categoría y cobrados, **separado** de las líneas de Auphere y con la frase «Meta los factura directamente al negocio».
3. No entra en `usage_records` ni en el medidor de pago: Auphere es Tech Provider y no cobra esos mensajes (`kb/.../01-meta-tech-provider.md`).

## D10 — Perfil del negocio y PIN de dos pasos

**Contratos** (`D/business-profiles.md`, `D/business-phone-numbers/two-step-verification.md`).

- **Perfil:**
  - `GET/POST /{phone}/whatsapp_business_profile` con los campos `about`, `address`, `description`, `email`, `websites` y `vertical`;
  - la foto va con `profile_picture_handle`, obtenido por Resumable Upload;
  - en coexistencia **no** se admite.
- **PIN:** `POST /{phone}` `{pin}`, de 6 dígitos. No se puede desactivar.

**Decisión.**
1. **Perfil.**
   - Sección en la página del número de la consola nueva: leer y editar con la barra de guardado.
   - En coexistencia, la sección explica que se edita desde la app.
   - La foto depende de D7.3 (Resumable Upload).
2. **PIN.**
   - `MetaCredentials` gana `two_step_pin`, cifrado como el resto.
   - El alta y `connect_with_token` lo guardan.
   - El operador lo rota desde el panel (`POST /{phone}` `{pin}` nuevo), con auditoría.
3. **Reconexión:** `_upsert_channel` **conserva** la configuración del canal (catálogo, historial, audiencia) en vez de reemplazarla (`signup.py:440-475`). Es un fallo de hoy, y se corrige en la iteración 1.

## D11 — Catálogo en la consola

**Contratos** (`docs/marketing-api/reference/product-catalog/`, `product-item/`, `whatsapp-business-account/product_catalogs/`, `D/catalogs/set-commerce-settings.md`).

- **Catálogo:**
  - crear: `POST /{business}/owned_product_catalogs {name, vertical:"commerce"}`;
  - enlazar: `POST /{waba}/product_catalogs {catalog_id}`;
  - desenlazar: no hay `DELETE` del enlace.
- **Productos:**
  - crear: `POST /{catalog}/products` con `retailer_id`, `name`, `price` en céntimos, `currency` e `image_url`; opcionales `description`, `url` y `availability`;
  - editar: `POST /{product}`; borrar: `DELETE /{product}`;
  - estado: `review_status`, `review_rejection_reasons`, `visibility`.
- **Origen:** `GET /{catalog}/product_feeds`. Ningún campo documentado distingue Shopify de WooCommerce.
- **Comercio:** `whatsapp_commerce_settings` con `is_catalog_visible` e `is_cart_enabled`.

**Código hoy.** Hay listar, enlazar y desenlazar catálogos, y buscar y leer productos. No hay crear ni editar. Las herramientas de catálogo del agente llegan por la plantilla (`restaurante_v1`, `inventario_v1`, `woocommerce_sales_v1`), y `requires="channel_catalog"` solo las esconde en la consola.

**Decisión.**
1. **Sección «Catálogo» en la página del número** (`components/builder/channel-page.tsx`, nueva entrada de `SECTIONS`, con su propio guardado por producto), en todos los números de WhatsApp:
   - sin catálogo: «Crear catálogo» (crea, enlaza y pone `is_catalog_visible=true`), o «Enlazar uno que ya tengo» (el selector de hoy);
   - con catálogo propio (`feed_count = 0`): lista con búsqueda y filtro por disponibilidad; alta y edición en un panel lateral; borrar con confirmación;
   - con feed (`feed_count > 0`): solo lectura, con «Se gestiona desde la tienda o el archivo del negocio»;
   - en coexistencia: el modo manual de hoy.
2. **Productos uno a uno** con los endpoints de producto, no `items_batch`: la respuesta es inmediata y el error es por producto. `retailer_id` lo genera el servidor (`aup_<ulid>`). El precio se pide en la moneda del negocio y se guarda en céntimos.
3. **Herramientas del agente por canal.**
   - **Problema:** hoy no salen si la plantilla del agente no las trae.
   - **Decisión:** el conjunto de herramientas de un turno es el de la versión del agente **más** las derivadas del canal del turno (`catalog.search_products`, `catalog.get_product` y el envío de tarjetas), solo si ese canal tiene catálogo. La lista blanca sigue siendo por tenant y por turno: se calcula del estado del propio negocio, no es global (constitución §I).
   - **Prueba de aislamiento:** un canal con catálogo de A nunca da las herramientas a un turno de B, ni a un número de A sin catálogo.
4. Lo que el agente no debe ofrecer (agotado, rechazado u oculto) se filtra en las herramientas, no en el prompt.

## D12 — Revisión de Meta de `catalog_management` y `business_management`

**Guías oficiales** (`docs/permissions`, `D/solution-providers/app-review`).

- **`catalog_management`:** el vídeo muestra conceder el permiso y crear, editar y borrar un catálogo o sus productos.
- **`business_management`:** descripción con el permiso del que depende.

**Decisión.**
1. Se graba sobre la Historia 9: crear el catálogo en el portafolio del cliente (`business_management`) y crear, editar y borrar productos (`catalog_management`).
2. Demo del revisor con número **Cloud API**, que el kit de la spec 049 no tiene.
3. Las configuraciones de inicio de sesión de WhatsApp (Cloud API y coexistencia) **ya** piden `catalog_management`. Hay que comprobar si piden `business_management`, y si no, añadirlo: lo hace el owner en el Dashboard.

## Riesgos abiertos

| Riesgo | Mitigación |
|---|---|
| La Resumable Upload API puede exigir un token de usuario (D7.3) | Primera tarea de la iteración 2, en staging; se documenta la alternativa |
| Enviar a un BSUID: Meta no da versión mínima ni fecha exacta | Pruebas en staging con una cuenta que tenga nombre de usuario; si falla, el envío se retiene con `needs_phone` y se dice |
| El fin de `only_waba_sharing` (2026-11-16) no tiene equivalente documentado | No lo usamos; confirmar con una búsqueda en el código en la iteración 1 |
| v5 cambia `waba_id` por `messaging_account_ids` | Parser compatible ya; v5 detrás del interruptor |
| Fusión de identidades incorrecta | Nunca se funden filas existentes; conflicto → log y revisión |
