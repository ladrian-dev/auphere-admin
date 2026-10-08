# Contrato: tiempo real de la Bandeja

## Canal Redis `inbox:{tenant_id}`

Mensajes JSON sin cuerpo de mensaje (la consola vuelve a pedir lo que cambió):

```json
{"event": "conversation.updated", "conversation_id": "…", "at": "…"}
{"event": "message.new", "conversation_id": "…", "message_id": "…", "direction": "inbound", "at": "…"}
{"event": "message.status", "conversation_id": "…", "message_id": "…", "delivery": "failed", "at": "…"}
```

| Quién publica | Cuándo |
|---|---|
| worker | mensaje entrante guardado · mensaje del agente guardado · escalado |
| API (webhook de Meta) | cambio de estado de entrega |
| API (lite y admin) | tomar el control, devolver, enviar, resolver, reabrir, etiquetar |

El tenant del canal sale del contexto de quien publica, nunca de un argumento.

## SSE `GET /console/lite/inbox/stream`

- Se suscribe **solo** a `inbox:{tenant de la sesión}`.
- `event:` = el `event` del mensaje; `data:` = el JSON.
- Latido `event: ping` cada 15 s.
- La BFF lo pasa en `/api/lite/inbox/stream` acuñando su token como hace el
  Playground (`tokenFor`).
- Si la conexión cae, la consola sondea `GET …/conversations` cada 15 s,
  pinta «Reconectando…» y vuelve al SSE cuando puede.
