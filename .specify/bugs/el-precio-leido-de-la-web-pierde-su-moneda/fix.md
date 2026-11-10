# Bug Fix: el precio leído de la web pierde su moneda

- **Slug**: el-precio-leido-de-la-web-pierde-su-moneda
- **Fixed**: 2026-11-08
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`parse_extraction` añade `price_currency` al servicio cuando hay importe y moneda. El
lector lo pasa a `create_service` y a `update_service`. Con eso, el primer importe leído
fija la moneda de un negocio que no tenía (`currency_for_amount`, 055, 3.1). Sin moneda
leída nada cambia: el importe sigue sin inventarse.

## Files

- `apps/api/src/nexus_api/services/business/reader.py`
- `apps/api/tests/unit/test_reader_structured.py` (dos pruebas nuevas y la forma esperada de JSON-LD)
