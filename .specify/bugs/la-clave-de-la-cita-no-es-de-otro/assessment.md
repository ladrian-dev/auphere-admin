# Bug Assessment: la clave de idempotencia de una cita entrega la cita de otro cliente

- **Slug**: la-clave-de-la-cita-no-es-de-otro
- **Created**: 2026-10-22
- **Source**: pasted text — `/cso --diff` de las specs 043/045 (2026-10-22), apéndice de
  `specs/043-reservas/evidence/T061/cso.md` (rama de la 043, aún sin fusionar)
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

El `/cso --diff` de la 043 encontró CSO-001 (Media, verificado) en `reservas.create`:

> el modelo elige la clave de idempotencia y no conoce el id de la conversación; dos
> personas con la misma clave → la segunda recibía la reserva de la primera

Se arregló en la rama de la 043 (`_agent_key` en `servers/reservas/tools.py`,
`idempotency_conflict` en `services/reservations/core.py`, pruebas en
`tests/isolation/test_reservas_customer_axis.py`). El mismo informe deja para después:

> el mismo defecto de clave de CSO-001 existe en `booking.create_appointment`.

`booking.*` es la herramienta anterior, que escribe en `appointments`.

## Symptom

Dos clientes finales del mismo negocio llaman a `booking.create_appointment` con la
misma `idempotency_key`. El segundo no obtiene su cita: recibe la **del primero**
(`appointment_id`, hora, servicio, barbero, precio) marcada como
`idempotent_replay=True`, y el agente le confirma una cita que no tiene. Lo esperado:
la clave es de cada persona; el segundo obtiene una cita suya y, si repite la llamada,
la misma.

## Reproduction

1. Un tenant con dos clientes, Ana y Bruno.
2. Turno de Ana (`customer_context(ana)`): `booking.create_appointment` a las 10:00
   con `idempotency_key="sabado-1000"`.
3. Turno de Bruno (`customer_context(bruno)`): la misma llamada, a las 11:00, con la
   misma clave.
4. Resultado: Bruno recibe la cita de Ana (10:00, su id) con `idempotent_replay=True`;
   en `appointments` hay una sola fila y es de Ana.

Reproducido en `apps/api/tests/isolation/test_35_customer_scope_within_tenant.py`
(ver `test.md`).

## Suspected Code Paths

- `apps/mcp/src/nexus_mcp/servers/booking/tools.py:212-228` — el camino idempotente
  busca `Appointment.idempotency_key == payload.idempotency_key` y devuelve la fila sin
  mirar `customer_id`. La RLS solo separa tenants: la fila de Ana es visible en el
  turno de Bruno.
- `apps/mcp/src/nexus_mcp/servers/booking/tools.py:254-280` — el camino de la carrera
  (`IntegrityError` → re-select por la misma clave) tiene el mismo defecto.
- `apps/mcp/src/nexus_mcp/servers/booking/tools.py:246` — se guarda la clave tal cual
  la manda el modelo; la unicidad es `(tenant_id, idempotency_key)`
  (`db/models/appointment.py:28`), así que la clave es del negocio, no de la persona.
- `apps/mcp/src/nexus_mcp/servers/booking/tools.py:194-199` — la descripción pide
  derivar la clave de `conv:{conversation_id}:…`, un dato que el modelo no tiene; en la
  práctica la deriva de lo que se reserva («corte sábado 10:00»), que es justo lo que
  dos personas comparten.

## Root Cause Hypothesis

Confianza alta. La clave de idempotencia la elige el modelo y se guarda con alcance de
tenant, mientras que la cita tiene alcance de persona. Spec 014 sacó el cliente de los
argumentos (`_own_appointment` protege modify y cancel), pero el camino de replay de
`create` quedó fuera: es una lectura por clave que no pasa por el eje cliente. Viene
del bloque D (2026-05-08, `8ce6acae`), anterior a la 014, cuyo `fix.md` dejó la
idempotencia explícitamente fuera de alcance.

## Proposed Remediation

**Preferred** (el mismo arreglo que la 043 en `reservas.create`):

1. La herramienta guarda `agent:` + sha256(`{customer_id}:{clave}`) en vez de la clave
   cruda (`_agent_key`, 70 caracteres; cabe en la columna de 120 y en el campo de 120
   de `agendapro_public.create_appointment`, que recibe la clave de la fila). Dos
   personas ya no pueden compartir clave; la misma persona sigue siendo idempotente.
2. Defensa en el replay: si la fila que encuentra la clave es de otra persona, la
   herramienta responde `idempotency_conflict` y no la entrega. Se aplica en los dos
   caminos (lookup y carrera), con un solo helper.
3. La descripción de la herramienta y del campo dicen «por persona» y dejan de citar un
   id de conversación que el modelo no tiene.

`booking.*` no tiene capa de dominio en la API: la herramienta es la única que escribe
`appointments` con clave (el cron de AgendaPro la lee de la fila). La defensa del paso
2 vive, por tanto, en la propia herramienta.

**Alternatives**:
- Filtrar el lookup por `customer_id` (ignorar la fila ajena) sin cambiar la clave: no
  basta, porque la unicidad `(tenant_id, idempotency_key)` haría fallar el `INSERT` de
  Bruno y el camino de carrera volvería a encontrar la fila de Ana.
- Cambiar la unicidad a `(tenant_id, customer_id, idempotency_key)`: exige migración y
  deja la columna con semántica distinta a la de `reservations`; la 043 eligió la
  clave derivada.

**Files likely to change**:
- `apps/mcp/src/nexus_mcp/servers/booking/tools.py`
- `apps/mcp/src/nexus_mcp/servers/booking/schemas.py` (solo descripción del campo)
- `apps/api/tests/isolation/test_35_customer_scope_within_tenant.py`

**Tests to add or update**:
- Aislamiento, eje cliente: Ana y Bruno con la misma clave → Bruno obtiene una cita
  suya (otra id, su hora, `idempotent_replay=False`), repetir es replay para él, y en
  base cada fila es de su persona.
- Aislamiento, defensa: una fila de Ana con la clave que derivaría Bruno → la
  herramienta responde `idempotency_conflict` y no devuelve la cita de Ana.
- La prueba de replay existente (`tests/integration/mcp/test_servers_happy_path.py`)
  debe seguir verde sin cambios.

## Risks & Considerations

- **Filas anteriores al despliegue** guardan la clave cruda; una llamada nueva nunca
  las encuentra. Un reintento del webhook que cruce el despliegue podría duplicar una
  cita: ventana de segundos, aceptable.
- **Sin migración ni cambio de API**: el contrato de entrada y salida es el mismo.
- El payload del job `async_booking` pasa a reflejar la clave de la fila (lo que ya
  dice su docstring); el cron lee la de la fila, así que no cambia lo que llega a
  AgendaPro más allá de que ahora es por persona.
- Exposición: dentro del mismo tenant, datos de la cita (hora, servicio, barbero,
  precio, id), no de contacto. El id no permite actuar sobre la cita
  (`_own_appointment`). El daño mayor es de integridad: una confirmación falsa a quien
  no tiene cita.

## Open Questions

- Ninguna que bloquee el arreglo. Si hubo colisiones reales en producción se responde
  con una consulta de `appointments` agrupada por `(tenant_id, idempotency_key)` con
  más de un cliente en la conversación de origen; fuera de este bug.
