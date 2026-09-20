# Bug Assessment: el cliente del turno viajaba como argumento de la herramienta

- **Slug**: el-cliente-no-es-un-argumento
- **Created**: 2026-09-20
- **Source**: auditoría del 2026-09-19 (hallazgos S1 y C1), verificada contra el código
- **Verdict**: valid
- **Severity**: critical
- **Excepción aplicada**: hotfix P0 de `docs/spec-driven-development.md` §2 — datos en
  riesgo. La spec retroactiva entra dentro de las 48 h.

> **El detalle de explotación, el alcance y la respuesta a incidente viven en la KB
> privada**, no aquí: `research/2026-09-19-auditoria-clase-mundial/` (nota
> `incidente-cliente-como-argumento`). Este repositorio era público cuando se
> escribió esto. Aquí queda lo que hace falta para entender el arreglo y no
> repetirlo.

## Symptom

Tres servidores MCP de cara al cliente final —`booking.*`, `client.*` y `queue.*`—
declaraban `customer_id` como **argumento de entrada**. Es decir: la persona sobre la
que actúa la herramienta la elegía el modelo, y al modelo lo escribe quien manda el
mensaje.

Consecuencias, las tres verificadas leyendo el código y reproducidas en test:

1. **Lectura.** `booking.get_appointments` sin argumento de cliente no filtraba por
   nadie: devolvía las citas del negocio entero. `client.get_history` devolvía el
   historial de cualquier id.
2. **Escritura.** `booking.modify_appointment` y `cancel_appointment` buscaban la cita
   solo por `appointment_id`; `queue.remove_from_queue` sacaba de la cola a quien se
   nombrara.
3. **Y la tarea nunca se completaba.** `booking.create_appointment` exigía un
   `customer_id` que el runtime **nunca le da al modelo** — `pipeline.py` lo fija en
   servidor y su propio comentario dice que el LLM «never [sees] the customer_id
   itself». Un UUID inventado viola la FK, y el `IntegrityError` se interpretaba como
   colisión de idempotencia: el modelo recibía un error que no decía la verdad.

El aislamiento **entre tenants** nunca estuvo en cuestión: la RLS lo sostiene y sus
tests siguen verdes. Esto es el eje de dentro de un tenant, que ninguna de las 7
garantías mira.

## Root cause

Una regla escrita en dos sitios del repositorio, y aplicada en uno solo.

`core/tenant_context.py` ya fijaba el cliente del turno en servidor, con este
propósito literal:

> Set by the runtime per turn so customer-facing tools can resolve "the person I'm
> talking to" WITHOUT trusting an LLM-supplied identifier — e.g. billing.get_my_debt
> looks up only this customer's debt, **making cross-customer lookups impossible**.

Y `nexus_mcp/base.py` prohíbe los campos extra:

> Disallow extras so the LLM cannot smuggle `tenant_id` or **other ambient state**
> through arguments.

El cliente **es** ambient state. Solo `billing.get_my_debt` leía el contexto; los tres
servidores de la agenda seguían tomándolo por argumento, que es la forma exacta de
«smuggle ambient state» que esa frase prohíbe.

**Por qué no lo vio nadie**: los tests pasaban el `cust.id` real a mano
(`test_react_loop.py`, `test_2_tool_whitelist_runtime.py`, la suite de integración de
MCP). Con el id correcto puesto por el test, el contrato roto se comporta bien. Es el
mismo patrón que el resto de la auditoría encontró en otros sitios: la suite verde no
contradecía el defecto porque ejercitaba un camino que producción no recorre.

## Reproduction

`apps/api/tests/isolation/test_35_customer_scope_within_tenant.py`, siete casos. El
más corto de contar, y el que no admite discusión:

```
with tenant_context(t), customer_context(None):
    out = await GetAppointments().run(GetAppointmentsInput())
```

Antes del arreglo: devuelve las citas de **los dos** clientes sembrados, sin cliente
alguno en contexto. Después: lista vacía.

## Scope

| Servidor | Herramientas tocadas |
|---|---|
| `booking.*` | `create_appointment`, `modify_appointment`, `cancel_appointment`, `get_appointments` |
| `client.*` | `get_preferences`, `update_preferences`, `get_history` |
| `queue.*` | `join_queue`, `get_position`, `check_in`, `remove_from_queue` |

`booking.check_availability` y `queue.get_estimated_wait` no tienen eje de cliente y
no cambian. `billing.get_my_debt` ya lo hacía bien y queda como estaba.

## Nota para la spec retroactiva

Sale de aquí una propuesta que excede al bug y merece decidirse aparte: **el eje
cliente-dentro-del-tenant debería ser la octava garantía** de
`architecture/agent-isolation.md`. Hoy la suite de aislamiento tiene un test
(`test_35`) que no cuelga de ninguna garantía declarada, y esa es exactamente la
grieta por la que esto entró.
