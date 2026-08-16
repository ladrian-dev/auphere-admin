"""Functional tests of the console playground (CP-16, lane B).

Pins: threads are private to the member AND to the client (A creates,
B gets 404; a second member of A gets 404 too); the run stream carries
tool/cost events plus the lane's ``budget.updated``; the monthly cap is
checked BEFORE a turn (``cap=0`` → 429 with ``Retry-After`` and a deduped
``qa.cap_reached`` notification); the budget endpoint sums finished runs
of the partner only; the console thread is always dry-run.

The agent graph is never run: ``qa._get_qa_pipeline`` is monkey-patched
with the same kind of fake the QA streaming tests use.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
import sqlalchemy as sa

from nexus_api.api.console.playground import (
    CONSOLE_OPERATOR_PREFIX,
    budget_out,
    month_window,
    retry_after_seconds,
)
from nexus_api.db.models import Partner
from nexus_api.db.models.console_notification import ConsoleNotification
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio


# ── fake pipeline ──────────────────────────────────────────────────────


class _Chunk:
    def __init__(self, msg_id: str, text: str) -> None:
        self.id = msg_id
        self.content = text
        self.additional_kwargs: dict[str, Any] = {}


class _Final:
    usage_metadata: ClassVar[dict[str, Any]] = {"input_tokens": 120, "output_tokens": 30}
    response_metadata: ClassVar[dict[str, Any]] = {"model_name": "claude-sonnet-4-6-fake"}


class _FakePipeline:
    async def astream_events(
        self, state: dict[str, Any], config: dict[str, Any], version: str = "v2"
    ) -> AsyncIterator[dict[str, Any]]:
        yield {
            "event": "on_custom_event",
            "name": "tool.call.started",
            "data": {"tool_call_id": "c1", "name": "book_appointment", "args": {}},
        }
        yield {
            "event": "on_custom_event",
            "name": "audit.blocked",
            "data": {"tool_name": "book_appointment", "tool_args": {}, "blocked_reason": "dry_run"},
        }
        yield {
            "event": "on_custom_event",
            "name": "tool.call.completed",
            "data": {"tool_call_id": "c1", "latency_ms": 3},
        }
        for word in ("Hola", " ", "socio"):
            yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk("m1", word)}}
        yield {"event": "on_chat_model_end", "data": {"output": _Final()}}


@pytest.fixture
def fake_pipeline(monkeypatch: pytest.MonkeyPatch) -> _FakePipeline:
    fake = _FakePipeline()
    monkeypatch.setattr("nexus_api.api.qa._get_qa_pipeline", lambda *, live: fake)
    return fake


def _parse_sse(wire: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in wire.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        ev: dict[str, Any] = {}
        for line in block.split("\n"):
            k, _, v = line.partition(":")
            ev[k.strip()] = v.lstrip()
        if "data" in ev:
            with contextlib.suppress(json.JSONDecodeError):
                ev["data"] = json.loads(ev["data"])
        out.append(ev)
    return out


async def _stream(client: Any, url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    async with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200, await response.aread()
        assert response.headers["content-type"].startswith("text/event-stream")
        chunks: list[str] = []
        async for chunk in response.aiter_text():
            chunks.append(chunk)
            if "event: run.completed" in "".join(chunks):
                break
    return _parse_sse("".join(chunks))


def _pg(ref: str) -> str:
    return f"/console/clients/{ref}/playground"


# ── pure helpers ───────────────────────────────────────────────────────


async def test_month_window_and_retry_after() -> None:
    w = month_window(datetime(2026, 12, 15, 10, tzinfo=UTC))
    assert w.period == "2026-12"
    assert w.start == datetime(2026, 12, 1, tzinfo=UTC)
    assert w.next_start == datetime(2027, 1, 1, tzinfo=UTC)
    assert retry_after_seconds(w, datetime(2026, 12, 31, 23, 59, tzinfo=UTC)) == 60
    b = budget_out(150, 200, w)
    assert (b.remaining, b.percent, b.exhausted) == (50, 75.0, False)
    assert budget_out(0, 0, w).exhausted is True
    assert budget_out(5, 0, w).percent == 100.0


# ── threads ────────────────────────────────────────────────────────────


async def test_threads_are_private_to_member_and_client(client, console_world, db_session) -> None:
    a, b = console_world["a"], console_world["b"]
    r = await client.post(
        f"{_pg(a['ref'])}/threads", headers=a["headers"](), json={"title": "Prueba 1"}
    )
    assert r.status_code == 201, r.text
    thread = r.json()
    assert set(thread) == {
        "id",
        "title",
        "archived_at",
        "last_run_at",
        "turn_count",
        "created_at",
        "updated_at",
    }
    tid = thread["id"]

    # Owner of A lists it; B (its own client ref) does not see it; B with
    # A's ref is the opaque client 404.
    r = await client.get(f"{_pg(a['ref'])}/threads", headers=a["headers"]())
    assert [t["id"] for t in r.json()] == [tid]
    r = await client.get(f"{_pg(b['ref'])}/threads", headers=b["headers"]())
    assert r.json() == []
    r = await client.patch(
        f"{_pg(a['ref'])}/threads/{tid}", headers=b["headers"](), json={"title": "x"}
    )
    assert r.status_code == 404
    assert r.json() == {"detail": "Unknown client reference"}

    # A second member of partner A: same client, different operator → 404.
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    r = await client.get(f"{_pg(a['ref'])}/threads", headers=builder["headers"]())
    assert r.json() == []
    r = await client.patch(
        f"{_pg(a['ref'])}/threads/{tid}", headers=builder["headers"](), json={"title": "x"}
    )
    assert r.status_code == 404
    assert r.json() == {"detail": "Unknown thread"}

    # Analyst cannot use the playground at all.
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    r = await client.get(f"{_pg(a['ref'])}/threads", headers=analyst["headers"]())
    assert r.status_code == 403

    # Rename + archive by the owner; archived threads drop from the default list.
    r = await client.patch(
        f"{_pg(a['ref'])}/threads/{tid}",
        headers=a["headers"](),
        json={"title": "Renombrado", "archived": True},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Renombrado"
    assert r.json()["archived_at"] is not None
    assert (await client.get(f"{_pg(a['ref'])}/threads", headers=a["headers"]())).json() == []
    r = await client.get(
        f"{_pg(a['ref'])}/threads", headers=a["headers"](), params={"include_archived": "true"}
    )
    assert [t["id"] for t in r.json()] == [tid]
    r = await client.patch(f"{_pg(a['ref'])}/threads/{tid}", headers=a["headers"](), json={})
    assert r.status_code == 400

    # The row is always dry-run and stamped with the console operator.
    row = (
        await db_session.execute(
            sa.text("SELECT operator_id, dry_run, tenant_id FROM qa.threads WHERE id = :id"),
            {"id": tid},
        )
    ).one()
    assert row.operator_id == f"{CONSOLE_OPERATOR_PREFIX}{a['user_id']}"
    assert row.dry_run is True
    assert row.tenant_id == a["tenant_id"]


# ── runs + stream + budget ─────────────────────────────────────────────


async def test_run_streams_tools_cost_and_budget(
    client, console_world, db_session, fake_pipeline
) -> None:
    a = console_world["a"]
    r = await client.post(f"{_pg(a['ref'])}/threads", headers=a["headers"](), json={})
    tid = r.json()["id"]

    r = await client.post(
        f"{_pg(a['ref'])}/threads/{tid}/runs", headers=a["headers"](), json={"prompt": "hola"}
    )
    assert r.status_code == 202, r.text
    assert set(r.json()) == {"run_id", "thread_id", "status"}
    run_id = r.json()["run_id"]

    events = await _stream(
        client, f"{_pg(a['ref'])}/threads/{tid}/stream?run_id={run_id}", a["headers"]()
    )
    names = [e["event"] for e in events if e.get("event") != "ping"]
    assert names[0] == "run.started"
    assert names[-1] == "run.completed"
    assert "tool.call.started" in names
    assert "audit.blocked" in names
    assert "tool.call.completed" in names
    assert "text.delta" in names
    assert "cost.updated" in names
    # The lane's own event, right before completion.
    assert names[-2] == "budget.updated"
    budget = next(e for e in events if e["event"] == "budget.updated")["data"]
    assert budget["used"] == 150
    assert budget["cap"] == 2_000_000
    assert budget["exhausted"] is False
    assert "cost_usd" not in json.dumps(events)

    # qa.runs row closed with the token numbers; the budget endpoint agrees.
    row = (
        await db_session.execute(
            sa.text("SELECT status, input_tokens, output_tokens FROM qa.runs WHERE id = :id"),
            {"id": run_id},
        )
    ).one()
    assert (row.status, row.input_tokens, row.output_tokens) == ("completed", 120, 30)
    r = await client.get("/console/playground/budget", headers=a["headers"]())
    assert r.status_code == 200
    body = r.json()
    assert body["used"] == 150
    assert body["remaining"] == 2_000_000 - 150
    assert body["period"] == month_window().period
    # Partner B's budget is untouched.
    b = console_world["b"]
    assert (await client.get("/console/playground/budget", headers=b["headers"]())).json()[
        "used"
    ] == 0

    # Thread bookkeeping + resume with since_seq skips the replayed prefix.
    r = await client.get(f"{_pg(a['ref'])}/threads", headers=a["headers"]())
    assert r.json()[0]["turn_count"] == 1
    assert r.json()[0]["last_run_at"] is not None
    tail = await _stream(
        client,
        f"{_pg(a['ref'])}/threads/{tid}/stream?run_id={run_id}&since_seq=3",
        a["headers"](),
    )
    assert all(int(e["id"]) > 3 for e in tail if e.get("event") != "ping")

    # Streams and cancels of a foreign member are opaque 404s.
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    r = await client.get(
        f"{_pg(a['ref'])}/threads/{tid}/stream?run_id={run_id}", headers=builder["headers"]()
    )
    assert r.status_code == 404
    r = await client.delete(f"{_pg(a['ref'])}/runs/{run_id}", headers=builder["headers"]())
    assert r.status_code == 404
    r = await client.delete(f"{_pg(a['ref'])}/runs/{run_id}", headers=a["headers"]())
    assert r.status_code == 204  # finished run: cancel is a no-op but allowed


async def test_cap_reached_is_429_with_retry_after_and_notification(
    client, console_world, db_session, fake_pipeline
) -> None:
    a = console_world["a"]
    await db_session.execute(
        sa.update(Partner).where(Partner.id == a["partner_id"]).values(qa_monthly_token_cap=0)
    )
    await db_session.commit()
    r = await client.post(f"{_pg(a['ref'])}/threads", headers=a["headers"](), json={})
    tid = r.json()["id"]

    r = await client.post(
        f"{_pg(a['ref'])}/threads/{tid}/runs", headers=a["headers"](), json={"prompt": "hola"}
    )
    assert r.status_code == 429, r.text
    assert "cap reached" in r.json()["detail"]
    assert "0 of 0" in r.json()["detail"]
    retry = int(r.headers["Retry-After"])
    assert 1 <= retry <= 32 * 86400

    # Nothing was written: no qa.runs row, no inbound message.
    n_runs = await db_session.scalar(
        sa.text("SELECT count(*) FROM qa.runs WHERE thread_id = :t"), {"t": tid}
    )
    assert n_runs == 0

    # One deduped notification per partner and month, even after a retry.
    r = await client.post(
        f"{_pg(a['ref'])}/threads/{tid}/runs", headers=a["headers"](), json={"prompt": "otra"}
    )
    assert r.status_code == 429
    notes = (
        (
            await db_session.execute(
                sa.select(ConsoleNotification).where(
                    ConsoleNotification.partner_id == a["partner_id"],
                    ConsoleNotification.kind == "qa.cap_reached",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notes) == 1
    assert notes[0].dedupe_key == f"partner:{a['partner_id']}:qa_cap:{month_window().period}"
    assert notes[0].payload == {"period": month_window().period}

    budget = (await client.get("/console/playground/budget", headers=a["headers"]())).json()
    assert budget["exhausted"] is True
    assert budget["percent"] == 100.0

    # A cap of exactly one turn: the run goes through, then the next is 429
    # and the stream's budget.updated already says exhausted.
    await db_session.execute(
        sa.update(Partner).where(Partner.id == a["partner_id"]).values(qa_monthly_token_cap=100)
    )
    await db_session.commit()
    r = await client.post(
        f"{_pg(a['ref'])}/threads/{tid}/runs", headers=a["headers"](), json={"prompt": "hola"}
    )
    assert r.status_code == 202, r.text
    events = await _stream(
        client, f"{_pg(a['ref'])}/threads/{tid}/stream?run_id={r.json()['run_id']}", a["headers"]()
    )
    budget_ev = next(e for e in events if e["event"] == "budget.updated")["data"]
    assert budget_ev == {
        **budget_ev,
        "used": 150,
        "cap": 100,
        "remaining": 0,
        "percent": 100.0,
        "exhausted": True,
    }
    r = await client.post(
        f"{_pg(a['ref'])}/threads/{tid}/runs", headers=a["headers"](), json={"prompt": "hola"}
    )
    assert r.status_code == 429


async def test_run_on_foreign_or_archived_thread(client, console_world, fake_pipeline) -> None:
    a = console_world["a"]
    r = await client.post(f"{_pg(a['ref'])}/threads", headers=a["headers"](), json={})
    tid = r.json()["id"]
    r = await client.post(
        f"{_pg(a['ref'])}/threads/{uuid.uuid4()}/runs", headers=a["headers"](), json={"prompt": "x"}
    )
    assert r.status_code == 404
    assert r.json() == {"detail": "Unknown thread"}
    await client.patch(
        f"{_pg(a['ref'])}/threads/{tid}", headers=a["headers"](), json={"archived": True}
    )
    r = await client.post(
        f"{_pg(a['ref'])}/threads/{tid}/runs", headers=a["headers"](), json={"prompt": "x"}
    )
    assert r.status_code == 409
    # Prompt is required and bounded.
    r = await client.post(f"{_pg(a['ref'])}/threads/{tid}/runs", headers=a["headers"](), json={})
    assert r.status_code == 422
