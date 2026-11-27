# Contrato: el freno de citas y las herramientas por intención (spec 080, requisitos 1 y 2)

## Qué respalda una respuesta que da por hecha una cita

Respaldan, en este orden y como hasta ahora:

1. Una herramienta de este turno que reservó, cambió o mantuvo la cita (`is_backed`). Sin cambios.
2. Una reserva viva con el `conversation_id` de la conversación (`load_conversation_backing`). Sin cambios.
3. El éxito de un conector o de una herramienta `booking.*` antigua en un saliente desde `attended_at`. Sin cambios.
4. **Nuevo (080).** Una reserva viva del `customer_id` de la conversación que tenga un evento `created` o `moved` desde `coalesce(context_from, attended_at)`.
   - Se lee en la sesión del cliente.
   - El `customer_id` sale de `conversations`, nunca del turno ni del modelo.
   - Sin cliente o sin inicio de ciclo, este punto no aplica.

Si la lectura falla, no respalda: el freno se cierra igual que hoy.

## Herramientas por intención

| Intención | Antes | Ahora (agente con esas herramientas en su lista blanca) |
|---|---|---|
| `book` | `reservas.*`, `booking.*`, `client.*`, `operator.consult_owner` y salida nativa | Sin cambios |
| `fallback` | Salida nativa y `escalate.escalate_to_human` | **+ las 9 `reservas.*`** |
| `escalate` | `escalate.escalate_to_human`, `notification.send_template`, `notification.send_text` y `operator.consult_owner` | **+ las 9 `reservas.*`** |
| `info`, `queue` | — | Sin cambios |

La lista blanca del agente sigue siendo el techo. Los conectores siguen fuera de `escalate`.
