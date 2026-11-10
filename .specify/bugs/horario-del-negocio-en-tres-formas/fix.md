# Bug Fix: el horario del negocio se guarda en tres formas y el agente no entiende la del admin

- **Slug**: horario-del-negocio-en-tres-formas
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Hay una forma canónica (siete días, lista de tramos `{from, to}` por día, lista
vacía = cerrado) y un solo lector que entiende todas las que se guardaron
(`services/business_hours.py`). La disponibilidad del agente usa ese lector:
deja de reventar con el horario del admin, no ofrece días cerrados ni días que
el horario no nombra, y respeta los días partidos. La API normaliza al escribir
y rechaza con 422 lo que no entiende; el asistente del admin escribe la canónica;
la migración `0170` pasa a la canónica las filas que ya había.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/services/business_hours.py` | added | `parse_business_hours` (tolerante: ilegible o ausente = cerrado; sin horario = `None`), `canonical_business_hours` (estricto), `maybe_canonical` |
| `apps/mcp/src/nexus_mcp/servers/booking/availability.py` | modified | Tramos del día en UTC; cerrado = sin huecos; sin horario configurado sigue 10–19 |
| `apps/api/src/nexus_api/schemas/tenant.py` | modified | Validador en `TenantCreateIn` y `TenantUpdateIn`: guarda la canónica, 422 si no se entiende |
| `apps/api/alembic/versions/0170_canonical_business_hours.py` | added | Normaliza las filas; deja intactas las ilegibles; idempotente; `downgrade` vacío a propósito |
| `apps/admin/src/components/forms/business-hours-picker.tsx` | modified | Serializa la canónica; lee la canónica y la cadena antigua |
| `apps/api/scripts/seed_clinica_boreal.py` | modified | Semilla en la forma canónica |
| `apps/api/tests/unit/test_business_hours.py` | added test | Las cinco formas, cerrado, día ausente, tramos, basura, punto fijo |
| `apps/api/tests/integration/mcp/test_availability_business_hours.py` | added test | La herramienta con el horario del admin, la semilla y un día partido |
| `apps/api/tests/unit/test_endpoint_tenants.py` | modified test | Crear y actualizar guardan la canónica; basura → 422 |
| `apps/api/tests/integration/test_migration_0170_canonical_business_hours.py` | added test | Normaliza, no toca lo ilegible ni `{"label"}`, idempotente |
| `apps/admin/src/components/forms/__tests__/business-hours-picker.test.ts` | added test | Serializa la canónica, lee las dos |

## Diff Highlights

```python
# availability.py — los tramos del día, no un (inicio, fin) inventado
if hours is None:
    day_ranges = [(DEFAULT_DAY_START, DEFAULT_DAY_END)]
else:
    day_ranges = hours[WEEKDAYS[on_date.weekday()]]
```

## Deviations from Assessment

- La migración lleva su propio normalizador congelado en vez de importar el
  módulo de la aplicación: ninguna migración del repo importa `nexus_api`, y una
  migración no puede cambiar de comportamiento porque cambie el código.
- `{"label": "…"}` (sin días) se trata como «sin horario» y la migración no lo
  toca: `agent_configs` lo lee para la etiqueta del prompt.
- Al escribir pasa igual (revisión del 2026-10-22): `canonical_business_hours`
  guarda `{"label": "…"}` tal cual en vez de siete días cerrados, y conserva
  `label` junto a los días. Lo que el negocio cambia desde Reservas no toca la
  etiqueta. Pruebas: `test_a_label_alone_is_no_hours_and_is_kept`,
  `test_the_label_survives_next_to_the_days` y, en Reservas,
  `test_editing_the_hours_keeps_the_prompt_label`.

## Follow-ups

- Qué hace el agente con un tenant **sin** horario (hoy, 10–19 todos los días)
  lo decide la spec 043: Reservas exige horario para ofrecer huecos.
