# Contrato: API del panel

## `GET /admin/tenants/{tenant_id}/connectors/{slug}/customer-accounts`

**Autorización**: el token de operador (`require_admin_token`), con la sesión fijada al tenant de la ruta (`scoped_session_from_path`).

**200**: el conector vincula a cada persona con su cuenta (hoy, solo `quedate`). El vínculo no guarda ninguna credencial (enmienda del 2026-11-16).

```json
{ "slug": "quedate", "linked": 12, "needs_review": 1, "last_linked_at": "2026-11-13T15:02:11Z" }
```

`last_linked_at` es `null` si no hay ninguna. **No** devuelve datos personales, ids externos ni credenciales.

**404 `customer_accounts_not_supported`**: el conector no vincula personas. El panel no pinta el bloque «Anfitriones vinculados».

## Conectar con clave (consola y panel): cambio de comportamiento

`POST /console/clients/{ref}/connectors/{slug}/api-key` y el alta por clave del panel comprueban ahora la clave cuando el conector tiene comprobador (`quedate`: `GET /agent/hosts?per_page=1` en el entorno que diga `endpoint_meta.environment`; `dev` es desarrollo y lo demás, producción). Responden lo que ya define `last_sync`:

- clave aceptada: `last_sync.status="ok"`;
- Quédate la rechaza (401, o 403 si la clave no puede usar la API del agente): `last_sync.status="error"`, `reason="auth_rejected"`, conexión `needs_reauth` y ninguna herramienta activada;
- Quédate no responde: `last_sync.status="error"`, `reason="provider_unavailable"`, conexión guardada.
