# Rubric: ecommerce.order_status

Aplica cuando la respuesta del agente informa sobre el estado de una
orden del cliente.

## Criterios obligatorios

### C1 — Estado respaldado por tool

La respuesta debe basarse en un `tool_result` de `get_order`,
`order_status`, `list_orders` o equivalente. El estado mencionado
(en preparación, enviado, entregado, cancelado) debe coincidir con
el campo `status` del envelope.

**fail** si afirma un estado que no aparece en ningún tool result, o
si traduce mal el estado (ej. dice "entregado" cuando el envelope dice
`shipped`).

### C2 — Tracking number si lo hay

Si el `tool_result` incluye `tracking_number` / `tracking_url`:

- la respuesta debe incluirlo cuando informa que la orden fue enviada.

**fail** si el tracking number está disponible y la respuesta no lo
ofrece (UX missed opportunity confirmada con operations).

### C3 — Sin promesas de tiempos sin respaldo

NO afirmar fechas de entrega ("llega mañana", "te llega el martes") a
menos que el `tool_result` incluya un `estimated_delivery_date` o
campo equivalente.

**fail** si inventa una fecha de entrega que el tool result no contiene.

## Salida del grader

```json
{
  "C1": "pass|fail",
  "C2": "pass|fail",
  "C3": "pass|fail",
  "overall": "pass|fail",
  "feedback": "string si overall=fail"
}
```
