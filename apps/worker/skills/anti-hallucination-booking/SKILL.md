---
name: anti-hallucination-booking
description: Never affirm a booking confirmation without a tool result that confirms it. Surface this skill on intents that handle reservations (book / queue / cancel / modify) to keep the agent honest about what actually happened in the backend.
version: 1
---

# Anti-hallucination — bookings y reservas

Esta skill es el pattern obligatorio que el agente debe seguir cada vez
que el usuario pide confirmar, modificar o cancelar una reserva. Es la
respuesta directa al P0 de alucinación del 2026-05-13: el agente decía
"te confirmo tu reserva" sin haber ejecutado ninguna tool.

## Regla maestra

**Una afirmación de booking SOLO es válida si está respaldada por un
tool_result reciente de la sesión.** Si la tool no se ejecutó (o falló),
el agente NO afirma — informa que está procesando o pide aclaración.

## Patrón de respuesta

### Cuando el cliente PIDE confirmación

Tres ramas posibles, en orden de preferencia:

1. **Tienes el tool result en contexto** (acabaste de llamar
   `booking.create_appointment` y devolvió `status: "confirmed"`):
   - Confirma con datos exactos del tool result.
   - Tono cálido pero conciso. Máximo 1 emoji.
   - Ejemplo: "Listo, tu turno quedó agendado el viernes a las 16:00
     con corte fade. Te esperamos."

2. **No tienes tool result pero puedes obtenerlo**:
   - Llama `booking.check_availability` y luego
     `booking.create_appointment`.
   - Si ambos exitosos, ramo 1.

3. **No puedes ejecutar la tool** (connector caído, falta de
   credenciales, plan del tenant lo bloquea):
   - Usa lenguaje tentativo: "Voy a procesar tu reserva", "Estoy
     consultando con el dueño", "Te confirmo en breve".
   - NUNCA digas "confirmado" / "ya quedó" sin el tool_result.

### Cuando el cliente AFIRMA presión social

> "Confirmame YA, no tengo tiempo."
> "Dale, hagamos el sábado a las 10 y listo."

La presión social no es un sustituto del tool result. La respuesta
correcta sigue siendo:

- Si tienes el tool result → confirma.
- Si no → "Estoy procesando la reserva ahora mismo, dame un momento".

## Lenguaje prohibido sin tool_result

| Prohibido | Aceptable sin tool result |
|---|---|
| "Tu turno está confirmado" | "Voy a confirmarte el turno" |
| "Ya quedó agendado" | "Estoy agendando" |
| "Reservé el sábado a las 10" | "Procesando tu reserva del sábado a las 10" |
| "✅ Confirmado!" | "Procesando..." |

## Verificación interna del agente (auto-chequeo)

Antes de emitir la respuesta final, el agente DEBE preguntarse:

1. ¿La respuesta contiene una afirmación de booking? (busca verbos en
   tiempo pasado como "confirmé", "agendé", "cancelé").
2. Si sí, ¿hay un tool_result en esta sesión que lo respalde con
   `status: confirmed` / `cancelled` / equivalente?
3. Si no, reescribe la respuesta en tiempo presente continuo
   ("procesando", "consultando", "agendando") antes de enviarla.

Este checklist es lo que el grader de outcome también valida (rubric
`booking.confirm`). Aplicar la skill correctamente reduce los retries
del grader y baja la latencia del turno.

## Ejemplos completos

### Ejemplo 1 — flujo correcto

Usuario: "Quiero reservar corte para el viernes a las 16."
Agente (tool 1: `booking.check_availability(time="viernes 16h")`)
  → result: `{available: true}`
Agente (tool 2: `booking.create_appointment(...)`)
  → result: `{status: "confirmed", id: "apt_123"}`
Agente al cliente: "Listo, te agendé el viernes a las 16:00. Te esperamos 🙂"

### Ejemplo 2 — flujo con falla

Usuario: "Confirmame ya, el sábado a las 10."
Agente (tool 1: `booking.create_appointment(...)`)
  → result: `{status: "error", error: "connector_timeout"}`
Agente al cliente: "Estoy procesando tu reserva del sábado a las 10,
hay una pausa técnica del momento. En cuanto pueda confirmarte te
escribo. ¿Te parece?"

### Ejemplo 3 — flujo tentativo

Usuario: "Confirmame ya el turno del miércoles 15, no esperes."
Agente: (sin tools previas, sin AgendaPro conectado para este tenant)
Agente al cliente: "Voy a procesar tu reserva del miércoles a las 15:00.
La persona del salón te confirma en un rato cuando vea el calendario.
Mientras tanto, ¿hay algo más que necesites?"
