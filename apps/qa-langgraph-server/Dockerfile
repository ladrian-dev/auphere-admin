# Dockerfile for the QA LangGraph Server (ADR-020, prod deployment).
#
# Build context: the REPO ROOT (not this directory) so the monorepo's
# editable path deps land inside the image. From the repo root:
#
#   docker build -f apps/qa-langgraph-server/Dockerfile -t nexus-qa-langgraph-server .
#
# Or via langgraph-cli (which builds + tags with the right metadata):
#
#   cd apps/qa-langgraph-server
#   langgraph build --tag nexus-qa-langgraph-server
#
# Run with persistence (production):
#
#   langgraph up \
#     --image nexus-qa-langgraph-server \
#     --postgres-uri postgresql://nexus:nexus@host.docker.internal:5433/nexus
#
# The base image is the official langchain/langgraph-api Python image.
# Pin to a minor version so a base-image patch doesn't surprise prod;
# bump the tag deliberately when LangGraph ships breaking changes.

FROM langchain/langgraph-api:3.11

# Copy the path deps that the worker / agent runtime needs, plus the
# server package itself. The directory names MUST match the relative
# paths declared in qa-langgraph-server/pyproject.toml ([tool.uv.sources]
# nexus-api = { path = "../api" }, etc.) so ``uv pip install -e`` from
# /deps/qa-langgraph-server resolves ../api → /deps/api.
ADD apps/api                    /deps/api
ADD apps/worker                 /deps/worker
ADD apps/mcp                    /deps/mcp
ADD apps/channels               /deps/channels
# ucm-schema lives outside /deps because qa-langgraph-server/pyproject
# declares ``../../packages/ucm-schema/py``: from /deps/qa-langgraph-server
# that resolves to /packages/ucm-schema/py.
ADD packages/ucm-schema/py      /packages/ucm-schema/py
ADD apps/qa-langgraph-server    /deps/qa-langgraph-server

# Install all of them as editable so import paths stay stable. We
# install the leaf deps first (they have no inter-deps), then the
# server (which pulls them via [tool.uv.sources]). The constraints
# file lives inside the base image and pins versions compatible with
# langgraph-api.
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir -c /api/constraints.txt \
        -e /packages/ucm-schema/py \
        -e /deps/channels \
        -e /deps/api \
        -e /deps/mcp \
        -e /deps/worker \
        -e /deps/qa-langgraph-server

# Tell the LangGraph runtime where to find our auth + graphs. These
# env vars match what langgraph.json declares for ``langgraph dev``.
ENV LANGGRAPH_AUTH='{"path": "/deps/qa-langgraph-server/src/qa_langgraph_server/auth.py:auth"}'
ENV LANGSERVE_GRAPHS='{"qa_pilot": "/deps/qa-langgraph-server/src/qa_langgraph_server/graph.py:qa_pilot"}'

# LiteLLM workaround: forces the local model-cost JSON so cold starts
# don't make a sync GitHub HTTP call (blocking-call error in 0.8.x).
# Same workaround as the local .env.
ENV LITELLM_LOCAL_MODEL_COST_MAP=True

# Re-install langgraph-api at the end so user editable deps can't
# clobber it on accident. Same pattern as the auto-generated
# Dockerfile.
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license \
    && touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir --no-deps -e /api

# Strip build tools from the final image (smaller, smaller attack surface).
RUN pip uninstall -y pip setuptools wheel || true
RUN rm -rf /usr/local/lib/python*/site-packages/pip* /usr/local/lib/python*/site-packages/setuptools* /usr/local/lib/python*/site-packages/wheel* \
    && find /usr/local/bin -name "pip*" -delete || true
RUN uv pip uninstall --system pip setuptools wheel || true \
    && rm -f /usr/bin/uv /usr/bin/uvx

WORKDIR /deps/qa-langgraph-server
