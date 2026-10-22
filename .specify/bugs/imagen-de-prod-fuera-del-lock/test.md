# Bug Verification: la imagen de producción no instala lo que fija el lock

- **Slug**: imagen-de-prod-fuera-del-lock
- **Tested**: 2026-10-22 (local, base propia `nexus_test_hotfix`, Redis db 13)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified en local; **la imagen no se ha construido** (ver «Not covered»)

## Red before the fix

Los logs de build de `deploy-prod` (`gh run view … --log`): `litellm==1.105.0` el
12-oct, `1.106.0` el 19-oct, `1.106.2` el 21-oct; `composio==0.28.0` frente al
`0.13.0` del lock. Diferencia completa contra `apps/api/uv.lock`: 123 de 148
paquetes, 12 de versión mayor.

## Green after the fix

Los pasos nuevos de los dos Dockerfile, repetidos fuera de Docker con `uv`
0.13.4 (la versión fijada) sobre Python 3.11 (la de la imagen), en entornos
limpios:

| Paso | api | worker |
|---|---|---|
| `uv export --frozen --no-dev --no-emit-project` (`--locked` desde la corrección) | ok (135 paquetes) | ok |
| `uv pip install --no-editable -r` + `--no-deps .` | ok | ok |
| `python -I -m nexus_api.core.litellm_smoke` | `litellm 1.83.0: tool calls need no missing package` | `litellm 1.83.14: …` |
| importar desde `site-packages` | `nexus_api.main`, `nexus_worker.bootstrap`, `nexus_mcp`, `nexus_channels`, `ucm_schema` | `nexus_worker.main`, `nexus_api.main` |

| Suite | Resultado |
|---|---|
| `./scripts/verify.sh lint` | verde (ruff y formato de los cuatro paquetes; mypy --strict api, worker, channels, mcp) |
| `./scripts/verify.sh py` | verde: API 4 967 passed / 415 skipped / 4 xfailed; worker 448; channels 61; MCP 123 |

## Not covered

- **`docker build`**: no se ha construido ninguna imagen (el disco local estaba
  al 99 %) y ninguna tubería las construye antes de `main`. El primer build real
  será el de `deploy-prod`; si falla, falla antes de desplegar y producción se
  queda como está. Vale la pena un `workflow_dispatch` o un build a mano antes de
  fusionar.
- El comportamiento de producción con las versiones del lock: es lo que prueba CI,
  pero producción no lo ha corrido nunca.
