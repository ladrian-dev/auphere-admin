# nexus-worker

Agent runtime worker. Block C scaffold.

## Responsibilities

- Consume the `nexus:inbound` Redis Stream populated by the YCloud webhook.
- Run a LangGraph 1.0 pipeline (8 nodes) per inbound message.
- Filter the global `tool_catalog` by the active `agent_config.tools` whitelist
  before any tool definition reaches the LLM (garantía 2).
- Drive a Postgres checkpointer with `thread_id = tenant:{t}:channel:{c}:user:{u}`
  (garantía 4).
- Route LLM calls through LiteLLM with batching disabled (garantía 7).
- Persist outbound `messages` rows. Real WhatsApp send lands in block F.

Reminders / cron / MCP servers ship in block D — Dramatiq enters then.

## Layout

```
src/nexus_worker/
  config.py                # WorkerSettings (extends nexus_api Settings)
  main.py                  # asyncio entry point: stream consumer
  runtime/
    thread_id.py           # canonical thread_id format
    state.py               # AgentState TypedDict for the graph
    checkpointer.py        # AsyncPostgresSaver factory
    agent_loader.py        # AgentLoader with LRU + Redis pub/sub
    llm.py                 # LiteLLM router (classify/respond/fallback)
    pipeline.py            # 8-node graph builder
    promote_subscriber.py  # invalidates AgentLoader cache on promote
  tools/
    registry.py            # name -> callable + Pydantic schemas
    booking.py / queue.py / client.py / notification.py /
    commission.py / escalate.py
  streams/
    consumer.py            # XREADGROUP loop
    publisher.py           # XADD helper used by the API webhook
  persistence/
    messages.py            # upsert customer/conversation, write Message rows
```

## Run locally

```bash
cd apps/worker
uv sync
uv run nexus-worker
```

## Tests

```bash
uv run pytest -x
```

The end-to-end runtime isolation tests live in `apps/api/tests/isolation/`
(`test_2_*_runtime.py`, `test_4_*_runtime.py`, `test_7_*_runtime.py`) and import
from this package.
