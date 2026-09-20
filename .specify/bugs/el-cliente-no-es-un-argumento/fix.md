# Bug Fix: el cliente del turno viajaba como argumento

- **Slug**: el-cliente-no-es-un-argumento
- **Fixed**: 2026-09-20
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

El cliente deja de ser un argumento y pasa a resolverse en servidor, como el tenant y
por la misma razón. Doce herramientas de tres servidores; el campo `customer_id`
desaparece de sus entradas, así que **no es que el modelo no deba nombrarlo: es que
ya no puede** — `extra="forbid"` rechaza el intento antes de tocar la base.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/mcp/src/nexus_mcp/_customer.py` | añadido | `current_customer_or_refuse()`. Vive al lado de `_db.py` a propósito: uno resuelve el negocio, el otro la persona |
| `apps/mcp/.../booking/schemas.py` | modificado | Fuera `customer_id` de `CreateAppointmentInput` y `GetAppointmentsInput` |
| `apps/mcp/.../booking/tools.py` | modificado | `_own_appointment()` para modify y cancel; `get_appointments` filtra siempre; descripciones reescritas |
| `apps/mcp/.../client/schemas.py` | modificado | Fuera de las tres entradas; sigue en las salidas, como eco |
| `apps/mcp/.../client/tools.py` | modificado | Las tres leen del contexto |
| `apps/mcp/.../queue/schemas.py` | modificado | Fuera de las cuatro entradas |
| `apps/mcp/.../queue/tools.py` | modificado | Las cuatro leen del contexto |
| `apps/api/tests/isolation/test_35_customer_scope_within_tenant.py` | añadido | Siete casos. Escrito primero, visto en rojo |
| `apps/api/tests/integration/mcp/test_servers_happy_path.py` | modificado | Entra en `customer_context`; deja de pasar el id |
| `test_react_loop.py`, `test_2_tool_whitelist_runtime.py`, `test_evals_real_pipeline.py`, `test_agent_promote_no_redeploy.py` | modificado | Las llamadas guionizadas dejan de llevar el id a mano |

## Las tres decisiones que no son obvias

**1. Mismo mensaje para «no existe» y «es de otro».**

```python
appt = await session.get(Appointment, appointment_id)
if appt is None or appt.customer_id != customer_id:
    raise ToolError(f"appointment {appointment_id} not found for this customer")
```

Distinguirlos le confirmaría a quien pregunta por un id ajeno que ese id existe.

**2. Sin cliente en contexto, leer devuelve vacío pero escribir falla.**

`get_appointments` devuelve `[]` —mismo criterio que `billing.get_my_debt`, que ya
estaba bien—, mientras que reservar, cancelar o cambiar lanzan `ToolError`. La
asimetría es deliberada: una lectura sin sujeto no tiene respuesta correcta más allá
de «nada», pero una escritura sin sujeto es una regresión del runtime y debe hacer
ruido, no elegir a alguien por su cuenta.

**3. Las descripciones se reescribieron, no solo los schemas.**

El modelo tiene que entender el mundo nuevo, no chocarse con él. «List appointments
for the tenant, optionally restricted to a customer» pasa a «List the appointments of
the person you are talking to — never anyone else's, and there is no way to ask for
another customer's». Un schema que cambia sin que cambie su descripción produce un
modelo que insiste en lo imposible y gasta iteraciones.

## Lo que este arreglo NO hace

- **No toca la idempotencia.** `idempotency_key` la sigue inventando el modelo
  (P1-5 de la auditoría). Un reintento del turno puede duplicar efectos. Va en la
  spec 016, y es un defecto distinto con otro arreglo (clave derivada en servidor).
- **No añade comprobación de solapes** en `create`/`modify` (P1-12).
- **No declara la octava garantía.** `test_35` existe y bloquea el merge, pero
  `architecture/agent-isolation.md` sigue hablando de siete. La propuesta queda en el
  assessment para la spec retroactiva.

## Deuda que deja abierta, con fecha

Este arreglo entró por la excepción de **hotfix P0**. La spec retroactiva vence el
**2026-09-22**. Si no se escribe, la regla del repositorio dice que esto se revierte.
