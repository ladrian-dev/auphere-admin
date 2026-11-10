# Bug Assessment: el precio leído de la web pierde su moneda

- **Slug**: el-precio-leido-de-la-web-pierde-su-moneda
- **Created**: 2026-11-08
- **Source**: `tests/integration/clients/test_client_read_job.py::test_what_was_read_is_proposed_for_review`, en rojo en `develop` desde la spec 055 (`9bab91ef`); visto al preparar el paso a producción
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

La lectura de la web de un cliente nuevo encuentra «Corte de pelo 15 €», pero el
servicio queda en la ficha sin precio (`price_kind = none`). La prueba espera
`amount` y 1500.

## Symptom

Un negocio que aún no tiene moneda guardada pierde todos los precios que se leen de
su web. Lo esperado: el importe se guarda y la moneda leída pasa a ser la del
negocio, como cuando una persona escribe el primer precio (spec 055, requisito 3.1).

## Reproduction

1. Cliente sin `business_profiles.price_currency`.
2. Lectura de una web que dice «Corte de pelo 15 €».
3. `reservation_services` → `price_kind = none`, `price_minor = null`.

## Suspected Code Paths

- `apps/api/src/nexus_api/services/business/reader.py:832-840` — `parse_extraction` sabe la moneda (`svc.currency`) y no la deja en el servicio.
- `reader.py:1068` — el lector crea el servicio sin `price_currency`.
- `apps/api/src/nexus_api/services/business/services_catalog.py:519-523` — sin moneda, `currency_for_amount` da `None` para un actor que no es una persona y el importe se quita («no se inventa»).

## Root Cause Hypothesis

La regla de la 055 es correcta: sin moneda, no se inventa. Pero aquí la moneda sí
se sabe y se pierde por el camino. Confianza: **alta** (lectura directa y prueba).

## Proposed Remediation

**Preferred**: la extracción deja `price_currency` junto al servicio, sin tocar la
forma de `price`, que es la de la ficha; el lector la pasa al catálogo al crear y al
actualizar.
