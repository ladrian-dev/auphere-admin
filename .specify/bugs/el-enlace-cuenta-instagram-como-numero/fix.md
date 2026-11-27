# Bug Fix: el enlace de WhatsApp cuenta Instagram y Messenger como números

- **Slug**: el-enlace-cuenta-instagram-como-numero
- **Fixed**: 2026-11-27
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

La regla de la cuota de números pasa a un solo sitio, `services/channel_quota.py`, que usan la consola y el enlace del dueño. El enlace deja de contar Instagram y Messenger y deja volver a autorizar un número que el cliente ya tiene, como la consola.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/services/channel_quota.py` | added | `INTERNAL_PROVIDERS`, `count_connected_channels(session)` (movida desde la consola) e `is_reconnect(session, phone_number_id)` (la `_is_reconnect` de la consola, con la sesión en vez del `ClientScope`). |
| `apps/api/src/nexus_api/services/channel_signup_links.py` | modified | `connect_with_link` usa las dos funciones. Desaparecen su recuento propio y `_INTERNAL_PROVIDERS`. |
| `apps/api/src/nexus_api/api/console/channels.py` | modified | Importa `INTERNAL_PROVIDERS` y `count_connected_channels` del servicio. Siguen importables desde aquí y `__all__` no cambia. |
| `apps/api/src/nexus_api/api/console/whatsapp.py` | modified | Usa `count_connected_channels` e `is_reconnect` del servicio. Se borra `_is_reconnect` y los imports que solo usaba ella. |
| `apps/api/src/nexus_api/api/console/channel_config.py` | modified | Importa `INTERNAL_PROVIDERS` del servicio, para que `mypy --strict` no lo vea como reexportación implícita. |
| `apps/api/tests/integration/test_channel_signup_links.py` | added tests | Tres pruebas de la cuota del enlace. |

## Diff Highlights

```python
# services/channel_signup_links.py, connect_with_link
used = await count_connected_channels(session)
if used >= partner.max_channels_per_client and not await is_reconnect(
    session, payload.phone_number_id
):
    raise HTTPException(status_code=409, detail={"code": "channel_quota_full"})
```

## Tests Added or Updated

- `test_channel_signup_links.py::test_an_instagram_account_does_not_take_a_number_slot`: con un tope de 1 y un Instagram conectado, el enlace llega al alta.
- `test_channel_signup_links.py::test_reauthorising_the_same_number_by_link_passes_the_quota`: en el tope, volver a autorizar el mismo `phone_number_id` llega al alta.
- `test_channel_signup_links.py::test_a_new_number_by_link_still_hits_the_quota`: en el tope, un número distinto sigue recibiendo `channel_quota_full`.

El alta se sustituye por una que responde 418, como en `test_076_whatsapp_reconnect_quota.py`: llegar a ella es haber pasado la cuota.

## Local Verification

Base propia `nexus_test_fixrev`, Redis 14.
- **Antes del arreglo:** 2 failed y 1 passed. Las dos primeras dieron `409 channel_quota_full`, que es justo el fallo. La tercera pasa antes y después.
- **Después del arreglo:**
  - `test_channel_signup_links.py` y `test_076_whatsapp_reconnect_quota.py`: 10 passed;
  - `tests/unit/test_endpoint_console_whatsapp.py`, `tests/unit/test_endpoint_console_channels.py` y `tests/isolation/test_console_scope.py`: 1735 passed;
  - `./scripts/verify.sh lint` (ruff y `mypy --strict` de la API y el worker): todo verde.

## Deviations from Assessment

- `channel_config.py` también cambia (una línea). La evaluación no lo listaba: importaba `INTERNAL_PROVIDERS` desde `api/console/channels.py`, y desde allí ahora es un nombre importado.
- `channels_overview` sigue con su propio recuento para pintar. Era la alternativa opcional de la evaluación y queda fuera.

## Follow-ups

- Que `channels_overview` use también `count_connected_channels`, para que la regla viva en un solo sitio también en lo que se pinta.
- `services/agents.py` tiene su propia copia de `_INTERNAL_PROVIDERS`. Es la misma constante y podría importarse del servicio.
