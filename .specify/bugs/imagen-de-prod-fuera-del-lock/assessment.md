# Bug Assessment: la imagen de producción no instala lo que fija el lock

- **Slug**: imagen-de-prod-fuera-del-lock
- **Created**: 2026-10-22
- **Source**: logs de producción (CloudWatch) tras el alta manual de `demo-lorenzo`
- **Verdict**: valid
- **Severity**: critical — **hotfix P0**: ningún turno con herramientas sale en
  producción desde el 2026-10-19. Esta carpeta es su spec retroactiva (el
  arreglo de LiteLLM entró en `develop` el 2026-10-21; vencía el 2026-10-23).

## Report (summarized)

Luis creó un cliente a mano (`demo-lorenzo`), lo configuró entero en la consola,
conectó WhatsApp y el agente «falló».

## Symptom

El primer mensaje del cliente (12:21:33 UTC del 22-oct) pasa la clasificación y
muere en el paso de reserva: cuatro `llm.attempt_failed` con `proxy unreachable`
sobre `gpt-5.6-terra` y `gpt-5.6-sol`, y el cliente recibe la respuesta de
respaldo en vez de la reserva. Lo mismo le pasó a `flor-y-encanto` el 20-oct. Muna
no lo ha sufrido porque sus admins no escriben desde el 18-oct; la próxima
consulta caería igual.

Lo esperado: el agente responde con sus herramientas, como hasta el 12-oct.

## Reproduction

1. `gh run view <id> --log | grep -oE 'litellm==[0-9.]+'` sobre los despliegues a
   prod: 12-oct `1.105.0`, 19-oct `1.106.0`, 21-oct `1.106.2`.
2. Desde LiteLLM 1.106, toda `completion()` con `tools` importa el paquete
   opcional `mcp`, que no está instalado. `llm_proxy.map_proxy_failure` convierte
   el `ModuleNotFoundError` en «proxy unreachable».
3. La clasificación va sin herramientas y funciona; todo lo demás falla.

## Root cause

Los Dockerfile de `api` y `worker` hacen `uv pip install .`: resuelven en cada
build lo último que permita `pyproject.toml`. CI instala desde `uv.lock`
(`uv export --frozen`). Lo que corre en producción no es lo que CI prueba.

La deriva no es solo LiteLLM. Comparando el log del build del 21-oct con
`apps/api/uv.lock`: **123 de 148 paquetes distintos, 12 de versión mayor**
(`anthropic` 0.104→2.0, `sqlalchemy` 2.0→2.1, `composio` 0.13→0.28 con
`composio-client` 2.0.0rc17, `protobuf` 6→7, `wrapt` 1→2, `langfuse` 4→5,
`stripe` 15→16…). `uv` tampoco estaba fijado (prod construía con 0.13.4).

## Suspected Code Paths

- `apps/api/Dockerfile`, `apps/worker/Dockerfile` — `uv pip install .` sin lock.
- `apps/api/pyproject.toml`, `apps/worker/pyproject.toml` — `litellm>=1.52.0` sin techo.

## Possible Remediation

1. Techo `litellm<1.106` y `nexus_api.core.litellm_smoke` en el build — ya
   hecho en `develop` (5d54110d), sin llegar a `main` (el PR #11 está en rojo).
2. Construir las imágenes **desde el lock**: `uv export --frozen` + `uv pip
   install -r`, y fijar `uv`.

## Related

- `.specify/bugs/conector-de-calendario-sin-herramientas/` — la otra víctima
  visible de la deriva (`composio` 0.28).
