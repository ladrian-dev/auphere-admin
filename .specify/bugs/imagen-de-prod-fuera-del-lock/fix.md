# Bug Fix: la imagen de producción no instala lo que fija el lock

- **Slug**: imagen-de-prod-fuera-del-lock
- **Fixed**: 2026-10-22
- **Assessment**: ./assessment.md
- **Status**: applied (rama `hotfix/prod-2026-10-22`, sin desplegar)

## Summary

Las dos imágenes instalan exactamente lo que fija su `uv.lock`, con `uv` fijado
en 0.13.4, y siguen pasando el smoke de LiteLLM en el build. El techo de LiteLLM
de `develop` viaja también, para que la regla siga en pie aunque alguien vuelva
a resolver sin lock.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/pyproject.toml`, `apps/worker/pyproject.toml`, los cuatro `uv.lock` | cherry-pick de 5d54110d | `litellm<1.106` |
| `apps/api/src/nexus_api/core/litellm_smoke.py` + su test | cherry-pick de 5d54110d | llamada con herramientas a un puerto cerrado |
| `apps/api/Dockerfile` | modified | copia `uv.lock`; `uv export --locked --no-dev --no-emit-project` → `uv pip install -r` → `uv pip install --no-deps .`; `uv==0.13.4` |
| `apps/worker/Dockerfile` | modified | lo mismo con `apps/worker/uv.lock` |

## Diff Highlights

```dockerfile
COPY apps/api/uv.lock /build/apps/api/uv.lock
RUN uv export --locked --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt \
    && uv pip install --system --no-cache-dir --no-editable -r /tmp/requirements.txt \
    && uv pip install --system --no-cache-dir --no-editable --no-deps .
RUN python -m nexus_api.core.litellm_smoke
```

## Deviations from Assessment

Ninguna. Construir desde el lock va en un commit propio: si hubiera que
retirarlo, el techo de LiteLLM sigue protegiendo el P0.

## Riesgo que se acepta

El primer despliegue con este cambio **baja** en producción 123 paquetes a las
versiones del lock (entre ellos `anthropic` 2.0→0.104, `sqlalchemy` 2.1→2.0,
`composio` 0.28→0.13). Son las versiones con las que se desarrolla y con las
que CI pasa; las de producción no las había probado nadie.

## Corrección (2026-10-22, en `develop`)

El hotfix que llegó a `main` usa `uv export --frozen` y su comentario decía que
eso hacía fallar el build con un lock desfasado. No es así: `--frozen` exporta
el lock tal cual, y una dependencia nueva del `pyproject` se quedaría fuera de la
imagen sin avisar. `--locked` es el que falla. En `develop` los Dockerfile pasan
a `--locked`; a `main` llega con la siguiente release. El 22-oct los locks de
`api` y `worker` estaban al día en `main` y en `develop` (`uv lock --check`), así
que el despliegue del hotfix instaló lo correcto.

## Pendiente

- Ninguna tubería construye la imagen antes de fusionar a `main`: el primer
  build real de estos Dockerfile será el de `deploy-prod`. Ver `test.md`.
