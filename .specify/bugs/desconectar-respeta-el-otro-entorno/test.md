# Bug Verification: desconectar un número en un entorno deja sin webhook al otro

- **Slug**: desconectar-respeta-el-otro-entorno
- **Tested**: 2026-10-22
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

Con el arreglo, desconectar el último número de una cuenta **no** borra una
suscripción que emite a otro entorno, a ninguno, o que ya no es nuestra, y el
número deja de llevar a su cliente en el acto. Los seis tests nuevos lo fijan
(cinco vistos en rojo antes del arreglo) y la tubería de Python entera está en
verde. **No** se reprodujo en vivo con dos entornos y Meta real: por eso
`partial`, no `verified`.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Reproducción en vivo (dos entornos + Meta) | — | not-run | Exige conectar y desconectar un número real en producción; no se hace sin pedirlo. La secuencia del incidente se reconstruyó con los logs (ver `assessment.md`) |
| Reproducción simulada | `pytest tests/unit/test_endpoint_console_channels.py -k "environment or override or our_app or own_subscription or reading_the_subscription or stops_routing"` | pass | Antes del arreglo: 4 + 1 en rojo; el de la suscripción propia ya pasaba (protege lo que funcionaba) |
| Tests del archivo de canales | `pytest tests/unit/test_endpoint_console_channels.py` | pass | 53 passed: incluye todos los de desconexión de la spec 021 sin cambiar sus aserciones |
| Lint y tipos | `./scripts/verify.sh lint` | pass | ruff check/format y `mypy --strict` de api, worker, channels y mcp |
| Regresión Python | `./scripts/verify.sh py` (base `nexus_test_consolas`, sin otra suite viva) | pass | API 6050 passed, 468 skipped, 4 xfailed · worker 463 · channels 61 · mcp 123 |
| Seguridad | `/cso --diff` | pass | 1 hallazgo medio (caché del resolver sin invalidar), corregido en esta rama con test |

## Output Excerpts

```
▸ pytest · api
6050 passed, 468 skipped, 4 xfailed, 173 warnings in 2128.76s (0:35:28)
▸ pytest · worker
463 passed, 15 warnings in 15.84s
▸ pytest · channels
61 passed in 5.87s
▸ pytest · mcp
123 passed, 1 warning in 1.07s
Todo verde. La tubería debería pasar.
```

## Residual Risks

- **Forma real de `GET /{waba}/subscribed_apps`.** Los tests suponen que Meta
  devuelve `override_callback_uri` en cada entrada cuando hay override. Si no lo
  devolviera, la regla deja la suscripción: el peor caso es una suscripción de
  más, ya inocua porque el número deja de resolverse al instante.
- **No devuelve lo ya roto.** El `+34672138367` sigue sin suscripción hasta que se
  reconecte en staging.
- **Compartir app entre entornos sigue siendo frágil.** Dar de alta en un entorno
  un número que vive en otro le roba los mensajes hasta que se reconecte allí.

## Recommendation

Fusionar. Para pasar a `verified`, comprobarlo en staging cuando se reconecte el
número de la farmacia: desconectar en staging un número de pruebas cuya
suscripción emita a otro sitio y ver en la auditoría `meta.kept_subscription` y,
en los logs, `channel.unlink.subscription_kept`.
