---
name: whatsapp-24h-window
description: WhatsApp's 24-hour customer service window rule and the Meta template fallback. Surface this skill on any intent that may need to message a customer outside an active conversation so the agent picks the right path (free-form vs. approved template).
version: 1
---

# WhatsApp — la ventana de 24 horas y plantillas Meta

Esta skill explica las reglas de mensajería de WhatsApp Business API
(Meta) que el agente debe respetar para no quemar el número del tenant
ni recibir un `131058` / `131056` que rompe la conversación.

## La regla

WhatsApp distingue dos tipos de mensajes outbound:

1. **Mensajes de sesión** (free-form): el tenant puede enviar cualquier
   texto / media SI el cliente envió un mensaje en las últimas 24 horas.
   La ventana se reabre con cada inbound del cliente.

2. **Mensajes de plantilla** (template): aprobados previamente por
   Meta. Necesarios cuando la ventana está cerrada (último inbound > 24
   horas). Algunas categorías:
   - `utility` — recordatorios, confirmaciones operativas. Categoría
     usada para `appointment_reminder`, `booking_confirmation`.
   - `marketing` — promociones. Bajo opt-in explícito del cliente.
   - `authentication` — códigos OTP.

## Cómo decide el agente

Para cada outbound el agente debe consultar el estado de la conversación:

| Estado | Acción |
|---|---|
| Ventana abierta (último inbound ≤ 24h) | Enviar free-form, cualquier contenido permitido por las policies. |
| Ventana cerrada | NO enviar free-form. Llamar `notification.send_template` con una plantilla aprobada. |
| Tenant sin plantillas aprobadas + ventana cerrada | Encolar como `scheduled_job` para cuando el cliente vuelva a escribir; NO enviar nada todavía. |

## Plantillas disponibles (operación)

Cada tenant tiene su propia lista de plantillas aprobadas en Meta. El
catálogo vive en `whatsapp_template_status`. El agente puede llamar
`whatsapp.template_status` para listar las disponibles si necesita
elegir una en runtime.

Las plantillas que pueden faltar al provisionar un tenant nuevo:

- `appointment_reminder_v1` (utility) — recordatorio 2h antes.
- `booking_confirmation_v1` (utility) — confirma una reserva ya creada.
- `cancellation_notice_v1` (utility) — cancelación iniciada por el tenant.

Si la plantilla necesaria no está aprobada, el agente NO la inventa —
informa al operador via `operator.consult_owner` o difiere el envío.

## Errores Meta más comunes

- `#131058` — `hello_world` ya no se puede enviar desde números reales.
  Usar siempre una plantilla aprobada del tenant.
- `#131056` — número fuera de la ventana de 24h y mensaje no es
  plantilla aprobada. Reescribir como template send.
- `#131032` — plantilla no aprobada para esta categoría. Revisar
  `template_status`.

## Lo que el agente NO debe hacer

1. **NO** intentar enviar marketing fuera de la ventana sin opt-in
   explícito.
2. **NO** "envolver" un mensaje promocional en categoría utility para
   bypassear la regla — Meta rechaza la plantilla en revisión y queda
   marcada.
3. **NO** asumir que la ventana está abierta por defecto — leer del
   estado de la conversación.

## Verificación

Antes de cualquier outbound proactivo (no es respuesta directa a un
inbound del último turno), el agente DEBE:

1. Consultar `conversation_status` o equivalente.
2. Si la ventana está cerrada, ramo de template.
3. Si template no disponible, encolar o escalar al operador.
