# Bug Verification: la Bandeja lite avisa en tiempo real antes de confirmar lo que avisa

- **Slug**: bandeja-publica-antes-del-commit
- **Tested**: 2026-10-19
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

La reproducción automática (un suscriptor que relee por su propia conexión al
oír el aviso) falla en las siete acciones antes del arreglo y pasa después; un
rollback ya no avisa. Las cuatro suites de Python y el lint quedan en verde
sobre `28a5b562`, que es la punta de `origin/main` y `origin/develop`
(comprobado con `git fetch` antes y después de la suite: no entró nada nuevo).

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproducción (antes del arreglo) | `uv run pytest tests/unit/test_lite_inbox_publish_after_commit.py` | fail (esperado) | 8 rojos: las 7 acciones «llegó antes del commit» (el suscriptor leía el estado previo) y el rollback con un aviso oído. |
| Reproducción (después del arreglo) | el mismo comando | pass | 9 passed. |
| Pruebas cercanas | `uv run pytest tests/unit/test_lite_inbox_*.py tests/unit/test_lite_by_agent.py tests/isolation/test_lite_*.py tests/integration/channels/test_member_messages_outbound.py` | pass | 342 passed (incluye los barridos de aislamiento lite). |
| Regresión completa | `./scripts/verify.sh py` | pass | api 4817 passed / 377 skipped / 4 xfailed; worker 438; channels 61; mcp 123. «Todo verde». |
| Lint / tipos | `./scripts/verify.sh lint` | pass | ruff check + format y mypy --strict en api, worker, channels, mcp. |
| Base actualizada | `git fetch origin` + `git rev-list --count HEAD..origin/main` | pass | 0 commits nuevos en `main`/`develop`; no hubo que fusionar nada. |
| Orden respuesta/cierre en FastAPI 0.136 | experimento ASGI mínimo (fuera del repo) | observado | `['response body sent', 'dependency teardown (commit)']`: el aviso sale tras el commit y tras la respuesta. |

## Output Excerpts

```
attachments: «message.new» llegó antes del commit — quien lo oyó leyó {... 'messages': [2 ids] ...},
y lo confirmado es {... 'messages': [3 ids] ...}
takeover: «conversation.updated» llegó antes del commit — quien lo oyó leyó
{'agent_active': True, 'version': 0, 'assignee': None, ...}, y lo confirmado es
{'agent_active': False, 'version': 1, 'assignee': 'client_…', ...}
```

```
▸ pytest · api      4817 passed, 377 skipped, 4 xfailed, 152 warnings in 1339.91s
▸ pytest · worker   438 passed
▸ pytest · channels 61 passed
▸ pytest · mcp      123 passed
Todo verde. La tubería debería pasar.
```

## Residual Risks

- La reproducción de la evaluación con dos pestañas reales sobre la SSE no se
  hizo en un navegador: se ejercitó su equivalente por API (app FastAPI real,
  Postgres real, Redis falso cuyo `publish` hace de suscriptor). El reenvío de
  la SSE lo cubre aparte `test_stream_relays_only_its_clients_channel`.
- La respuesta HTTP sigue saliendo antes del commit (ver «Follow-ups» en
  `fix.md`); es otra carrera y queda abierta.
- Los 377 skips de la API son anteriores a este cambio; ninguno es de las
  pruebas nuevas (9 passed en su archivo).

## Recommendation

Cerrar el bug: verificado con la reproducción automática en rojo y en verde y
con la tubería de Python completa en verde sobre la punta actual de `main`.
Abrir aparte el seguimiento de la respuesta antes del commit.
