"""Integration tests for the ADR-021 streaming endpoints.

End-to-end through the FastAPI app:
  - POST   /qa/threads/{id}/runs       — start a streaming turn
  - GET    /qa/threads/{id}/stream     — consume SSE
  - DELETE /qa/runs/{run_id}            — cancel
  - GET    /qa/threads/{id}/messages   — hydrate history

We never run the real agent graph here — too slow, requires API keys.
Instead we monkey-patch ``qa._get_qa_pipeline`` to return a fake whose
``astream_events`` yields a deterministic synthetic event stream. The
real translator + orchestrator + DB writes still execute, so the test
covers:
  - the wire format ordering;
  - run_id → qa.runs row lifecycle;
  - RLS on the new endpoints;
  - cancel semantics;
  - history retrieval from the messages table.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, ClassVar

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


# ── helpers ──────────────────────────────────────────────────────────────────


def qa_headers(operator_id: str, admin_headers: dict[str, str]) -> dict[str, str]:
    return {**admin_headers, "X-Operator-Id": operator_id}


def _op_id() -> str:
    import secrets

    return secrets.token_urlsafe(16)


def _parse_sse(wire: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in wire.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        ev: dict[str, Any] = {}
        for line in block.split("\n"):
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            ev[k.strip()] = v.lstrip()
        if "data" in ev:
            with contextlib.suppress(json.JSONDecodeError):
                ev["data"] = json.loads(ev["data"])
        out.append(ev)
    return out


@pytest_asyncio.fixture
async def tenant_id(db_session: Any) -> uuid.UUID:
    from nexus_api.db.models import Tenant, TenantPlan

    tid = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            Tenant(id=tid, name="QA-Stream", slug=f"qas-{tid.hex[:6]}", plan=TenantPlan.PRO)
        )
    return tid


@pytest_asyncio.fixture
async def channel(db_session: Any, tenant_id: uuid.UUID) -> uuid.UUID:
    """Active channel so ``_ensure_qa_conversation`` can pick it up."""
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    ch_id = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            Channel(
                id=ch_id,
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="ycloud",
                provider_identifier="qa-stream-pn",
                status=ChannelStatus.ACTIVE,
                config={"display_phone_number": "+5491100000000"},
            )
        )
    return ch_id


# ── fake pipeline that drives translate_event through synthetic events ──────


class _FakeChunk:
    def __init__(self, msg_id: str, text: str) -> None:
        self.id = msg_id
        self.content = text
        self.additional_kwargs: dict[str, Any] = {}


class _FakeFinalMsg:
    usage_metadata: ClassVar[dict[str, Any]] = {"input_tokens": 50, "output_tokens": 20}
    response_metadata: ClassVar[dict[str, Any]] = {"model_name": "claude-sonnet-4-6-fake"}


class _FakePipeline:
    """astream_events yields a small but realistic event sequence."""

    def __init__(self, slow: bool = False) -> None:
        self.slow = slow

    async def astream_events(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
        version: str = "v2",
    ) -> AsyncIterator[dict[str, Any]]:
        # 1. Three text chunks.
        for word in ("Hola", " ", "Lee"):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": _FakeChunk("msg-1", word)},
            }
            if self.slow:
                await asyncio.sleep(0.5)
        # 2. Final chat model event with usage_metadata.
        yield {
            "event": "on_chat_model_end",
            "data": {"output": _FakeFinalMsg()},
        }
        # 3. The ucm_formatter chain end emits a UCM payload.
        yield {
            "event": "on_chain_end",
            "name": "ucm_formatter",
            "data": {
                "output": {
                    "ucm": {
                        "ucm_version": "1.0.0",
                        "message_id": "ucm-fake",
                        "type": "text",
                        "content": {"text": "Hola Lee"},
                        "fallback_text": "Hola Lee",
                        "capabilities_required": ["text"],
                    },
                    "intent": "info",
                }
            },
        }


@pytest.fixture
def patch_pipeline(monkeypatch: pytest.MonkeyPatch) -> _FakePipeline:
    """Swap the cached pipeline with a fake so tests don't hit real LLMs."""
    fake = _FakePipeline()
    monkeypatch.setattr("nexus_api.api.qa._get_qa_pipeline", lambda: fake)
    return fake


@pytest.fixture
def patch_pipeline_slow(monkeypatch: pytest.MonkeyPatch) -> _FakePipeline:
    fake = _FakePipeline(slow=True)
    monkeypatch.setattr("nexus_api.api.qa._get_qa_pipeline", lambda: fake)
    return fake


async def _create_thread(
    client: Any, admin_headers: dict[str, str], operator: str, tenant_id: uuid.UUID
) -> uuid.UUID:
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "stream-test"},
        headers=qa_headers(operator, admin_headers),
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


# ── tests ───────────────────────────────────────────────────────────────────


async def test_run_emits_full_event_sequence(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: uuid.UUID,
    channel: uuid.UUID,
    patch_pipeline: _FakePipeline,
) -> None:
    """Full happy path: start run → consume stream → assert order + final
    qa.runs row is closed as completed."""
    op = _op_id()
    thread_id = await _create_thread(client, admin_headers, op, tenant_id)

    # Start a run.
    r = await client.post(
        f"/qa/threads/{thread_id}/runs",
        json={"message": "hi"},
        headers=qa_headers(op, admin_headers),
    )
    assert r.status_code == 202, r.text
    body = r.json()
    run_id = uuid.UUID(body["run_id"])
    assert body["status"] == "running"

    # Stream and collect events.
    async with client.stream(
        "GET",
        f"/qa/threads/{thread_id}/stream",
        params={"run_id": str(run_id)},
        headers=qa_headers(op, admin_headers),
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        chunks: list[str] = []
        async for chunk in response.aiter_text():
            chunks.append(chunk)
            # Stop when we see run.completed.
            if "event: run.completed" in "".join(chunks):
                break

    parsed = _parse_sse("".join(chunks))
    names = [p["event"] for p in parsed if p.get("event") != "ping"]
    assert names[0] == "run.started"
    assert names[-1] == "run.completed"
    assert "text.delta" in names
    assert "ucm.final" in names
    assert "cost.updated" in names

    completed = next(p for p in parsed if p.get("event") == "run.completed")
    assert completed["data"]["status"] == "completed"


async def test_cancel_run_ends_with_status_cancelled(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: uuid.UUID,
    channel: uuid.UUID,
    patch_pipeline_slow: _FakePipeline,
) -> None:
    """DELETE /qa/runs/{run_id} cancels the in-flight task and the
    final SSE event reports status=cancelled."""
    op = _op_id()
    thread_id = await _create_thread(client, admin_headers, op, tenant_id)

    r = await client.post(
        f"/qa/threads/{thread_id}/runs",
        json={"message": "slow"},
        headers=qa_headers(op, admin_headers),
    )
    assert r.status_code == 202
    run_id = uuid.UUID(r.json()["run_id"])

    # Open the stream + cancel in parallel.
    cancel_task: asyncio.Task[Any] = asyncio.create_task(asyncio.sleep(0.05))

    async def do_cancel() -> Any:
        await asyncio.sleep(0.1)
        return await client.delete(
            f"/qa/runs/{run_id}",
            headers=qa_headers(op, admin_headers),
        )

    cancel_task = asyncio.create_task(do_cancel())

    async with client.stream(
        "GET",
        f"/qa/threads/{thread_id}/stream",
        params={"run_id": str(run_id)},
        headers=qa_headers(op, admin_headers),
    ) as response:
        assert response.status_code == 200
        chunks: list[str] = []
        async for chunk in response.aiter_text():
            chunks.append(chunk)
            if "event: run.completed" in "".join(chunks):
                break

    cancel_resp = await cancel_task
    assert cancel_resp.status_code == 204

    parsed = _parse_sse("".join(chunks))
    completed = next(p for p in parsed if p.get("event") == "run.completed")
    assert completed["data"]["status"] == "cancelled"


async def test_stream_404_for_run_owned_by_other_operator(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: uuid.UUID,
    channel: uuid.UUID,
    patch_pipeline: _FakePipeline,
) -> None:
    """RLS hides another operator's run — GET /stream returns 404."""
    op_a = _op_id()
    op_b = _op_id()
    thread_a = await _create_thread(client, admin_headers, op_a, tenant_id)

    r = await client.post(
        f"/qa/threads/{thread_a}/runs",
        json={"message": "alpha"},
        headers=qa_headers(op_a, admin_headers),
    )
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    # op_b tries to read op_a's stream.
    r2 = await client.get(
        f"/qa/threads/{thread_a}/stream",
        params={"run_id": run_id},
        headers=qa_headers(op_b, admin_headers),
    )
    assert r2.status_code == 404


async def test_cancel_404_for_run_owned_by_other_operator(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: uuid.UUID,
    channel: uuid.UUID,
    patch_pipeline_slow: _FakePipeline,
) -> None:
    op_a = _op_id()
    op_b = _op_id()
    thread_a = await _create_thread(client, admin_headers, op_a, tenant_id)

    r = await client.post(
        f"/qa/threads/{thread_a}/runs",
        json={"message": "x"},
        headers=qa_headers(op_a, admin_headers),
    )
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    r2 = await client.delete(
        f"/qa/runs/{run_id}",
        headers=qa_headers(op_b, admin_headers),
    )
    assert r2.status_code == 404


async def test_get_thread_messages_returns_inbound_after_run(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: uuid.UUID,
    channel: uuid.UUID,
    patch_pipeline: _FakePipeline,
) -> None:
    """After a turn, ``GET /qa/threads/{id}/messages`` returns the
    inbound row. Outbound surfaces once the graph's checkpoint node
    persists it (out of scope for this fake — but the inbound is
    enough to validate the endpoint's plumbing)."""
    op = _op_id()
    thread_id = await _create_thread(client, admin_headers, op, tenant_id)

    r = await client.post(
        f"/qa/threads/{thread_id}/runs",
        json={"message": "hola"},
        headers=qa_headers(op, admin_headers),
    )
    assert r.status_code == 202
    # Drain the stream so the run finalises.
    run_id = r.json()["run_id"]
    async with client.stream(
        "GET",
        f"/qa/threads/{thread_id}/stream",
        params={"run_id": str(run_id)},
        headers=qa_headers(op, admin_headers),
    ) as response:
        async for chunk in response.aiter_text():
            if "event: run.completed" in chunk:
                break

    r2 = await client.get(
        f"/qa/threads/{thread_id}/messages",
        headers=qa_headers(op, admin_headers),
    )
    assert r2.status_code == 200
    msgs = r2.json()
    assert any(m["direction"] == "inbound" and m["content"] == "hola" for m in msgs)


async def test_qa_runs_row_finalised_with_status_completed(
    client: Any,
    admin_headers: dict[str, str],
    tenant_id: uuid.UUID,
    channel: uuid.UUID,
    db_session: Any,
    patch_pipeline: _FakePipeline,
) -> None:
    """After draining the stream, qa.runs.status == 'completed' and
    usage tokens are stamped from the on_complete hook."""
    from sqlalchemy import text

    op = _op_id()
    thread_id = await _create_thread(client, admin_headers, op, tenant_id)
    r = await client.post(
        f"/qa/threads/{thread_id}/runs",
        json={"message": "go"},
        headers=qa_headers(op, admin_headers),
    )
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    async with client.stream(
        "GET",
        f"/qa/threads/{thread_id}/stream",
        params={"run_id": str(run_id)},
        headers=qa_headers(op, admin_headers),
    ) as response:
        async for chunk in response.aiter_text():
            if "event: run.completed" in chunk:
                break

    # Wait for the on_complete hook (it fires after the stream emits
    # run.completed but runs as a finally block — usually microseconds).
    await asyncio.sleep(0.1)

    res = await db_session.execute(
        text("SELECT status, input_tokens, output_tokens FROM qa.runs WHERE id = :id"),
        {"id": run_id},
    )
    row = res.fetchone()
    assert row is not None
    status, in_tokens, out_tokens = row
    assert status == "completed"
    # FakeFinalMsg reports input=50 / output=20.
    assert in_tokens == 50
    assert out_tokens == 20
