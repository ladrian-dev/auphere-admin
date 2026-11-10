# Bug Assessment: el horario del negocio se guarda en tres formas y el agente no entiende la del admin

- **Slug**: horario-del-negocio-en-tres-formas
- **Created**: 2026-10-22
- **Source**: pasted text (lectura de dominio de Reservas, KB
  `research/2026-10-22-reservas-y-consola-customers/lecturas/reservas-dominio.md` §7.3.1)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

> Horario en tres formas. El admin guarda `{"monday":"09:00-18:00"|"closed"}`.
> `apps/mcp/src/nexus_mcp/servers/booking/availability.py:61-63` espera
> `{"monday":{"start","end"}}` y llama a `.get` sobre un string: lanza
> `AttributeError` en `check_availability`. Si falta el día, abre de 10 a 19
> (también el domingo). La consola (spec 019) usa `{from,to}|null` y solo envía
> la etiqueta. La regla «solo días y horas hábiles» exige una forma canónica.

## Symptom

`booking.check_availability` revienta para **cualquier** tenant creado desde el
asistente del panel de operador con horario, y para los que lo tienen cerrado
algún día ofrece huecos igual:

1. **El tenant tiene horario del admin** (`{"monday": "09:00-18:00", …}`):
   `spec.get("start")` sobre un `str` lanza `AttributeError: 'str' object has
   no attribute 'get'`. La herramienta devuelve error al agente, que no puede
   ofrecer ninguna hora.
2. **El día está cerrado** (`"sunday": "closed"`): mismo `AttributeError`.
3. **El horario es el de la semilla de Boreal** (`{"open","close"}` o `None`):
   no revienta, pero ignora las horas (no son `start`/`end`) y abre de 10 a 19;
   con `"sunday": None` abre el domingo de 10 a 19.
4. **Falta el día** en un horario configurado: abre de 10 a 19, incluido el
   domingo.

Lo esperado: un solo formato que todas las piezas entienden; un día cerrado no
ofrece huecos; las horas son las del negocio.

## Reproduction

1. Tenant con `business_hours = {"monday": "09:00-18:00", …, "sunday": "closed"}`
   (lo que guarda `BusinessHoursPicker` del asistente del admin).
2. `booking.check_availability` para un lunes.
3. Resultado: `AttributeError` dentro de `_resolve_tenant_hours`.
4. Con `{"monday": {"open": "09:00", "close": "18:00"}, "sunday": None}` (semilla
   de Boreal): el lunes ofrece de 10:00 a 19:00 y el domingo también.

## Suspected Code Paths

- `apps/mcp/src/nexus_mcp/servers/booking/availability.py:58-63`
  (`_resolve_tenant_hours`) — solo entiende `{"start","end"}`, llama a `.get`
  sobre lo que haya y cae a 10–19 si no lo encuentra. No conoce «cerrado».
- `apps/admin/src/components/forms/business-hours-picker.tsx:62-69`
  (`serialize`) — escribe `"HH:MM-HH:MM"` o `"closed"`.
- `apps/api/scripts/seed_clinica_boreal.py:76-84` — escribe
  `{"open","close"}` y `None`.
- `apps/api/src/nexus_api/api/admin/tenants.py:158,274-275` y
  `apps/api/src/nexus_api/schemas/tenant.py:66,136` — aceptan cualquier
  `dict[str, Any]` y lo guardan tal cual: la API no impone forma.
- `apps/console/src/components/clients/new/hours.ts` (spec 019) — usa
  `{from,to}|null` pero **no** escribe `tenants.business_hours`: solo compone la
  etiqueta `tenant.business_hours_label` para la semilla. No es una cuarta
  forma guardada, sí una cuarta forma en el código.
- `apps/api/src/nexus_api/api/admin/agent_configs.py:675-679` — lee
  `business_hours["label"]`, una clave que nadie escribe hoy.

## Root Cause Hypothesis

`business_hours` es un JSONB sin esquema. Cada pieza que lo tocó eligió su
forma sin que la API la impusiera, y el único lector estructurado (la
disponibilidad del agente) se escribió contra una forma que no escribe nadie.
**Confianza: alta** — se ve leyendo el código; la prueba lo fija.

## Proposed Remediation

**Preferred**: una forma canónica, un solo lector tolerante y la API como
única puerta de escritura.

1. **Forma canónica**, con tramos para poder partir el día (comida y cena):
   `{"monday": [{"from": "09:00", "to": "14:00"}, {"from": "15:00", "to": "19:00"}], …, "sunday": []}`.
   Lista vacía = cerrado. Las siete claves siempre presentes.
2. **Un módulo puro** `nexus_api/services/business_hours.py` con
   `parse_business_hours(raw)` (lee las cuatro formas que existen —cadena
   `"HH:MM-HH:MM"`/`"closed"`, `{start,end}`, `{open,close}`, `{from,to}`,
   `None` y listas de cualquiera—; un día que falta en un horario configurado o
   que no se entiende es **cerrado**) y `canonical_business_hours(raw)`.
   `parse_business_hours` devuelve `None` si el tenant no tiene horario (se
   conserva el 10–19 de hoy para ese caso: cambiarlo es decisión de la spec 043,
   que exige horario para activar Reservas).
3. **`availability.py`** usa ese lector y recorre los tramos del día; un día
   cerrado no da huecos.
4. **La API normaliza al escribir** (`TenantCreate`, `TenantUpdate`): acepta
   cualquiera de las formas que existen, guarda la canónica y rechaza con 422 lo
   que no se entiende.
5. **El selector del admin** escribe la forma canónica y lee las dos.
6. **Migración de datos** que normaliza las filas existentes (las que no se
   entiendan se dejan como estaban y se cuentan en el log).

**Alternatives**:
- *Arreglar solo el lector para que entienda la cadena del admin.* Quita el
  `AttributeError` pero deja tres formas guardadas y la siguiente pieza (la 043,
  la consola lite) volvería a elegir una cuarta.
- *Hacer canónica la cadena del admin.* No admite dos tramos por día, que un
  restaurante con comida y cena necesita.

**Files likely to change**:
- `apps/api/src/nexus_api/services/business_hours.py` (nuevo)
- `apps/mcp/src/nexus_mcp/servers/booking/availability.py`
- `apps/api/src/nexus_api/schemas/tenant.py`
- `apps/admin/src/components/forms/business-hours-picker.tsx`
- `apps/api/scripts/seed_clinica_boreal.py`
- `apps/api/alembic/versions/0181_canonical_business_hours.py` (o el siguiente número libre)

**Tests to add or update**:
- Unidad del lector: las cuatro formas, «cerrado», día que falta, valor basura,
  dos tramos, `None`.
- Integración de `booking.check_availability` con el horario del admin: huecos
  dentro del horario, ninguno en domingo cerrado, dos tramos sin hueco en la
  comida.
- Admin: crear y actualizar un tenant con la forma del picker guarda la canónica;
  basura → 422.
- Migración: normaliza, no toca lo que no entiende, idempotente y reversible en
  la prueba de reversibilidad.
- Vitest del picker: serializa la forma canónica y lee la antigua.

## Risks & Considerations

- **El agente cambia de comportamiento**: los tenants con horario dejarán de
  ofrecer huecos fuera de él y en días cerrados. Es lo correcto, y hoy esos
  tenants ni siquiera reciben huecos (error).
- **Etiqueta del prompt** (`business_hours_label`) sigue saliendo de la semilla;
  no cambia.
- **Producción**: solo se puede saber cuántos tenants tienen cada forma con una
  consulta de solo lectura; la migración es tolerante, así que no depende de ese
  dato.

## Open Questions

Ninguna que bloquee. Qué hacer con un tenant **sin** horario (hoy 10–19 todos los
días) lo decide la spec 043.
