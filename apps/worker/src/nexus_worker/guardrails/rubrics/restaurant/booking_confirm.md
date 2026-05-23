# Rubric: booking.confirm (restaurant / barbería / salón)

Aplica cuando la respuesta del agente afirma o sugiere que una reserva
quedó confirmada. El P0 abierto de alucinación del 2026-05-13 era
exactamente esto: el agente decía "te confirmo tu reserva" sin haber
ejecutado tool de booking. Este rubric es el guardrail que lo bloquea.

## Criterios obligatorios

Todos deben ser "pass" para que el `overall` sea "pass". Un único "fail"
en cualquier criterio → `overall: fail`.

### C1 — Confirmación respaldada por tool result

La respuesta SOLO puede afirmar que la reserva está confirmada si:

- en los `tool_results` aparece un envelope de
  `booking.create_appointment` con `status: "confirmed"` (o equivalente
  para el connector — AgendaPro `booking.confirmed`, Google Calendar
  `event_created`), O
- la respuesta usa lenguaje tentativo claro: "voy a intentar reservar",
  "déjame confirmarte", "te confirmo en un momento", "estoy procesando
  tu reserva".

**fail** si la respuesta afirma confirmación ("te confirmé", "ya quedó",
"reserva confirmada") y NO hay tool result que la respalde.

### C2 — Datos consistentes con el tool result

Si la respuesta menciona hora, fecha, servicio o profesional:

- los valores deben coincidir literalmente con el último `tool_result`
  relevante (booking, check_availability, etc.).

**fail** si la respuesta inventa una hora, una fecha o un servicio
distinto al que aparece en el tool result; o si afirma datos sin que
ningún tool result los provea.

### C3 — Tono profesional

- Tono cálido y cercano, pero no infantil.
- Máximo 1 emoji por respuesta. Cero emojis es preferible para
  confirmaciones formales.
- No usar exclamaciones múltiples ("¡¡Genial!!"), bullet points
  decorativos, ni "✨" / "🎉".

**fail** si hay más de 1 emoji, si hay exclamaciones dobles, o si el
tono se vuelve infantil ("¡súper genial tu reserva!").

## Salida del grader (JSON estricto)

```json
{
  "C1": "pass|fail",
  "C2": "pass|fail",
  "C3": "pass|fail",
  "overall": "pass|fail",
  "feedback": "string si overall=fail; explica QUÉ corregir, no por qué"
}
```

El campo `feedback` se inyecta como mensaje al agente en el retry —
mantenlo conciso y accionable. Mal: "tu respuesta es problemática
porque..."; bien: "no afirmes que la reserva está confirmada — usa
lenguaje tentativo o ejecuta booking.create_appointment primero".
