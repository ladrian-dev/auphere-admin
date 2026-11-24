# Canales: alta, coexistencia, página del canal y enlace del dueño

Spec 047 (requisitos 28 a 34). Un **canal** es un número de WhatsApp, una cuenta
de Instagram o una Página de Facebook (Messenger, spec 049) que atiende **un
agente** (`channels.agent_id`). Este documento cuenta cómo se
conecta, cómo se configura y qué pasa cuando el negocio sigue usando su app.

## 1. Conectar un número

- **Desde la consola** (Embedded Signup v5 de Meta,
  `api/console/channel_signup.py`) o **con el enlace del dueño** (sección 4).
- **Modos** (`services/channel_signup_links.MODES`): `coexistence` (el negocio
  sigue con su app WhatsApp Business y Auphere responde a la vez), `cloud_api` (el
  número pasa entero a la API) y `whatsapp_login` (beta por país, nunca en la UE
  ni en el EEE; la activa Auphere en el admin, `whatsapp_login_beta_countries`).
  El `config_id` de Meta del modo beta es `NEXUS_META_CONFIG_ID_WA_LOGIN` (si no
  está, el de `cloud_api`).
- Un número nuevo empieza **en prueba**: «Solo mi equipo» con el teléfono del
  dueño, para que nadie de fuera hable con un agente a medio hacer.

### Llegar a la configuración del número (spec 063, requisito 2)

- **Quién atiende un número sin agente:** el **principal** del cliente, es decir,
  el marcado por defecto o, si ninguno lo está, el activo más antiguo
  (`services/agents.principal_agent_id`, la regla del turno). Lo usan la página
  del número (`_agent_of`), la pestaña Canales de cada agente (`agent_channels`) y
  las tarjetas de Agentes. El canal interno del probador no sale en ninguna.
- **Desde Canales del cliente:** cada tarjeta lleva a la configuración del número
  («Configurar», `/clients/{ref}/channels/{id}`, que redirige dentro de su agente).
  - **«Sin configurar»:** dice «No responde a nadie» en vez de «Activo», y su
    acción principal es «Decidir a quién responde».
  - **Sin agentes en el cliente:** la tarjeta lleva a crear uno.
  - **Al conectar un número aquí:** al terminar, la consola abre su configuración,
    después de la oferta del catálogo si la hay (047, 30.6).
- **Desde un agente:** todo enlace a «los canales» lleva a su pestaña Canales
  (`?tab=channels`), nunca a Canales del cliente. Eso incluye su tarjeta cuando
  espera un número, «Guardar y conectar un canal» y el arreglo «canal» de la
  revisión.
  - **Por qué importa:** antes, un agente «Listo · sin canal» llevaba a la página
    del cliente. El número se conectaba allí sin agente, se quedaba «Sin
    configurar» y el partner no volvía a ver su configuración (prod, 2026-11-18).
- **«Listo · número sin configurar»:** así sale un agente publicado cuyo único
  número no responde a nadie (`visible_state` con `reason="unconfigured"`).

## 2. La página del canal

`api/console/channel_config.py`, `services/channel_config.py`,
`/console/clients/{ref}/channels/{channel_id}`:

- **Audiencia**: `unset` (sin configurar: no responde a nadie), `team_only` («Solo
  mi equipo», con sus números de prueba) o `everyone` («A todos», con sus
  excepciones). La regla de audiencia se aplica de forma **estricta** en WhatsApp
  para los partners con la consola nueva; los demás siguen con las políticas de
  `admin_access` de la versión (`core/admin_gate.audience_suppresses`).
  «A todos» exige saldo en la bolsa del cliente (`bag_empty`).
- **Escalada**: cuándo se pasa a una persona (pide hablar con alguien, intentos
  fallidos, una queja o un motivo propio), a quién se avisa (campana, correo o
  WhatsApp) y el mensaje de espera. El aviso por WhatsApp sale del propio número
  si su WABA tiene la plantilla `alert_escalation_v1` aprobada, en el idioma en
  que está aprobada (el español primero si hay varios); si no, del número de
  avisos de Auphere (el predeterminado de `auphere_owner_channels`, en el admin
  «Números de Auphere») en el idioma `NEXUS_AUPHERE_ALERT_TEMPLATE_LANGUAGE`
  (`es_CL` por defecto). Si no hay ninguno de los dos, el aviso por WhatsApp no
  sale ni se da por enviado (`escalation_whatsapp_unavailable` en
  `operator_notifications.last_error` y un evento
  `operator_alerter.whatsapp_unavailable` al día por cliente), el correo y la
  Bandeja siguen igual y la página lo enseña con la comprobación
  `escalation_template_missing`. Además, la página no dice que los avisos salgan
  del número de Auphere cuando Auphere no tiene ninguno que pueda enviar
  (`auphere_can_notify`): `notify_from` vale `none` y la página dice que no
  pueden salir (spec 049, requisito 7.1, que enmienda el 33.3 de la 047). El
  envío no cambia. Lo mismo vale para los avisos de siempre al
  dueño (canal sin destinatarios propios): del número del cliente solo con la
  plantilla aprobada en su WABA, si no del de Auphere.
- Cada cambio lleva `If-Match` (`412` con lo que cambió), queda en el historial
  y se puede **deshacer**. **Mover** el número a otro agente, **pausar** y
  **reanudar** avisan al partner y quedan en la auditoría.
- Los checks de la página dicen qué falta para «A todos» y qué bloquea, y
  avisan (sin bloquear) si las pruebas no están al día, si nadie recibe el
  escalado o si el aviso por WhatsApp no puede salir.
- **Instagram y Messenger** (spec 049) usan la misma página con tres
  diferencias, y la página las dice en vez de copiar el texto de WhatsApp
  (`channel-page.tsx`, `social`):
  - **Sin modo de prueba ni excepciones:** escriben con un IGSID o un PSID, no
    con un teléfono, así que solo hay «A todos». El texto manda probar el agente
    en sus pruebas antes de elegirlo.
  - **Avisos siempre del número de Auphere:** no tienen plantillas. Si Auphere
    no tiene número de avisos, la página dice que no pueden salir.
  - **Desconectar borra:** el token se borra al momento y lo recibido por el
    canal se anonimiza a los 30 días (`meta_social_retention`, requisito 5.3).
    Volver a conectarlo antes lo cancela. El diálogo de «Desconectar» y el
    aviso de canal desconectado lo dicen.
  - **Conectar se puede cancelar:** mientras la ventana de Meta está abierta, la
    consola ofrece «Cancelar» (y Escape). Lo que Meta devuelva después a un
    intento cancelado se descarta (`meta-social-connect.tsx`, requisito 7.2).
  - **Pasar a otro agente** dice «Pasar el canal».
  - **Comentarios** (Instagram y Messenger): responder sí o no y la respuesta
    pública bajo el comentario (`_COMMENT_CHANNELS` en
    `api/console/channel_config.py`).

## 3. Coexistencia

El webhook de Meta deja tres streams en Redis y responde enseguida; tres
consumidores del worker los procesan con la RLS del cliente
(`wk/streams/meta_*_consumer.py`):

- **Ecos** (`smb_message_echoes`): lo que el negocio escribe desde su app se
  guarda como mensaje de una persona (`origin = business_app_echo`) y la
  conversación pasa a «La lleva una persona» **2 horas**: el agente calla. Pasado
  el plazo, el siguiente mensaje del contacto lo atiende el agente.
- **Historial**: solo si el canal lo pidió (`config.history_import`); entra como
  `origin = history_import`.
- **Contactos** (`state_sync`): pasan a clientes del negocio.

Los avisos de cuenta de Meta (`account_update`) marcan el canal `degraded` con su
motivo: `PARTNER_REMOVED` → `auth_expired`; `ACCOUNT_OFFBOARDED` y
`PARTNER_APP_UNINSTALLED` → `coexistence_inactive`; `ACCOUNT_DELETED`,
`ACCOUNT_RESTRICTION` y `DISABLED_UPDATE` → `meta_error`. Cada uno deja la
auditoría `channel.problem` y el aviso `channel.problem` al partner. Los tics azules
no se mandan a quien queda fuera de la audiencia.

## 4. El enlace del dueño

`services/channel_signup_links.py`, `api/console/channel_signup.py`: el partner
genera un enlace para un agente (uno pendiente a la vez, `409
link_pending_exists`), el dueño conecta su número desde el móvil, el número queda
asignado a ese agente y empieza en prueba con el teléfono del dueño. Al conectar
se avisa al partner (`channel.connected`). Revocar el enlace lo invalida al
momento.

## 5. Instagram y Messenger: quién los ve y por dónde llegan

Spec 049. Meta aprobó los permisos el 2026-11-19 (solicitud del 2026-11-03).

- **Quién los ve:** con `NEXUS_META_SOCIAL_GENERAL_AVAILABILITY=true`, todos los
  partners. Sin ella, solo los que tienen el canal en `partners.beta_channels`
  (panel → Partners → Módulos → Canales en beta). La bandera vive en el entorno
  común de `infra/terraform/20-services/taskdefs.tf` y llega con un
  `terraform apply` por workspace: el despliegue no la cambia.
- **Human Agent:** con `NEXUS_META_HUMAN_AGENT_APPROVED=true`, una persona del
  equipo responde hasta 7 días después del último mensaje del contacto, con la
  etiqueta `HUMAN_AGENT`. El agente sigue con 24 horas (`services/meta_window`).
  La leen la API y el worker que envía.
- **Configuraciones de Facebook Login for Business** (`config.py`,
  `meta_config_id_instagram` y `meta_config_id_messenger`). Las dos dan un
  token de usuario del sistema que no caduca.
  - **Instagram: «Auphere Instagram» `29353122964304011`.** Solo pide la
    cuenta de Instagram y `instagram_basic`, `instagram_manage_messages` e
    `instagram_manage_comments`, y Meta la marca como compatible con el inicio
    de sesión con Instagram: el negocio puede entrar con Instagram o con
    Facebook. La consola le añade `prompt=login`, porque sin él quien tiene una
    sesión de Facebook abierta entra con ella y no ve la opción de Instagram
    (spec 049, requisito 8).
  - **No puede pedir Páginas.** Entrar con Instagram no puede conceder
    Páginas, y una configuración que las pide deja de ser compatible. Le pasó
    a la anterior, `1157578836735566`, cuando se le añadieron por INC-53
    (2026-11-01). Las cuentas conectadas con ella siguen funcionando.
  - **Messenger: «Auphere Messenger» `2188508105420190`** (7 permisos). Solo
    se entra con Facebook, sin `prompt=login`.
- **Webhooks:** Meta admite **una sola URL por app** para los objetos `page` e
  `instagram`. El entorno que recibe un evento de una cuenta que no es suya lo
  reenvía al otro, con el cuerpo y la firma intactos (`meta_webhook_peer`). Si
  el reenvío falla, se registra y Meta recibe igualmente su 200.
  - Del 2026-10-30 al paso a producción apuntaron a staging, para grabar la
    revisión (`docs/qa-canales-meta-2026-10-30/07-webhooks-a-staging.md`).
  - En producción tienen que apuntar a `https://webhooks.auphere.com/webhook/meta`.
    Si no, producción depende de que staging esté encendido para recibirlos.
- **Campos suscritos:** Página, 9 (`messages`, `message_echoes`,
  `message_reactions`, `message_reads`, `messaging_handovers`,
  `messaging_postbacks`, `messaging_referrals`, `messaging_policy_enforcement`,
  `feed`). Instagram, 8 (`comments`, `mentions`, `message_reactions`, `messages`,
  `messaging_handover`, `messaging_postbacks`, `messaging_referral`,
  `messaging_seen`).

## 6. De qué anuncio viene cada persona (spec 076)

Cuando alguien escribe desde un anuncio de clic a WhatsApp, o desde una
publicación, Meta manda en ese primer mensaje un objeto `referral`.

- **El webhook lo filtra** antes de que salga del proceso
  (`services/ad_referrals.clean_referral`):
  - solo pasan `source_type` (`ad` o `post`), `source_id`, `source_url`,
    `headline`, `body`, `media_type`, `ctwa_clid` y `ref`, cada una con su tope;
  - viaja en la clave `referral_json` del stream;
  - el worker lo vuelve a filtrar al leerlo, y un JSON roto deja
    `inbound.referral_unreadable` y el mensaje sigue.
- **El worker guarda una fila por clic** en `customer_ad_referrals`
  (`persistence/ad_referrals.store_referral`), en la transacción del mensaje:
  - el contacto y el número los fija el servidor;
  - `UNIQUE (tenant_id, provider_message_id)`, así que un reintento del
    webhook no duplica.
- **Qué lo usa:**
  - *La Bandeja lite*: enseña el último clic del contacto en ese número
    (`ad_origin`, ver `docs/consola-lite.md`).
  - *El agente*: recibe el titular y el texto del anuncio como dato, cercados
    con `<ad_referral>` (`pipeline._ad_note`). Solo si el clic es del ciclo
    actual de la conversación, después de `coalesce(context_from, created_at)`.
    Nunca recibe el `ctwa_clid` ni la URL.
- **El `ctwa_clid` es un identificador personal:**
  - nunca va a un log ni a una respuesta de la API;
  - el cron `ad-referral-retention-cron` (planificador, una vez al día y por
    tenant) lo pone a NULL a los `retention_ad_click_days` (90);
  - el resto del origen se queda.
- **Garantía 8:** el clic de un contacto no aparece nunca en la conversación ni
  en el turno de otro, ni en otro número del mismo negocio
  (`tests/isolation/test_076_ad_click_customer_axis.py`).

## 7. Enviar los resultados a Meta (spec 076)

Cada reserva o pedido que el agente consigue en un número se le puede decir a
Meta por la API de conversiones de mensajería, para que los anuncios del
cliente aprendan. Está apagado en todos los números hasta que un partner lo
enciende.

- **Dónde se ofrece** (`services/ad_measurement.available`): números de
  WhatsApp de Meta conectados por Cloud API, no desconectados, de un tenant de
  la lista `NEXUS_AD_MEASUREMENT_TENANTS` o con
  `NEXUS_AD_MEASUREMENT_GENERAL_AVAILABILITY`. La coexistencia no: Meta no lo
  admite. Donde no se ofrece, la página del número no tiene la sección ni la
  explica.
- **Encenderlo** (`PUT /console/clients/{ref}/channels/{id}/ad-measurement`):
  - pide `confirm_data_sharing: true` (`422 confirm_required` sin ella);
  - comprueba con `debug_token` que el token del número tiene
    `whatsapp_business_manage_events`. Si no, `409 reauthorize`, la marca queda
    en `channel_ad_measurement` y la consola pide «Volver a conectar»;
  - crea u obtiene el conjunto de datos de la cuenta (`POST /{waba_id}/dataset`)
    y lo guarda. Si Meta falla, `502 meta_unavailable` y no se enciende nada;
  - queda en la auditoría (`console.channel.ad_measurement`) con quién y la
    confirmación.
- **Volver a conectar** (no con el número en pausa: el alta lo reanudaría) es
  el mismo alta de Meta que conectar el número, con la
  configuración que dice `reconnect_config_id` (la de pruebas del modo si
  `NEXUS_META_CONFIG_ID_WA_EVENTS_TEST_*` está puesta, si no la normal). No
  gasta cuota de canales: `api/console/whatsapp.py` no cuenta el
  `phone_number_id` que el cliente ya tiene.
- **Qué se encola** (`services/ad_conversions.py`, en un savepoint, así que
  medir nunca rompe una reserva):
  - reserva del agente con precio → `Purchase`, sin precio → `LeadSubmitted`;
  - su cancelación, la haga quien la haga, si el original salió o está en cola
    → `OrderCanceled`;
  - pedido o enlace de pago del agente (WooCommerce) → `OrderCreated`;
  - nada de lo creado fuera del chat, nada de quien tiene una baja en ese
    número, y nada si no hay clic ni teléfono.
- **El despachador** (`conversion-events-dispatcher`, en `egress`, cada
  `conversion_dispatch_tick_seconds`): reserva por tenant con plazo y
  `SKIP LOCKED`, envía **un evento por petición** fuera de la transacción y
  anota el resultado.
  - El cuerpo lleva el clic (`ctwa_clid`) si sigue guardado; si no, el teléfono
    normalizado y cifrado con SHA-256 y el número. `partner_agent: auphere`.
  - Un pasajero se reintenta con espera (hasta 6 intentos). Un token o permiso
    retirado deja `reauthorize` en el número. Sin clic ni teléfono,
    `no_identity`. Otro error deja `meta_<código>`. `page_required` aún no lo
    produce nada: falta saber qué código de Graph lo dice (T026).
  - Un evento de más de 6 d 23 h no sale (`too_old`): Meta rechazaría el lote.
  - Apagar descarta lo pendiente. Una cancelación espera a que su original sea
    final.
- **Garantías:** cada evento sale con el conjunto de datos y el token de su
  tenant (`tests/isolation/test_076_conversion_events_tenant.py`), los logs
  llevan el tenant y nunca el clic, el teléfono ni su hash
  (`test_076_logs_carry_no_click.py`), y el evento de un contacto nunca lleva el
  clic de otro (`test_076_ad_click_customer_axis.py`).

## 8. Dónde mirar si algo falla

- El estado visible del canal sale de `services/agent_lifecycle.channel_visible_state`
  (`pending_link`, `disconnected`, `problem`, `paused`, `unconfigured`,
  `team_only`, `everyone`).
- La conciliación diaria de mensajes con Meta queda en `meta_reconciliation_runs`
  y sus diferencias se ven en el admin (`GET /admin/reconciliations`).
- Los consumidores de coexistencia mandan lo que falla a su buzón de descarte con
  el error.
