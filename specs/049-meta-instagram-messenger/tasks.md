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
- [ ] T042 Despliegue en staging; webhook de Instagram y Page apuntado a staging (con permiso del owner); DM de ida y vuelta con cuentas con rol. _Req: CE-001, CE-002_

## Fase 6 — Revisión de Meta

- [ ] T050 Dashboard (con permiso del owner): `pages_read_engagement` en «Auphere Messenger», `messaging_policy_enforcement` en Page, evaluadores de Instagram y Facebook. _Req: 6.1_
- [ ] T051 Llamada exitosa de cada permiso, vídeos y descripciones (kit) e instrucciones del revisor reescritas para la consola. _Req: 6.2–6.5_
