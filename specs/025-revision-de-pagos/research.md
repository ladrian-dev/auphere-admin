# Fase 0 — investigación

Medido contra el código el 2026-10-01 (tres exploraciones: envíos y ventana,
ruta de entrada y retorno, herramientas y Ajustes).

## D0 · Lo que existe y se reutiliza

| Pieza | Dónde | Uso aquí |
|---|---|---|
| Mensaje saliente pendiente que el despachador envía solo | `Message(direction=OUTBOUND, status=PENDING)` + disparador `pg_notify('nexus_outbound')` (migración 0062) + `streams/outbound.py::_dispatch_message` | Cada aviso, cada respuesta al revisor y la respuesta al cliente son filas pendientes. Nadie llama a Meta a mano |
| Botones de respuesta con id | `interactive_payload={"body","buttons":[{id,title}]}` → `_to_meta_interactive` (outbound.py:1072) | El aviso con botones |
| Adjunto saliente desde el almacén | `media_kind` + `media_s3_key` → enlace prefirmado (outbound.py:770) | Reenviar el comprobante tal como se guardó al entrar |
| Comprobante guardado al entrar | `messages.media_s3_key/media_kind/media_mime/media_filename` (dispatcher.py:236-248) | Se busca el último entrante con adjunto de la conversación |
| Cliente y conversación por número | `nexus_worker.persistence.messages.upsert_customer/upsert_conversation_for_customer` | El revisor tiene su conversación en el canal del negocio; el despachador manda al `Customer.identifier` de la conversación |
| Ventana de 24 horas | `conversations.last_inbound_at` (notification/tools.py:91) | Ventana abierta = último entrante del revisor en ese canal hace menos de 24 horas |
| Pulsación de un botón | `interactive.button_reply` → `InboundMessage.interactive.payload_id` (webhook_adapter.py:580) | El id del botón lleva la revisión |
| Silenciar al agente en una conversación | `conversations.agent_active=False` + `takeover_context` (dispatcher.py:501) | Rechazo: pasa a una persona de verdad |
| Lista de números en Ajustes | spec 024: `agent_audience.py`, `AudienceIn/Out`, `audience-lines.ts` | Mismo patrón para los revisores |

Lo que **no** sirve, y por qué:

- `operator.consult_owner`: número de Auphere, un solo teléfono, sin
  botones ni imagen, emparejado por texto.
- `escalate.escalate_to_human`: marca la conversación `ESCALATED` pero **no
  silencia al agente**; el siguiente mensaje del cliente abre otra
  conversación y el agente sigue respondiendo. Para el rechazo hace falta
  `agent_active=False`.
- `owner_fanout` para volver al cliente: relanza el agente con mensaje vacío
  (el clasificador no ve la nota) y no comprueba `result_applied_at` antes
  de relanzar. Aquí no hace falta el modelo (D6).

## D1 · Sale del número del negocio, por el canal de la conversación del cliente

El aviso sale por el mismo canal en el que el cliente mandó el comprobante.
El revisor ve el número de la tienda. Sin cuenta nueva, sin plantillas de
Auphere.

## D2 · Los revisores viven en `policies.payment_review.reviewers`

`{"reviewers": [{"phone": "+56991280655", "name": "Daniela"}]}` en la
versión del agente. Viaja con borrador, publicar y revertir, como la lista
de la 024. Máximo 10. Normalizados con `to_e164`, sin duplicados, con la
misma comparación por los últimos dígitos (`usable_admin_phones`). Servicio
`services/agent_payment_review.py` espejo de `agent_audience.py`.

## D3 · Una herramienta: `payments.request_review`

Servidor MCP nuevo `payments` (corre en el proceso del worker, como todos).
Entrada: `conversation_id`, `method` (`transfer`/`link`), resumen
estructurado (producto, modalidad, lugar, fecha, rango u hora, total,
nombre del cliente), y para `link` el número y el estado del pedido que el
agente leyó en la tienda. Hace, en una transacción con RLS:

1. Lee los revisores de la versión activa. Sin revisores → error que dice
   usar `escalate.escalate_to_human`.
2. Si la conversación ya tiene una revisión pendiente, suma el comprobante
   nuevo y no avisa otra vez (caso límite «dos comprobantes»).
3. Crea la revisión con un `token` de 12 caracteres.
4. Por revisor: su cliente y su conversación en el canal; si la ventana está
   abierta, encola el comprobante (si hay) y el mensaje con el resumen y los
   botones; si no, apunta el aviso como no entregado por ventana cerrada.
5. Devuelve cuántos avisos salieron y el texto para el cliente.

`side_effects = ("mutates_db", "sends_message")`: queda bloqueada en el
Playground, como cualquier herramienta que envía.

## D4 · El botón lleva `prv:<token>:ok` o `prv:<token>:no`

Ids de botón ≤ 256 caracteres. El token es aleatorio y único. Emparejar por
el id del botón, nunca por texto (Requisito 2.4).

## D5 · La pulsación se resuelve en el webhook, antes de encolar al agente

En `api/webhooks/meta.py`, justo después del preludio que resuelve tenant,
canal y políticas (≈:373): si el entrante es una pulsación con `payload_id`
que empieza por `prv:`, se llama a `services/payment_reviews.py::resolve_tap`
dentro de la sesión del tenant y se responde 200 sin encolar. Así:

- la pulsación nunca llega al agente, esté o no el número en la lista «A
  quién responde» (Requisito 2.6);
- la RLS hace que un token de otro tenant no exista (aislamiento);
- se exige que el remitente sea uno de los revisores avisados de esa
  revisión.

La resolución es un `UPDATE … WHERE status='pending' RETURNING`: el primero
gana (Requisito 2.1, CE-003). Después encola: el acuse al que pulsó, el
aviso al resto de revisores avisados y la respuesta al cliente. La
deduplicación de Redis por wamid (600 s) ya existe; la del `UPDATE` cubre el
resto.

## D6 · La respuesta al cliente es un texto fijo, sin modelo

Confirmado: «Tu pago está verificado. Tu pedido queda en preparación para
el {fecha}, {rango}.» Rechazado: «No pudimos verificar tu transferencia.
Una persona del equipo te escribe en un momento para revisarlo contigo.» y
`agent_active=False` con `takeover_context`. Sin llamada al modelo: más
barato, determinista, y coherente con el encabezado (la pulsación no llama
al modelo). Si la ventana del cliente está cerrada, no se encola nada y la
revisión queda con `customer_notified=false` (Requisito 3.3).

## D7 · Pago por enlace (aclaración A)

El agente busca el pedido con `woocommerce.list_orders` cuando el cliente
dice que pagó, y llama a la herramienta con `method=link`, `order_id` y
`order_status`. Con `processing` o `completed` la revisión nace `informed`
y el aviso va sin botones. Con otro estado va con botones, como una
transferencia.

## D8 · Plantilla para la ventana cerrada: iteración 2

Un toque de plantilla llega como tipo `button`, que el adaptador no entiende
hoy (webhook_adapter.py:661), y crear una plantilla con cabecera de imagen
exige subir un ejemplo a Meta. La iteración 1 entrega con ventana abierta y
dice claramente qué revisor no se pudo avisar. La iteración 2 añade el tipo
`button`, una plantilla de utilidad con tres respuestas rápidas
(Confirmar, Rechazar, Ver comprobante) creada en un clic desde la consola, y
la marca en Conversaciones (Historia 4).

## D9 · Auditoría

`AuditRepository.record` con `payment_review.opened` (actor `system:agent`)
y `payment_review.resolved` (actor `reviewer:<teléfono>`), y sus filas en
`console_audit_vocabulary` para que la consola las cuente.

## D10 · Aislamiento, licencias, medidor

- Tablas nuevas con `tenant_id`, RLS forzada y política de aislamiento.
- Ninguna dependencia nueva.
- Los mensajes a revisores y al cliente se miden como mensajes de canal en
  el despachador, como todos. La pulsación no llama al modelo.
