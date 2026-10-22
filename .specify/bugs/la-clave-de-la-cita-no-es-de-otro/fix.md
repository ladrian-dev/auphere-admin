# Bug Fix: la clave de idempotencia de una cita entregaba la cita de otro cliente

- **Slug**: la-clave-de-la-cita-no-es-de-otro
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`booking.create_appointment` hace con la clave lo mismo que `reservas.create` desde la
043: la clave que elige el modelo deja de ser del negocio y pasa a ser de la persona.
Se guarda `agent:` + sha256(`{customer_id}:{clave}`), así que dos personas con la misma
clave obtienen dos citas, y la misma persona que repite obtiene la suya. Además, el
replay se niega a entregar una fila de otra persona aunque la clave coincida.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/mcp/src/nexus_mcp/servers/booking/tools.py` | modificado | `_agent_key()` (idéntica a la de `reservas`); `_replay()` reúne los dos caminos de replay (lookup y carrera) y responde `idempotency_conflict` si la fila es de otra persona; el `INSERT` y los dos `SELECT` usan la clave derivada; el payload del job `async_booking` refleja la clave de la fila; descripción «per person», sin el `conv:{conversation_id}` que el modelo no tiene |
| `apps/mcp/src/nexus_mcp/servers/booking/schemas.py` | modificado | Descripción del campo: «for the same person», no «for the same tenant» |
| `apps/api/tests/isolation/test_35_customer_scope_within_tenant.py` | modificado | Dos casos nuevos. Escritos primero, vistos en rojo |

## Las decisiones que no son obvias

**1. La defensa vive en la herramienta, no en un dominio.** En la 043 el chequeo está
en `services/reservations/core.py::create_booking`, porque las reservas tienen dominio
en la API y lo usan también la consola y el cron. `appointments` no lo tiene: la
herramienta es la única que crea filas con clave, y el cron de AgendaPro solo la lee.
Sacar un servicio de dominio para un solo llamador sería inventar una capa.

**2. Responder `idempotency_conflict`, no ignorar la fila ajena.** La unicidad es
`(tenant_id, idempotency_key)`: ignorarla y seguir haría fallar el `INSERT`, y el
camino de carrera volvería a encontrarla. El mensaje es el mismo código que la 043 y
no dice de quién es la fila ni qué contiene. Con la clave derivada, llegar aquí exige
una colisión de sha256 o una fila escrita a mano: es defensa, no camino normal.

**3. La descripción también cambia.** Pedía derivar la clave de un id de conversación
que el modelo no ve, y por eso la derivaba de lo que se reserva, que es lo que dos
personas comparten. Tras el arreglo esa colisión ya no hace daño, pero la descripción
debe contar el mundo como es: «idempotente por persona», con un ejemplo que el modelo
puede construir.

## Lo que este arreglo NO hace

- **No migra las filas antiguas.** Las citas creadas antes guardan la clave cruda; una
  llamada nueva no las encuentra nunca. Un reintento del webhook que cruce el
  despliegue podría duplicar una cita (ventana de segundos).
- **No comparte `_agent_key` con `reservas`.** La de la 043 vive en su rama, aún sin
  fusionar; las dos son idénticas a propósito. Al fusionar ambas, se pueden reunir en
  `nexus_mcp/_customer.py`.
- **No toca `alembic/data/0007_tool_schemas.json`**, que conserva la descripción vieja
  del campo: es el dato histórico de una migración ya aplicada.
- **No responde si hubo colisiones reales en producción** (ver «Open Questions» del
  assessment).
