# Bug Verification: borrar un cliente que sale en la factura de su partner da 502

- **Slug**: borrar-cliente-con-factura-del-partner
- **Tested**: 2026-10-22 (local, base propia `nexus_test_hotfix`)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified en local; sin desplegar

## Red before the fix

`test_a_line_in_the_partners_invoice_also_blocks_with_a_readable_reason`:
`502 == 409`, la misma constraint que en producción.

## Green after the fix

`test_endpoint_tenant_delete.py`: 5 passed (la nueva y las cuatro que ya había).
