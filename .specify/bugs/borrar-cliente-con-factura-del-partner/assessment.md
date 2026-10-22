# Bug Assessment: borrar un cliente que sale en la factura de su partner da 502

- **Slug**: borrar-cliente-con-factura-del-partner
- **Created**: 2026-10-22
- **Source**: logs de `/nexus/prod/api`, 2026-10-21 16:20 y 16:21 UTC (`demo-farmacia-amacrux`)
- **Verdict**: valid
- **Severity**: low — el borrado se niega igual; lo que falla es el motivo

## Symptom

`DELETE /admin/tenants/f18e61ba-…` → 502, dos veces:

```
ForeignKeyViolationError: … violates foreign key constraint
"invoice_lines_tenant_id_fkey" on table "invoice_lines"
```

Lo esperado (WP-29, `tenant_lifecycle.py`): un 409 que diga que la facturación se
conserva por obligación legal, como ya pasa con las facturas propias.

## Root cause

El guardarraíl cuenta `invoices WHERE tenant_id = :t`. Una factura de partner no
lleva `tenant_id`: el cliente aparece como una de sus `invoice_lines`, que
también es RESTRICT. El guardarraíl no la ve, el borrado llega a Postgres y la
FK lo para.

## Suspected Code Paths

- `apps/api/src/nexus_api/services/tenant_lifecycle.py` — `hard_delete_tenant`.

## Possible Remediation

Contar también las facturas en las que el cliente es una línea. Bajo la RLS de la
sesión del tenant esas líneas son visibles (policy por `tenant_id`).
