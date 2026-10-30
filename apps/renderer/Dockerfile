# syntax=docker/dockerfile:1.7
#
# Fallback page renderer (spec 047, requirement 59.2, research D50): FastAPI +
# Playwright + Chromium behind an in-process, address-vetting proxy. Its own
# image on purpose: Chromium never goes into the worker's (~400 MB → ~1.2 GB).
#
# Build context: apps/renderer
#   docker build -t nexus-renderer apps/renderer
#
# The base is Microsoft's Playwright image for Python, pinned by version AND
# digest (the multi-arch index of v1.64.1-noble, read from mcr.microsoft.com
# on 2026-10-29): Ubuntu 24.04, Python 3.12, Chromium's system libraries and
# the browsers for exactly this Playwright release in /ms-playwright. The
# ``playwright`` package in uv.lock must be the same release (1.64.1) or the
# browser is not found at start — bump both together; the check below fails
# the build if they drift.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble@sha256:330d401ae23c905896a0c26c66c36fc971b621519e7b11b435a8328d7bf6e031

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --no-cache-dir uv==0.13.4

# Versions come from uv.lock, not from a fresh resolution (same as the API
# and worker images). No dev extra: pytest, ruff and mypy stay out.
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv export --locked --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt \
    && uv pip install --system --no-cache-dir -r /tmp/requirements.txt \
    && uv pip install --system --no-cache-dir --no-deps . \
    && rm /tmp/requirements.txt

# The browser this Playwright release expects must be in the image.
RUN python -c "import os; from playwright.sync_api import sync_playwright; \
p = sync_playwright().start(); path = p.chromium.executable_path; p.stop(); \
assert os.path.exists(path), f'Chromium missing at {path}: playwright and the base image differ'"

# Non-root. Chromium runs without its own sandbox (Fargate grants neither
# user namespaces nor SYS_ADMIN); what contains it is the proxy, an
# unprivileged user, a task with no IAM role and a security group that only
# lets the runner in and only lets 80/443 out (docs/renderer.md).
RUN groupadd --system --gid 10001 nexus \
    && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /home/nexus \
       --shell /usr/sbin/nologin nexus
USER nexus

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --silent --fail http://127.0.0.1:8080/health || exit 1

CMD ["nexus-renderer"]
