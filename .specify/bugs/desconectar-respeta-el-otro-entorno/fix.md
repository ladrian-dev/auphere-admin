# Bug Fix: desconectar un número en un entorno deja sin webhook al otro

- **Slug**: desconectar-respeta-el-otro-entorno
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Antes de desuscribir la app de la cuenta de WhatsApp Business al desconectar su
último número, la consola lee `GET /{waba}/subscribed_apps` y solo borra la
suscripción si emite al webhook de **este** entorno. Si emite a otro sitio, a
ninguno (webhook general de la app) o nuestra app ya no está, la deja como está,
lo anota en la auditoría y en el log, y suelta igualmente lo propio.

## Changes

| File | Change | Notes |
|---|---|---|
| `apps/api/src/nexus_api/api/console/diagnostics.py` | modified | `_our_entry` (compartido con `webhook_subscribed`), `same_callback` y `subscription_owner`, puros |
| `apps/api/src/nexus_api/api/console/channels.py` | modified | `disconnect_channel`: el paso `unsubscribe` pasa por `subscription_owner`; `meta.kept_subscription` en la auditoría; log `channel.unlink.subscription_kept`; **invalida la caché del resolver** del número tras escribir el estado |
| `apps/api/tests/unit/test_endpoint_console_channels.py` | added tests + simulador | `_MetaSim.list_subscribed_apps` (por defecto, la suscripción de este entorno), `_subscribed()`, cinco tests nuevos |
| `docs/console.md` | modified | qué hace desconectar con la suscripción |

## Diff Highlights

```python
elif step == "unsubscribe":
    owner, target = subscription_owner(
        await client.list_subscribed_apps(waba_id=waba_id, access_token=token),
        app_id=settings.meta_app_id,
        callback_url=settings.meta_webhook_callback_url,
    )
    if owner != "ours":
        kept = {"reason": "not_subscribed" if owner == "none" else "subscription_elsewhere",
                "callback_host": urlsplit(target).hostname if target else None}
        ...  # log, skipped, pending.remove, borra la credencial local, continue
    await client.unsubscribe_app(waba_id=waba_id, access_token=token)
```

`subscription_owner` → `ours` solo si `override_callback_uri` es la URL de este
entorno (esquema y host sin caja, ruta sin la barra final); sin override o con
otra URL → `elsewhere`; sin nuestra app → `none`.

## Tests Added or Updated

- `test_a_subscription_to_another_environment_is_left_alone` — el caso real: emite a `api.staging.auphere.com` → sin `DELETE`, sin pendientes, `skipped: ["unsubscribe"]`, `kept_subscription` con el motivo y el host, credencial del canal borrada.
- `test_a_subscription_without_override_is_left_alone` — sin override → no se borra.
- `test_an_account_without_our_app_has_nothing_to_unsubscribe` — nuestra app no suscrita → sin `DELETE`, sin pendientes, `not_subscribed`.
- `test_our_own_subscription_is_still_removed` — la suscripción propia (con otra caja en esquema y host y barra final) se sigue borrando: spec 021 R2.2 intacta.
- `test_reading_the_subscription_fails_and_the_step_waits` — la lectura falla → `unsubscribe` pendiente con su error.
- `test_disconnecting_stops_routing_the_number_right_away` — la clave `nexus:tenant_resolve:meta:<número>` de Redis desaparece al desconectar. Vista en rojo antes de añadir la invalidación.
- El simulador devuelve por defecto la suscripción de este entorno, así que los tests de desconexión que ya había (spec 021) siguen diciendo lo mismo sin cambiar sus aserciones: `calls` son las escrituras; las lecturas van en `reads`.

**Rojo antes del arreglo**: los cuatro primeros de los nuevos fallaron con el
código de `develop` (`4 failed, 1 passed`); el que pasó es el de la suscripción
propia, que protege el comportamiento que ya era correcto.

## Local Verification

- `uv run pytest tests/unit/test_endpoint_console_channels.py` → **53 passed** (base propia, sin otra suite corriendo).
- `ruff check` y `ruff format --check` de los tres archivos → limpios; `mypy --strict` de `channels.py` y `diagnostics.py` → sin errores.
- `./scripts/verify.sh lint` y `./scripts/verify.sh py` → todo verde (detalle en `test.md`).

## Deviations from Assessment

- **Alcance ampliado: la caché del resolver.** La evaluación da por inocua una
  suscripción de más porque «sus mensajes llegan a un canal desconectado» y no se
  resuelven (`resolve_channel_tenant` solo acepta `status = 'active'`). Eso es
  cierto en la base, pero el resolver guarda número → cliente **una hora** en
  Redis (`tenant_cache_ttl = 3600`) y desconectar no la invalidaba: durante esa
  hora los mensajes del número seguían llegando a su agente. Antes lo tapaba la
  baja de la suscripción en el caso del último número; con este arreglo ya no
  siempre hay baja, así que la desconexión invalida la caché justo después de
  escribir el estado (`invalidate_tenant_cache`, lo mismo que hace el alta). Salió
  de la pasada de `/cso` sobre el diff.
- «Nuestra app no está suscrita» se anota como `skipped` con motivo
  `not_subscribed`, no como paso hecho: no se llamó a Meta para nada, y `done`
  quiere decir que se hizo.
- No hizo falta tocar `meta_client.py`: `list_subscribed_apps` ya existía.

## Follow-ups

- **Reconectar el `+34672138367` en staging** (consola de partners de staging ›
  Demo Farmacia Amacrux › Canales). Este arreglo evita que vuelva a pasar; no
  devuelve la suscripción que ya se borró.
- Valorar una app de Meta por entorno, o no usar en producción los números de
  pruebas de staging. Mientras compartan app, **conectar** en un entorno sigue
  llevándose los mensajes del otro hasta que se reconecte allí (el alta reescribe
  el `override_callback_uri`): eso no es este bug, es compartir la app.
