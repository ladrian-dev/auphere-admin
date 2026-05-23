# Rubric: booking.cancel (restaurant / barbería / salón)

Cancelar es destructivo. Aplica cuando la respuesta del agente confirma
o sugiere que una cita fue cancelada o modificada.

## Criterios obligatorios

### C1 — Cancelación respaldada por tool result

La respuesta SOLO puede afirmar que la cancelación se ejecutó si:

- en los `tool_results` aparece un envelope de
  `booking.cancel_appointment` con `status: "cancelled"` o equivalente,
  O
- la respuesta usa lenguaje tentativo ("voy a cancelar", "procesando la
  cancelación").

**fail** si afirma cancelación y NO hay tool result que la respalde.

### C2 — Identificación de la cita

Si la respuesta dice qué cita se canceló (hora, fecha, servicio):

- los valores deben coincidir con el `tool_result` de `cancel_appointment`
  o con un `get_appointments` previo.

**fail** si menciona una cita distinta a la que el tool result reporta,
o si menciona una cita sin que ningún tool result la haya identificado.

### C3 — Tono empático

Cancelar es un momento delicado. El tono debe ser comprensivo, NO frío
ni transaccional. Mal: "Cancelada. Adiós". Bien: "Listo, cancelé tu
cita del martes a las 10. ¿Quieres reagendar?".

**fail** si la respuesta es brusca, no acusa empatía, o no ofrece
re-agendar cuando la cancelación fue iniciada por el cliente.

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
