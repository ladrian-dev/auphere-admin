# Multi-package monorepo image — context MUST be the project root
# (``docker-compose.yml`` sets ``context: .`` and
# ``dockerfile: apps/api/Dockerfile``).
#
# Block F made ``apps/api`` depend on ``apps/channels`` for the YCloud
# adapter. The image now copies the dependent packages and lets uv
# resolve the path sources declared in ``apps/api/pyproject.toml``.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --no-cache-dir uv

# Copy each package's pyproject + src so uv can resolve the editable path
# sources. Dependency order: nexus-channels first (no api-internal path
# deps of its own besides nexus-api), then nexus-api.
COPY apps/channels/pyproject.toml /app/apps/channels/pyproject.toml
COPY apps/channels/src /app/apps/channels/src

COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml
COPY apps/api/src /app/apps/api/src
COPY apps/api/alembic.ini /app/apps/api/alembic.ini
COPY apps/api/alembic /app/apps/api/alembic

WORKDIR /app/apps/api
RUN uv pip install --system .

ENV PYTHONPATH=/app/apps/api/src:/app/apps/channels/src

EXPOSE 8000

CMD ["uvicorn", "nexus_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
