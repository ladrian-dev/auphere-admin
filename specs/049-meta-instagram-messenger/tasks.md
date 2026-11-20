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
- [ ] T067 Los avisos por WhatsApp cuando Auphere no tiene número de avisos: requisito 7.1 (enmienda escrita el 2026-11-20, también bajo el requisito 33 de la 047). Prueba primero: la página de un canal de WhatsApp sin plantilla y la de uno de Instagram, con y sin número de avisos de Auphere (`auphere_can_notify`). Se codifica con el sí del owner. _Req: 7.1; 047: 33.3_
- [ ] T068 Cancelar la espera de la ventana de Meta (7.2), la Bandeja entre 24 horas y 7 días con Human Agent (7.3) y «canal» en el diálogo de pasar un canal de Instagram o Messenger (7.4). Enmienda escrita el 2026-11-20. Prueba primero de cada criterio; para 7.3, la API dice hasta cuándo puede responder el agente, porque hoy solo manda la ventana de la persona. Se codifica con el sí del owner. _Req: 7.2, 7.3, 7.4_
