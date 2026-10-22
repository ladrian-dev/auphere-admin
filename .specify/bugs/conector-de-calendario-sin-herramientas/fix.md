# Bug Fix: Google Calendar y Calendly se conectan pero el agente no recibe herramientas, y reintentar da 502

- **Slug**: conector-de-calendario-sin-herramientas
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied (rama `hotfix/prod-2026-10-22`, sin desplegar); el webhook
  de Composio, suscrito al evento que faltaba el 2026-10-22

## Summary

Las herramientas de Composio se leen del esquema crudo y llegan con su nombre.
Un segundo «Conectar» sobre una instalación `pending` que ya está autorizada
arriba la reconcilia en el acto, la deja `connected` y responde 409 con
«… ya estaba autorizado: queda conectado.» en vez de 502. El cron de
reconciliación también recorre los tenants en `provisioning` y `paused`.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/services/connectors/composio_client.py` | modified | `list_tools` → `tools.get_raw_composio_tools`; etiquetas en lista → mapa; el falso imita el rechazo del SDK a una segunda cuenta `ACTIVE` |
| `apps/api/src/nexus_api/services/connectors/service.py` | modified | `ConsentAlreadyGranted`; `initiate_consent` reconcilia antes de volver a enlazar una instalación `pending` |
| `apps/api/src/nexus_api/api/console/tools.py` | modified | `ConsentAlreadyGranted` → `JSONResponse(409)` **devuelta**, no lanzada, para que la transacción confirme |
| `apps/worker/src/nexus_worker/streams/connector_reconcile_cron.py` | modified | `_list_reconcilable_tenants`: `active`, `paused`, `provisioning` |
| `apps/api/tests/unit/test_composio_live_list_tools.py` | new test | slug, etiquetas, toolkit y límite |
| `apps/api/tests/unit/test_endpoint_console_agent_tools.py` | modified test | segundo consentimiento tras autorizar |
| `apps/worker/tests/unit/test_connector_reconcile_cron.py` | modified test | estados de tenant del cron |

## Diff Highlights

```python
if existing and existing.status == TenantConnectorStatus.PENDING.value:
    await reconcile_connector_status(session, tenant_connector=existing, ...)
    if existing.status == TenantConnectorStatus.CONNECTED.value:
        raise ConsentAlreadyGranted(f"{connector.display_name} ya estaba autorizado: queda conectado.")
```

```python
except ConsentAlreadyGranted as exc:
    # Returned, not raised: an exception would roll back the transaction
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})
```

## Deviations from Assessment

- La consola no se toca: un 409 ya enseña el `detail` en el aviso. La tarjeta
  sigue en «pendiente» hasta recargar, aunque la base ya diga `connected`.

## Hecho fuera del código

- **Webhook de Composio** (2026-10-22): en el proyecto `auphere` (vista Platform →
  Settings → Webhooks), suscrito además a `composio.connected_account.activated`.
  La URL y los otros tres eventos ya estaban y no se han tocado.

## Pendiente (manual)

- **Comprobar el secreto de firma.** Composio solo lo enseña al crearlo o
  rotarlo, así que no se sabe si coincide con `NEXUS_COMPOSIO_WEBHOOK_SECRET`
  (el 19-ago prod aún tenía el valor de desarrollo). En la próxima autorización
  de un conector: si sale `composio_webhook.signature_invalid` en
  `/nexus/prod/api`, rotarlo en Composio, copiarlo a `nexus/prod/app` y volver a
  desplegar la API. Mientras tanto, el estado lo resuelven el cron (10 min) o un
  segundo clic.
- `demo-lorenzo` desconectó los dos conectores el 22-oct a las 13:59; hay que
  volver a conectarlos después de desplegar para que se sincronicen las
  herramientas.
- Un conector de Composio que ya esté `connected` con cero herramientas no se
  arregla solo: la reconciliación solo sincroniza en un cambio de estado. Tras
  desplegar, «Sincronizar» en cada uno.
