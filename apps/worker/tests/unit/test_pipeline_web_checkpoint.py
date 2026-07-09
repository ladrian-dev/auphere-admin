"""Checkpoint node: web widget outbound rows persist as SENT.

The outbound dispatcher only delivers WhatsApp rows (it parks any other
channel FAILED ``unsupported_channel``). So for ``channel_type == "web"``
the checkpoint must persist replies as ``MessageStatus.SENT`` — bypassing
the dispatcher — so the widget's poll endpoint reads them immediately.
Every other channel keeps the default ``PENDING`` so the dispatcher
delivers them.

DB-free: ``persist_outbound_message`` and the session machinery are
monkeypatched so we only assert the ``status`` the checkpoint chose.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

import pytest
from nexus_api.db.models import MessageStatus

import nexus_worker.runtime.pipeline as pipeline


@contextlib.asynccontextmanager
async def _null_ctx(*_a: Any, **_k: Any):
    yield object()


def _patch(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    recorded: list[dict[str, Any]] = []

    async def _fake_persist(_session: Any, **kwargs: Any) -> Any:
        recorded.append(kwargs)
        return object()

    monkeypatch.setattr(pipeline, "persist_outbound_message", _fake_persist)
    monkeypatch.setattr(pipeline, "get_sessionmaker", lambda: lambda: _null_ctx())
    monkeypatch.setattr(pipeline, "tenant_scoped_session", lambda *a, **k: _null_ctx())
    return recorded


def _state(channel_type: str, *, interactive: dict[str, Any] | None = None) -> dict[str, Any]:
    st: dict[str, Any] = {
        "tenant_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "response": "Tenemos la *Walker Ultra Hold* a *$19.990*.",
        "channel_type": channel_type,
    }
    if interactive is not None:
        st["interactive_payload"] = interactive
    return st


@pytest.mark.asyncio
async def test_web_channel_persists_outbound_as_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _patch(monkeypatch)
    checkpoint = pipeline.make_checkpoint_node()
    await checkpoint(_state("web"))
    assert len(recorded) == 1
    assert recorded[0]["status"] == MessageStatus.SENT


@pytest.mark.asyncio
async def test_whatsapp_channel_keeps_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _patch(monkeypatch)
    checkpoint = pipeline.make_checkpoint_node()
    await checkpoint(_state("whatsapp"))
    assert len(recorded) == 1
    assert recorded[0]["status"] == MessageStatus.PENDING


@pytest.mark.asyncio
async def test_missing_channel_type_defaults_to_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _patch(monkeypatch)
    st = _state("web")
    del st["channel_type"]  # legacy callers that predate channel_type
    checkpoint = pipeline.make_checkpoint_node()
    await checkpoint(st)
    assert recorded[0]["status"] == MessageStatus.PENDING


@pytest.mark.asyncio
async def test_web_interactive_row_also_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _patch(monkeypatch)
    checkpoint = pipeline.make_checkpoint_node()
    await checkpoint(
        _state("web", interactive={"body": "¿Confirmas?", "buttons": [{"id": "y", "title": "Sí"}]})
    )
    # Text row + interactive row, both SENT on the web channel.
    assert len(recorded) == 2
    assert all(r["status"] == MessageStatus.SENT for r in recorded)
