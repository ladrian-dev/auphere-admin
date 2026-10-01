# Contratos — spec 025

## Herramienta `payments.request_review`

Entrada (`extra="forbid"`):

```json
{
  "conversation_id": "uuid",
  "method": "transfer | link",
  "product": "Ramo de 12 rosas rojas",
  "modality": "envío | retiro",
  "place": "Ñuñoa",
  "date": "viernes 3 de octubre",
  "slot": "13:00 a 17:00",
  "total": "$34.990",
  "customer_name": "Camila",
  "order_id": "10452",
  "order_status": "processing"
}
```

Todos los campos del resumen son opcionales (≤ 120 caracteres). `order_id`
y `order_status` solo con `link`.

Salida:

```json
{"review_id": "uuid", "status": "pending | informed",
 "notified": 2, "unreachable": 0, "already_pending": false,
 "message_to_customer": "Recibimos tu comprobante. …"}
```

Errores (`ToolError`): sin revisores configurados → «use
escalate.escalate_to_human»; conversación inexistente.

## Mensaje al revisor (ventana abierta)

1. Si hay comprobante: el adjunto tal cual (imagen o documento).
2. Mensaje con botones:

```
Pago por revisar · Flor y Encanto
Cliente: Camila (+56 9 1234 5678)
Ramo de 12 rosas rojas
Envío a Ñuñoa · viernes 3 de octubre · 13:00 a 17:00
Total: $34.990 · Transferencia
[Confirmar pago]  id prv:<token>:ok
[Rechazar pago]   id prv:<token>:no
```

Con `link` pagado: el mismo texto con «Pago en línea · pedido 10452 ·
pagado» y sin botones.

## Pulsación

`interactive.button_reply.id = prv:<token>:ok|no` desde un revisor avisado.

| Caso | Al que pulsa | Al resto de avisados | Al cliente |
|---|---|---|---|
| Primera, `ok` | «Confirmado. Ya le avisamos al cliente.» | «{nombre} confirmó el pago de {cliente}.» | «Tu pago está verificado. Tu pedido queda en preparación para el {fecha}, {rango}.» |
| Primera, `no` | «Rechazado. El agente deja la conversación para que la tome una persona.» | «{nombre} rechazó el pago de {cliente}.» | «No pudimos verificar tu transferencia. Una persona del equipo te escribe en un momento para revisarlo contigo.» + `agent_active=false` |
| Ya resuelta | «Este pago ya lo {confirmó/rechazó} {nombre}.» | — | — |
| Remitente no avisado o token de otro tenant | nada | — | — |

Si la ventana del cliente está cerrada, no se encola nada al cliente y
`customer_notified=false`.

## Ajustes del agente (consola)

`GET/PUT /console/clients/{ref}/agent/settings` gana:

```json
"payment_review": {"reviewers": [{"phone": "+56991280655", "name": "Daniela"}]}
```

PUT sin `payment_review` no lo toca. 422 `payment_reviewer_invalid_phone`
con `phone`. Máx. 10. El resumen del borrador gana
`{"field": "payment_review", "before": {"count": n}, "after": {"count": m}}`.
