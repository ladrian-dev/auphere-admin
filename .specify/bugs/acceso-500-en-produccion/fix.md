# Bug Fix: la pestaña «Acceso» del admin da 500 en producción

- **Slug**: acceso-500-en-produccion
- **Fixed**: 2026-10-12
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Las cinco rutas de `/admin/tenants/{id}/client-access` y `…/client-members`
declaran el cliente de la URL (`declare_tenant`) al empezar su transacción.
La guarda de producción deja de cortarlas, y no cambia nada más.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/core/tenant_context.py` | added | `declare_tenant(session, tenant_id)`: solo el GUC, sin cambiar de rol |
| `apps/api/src/nexus_api/api/admin/client_access.py` | modified | Lo llaman las cinco rutas |
| `apps/api/tests/unit/test_admin_client_access_strict_isolation.py` | added test | Leer, encender con Bandeja, invitar, reenviar, quitar la Bandeja y revocar, con la guarda cortando |
| `docs/consola-lite.md` | modified | Por qué esas rutas declaran su cliente |

## Local Verification

- El test nuevo, **en rojo** antes del arreglo con el mismo
  `IsolationViolation` que en producción; en verde después.
- `tests/unit/test_admin_client_access.py` + el nuevo → 9 passed.
- Barrido con `NEXUS_ISOLATION_ENFORCER_RAISE_IN_DEV=true` sobre la spec 030
  (consola lite, Bandeja, agentes, avisos, acceso, personas, rutas de agente
  de la consola y pagos de Andrés) → 192 passed, sin ningún corte.

## Deviations from Assessment

Ninguna.

## Follow-ups

- Verificar en producción tras el despliegue: la pestaña «Acceso» abre.
- Hallazgo de proceso: correr la suite con la guarda cortando (hoy solo avisa
  fuera de producción).
- La tarjeta «Estado» del Resumen del admin llama a
  `/admin/tenants/{id}/readiness`, que la API no ha tenido nunca: necesita su
  spec, no es parte de este bug.
