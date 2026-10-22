# Bug Fix: borrar un cliente que sale en la factura de su partner da 502

- **Slug**: borrar-cliente-con-factura-del-partner
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied (rama `hotfix/prod-2026-10-22`, sin desplegar)

## Summary

El guardarraíl cuenta las facturas propias y las del partner en las que el
cliente es una línea (`UNION` sobre `invoices` e `invoice_lines`), y responde 409
con el motivo. Vale para el Admin y para la consola, que comparten
`hard_delete_tenant`.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/services/tenant_lifecycle.py` | modified | consulta y mensaje; docstring del punto 2 |
| `apps/api/tests/integration/test_endpoint_tenant_delete.py` | modified test | línea en la factura del partner → 409 y nada borrado |

## Nota

`demo-farmacia-amacrux` seguirá sin poder borrarse, ahora con un 409 legible.
Es lo correcto: su línea en la factura de Amacrux se conserva.
