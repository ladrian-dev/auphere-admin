"""Routing contract of the outbound dispatcher: which column on a pending
``messages`` row decides which adapter method sends it.

This is the seam where a whole class of silent bugs lives. The row is
self-contained by design — the dispatcher never re-reads the tool call that
produced it — so a producer that forgets to set the routing column does not
fail loudly: the row simply falls through to ``send_text`` and Cloud API
receives a human-readable preview string as the message body.

That is exactly what ``notification.send_template`` did before this suite
existed: it wrote ``content="[template:x] nombre='Ana'"`` and left
``template_payload`` NULL, so the customer would have received that literal
(inside the 24h window) or Meta would have rejected it with 131047 (outside).
Every producer of template rows — ``services/broadcasts``,
``services/direct_messages``, the cobranza reminder engine and the MCP tool —
now has a test here that pins the routing column, not just the send.
"""

from __future__ import annotations

import uuid
from typing import Any

from nexus_api.db.models import Message, MessageDirection, MessageStatus

from nexus_worker.streams.outbound import _dispatch_message


class RecordingAdapter:
    """Captures which send_* method the dispatcher chose, and with what."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        if not name.startswith("send_"):
            raise AttributeError(name)

        async def _record(**kwargs: Any) -> Any:
            self.calls.append((name, kwargs))
            return _Result()

        return _record

    @property
    def method(self) -> str:
        assert len(self.calls) == 1, f"expected exactly one send, got {self.calls}"
        return self.calls[0][0]

    @property
    def kwargs(self) -> dict[str, Any]:
        assert len(self.calls) == 1, f"expected exactly one send, got {self.calls}"
        return self.calls[0][1]


class _Result:
    provider_message_id = "wamid.TEST"
    cost_usd_estimate = None


def _pending(**overrides: Any) -> Message:
    """A pending outbound row with every routing column explicitly NULL.

    Built in memory: ``_dispatch_message`` only reads attributes, and being
    explicit about the NULLs is the point — a future column that silently
    defaults would otherwise change routing without a failing test.
    """
    row = Message(
        tenant_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        direction=MessageDirection.OUTBOUND,
        status=MessageStatus.PENDING,
        content=overrides.pop("content", "hola"),
        tool_calls=[],
    )
    for column in (
        "template_payload",
        "interactive_payload",
        "reaction_emoji",
        "reaction_target_wamid",
        "media_kind",
        "media_s3_key",
        "media_filename",
        "context_message_id",
    ):
        setattr(row, column, None)
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


async def _dispatch(msg: Message) -> RecordingAdapter:
    adapter = RecordingAdapter()
    await _dispatch_message(
        adapter=adapter,
        msg=msg,
        from_phone="+584249018017",
        recipient="584241234567",
        tenant_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
    )
    return adapter


class TestTemplateRouting:
    async def test_template_payload_routes_to_send_template(self) -> None:
        msg = _pending(
            content="[template:recordatorio_pago_vencido] cliente='Ana'",
            template_payload={
                "name": "recordatorio_pago_vencido",
                "language": "es",
                "params": {"body": {"cliente": "Ana", "monto": "120"}},
            },
        )
        adapter = await _dispatch(msg)
        assert adapter.method == "send_template"
        assert adapter.kwargs["template_name"] == "recordatorio_pago_vencido"
        assert adapter.kwargs["language"] == "es"
        assert adapter.kwargs["params"] == {"body": {"cliente": "Ana", "monto": "120"}}

    async def test_content_preview_never_reaches_the_wire_as_text(self) -> None:
        """The regression that motivated this file.

        ``content`` on a template row is an operator-panel preview. If the
        dispatcher ever sends it as a body, the customer sees the raw
        ``[template:...]`` string.
        """
        msg = _pending(
            content="[template:x] cliente='Ana'",
            template_payload={"name": "x", "language": "es", "params": {"body": {}}},
        )
        adapter = await _dispatch(msg)
        assert adapter.method != "send_text"
        assert "[template:" not in str(adapter.kwargs.get("text", ""))

    async def test_missing_language_defaults_to_es(self) -> None:
        msg = _pending(template_payload={"name": "x", "params": {"body": {}}})
        adapter = await _dispatch(msg)
        assert adapter.kwargs["language"] == "es"


class TestRoutingPrecedence:
    """Precedence is load-bearing: a row carries at most one intent, but the
    columns are independent, so the order the dispatcher checks them in is
    the only thing that makes a mixed row deterministic."""

    async def test_template_wins_over_interactive(self) -> None:
        msg = _pending(
            template_payload={"name": "x", "language": "es", "params": {}},
            interactive_payload={"body": "?", "buttons": [{"id": "a", "title": "Sí"}]},
        )
        adapter = await _dispatch(msg)
        assert adapter.method == "send_template"

    async def test_interactive_wins_over_reaction(self) -> None:
        msg = _pending(
            interactive_payload={"body": "?", "buttons": [{"id": "a", "title": "Sí"}]},
            reaction_emoji="👍",
            reaction_target_wamid="wamid.PRIOR",
        )
        adapter = await _dispatch(msg)
        assert adapter.method == "send_interactive"

    async def test_reaction_wins_over_media(self) -> None:
        msg = _pending(
            reaction_emoji="👍",
            reaction_target_wamid="wamid.PRIOR",
            media_kind="image",
            media_s3_key="tenant/x.png",
        )
        adapter = await _dispatch(msg)
        assert adapter.method == "send_reaction"

    async def test_bare_row_falls_through_to_text(self) -> None:
        adapter = await _dispatch(_pending(content="Te esperamos."))
        assert adapter.method == "send_text"
        assert adapter.kwargs["text"] == "Te esperamos."

    async def test_reaction_without_target_is_not_a_reaction(self) -> None:
        """Half a reaction is not a reaction — Cloud API needs both the emoji
        and the wamid being reacted to."""
        adapter = await _dispatch(_pending(content="hola", reaction_emoji="👍"))
        assert adapter.method == "send_text"


class TestQuotedReplies:
    async def test_context_message_id_forwarded_on_text(self) -> None:
        adapter = await _dispatch(_pending(context_message_id="wamid.QUOTED"))
        assert adapter.kwargs["context_message_id"] == "wamid.QUOTED"

    async def test_context_message_id_forwarded_on_template(self) -> None:
        msg = _pending(
            context_message_id="wamid.QUOTED",
            template_payload={"name": "x", "language": "es", "params": {}},
        )
        adapter = await _dispatch(msg)
        assert adapter.kwargs["context_message_id"] == "wamid.QUOTED"
