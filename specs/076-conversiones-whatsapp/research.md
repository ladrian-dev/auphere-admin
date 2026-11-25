# Research — spec 076

Lo que hay hoy, leído en `develop` (`bfe97215`) el 2026-11-24, y la decisión de
diseño de cada punto. La parte de producto y las fuentes de Meta están en la nota
de la KB `research/2026-11-24-conversiones-whatsapp.md`.

## D1 · Guardar el origen de anuncio (requisito 1)

**Hoy.**
- `webhook_adapter._build_inbound` copia `message["referral"]` entero en `InboundMessage.referral` (`base.py:146`), sin filtrar claves ni recortar.
- `api/webhooks/meta.py` (576-689) arma un `fields: dict[str, str]` plano para el stream y no lleva `referral`. No hay un campo JSON libre.
- El worker (`streams/consumer._to_event` → `InboundEvent` → `dispatcher.accept_inbound`) hace `_upsert_customer`, `upsert_conversation_for_customer` y `persist_inbound_message`. Nada lee el anuncio.

**Decisión.**
- `meta.py` añade una clave `referral_json` al stream, con una **lista blanca** de claves y tope de longitud: `source_type` (`ad`/`post`), `source_id` (64), `source_url` (512), `headline` (200), `body` (500), `media_type` (16), `ctwa_clid` (256), `ref` (128). Las claves fuera de la lista se descartan. Si nada sobrevive, no se escribe la clave.
- `InboundEvent` gana `referral: dict | None`, y `_to_event` lo parsea. Un JSON roto se registra y se ignora, sin tirar el mensaje.
- `accept_inbound` guarda una fila en la tabla nueva `customer_ad_referrals` en la misma transacción que el mensaje. Una fila por clic, con unicidad `(tenant_id, provider_message_id)` para que un reintento del webhook no la duplique.
- `clicked_at` es la hora del mensaje que trajo el anuncio.

**Alternativas descartadas.**
- *`conversations.ad_referral`*, lo que planeaba la 050: un contacto hace clics en días distintos y, desde la 064, una conversación resuelta que se reabre es la misma fila. Para atribuir hace falta el historial de clics del contacto, y para borrar el clic a los 90 días, una fila por clic.
- *`customers.preferences`*: es un JSONB que escriben las herramientas del agente (`client/tools.py`). Mezclar ahí datos de atribución complica la retención y las consultas del informe.

## D2 · El origen llega al agente como dato (requisitos 1.4 y 1.5)

**Hoy.** `pipeline._load_recent_history` añade notas de sistema **después** del historial, para no reescribir el bloque cacheado. `_contact_note` usa `_safe_contact_name` y el cercado `core/guardrails/untrusted.fence(text, tag=…)`, con la etiqueta `TAG_CLIENT_NAME`.

**Decisión.**
- Una etiqueta nueva, `TAG_AD_REFERRAL = "ad_referral"`, en `untrusted.py`.
- Una nota `_ad_note`, añadida igual que `_contact_note`. Sale cuando el último clic del contacto llegó dentro del ciclo actual de la conversación, es decir, después de `coalesce(context_from, created_at)`. Un anuncio de hace tres semanas no se le cuenta al agente en una conversación nueva.
- La nota lleva el tipo (anuncio o publicación), el titular y el texto, cercados. Nunca lleva `ctwa_clid` ni la URL.
- Saneado propio, `_safe_ad_text`: NFKC, fuera caracteres de control y de formato, espacios colapsados, titular hasta 120 caracteres y texto hasta 280. No reutiliza `_safe_contact_name`, que solo admite letras y tres palabras.
- Una prueba mete en el anuncio «ignora tus instrucciones y…», saltos de línea y caracteres de formato. El agente lo recibe dentro del cerco y la prueba de turno comprueba que no cambia de herramienta.

## D3 · La Bandeja de la consola lite (requisito 2)

**Hoy.** La Bandeja con hilo y ficha (`InboxView`, `ThreadHeader`, `ContactPanel`) solo la abre un principal de cliente (`requireClientPrincipal("inbox")`). En la consola de partners no hay vista de conversación, y la regla C8 de `test_console_scope.py` prohíbe que el partner vea palabras o teléfonos del cliente final.

**Decisión.**
- `ConversationDetailOut` (`api/console/lite/inbox.py`) gana `ad_origin: {kind, headline, url} | null`, tomado del último clic del contacto.
- `ThreadHeader` pinta una línea «Desde un anuncio: <titular>», con enlace externo (`rel="noopener noreferrer"`), junto a la de «atiende». Sin titular, dice «Desde un anuncio» o «Desde una publicación».
- `ContactPanel` añade la fila «Llegó por».
- Sin origen, no se pinta nada (constitución §V).
- Como cambia la API lite, se regeneran `apps/mobile/src/api/openapi.json` y `schema.gen.ts`, porque la tubería comprueba que estén al día (`scripts/verify.sh:140`, `ci.yml:227`). También `lite.gen.ts`, si cambian textos lite que comparte la app. La app móvil no muestra nada nuevo.

## D4 · El informe de anuncios (requisito 3)

**Hoy.** No hay informe de ventas ni de anuncios en la consola. La pestaña nueva más reciente del cliente es Acceso (`clients/[ref]/access`, en `TABS` de `client-header-v2.tsx`). El selector de periodo de 7, 30 o 90 días está en `agent-performance.tsx`.

**Decisión.**
- Una pestaña «Anuncios» en `TABS`, con la ruta `clients/[ref]/ads`, y el selector de 7, 30 o 90 días del rendimiento del agente.
- El endpoint es `GET /console/clients/{ref}/ads/report?days=7|30|90`, con `client_scope("conversations:read")`.
- Una fila por anuncio: `ad_id`, `ad_kind`, `ad_headline`, `ad_url`, `conversations`, `bookings` y `amounts[]` (`currency`, `amount_minor`).
- **Ningún campo se llama** `body`, `text`, `message`, `content` ni `reason` (lista de `test_console_scope.py`). Tampoco hay nombres ni teléfonos de clientes. El titular es texto del anunciante, no del cliente final.
- **Conversaciones**: las distintas `conversation_id` con un clic de ese anuncio en el periodo.
- **Reservas**: las de `origin = 'agent'`, no canceladas, creadas en el periodo. Cada una cuenta para el último clic de su contacto **en el número de su conversación** anterior a la reserva, aunque el clic sea de antes del periodo. Es la misma regla que al encolar (D7). Las reservas sin precio cuentan sin importe.
- Las dos columnas miden cosas distintas y la pantalla lo dice: «Conversaciones» son clics del periodo, y «Reservas» son reservas del periodo atribuidas a ese anuncio.
- Estados: esqueleto con la forma final, error con «Reintentar», y vacío con la explicación del requisito 3.5.

**Alternativa descartada.** *Una columna «Anuncio» en la lista de conversaciones del partner*: esa lista es solo metadatos, y añadirle texto del anuncio obliga a revisar la regla C8 sin ganar nada frente al informe.

## D5 · La medición por número (requisito 4)

**Hoy.**
- Las credenciales (`MetaCredentials`) son un JSON cifrado sin versión que **se reemplaza entero** al reconectar (`signup.complete`, `connect_with_token`).
- `dataset_id` ya significa conjunto de evaluaciones en `api/admin/evals.py`.
- La página del número es `ChannelConfigPage` (`components/builder/channel-page.tsx`), con secciones sueltas como Catálogo, que tienen sus propias acciones fuera de la barra de guardado.

**Decisión.**
- Una tabla `channel_ad_measurement`, con una fila por número: `enabled`, `meta_dataset_id`, quién y cuándo activó o desactivó, y el último error.
- El id del conjunto de datos vive aquí y no en las credenciales, para que una reconexión no lo borre. Se llama `meta_dataset_id` para no chocar con las evaluaciones.
- `PUT /console/clients/{ref}/channels/{channel_id}/ad-measurement` con `{enabled, confirm_data_sharing}` y `client_scope("channels:write")`. Para activar:
  1. Comprueba la disponibilidad (D10).
  2. Exige `confirm_data_sharing = true` (requisito 4.8). Si no, responde 422.
  3. Lee los permisos del token del número con `debug_token` y el token de la app, como `MetaSocialClient.granted_targets`. Si falta `whatsapp_business_manage_events`, responde 409 `{"code": "reauthorize"}`.
  4. `POST /{waba_id}/dataset` con el token del número, que devuelve el existente si ya lo hay, y guarda el id.
  5. Guarda `enabled`, quién y cuándo, y la auditoría `console.channel.ad_measurement`, con la confirmación en `after_json`.
- Para desactivar: `enabled = false`, y los eventos pendientes de ese número pasan a `discarded` en la misma transacción.
- `ChannelPageOut` gana un bloque `ad_measurement`:
  - `state`: `on`, `off` o `reauthorize`. No aparece si el número no la admite.
  - `dataset_linked`.
  - `sent_7d`.
  - `last_error`: `code`, `at` y `hint`.
- En la consola es una sección propia «Resultados de anuncios», al estilo de Catálogo:
  - el interruptor, con un diálogo de confirmación que dice qué sale a Meta;
  - el estado;
  - «Volver a conectar» cuando toca.
- La acción nueva de auditoría necesita su fila en `console_audit_vocabulary` (migración) y su etiqueta en `audit_words.py`.

## D6 · Volver a autorizar un número (requisitos 4.3 y 7)

**Hoy.**
- No hay un flujo de reautorización.
- Volver a lanzar el registro insertado choca con la cuota: `count_connected_channels` cuenta el número que ya está conectado, y un cliente en su tope recibe 409 (`api/console/whatsapp.py:83-91`).
- Los permisos **no se piden en el código**. Viven en las configuraciones del lado de Meta, cuyo id lee la consola de `NEXUS_META_CONFIG_ID_WA_CLOUD_API` y `_COEXISTENCE`.

**Decisión.**
- La comprobación de cuota excluye el número que se reconecta, identificado por el mismo `phone_number_id`. Reconectar no es dar de alta.
- **Reconectar vuelve a correr el alta entera.** `complete()` hace estos pasos:
  - canjea el código;
  - registra el número si es de Cloud API;
  - suscribe la app;
  - reemplaza las credenciales.

  Conserva la configuración del canal (`row.config = {**old, **new}`) y el PIN (`_known_pin`), y la medición vive en su tabla, así que no se pierde. Pero registrar un número que ya está vivo no se ha probado. **La primera tarea de la historia 3 lo prueba en staging** con el número de Auphere. Si `register` falla o cambia algo con el número vivo, `complete()` se salta el registro cuando el `phone_number_id` ya es de un canal conectado del mismo tenant.
- **La configuración de reconexión la decide la API**, según el modo del número (`MetaCredentials.mode`), y la devuelve en el bloque `ad_measurement` (`reconnect_config_id`). Así la consola no elige y no hace falta una variable suya.
- **Antes del acceso avanzado:**
  - Luis crea en Meta dos configuraciones de pruebas, copia de las de Cloud API y de Coexistencia con el permiso añadido.
  - Sus ids van en los ajustes de la API `meta_config_id_wa_events_test_cloud_api` y `meta_config_id_wa_events_test_coexistence`, que solo se ponen en staging.
  - Si están puestos, la API los devuelve como `reconnect_config_id`; si no, devuelve la configuración normal del modo.
  - Con acceso estándar, Meta solo concede el permiso a personas con rol en la app. Si alguien sin rol pasara por ellas, el permiso no saldría y la medición seguiría pidiendo reconexión.
- **Después del acceso avanzado**, Luis añade el permiso en Meta a las configuraciones normales y se quitan los dos ajustes de pruebas. No hay cambio de código.
- Crear configuraciones o tocarlas en Meta es un paso de Luis, que se apunta en `quickstart.md`. El plan no crea nada en Meta.

## D7 · Encolar los resultados (requisito 5)

**Hoy.**
- `create_booking` (`services/reservations/core.py:509`) trabaja en la sesión de quien llama: hace `flush` sin `commit` y ya escribe `reservation_events` y `reservation_outbox` en la misma transacción.
- **El discriminador de una reserva del agente es `origin == "agent"`.** `agent_id` o `conversation_id` no bastan: la lista de espera también los pone (`waitlist.py:648`).
- `cancel_booking` (:803) es el único punto de cancelación, para la consola, el agente, la automatización y el cambio de modo.
- `price_minor` solo se copia del servicio en modo Servicios. Es nulo en Aforo y en servicios gratuitos.
- Las herramientas de WooCommerce solo hacen POST a la tienda: no hay tabla local de pedidos ni conocen la conversación.
- Las herramientas corren dentro del worker. `customer_context` está en `core/tenant_context.py`, pero la conversación del turno solo vive en `nexus_worker.runtime.turns.current_turn()`.
- `reservas._turn` cae a «la última conversación de la persona» cuando el modelo no manda `conversation_id`, y esa puede ser de otro número del mismo negocio.

**Decisión.**
- `core/tenant_context.py` gana `conversation_context` / `get_current_conversation()`, que el pipeline abre junto a `customer_context` (`pipeline.py:1985`). Las herramientas lo leen sin importar el worker.
- `reservas._turn` usa primero la conversación del turno. La caída a «la última» queda para llamadas fuera de un turno.
- Un servicio nuevo, `services/ad_conversions.py`, con `enqueue_for_booking`, `enqueue_cancellation` y `enqueue_for_order`. Todo pasa dentro de la transacción de quien llama, con `INSERT … ON CONFLICT DO NOTHING`.
- **Cuándo se encola:**
  - `create_booking`, si `origin == "agent"`.
  - `cancel_booking`, sea cual sea el actor. Si la reserva tiene un evento original que no está `failed` ni `discarded`, se encola un `OrderCanceled`. Este evento:
    - apunta al original con `cancels_event_id`;
    - lleva su mismo clic (`referral_id`), su importe y su moneda, sin buscar un clic más nuevo;
    - **espera a que el original sea final**. Si el original queda `sent`, la cancelación sale. Si queda `failed` o `discarded`, la cancelación pasa a `discarded`.

    Así no hay carrera con el despachador: no se toca el original mientras puede estar saliendo, y Meta nunca recibe una cancelación de algo que no recibió.
  - Si no hubo evento, no se hace nada.
  - Las herramientas `woocommerce.create_order` y `build_checkout_link`, tras crear el pedido en la tienda, con la conversación del turno. Sin conversación del turno no se encola.
- **Reglas al encolar.** Si una falla, no se encola nada:
  1. El número de la conversación tiene la medición activa.
  2. **El contacto no tiene una baja activa en ese número.** Bloquea cualquier fila de `whatsapp_opt_outs` del mismo `channel_id` con `opted_in_at IS NULL`, sea cual sea su `scope`, que coincida por `customer_id` o por `recipient_phone` igual al teléfono del contacto. La tabla es por número y teléfono, y `customer_id` es opcional en ella, así que se miran las dos cosas.
  3. **Atribución:** el último clic con `ctwa_clid`, del mismo contacto y **del mismo número** (`channel_id`), anterior al resultado. Un clic en otro número del negocio es de otra cuenta de WhatsApp y no se usa. Si no hay clic, el contacto tiene que tener teléfono; si tampoco, no se encola.
- **Qué evento:**
  - una reserva con precio es `Purchase` con `value_minor` y `currency`;
  - sin precio, `LeadSubmitted` sin importe;
  - un pedido, `OrderCreated` con el total, que pasa a unidades menores con `services_catalog.ZERO_DECIMALS`.
- `event_id` estable: `"{source_kind}:{source_id}:{event_name}"`, único por tenant. Un reintento del turno no duplica (requisito 6.2).
- El evento guarda la referencia al clic (`referral_id`) y **no guarda el teléfono**, ni cifrado. El teléfono se lee y se cifra al enviar.

## D8 · Enviar a Meta (requisito 6)

**Hoy.**
- `reservation_outbox` no llama a nada externo y su recorrido solo visita tenants con Reservas.
- El patrón que llama a un servicio externo desde una cola es el de los avisos push (`services/push_fanout.py` y `push/dispatcher.py`):
  1. reserva las filas con `SKIP LOCKED` y un plazo de 2 minutos dentro de la transacción del tenant;
  2. hace la llamada HTTP **fuera** de la transacción;
  3. liquida el resultado en otra transacción.
- Vive en el servicio `egress`, porque una cola que se vacía «no es un cron» (`bootstrap.py:163-166`).
- `MetaClient` reintenta los transitorios con tenacity y clasifica los errores:
  - `TokenInvalidatedError`;
  - `MetaRateLimitedError`;
  - `MetaTransientError`;
  - el resto de 4xx, `MetaAPIError`, que no se reintenta.

**Decisión.**
- Un bucle `conversion-events-dispatcher` en `egress`, copiado del de push: reserva, envía fuera de la transacción, liquida.
- **Cada cuánto:** barrido cada 60 s, que basta para la hora del requisito 6.1. No hace falta `pg_notify`.
- **Recorrido propio:** tenants con medición activa y eventos pendientes, consultados con la sesión de identidad, como `tenants_with_pending` de push.
- **Un evento por petición.** El volumen es de reservas, no de mensajes. Con una petición por evento, un error de Meta solo afecta a ese evento. Meta rechaza el lote entero si un evento es malo o tiene más de 7 días. Además, cada llamada cuenta para el nivel de acceso a la API de marketing.
- **Antigüedad:** antes de enviar, un evento con `event_time` de más de 6 días y 23 horas pasa a `failed` con código `too_old` y no sale.
- **Carga útil:**
  - `event_name`, `event_time`, `event_id`;
  - `action_source: "business_messaging"`, `messaging_channel: "whatsapp"`;
  - `partner_agent: "auphere"`;
  - `custom_data` con `currency` y `value` en unidades mayores, si hay importe;
  - `user_data`:
    - con clic: `{whatsapp_business_account_id, ctwa_clid}`;
    - sin clic: `{whatsapp_business_account_id, whatsapp_phone_number_id, ph: [sha256]}`;
  - `test_event_code`, si `NEXUS_META_CAPI_TEST_EVENT_CODE` está puesto (solo staging).
- **El teléfono** se normaliza como dice Meta: solo dígitos, con código de país y sin ceros iniciales. El ejemplo de su página (`(650)555-1212`, `16505551212`) es una prueba unitaria con su SHA-256: `e323ec626319ca94ee8bff2e4c87cf613be6ea19919ed1364124e16807ab3176`.
- **Credenciales:** las del canal primero y, si no, las del tenant, como `resolve_send_credentials`. Hacen falta además `waba_id` y `phone_number_id`.
- **El conjunto de datos** sale de `channel_ad_measurement` del mismo tenant, nunca de la fila del evento ni de quien llama (requisito 6.5).
- **Errores:**
  - transitorio o límite de ritmo: reintento con espera de 1 min × 2^n, hasta 6 intentos;
  - `TokenInvalidatedError` o falta de permiso: `failed`, y la medición del número queda con `last_error = reauthorize`;
  - otro 4xx: `failed`, con el código de Meta en el evento y en `last_error` del número.
- **Comprobación al enviar:** baja de marketing y medición activa. Si cambiaron desde que se encoló, el evento pasa a `discarded`.
- **Las cancelaciones** solo se reservan cuando su original es final (D7). Mientras tanto siguen `pending` sin gastar intentos.
- **Los códigos de error de Meta** del contrato (permiso, Página) son provisionales. Se fijan con las respuestas reales de staging.
- **Logs:** `ad_conversion.sent` y `ad_conversion.failed`, con `tenant_id`, `channel_id`, `event_name`, el resultado y el código de Meta. Nunca `ctwa_clid` ni el teléfono (requisito 6.7). Una prueba captura los logs y busca los dos.

## D9 · Borrar el clic a los 90 días (requisito 1.7)

**Hoy.** `data_retention_cron` hace `UPDATE … SET NULL` por lotes, pero sin contexto de tenant. Con FORCE RLS y el rol `nexus_app` no está claro que toque filas. `meta_social_cron` sí recorre por tenant con `tenant_scoped_session`.

**Decisión.**
- Un cron `ad-referral-retention-cron` en el planificador, una vez al día y por tenant, con el patrón de `meta_social_cron`.
- Hace `UPDATE customer_ad_referrals SET ctwa_clid = NULL WHERE clicked_at < now() - interval` por lotes.
- El intervalo sale del ajuste del worker `retention_ad_click_days = 90`. Con 0 o menos, el paso se apaga.

## D10 · Quién tiene la medición (requisitos 4.7 y 7.6)

**Decisión.** Copia el precedente de Instagram y Messenger (`NEXUS_META_SOCIAL_GENERAL_AVAILABILITY`):
- `NEXUS_AD_MEASUREMENT_TENANTS`: lista de tenants con acceso antes de abrirla. En staging, el de Auphere.
- `NEXUS_AD_MEASUREMENT_GENERAL_AVAILABILITY`: apagado hasta que Meta conceda el acceso avanzado y la app tenga el nivel completo de la API de marketing.
- Un número la tiene si es de WhatsApp por Meta y su tenant está en la lista o la medición está abierta.
- Los números en **coexistencia** quedan fuera hasta que la prueba de staging diga que funcionan (`MetaCredentials.mode`). Si funcionan, se quita la exclusión.
- Fuera de eso, el bloque no aparece en la página del número (requisito 4.7).

## D11 · Lectura de RGPD del flujo nuevo

**Qué sale.** Por cada resultado del chat de un número con la medición activa, sale a Meta:
- el tipo de resultado, la hora y el importe;
- la cuenta y el número de WhatsApp;
- y el `ctwa_clid` del anuncio o el teléfono del cliente en SHA-256.

**Quién es quién.**
- El negocio decide activarlo y es responsable de esos datos.
- Auphere los trata por cuenta del negocio.
- Meta los recibe con sus Condiciones de las herramientas para empresas, que el negocio ya aceptó al anunciarse.

**Lo que este diseño hace por la minimización:**
- apagado por defecto, y activado por el partner con una confirmación que dice qué se envía y queda en la auditoría (requisito 4.8);
- nada del contacto con baja de marketing (requisito 5.9);
- ni el nombre del servicio, ni notas, ni texto (requisito 6.4);
- el teléfono no se guarda cifrado en Auphere: se calcula al enviar;
- el clic se borra a los 90 días.

**Lo que no resuelve el código, para Luis:**
- **La base legal para enviar el teléfono cifrado de clientes de la UE** (España) que no tocaron un anuncio. Es la opción que eligió Luis, y conviene revisarla con asesoría antes de abrirla a negocios europeos. Si la revisión lo pide, el cambio es pequeño: limitar a «solo con clic» por país del número.
- **La política de privacidad y el anexo de encargado de Auphere** deben nombrar a Meta como destinatario cuando el negocio activa la medición.
- **Las respuestas de tratamiento de datos de la revisión de la app en Meta** se revisan al enviar la solicitud (requisito 7).

## D12 · Medidor, licencias y suites que lo verán

- **Medidor:** nada nuevo (encabezado de la spec).
- **Licencias:** ninguna dependencia nueva. SHA-256 es `hashlib` y las llamadas usan el `httpx` y el `MetaClient` de hoy.
- **Suites que ya barren lo nuevo y deben seguir en verde:**
  - `test_21_rls_covers_every_tenant_table`, `test_43_force_and_composite_fk_sweep` y `test_22_tenant_delete_leaves_nothing`, por las tres tablas;
  - `test_console_scope.py`, por las rutas `/console/*` nuevas (404 opaco con otro `ref`, sin campos de cuerpo, barrido C8);
  - `test_lite_route_scope.py` y `test_lite_bodies_only_in_inbox.py`, por el campo nuevo de la Bandeja lite;
  - `test_bootstrap_split.py`, por los dos bucles nuevos. Cada uno va en `bootstrap.py` (`_spawn` y su conjunto) **y en `ALL_EXPECTED`**, y su constructor no hace E/S.
  - `test_51_new_tools_take_no_end_customer` no cambia: no hay herramientas ni argumentos nuevos.
- **Pruebas de aislamiento nuevas**, una por garantía:
  - garantía 8: el clic de un contacto nunca atribuye ni se muestra en otro (requisitos 1.6 y 6.6);
  - garantía 1: un evento de un negocio nunca sale con el conjunto de datos ni el token de otro (requisito 6.5);
  - garantía 6: los logs del envío llevan `tenant_id` y nunca el clic ni el teléfono (requisito 6.7).

## Desconocidos que se resuelven primero, con su alternativa

| Pregunta | Cómo se resuelve | Si sale que no |
|---|---|---|
| ¿Un token de una persona con rol, con acceso estándar, puede crear el conjunto de datos y enviar eventos? | Primera tarea de la fase de Meta: llamadas reales en staging con el número de Auphere | Se pide el acceso avanzado antes, con un vídeo de la historia 1 y del informe, y la descripción ajustada |
| ¿Volver a correr el alta sobre un número vivo es seguro? | Primera tarea de la historia 3: reconectar el número de Auphere en staging y comprobar que sigue recibiendo y enviando | `complete()` se salta el registro cuando el número ya es de un canal conectado del tenant (D6) |
| ¿La API de conversiones funciona con números en coexistencia? | Misma prueba con un número de coexistencia y su configuración de pruebas | Coexistencia sigue excluida (D10) y se dice en `docs/canales.md` |
| ¿El evento sin clic necesita una Página vinculada? Meta lo rechaza si el número no está en exactamente una Página | Enviar un evento sin clic en staging | El error se muestra en el estado del número con «Vincula una página de Facebook a este número», y el resto sigue |
| ¿Meta da otra ventana de atribución con clic? | Leer la respuesta y Events Manager en la prueba | Se ajusta `retention_ad_click_days` |
