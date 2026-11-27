# Tareas: 049 — Instagram y Messenger

Cada tarea nombra los requisitos que cubre. [P] = paralelizable.

## Fase 1 — Base

- [x] T001 Migración `0205_meta_social_channels`: `messenger` en el enum `channel_type`, `partners.beta_channels` y el vocabulario de auditoría. _Req: 5.1, 5.5_
- [x] T002 [P] `ChannelType.MESSENGER` en el modelo, en `nexus_channels.base` y en `schemas/agent_config.py`. _Req: 2.1_
- [x] T003 [P] Ajustes en `config.py`: `meta_config_id_instagram`, `meta_config_id_messenger`, `meta_social_graph_version`, `meta_webhook_peer_url` y `meta_social_enabled`. _Req: 1.7, 5.1_

## Fase 2 — Paquete `meta_social`

- [x] T010 Pruebas (en rojo) de los parsers de Instagram y Messenger: texto, adjuntos, eco, comentario, reacción, lectura, postback y respuesta rápida. _Req: 1.4, 2.5, 4.1, 4.4_
- [x] T011 `webhook_adapter.py`. _Req: 1.1, 2.5, 4.1, 4.4_
- [x] T012 `text.py`: partición por bytes y caracteres sin cortar palabras, con pruebas. _Req: 2.7_
- [x] T013 `graph.py` y `exceptions.py`: cliente y clasificación de errores, con pruebas con `respx` o `MockTransport`. _Req: 3.1, 5.2_
- [x] T014 `adapter.py`: envíos, agente humano, respuesta privada, medios y perfil, con pruebas. _Req: 2.1, 2.4, 2.8, 3.2, 4.2, 4.3_
- [x] T015 `connect.py`: canje, elección, suscripción, persistencia, desconexión y salud, con pruebas. _Req: 5.1, 5.2, 5.3, 5.7_

## Fase 3 — Webhook y API

- [x] T020 Pruebas del webhook: objeto `instagram` o `page` encolado; cuenta ajena reenviada con la firma; cabecera de reenvío sin bucle; WhatsApp igual que antes. _Req: 1.1–1.8_
- [x] T021 `api/webhooks/meta_social.py` y el desvío desde `meta.py`. _Req: 1.1–1.8_
- [x] T022 `services/meta_window.py`, con pruebas de la tabla de ventanas. _Req: 3.1–3.3, 4.3_
- [x] T023 Despachador de salida: tipos, ventana, proveedor en el medidor y aviso de reautenticación. _Req: 2.1, 2.6, 3.1–3.3_
- [x] T024 Respuesta privada para los turnos de comentario: el despachador toma el comentario como contexto de la respuesta del agente (sin tocar `persist_outbound_message`). _Req: 4.2, 4.3_
- [x] T025 Bootstrap del worker: adapters, acuses, medios combinados y perfil. _Req: 2.1, 2.8_
- [x] T026 API de consola: conectar, completar y overview, y desconexión por proveedor. _Req: 5.1–5.5_
- [x] T027 Bandeja: ventana de 7 días para una persona en Instagram y Messenger. _Req: 3.2_
- [x] T028 Crons de salud (resuscripción) y de borrado a 30 días. _Req: 5.3, 5.7_
- [x] T029 Borrado de una persona por canal desde el panel de operador. _Req: 5.6_

## Fase 4 — Interfaces

- [x] T030 Consola: visibilidad, botón de conexión, selector, tarjeta, i18n y logos de Messenger. _Req: 5.1, 5.2, 5.5_
- [x] T031 Panel: interruptores beta por partner y catálogo de canales. _Req: 5.5_

## Fase 5 — Aislamiento y verificación

- [x] T040 `tests/isolation/test_meta_social_channel_isolation.py` (resolución exacta, una cuenta en un solo cliente, desconexión inmediata, credencial por canal) y `test_endpoint_webhook_meta_social.py` (el cliente sale del canal, nunca del evento). _Req: 1.1, 2.2, 2.3_
- [x] T041 `scripts/verify.sh` en verde (lint, mypy estricto, py y js).
- [x] T042 Despliegue en staging; webhook de Instagram y Page apuntado a staging (con permiso del owner); DM de ida y vuelta con cuentas con rol. _Req: CE-001, CE-002_ — Hecho entre el 2026-10-30 y el 2026-11-03: webhooks a staging (`docs/qa-canales-meta-2026-10-30/07-webhooks-a-staging.md`), `@somos.auphere` y la Página «Auphere» conectadas a «Meta Review Demo» y las conversaciones grabadas para la revisión.

## Fase 6 — Revisión de Meta

- [x] T050 Dashboard (con permiso del owner): `pages_read_engagement` en «Auphere Messenger», `messaging_policy_enforcement` en Page, evaluadores de Instagram y Facebook. _Req: 6.1_ — Comprobado el 2026-11-20 en la app: «Auphere Messenger» pide 7 permisos (con `pages_read_engagement`, `pages_read_user_content` y `pages_manage_engagement`) y Page tiene 9 campos suscritos, `messaging_policy_enforcement` incluido.
- [x] T051 Llamada exitosa de cada permiso, vídeos y descripciones (kit) e instrucciones del revisor reescritas para la consola. _Req: 6.2–6.5_ — Enviada el 2026-11-03 y **aprobada el 2026-11-19**: 13 permisos y funciones (`instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`, `pages_messaging`, `pages_manage_metadata`, `pages_show_list`, `pages_read_engagement`, `pages_read_user_content`, `pages_manage_engagement`, `business_management`, `catalog_management`, Human Agent y Business Asset User Profile Access). Los de WhatsApp, renovados.

## Fase 7 — Apertura a todos los partners (2026-11-20)

Decisión del owner, 2026-11-20: abrir Instagram y Messenger **a todos los partners a la vez**, y que Human Agent no bloquee la apertura. El guion está en [apertura-produccion.md](apertura-produccion.md).

- [x] T060 `NEXUS_META_SOCIAL_GENERAL_AVAILABILITY` y `NEXUS_META_HUMAN_AGENT_APPROVED` en el entorno común de `infra/terraform/20-services/taskdefs.tf`, en un commit propio. _Req: 5.5, 3.2_
- [ ] T061 Staging: `terraform apply` desde el checkout principal (`/Users/lmatos/Workspace/nexus`, ya iniciado con el backend S3) en `develop`; comprobación de la disponibilidad general en el panel de staging («todos los partners los tienen»); y **conexión de una cuenta de Instagram y una Página desde un Facebook sin ningún rol en la app**, en staging: la app de Meta y sus configuraciones son las mismas que en prod, así que es la prueba del acceso avanzado y la puerta de T063. Lo hace el owner. _Req: 5.1, 5.5_
- [ ] T062 Webhooks de Página e Instagram a `https://webhooks.auphere.com/webhook/meta`, con el verify token de producción. Lo hace el owner en el panel de Meta. _Req: 1.7_
- [ ] T063 Producción: `terraform apply` desde el checkout principal en `main`, con `deploy-prod` en verde y la consola de `main` ya publicada por Vercel en `console.auphere.com` (el diálogo de desconectar de un canal de Instagram dice que los mensajes se borran a los 30 días). **Todo `apply` posterior en prod tiene que salir de un checkout con este cambio:** uno sin él quita las dos variables y vuelve a esconder los canales. Lo hace el owner. _Req: 5.5_
- [ ] T064 Human Agent de verdad: respuesta de una persona entre 24 h y 7 días después del último mensaje del contacto. Primero en staging (un DM hoy a las cuentas de staging, la prueba tras el `apply` de T061) y después en producción. Lo hace el owner. _Req: 3.2, CE-004_
- [x] T065 Textos de Instagram y Messenger en la página del canal, el menú ⋯ y el selector (excepción «cambio trivial»: solo textos, sin cambio de comportamiento). Sin modo de prueba ni excepciones, avisos de Auphere sin «porque», borrado a los 30 días al desconectar, «Conectar otra Página» y «canales» en vez de «números» en la lista. Prueba: `channel-meta-social-copy.test.tsx`. _Req: 5.2, 5.3_
- [ ] T066 Respuestas rápidas en Instagram. **Decisión del owner, 2026-11-20: se mantienen.** El agente puede seguir ofreciendo opciones como respuestas rápidas en Instagram. Queda actualizar en el panel de Meta la descripción de `instagram_manage_messages`, que dice «Auphere does not use ice breakers, quick replies or a persistent menu on Instagram». Lo hace el owner. _Req: 2.4_
- [x] T067 Los avisos por WhatsApp cuando Auphere no tiene número de avisos: requisito 7.1 (enmienda del 2026-11-20, también bajo el requisito 33 de la 047). `notify_from` vale `none` (`channel_config.notify_from_shown`) y la página lo dice en WhatsApp y en Instagram y Messenger. Pruebas: `test_channel_config.py`, `test_escalation_recipients.py` (vistas en rojo) y `channel-meta-social-copy.test.tsx`. _Req: 7.1; 047: 33.3_
- [x] T068 Cancelar la espera de la ventana de Meta (7.2, `meta-social-connect.test.tsx`), la Bandeja entre 24 horas y 7 días con Human Agent (7.3: `window.agent_open` desde `inbox_view.reply_windows`, `test_inbox_reply_windows.py`, `inbox-model.test.ts` y `composer.test.tsx`) y «Pasar el canal» al pasar un canal de Instagram o Messenger (7.4, `channel-meta-social-copy.test.tsx`). Todas vistas en rojo antes del cambio. Puertas de UI en estático (sin navegador): el «Cancelar» va fuera de la región que se anuncia, recibe el foco al abrirse la espera y lo devuelve al cancelar, Escape también cancela, mide 36 px de alto, y usa la variante `on-dark` nueva de `Button` en `@nexus/ui`, con contorno de foco pistacho a 9,6:1 sobre el verde oscuro (el `ring` de antes daba 2,8:1). En vivo queda en staging: cancelar y volver a conectar hasta el final con el SDK de Meta real (paso 3 del guion de apertura), y el texto de la Bandeja entre 24 horas y 7 días (paso 7). _Req: 7.2, 7.3, 7.4_

## Fase 8 — Entrar con Instagram (requisito 8, 2026-11-20)

Decisión del owner, 2026-11-20: abrir la enmienda para que Instagram se conecte también entrando con Instagram. Las cuentas ya conectadas no se tocan.

- [x] T069 Configuración nueva en Meta, compatible con el inicio de sesión con Instagram: Casos de uso → API de Instagram → «API setup with Unified login» → «Crear nueva configuración».
  - Permisos: solo `instagram_basic`, `instagram_manage_messages` e `instagram_manage_comments`. Se quitan `instagram_content_publish`, `ads_management` y `ads_read`, que Meta pone por defecto.
  - Activo: la cuenta de Instagram, sin cuenta publicitaria. Token de usuario del sistema que no caduca.
  - La pestaña tiene que mostrarla como compatible. Se anota su `config_id`.
  - Antes de escribir código, se abre la URL de inicio de sesión de la guía de Meta (paso 4) con el `config_id` nuevo y `prompt=login`, y se comprueba que salen las dos opciones, Instagram y Facebook.
  - La configuración `1157578836735566` no se toca: la usan las cuentas ya conectadas y es la vuelta atrás.
  - Cambia la app de Meta, que es la misma en staging y en producción. Lo hace el owner, o Claude en su Chrome con su OK.
  - **Hecha el 2026-11-20** por Claude en el Chrome del owner, con su OK: «Auphere Instagram», `29353122964304011`, marcada «Compatible con el inicio de sesión de Instagram», solo la cuenta de Instagram y los tres permisos. Su ventana, abierta sin entrar: con `prompt=login` ofrece «Continuar con» el perfil de Facebook y «Continuar con Instagram»; sin `prompt=login` entra directamente con la sesión de Facebook; la configuración antigua, con `prompt=login`, solo ofrece Facebook.
  _Req: 8.2_
- [x] T070 Pruebas en rojo:
  - `meta-fb-sdk.test.ts`: `loginForCode` pasa `prompt: "login"` a `FB.login` cuando se le pide, y no lo pasa si no.
  - `meta-social-connect.test.tsx`: conectar Instagram lo pide; conectar Messenger, no.
  - `test_endpoint_console_meta_social.py`: la oferta de Instagram trae el `config_id` de T069, y la de Messenger sigue con `2188508105420190`.
  - Vistas en rojo el 2026-11-20 las tres. `channel-connect.test.tsx` esperaba la llamada sin `prompt`; se actualiza.
  _Req: 8.1, 8.2, 8.5_
- [x] T071 El cambio:
  - `loginForCode` acepta `prompt`, y `meta-social-connect.tsx` lo manda solo para Instagram.
  - `meta_config_id_instagram` pasa al `config_id` de T069 en `config.py`. No hay variable de entorno que lo pise.
  - `docs/canales.md` §5 dice qué configuración va con cada canal y por qué la de Instagram no puede pedir Páginas.
  - `auditoria-docs-oficiales.md` deja de decir que `1157578836735566` tiene la marca de compatible: la perdió con INC-53.
  - En verde el 2026-11-20: consola (vitest de `src/lib`, `channels`, `builder` e `i18n`, 916; `tsc --noEmit`; `eslint --max-warnings=0` de lo tocado), API (`test_endpoint_console_meta_social.py`, 18) y `verify.sh lint`. Sin navegador: `prompt=login` llegando a la ventana desde `FB.login` se comprueba en T072.
  _Req: 8.1, 8.2, 8.5_
- [x] T072 Staging, en vivo, con el owner. Antes de empezar: _(Hecho el 2026-11-27, según Luis: Gali entró en producción con su cuenta de Instagram y sus DMs llegan. Lo comprueba la T008 de la 081.)_
  - staging está despierto (se aparca de noche);
  - la cuenta de prueba es pública y no está conectada en producción, porque producción se queda los eventos de sus cuentas y no los reenvía a staging;
  - los comentarios se escriben desde otra cuenta.

  Pasos:
  1. **Control, primero:** un DM y un comentario a `@somos.auphere`, conectada en staging con `1157578836735566`, llegan a staging reenviados por producción y reciben respuesta. Sin esto, un comentario que no llega en el paso 5 no distingue INC-53 de un reenvío roto.
  2. Con una sesión de Facebook abierta en el navegador, la ventana ofrece Instagram y Facebook, y la URL que abre lleva `prompt=login` (se ve en el envoltorio de `window.open` de `meta-fb-sdk.ts`).
  3. Se conecta una cuenta profesional entrando con Instagram, y otra (o la misma, tras desconectarla) entrando con Facebook.
     - Entrando con Instagram, el `code` vuelve al callback de `FB.login`. La ventana nueva carga con `is_ig_oidc_with_redirect=1`. Si el código no vuelve, hace falta el flujo con redirección: es otra enmienda, no las salidas a) o b).
     - En cada una se anota el `source` de `meta_social.connect.instagram_accounts`: el 2026-10-31 `assigned_instagram_accounts` vino vacío, y sin Páginas hay un respaldo menos.
  4. Un DM recibe la respuesta del agente, en las dos.
  5. Un comentario recibe la respuesta privada y la pública, en las dos. Es la puerta del riesgo de INC-53.
  6. Conectar Messenger sigue igual.

  **Si falla el paso 5, se para aquí:** el cambio se revierte en `develop` antes del siguiente paso a `main`, y el owner elige entre las salidas a) y b) del requisito 8. **Hasta que pase, ningún PR de `develop` a `main`:** llevaría a producción la configuración nueva sin probar.
  _Req: 8.1, 8.3, 8.4, 8.5_
- [ ] T073 Producción, después de fusionar en `main` y con la consola de `main` publicada: el owner conecta una cuenta entrando con Instagram y comprueba un DM. _Req: 8.1, 8.3_
