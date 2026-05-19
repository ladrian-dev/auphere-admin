# qa-langgraph-server

LangGraph Server self-hosted for the Nexus QA Playground ([ADR-020](../../../../Work/Auphere/nexus/decisions/ADR-020-qa-playground-ucm-multichannel.md)).

Serves the production agent graph in **dry_run mode** so an Auphere
operator can chat with a tenant's agent without triggering real side
effects (no real bookings, no real WhatsApp sends, no real external API
calls). Every intercepted dispatch is persisted to
[`qa.side_effect_audit`](../api/alembic/versions/0025_qa_schema.py) for
the operator to inspect.

The frontend Playground UI (Fase 5) talks to this server through
`@assistant-ui/react-langgraph` (already validated by the Fase 0 spike).

## What's "QA mode"

1. **`MCPRegistry`** is constructed with `dry_run=True`. Any tool with a
   non-empty `side_effects` declaration is intercepted: the agent
   receives a synthetic envelope and a row lands in
   `qa.side_effect_audit`. Read-only tools still execute.
2. **`ucm_formatter`** is forced ON. Every turn produces a UCM v1.0.0
   payload in `state["ucm"]` so the frontend can render across channels.
3. **Auth** validates the same `Authorization: Bearer <admin_token>` +
   `X-Operator-Id: <uuid>` combination the `/qa/*` HTTP endpoints
   accept (see `core/qa_security.py` in the API package).

## Run locally

```bash
cd apps/qa-langgraph-server
uv venv --python 3.11 && uv pip install -e ".[dev]"
cp .env.example .env   # adjust NEXUS_DATABASE_URL etc.
.venv/bin/langgraph dev --port 2024 --no-browser
```

Sanity-check the assistant is registered:

```bash
curl -s http://localhost:2024/assistants/search \
  -H "Authorization: Bearer ${NEXUS_ADMIN_TOKEN}" \
  -H "X-Operator-Id: $(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{"limit": 10}' | jq
```

## What's NOT here (yet)

This package is the **runtime entrypoint** only. The Fase 3 PR closes
the lib-level integration (audit writer, build_qa_pipeline,
contextvars). The following are punted to a deployment-focused session:

- **Dockerfile** for Railway / Cloud Run deploys.
- **Healthchecks** + readiness probes.
- **End-to-end test** that spins up the server in a subprocess and
  drives it from a `@langchain/langgraph-sdk` client.
- **Wiring `qa.threads.external_id`** to the LangGraph thread id at
  POST /qa/threads time (so the Playground UI can resume runs).

## Reference

- ADR-020: design + decisions.
- Spike (Fase 0): `/Users/lmatos/Workspace/qa-spike/` — same wire
  protocol, simpler graph.
- `apps/worker/.../runtime/qa_pipeline.py`: the builder this server
  imports.
- `apps/worker/.../runtime/qa_audit.py`: the audit writer the dry_run
  callback uses.
