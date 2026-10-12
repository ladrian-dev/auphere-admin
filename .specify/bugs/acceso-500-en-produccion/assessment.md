# Bug Assessment: la pestaña «Acceso» del admin da 500 en producción

- **Slug**: acceso-500-en-produccion
- **Created**: 2026-10-12
- **Source**: pasted text — captura del admin de producción (Flor y Encanto → Acceso: «No se pudo leer el acceso. La API respondió 500.»)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

En producción, la pestaña «Acceso» de cualquier cliente enseña «No se pudo
leer el acceso. La API respondió 500». Sin ella no se puede encender la
consola lite de nadie.

## Symptom

`GET /admin/tenants/{id}/client-access` responde 500 en producción; en
staging y en las pruebas responde 200.

## Reproduction

1. Producción, `admin.auphere.com` → un cliente → «Acceso».
2. Log de la API (`/nexus/prod/api`, 2026-10-12 14:48 UTC):
   `isolation.unscoped_query` sobre `SELECT count(*) FROM channels WHERE …` y
   `IsolationViolation: SQL on tenant-scoped table without app.tenant_id` en
   `services/client_access.py:113 (_whatsapp_connected)`.
3. En local, con `NEXUS_ISOLATION_ENFORCER_RAISE_IN_DEV=true`, la misma
   excepción (`tests/unit/test_admin_client_access_strict_isolation.py`).

## Suspected Code Paths

- `apps/api/src/nexus_api/core/isolation_enforcer.py:117-118` — en producción
  (`settings.is_prod`) **corta** toda sentencia sobre una tabla de cliente sin
  `app.tenant_id`; fuera de producción solo avisa.
- `apps/api/src/nexus_api/api/admin/client_access.py` — las cinco rutas usan
  `get_db_session` (plataforma, sin declarar cliente).
- `apps/api/src/nexus_api/services/client_access.py:113` (`_whatsapp_connected`,
  tabla `channels`) en leer y guardar; `inbox_lifecycle.release_escalated_for_tenant`
  (tabla `conversations`) al quitar la Bandeja.

## Root Cause Hypothesis

Las rutas del admin de la spec 030 trabajan sobre un cliente con la sesión de
plataforma y no declaran `app.tenant_id`. La guarda solo corta en producción,
así que ni las pruebas ni staging lo vieron. Confianza: alta (traza de
producción y reproducción local).

## Proposed Remediation

**Preferred**: declarar el cliente de la ruta en la sesión de plataforma
(`set_config('app.tenant_id', …)`) sin cambiar de rol. Cambiar a `nexus_app`
(`scoped_session_from_path`) no sirve: la RLS de `partner_tenants`, que es por
partner, escondería el partner y la ruta diría «sin partner».

**Tests to add**: las cinco rutas de la pestaña con la guarda en modo de corte.

## Risks & Considerations

- La RLS sigue sin aplicar en esa sesión (rol de conexión): cada consulta
  sigue filtrando por `tenant_id` a mano, como hoy.
- **Hallazgo de proceso**: las pruebas no ejercitan la guarda en modo de
  corte. Un barrido de la spec 030 con la guarda cortando (192 pruebas) solo
  encontró este caso; activarla en toda la suite es trabajo aparte.
