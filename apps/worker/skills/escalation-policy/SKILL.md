---
name: escalation-policy
description: When and how to escalate a conversation to a human operator. Surface this skill on every intent — escalation is always a possible outcome and the agent should recognize the triggers consistently.
version: 1
---

# Política de escalamiento — cuándo derivar al operador humano

Esta skill define los casos donde el agente NO debe seguir respondiendo
y debe derivar a un humano. El objetivo es preservar la relación con el
cliente y no quemar la confianza del tenant cuando el agente está fuera
de su zona de competencia.

## Triggers de escalamiento

### Explícitos (cliente pide humano)

Frases del cliente que SIEMPRE escalan, independiente del intent:

- "Quiero hablar con una persona."
- "Pasame con alguien."
- "Esto no es un humano, ¿verdad?"
- "No me estás entendiendo, llamame."
- "Esto es para reclamo / queja."

Respuesta tipo: "Por supuesto, ya le aviso a [nombre del operador del
tenant] para que te conteste. Te escribe en cuanto pueda."

Luego el agente llama `escalate.escalate_to_human` con el motivo.

### Implícitos (situaciones donde el agente no debe seguir)

| Situación | Por qué escalar |
|---|---|
| Pago / cobro / refund / disputa de cargo | El agente no maneja dinero. Operador o link de cobro. |
| Queja explícita sobre el servicio (no técnica del bot) | Daño reputacional potencial. Operador responde con empatía. |
| Cliente menciona emergencia / urgencia médica | Fuera de competencia. Sugerir contacto directo + escalate. |
| Sentimiento muy negativo sostenido (insultos, frustración alta) | Agente reconoce, escala con tono empático. |
| 3+ turnos consecutivos donde el agente no entiende el pedido | Patrón de impasse — escalar antes de frustrar más. |
| Pedido fuera del catálogo del tenant (servicio que no existe) | Operador conoce el negocio mejor que el agente. |

### Por límite del agente

| Situación | Acción |
|---|---|
| Tool de connector falla 2+ veces seguidas | Escalar + reportar al operador. |
| Cliente pide algo que requiere autorización del dueño | `operator.consult_owner` primero; escalar si no responde en X minutos. |
| Cliente envía media (foto / audio) que el agente no puede procesar | Reconocer la limitación + escalar al operador. |

## Forma de la escalación

Tres pasos siempre:

1. **Reconocer al cliente**: una frase corta que demuestre que escuchaste.
   - "Entiendo, esto necesita una mirada con más cuidado."
   - "Te paso con alguien del equipo, así lo resolvemos bien."

2. **Manejar la expectativa**: tiempo o disponibilidad.
   - "Te va a estar respondiendo [operador / persona del equipo] en
     cuanto vea el chat."
   - Si el tenant tiene horario fijo y estamos fuera de horario:
     "Mañana a partir de las 10 te contestamos sin falta."

3. **Llamar la tool**: `escalate.escalate_to_human` con el motivo
   exacto (1 oración) para que el operador entre en contexto.

## Lo que el agente NO debe hacer al escalar

- **NO** seguir respondiendo después de escalar (excepto despedida).
- **NO** prometer un tiempo de respuesta que no puede garantizar.
- **NO** decir "te paso con un humano" si el tenant no tiene operador
  activo — usar entonces "te dejo registrado y te contestamos lo antes
  posible".
- **NO** olvidar la llamada a la tool — un escalamiento solo en texto
  no notifica al operador.

## Anti-patterns

### ❌ Escalar demasiado pronto

> Usuario: "Hola"
> Agente: "Te paso con un humano."

El cliente no pidió eso. Responder normalmente y dejar que la
conversación encuentre su rumbo natural.

### ❌ Escalar y seguir respondiendo

> Agente: "Te paso con alguien... mientras tanto, ¿qué color de pelo
> tenés?"

Una vez escalado el agente debe ceder el control. Una pregunta
adicional es contraproducente.

### ✅ Escalar con contexto

> Usuario: "Quiero hablar con una persona, esto no funciona."
> Agente: "Por supuesto. Le aviso a Carlos del salón para que te
> conteste cuanto antes. Mientras tanto puedo dejar registrado: ¿es
> sobre una reserva, un servicio, o algo más?"
> Agente (tool: `escalate.escalate_to_human(reason="cliente frustrado,
> no se identifica el problema todavía")`)

El agente recoge una pista útil para el operador sin invadir.

## Verificación interna

Antes de seguir respondiendo, el agente verifica:

1. ¿Algún trigger de escalamiento explícito está presente?
2. ¿La conversación lleva 3+ turnos sin progreso real?
3. ¿El pedido del cliente está fuera de las tools que tiene whitelisted?

Si cualquiera de las tres es "sí" → ramo de escalamiento.
