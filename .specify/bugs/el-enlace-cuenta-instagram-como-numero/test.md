# Bug Verification: el enlace de WhatsApp cuenta Instagram y Messenger como números

- **Slug**: el-enlace-cuenta-instagram-como-numero
- **Tested**: 2026-11-27
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

Los dos casos de la reproducción, Instagram que ocupaba la plaza y volver a autorizar el mismo número, ya no dan 409 por el enlace. Un número nuevo en el tope sigue dándolo. No aparecen regresiones en las rutas de canales de la consola ni en su aislamiento.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción (antes del arreglo) | `pytest tests/integration/test_channel_signup_links.py -k "quota or instagram_account"` | fail (esperado) | 2 failed, 1 passed: `409 channel_quota_full` donde se esperaba llegar al alta |
| Reproducción (después del arreglo) | el mismo comando, con el `POST /console/channel-signup/{token}` real contra la base | pass | Los pasos 1–4 de la evaluación, de punta a punta por la ruta pública; solo el alta de Meta está sustituida |
| Pruebas nuevas y cuota de la consola | `pytest tests/integration/test_channel_signup_links.py tests/integration/test_076_whatsapp_reconnect_quota.py` | pass | 10 passed |
| Regresión de la consola y aislamiento | `pytest tests/unit/test_endpoint_console_whatsapp.py tests/unit/test_endpoint_console_channels.py tests/isolation/test_console_scope.py` | pass | 1735 passed |
| Lint y tipos | `./scripts/verify.sh lint` | pass | ruff check, ruff format y `mypy --strict` de la API y el worker |
| Staging | — | not-run | No está desplegado; sin enlace real con Meta |

Base propia `nexus_test_fixrev` y Redis 14, para no chocar con otras suites.

## Output Excerpts

```
AssertionError: {"detail":{"code":"channel_quota_full"}}
assert 409 == 418            # antes, las dos primeras pruebas
10 passed, 1 warning in 14.77s
1735 passed, 1 warning in 111.11s
Todo verde. La tubería debería pasar.
```

## Residual Risks

- **No probado con Meta real:** la parte de Meta está sustituida; lo que cambia es la decisión anterior a llamarla. Conviene probar en staging un enlace de WhatsApp en un cliente con Instagram conectado.
- **«WhatsApp login»:** si su alta no trae `phone_number_id`, volver a autorizar por enlace cuenta como número nuevo, como hoy en la consola.

## Recommendation

Cerrar el bug como verificado en local. Fusionarlo a `develop` antes que la spec 085, y probar en staging un enlace de WhatsApp en un cliente con Instagram conectado y su tope de números lleno.
