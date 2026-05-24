"""Schema-level tests for ``response.send_interactive``.

The tool's runtime behaviour (24h-window check, registry dispatch) is
covered by the existing notification tool test suite. These tests
focus on the validator: exactly-one-component rule, button count
limits, and the ``list`` JSON-alias the LLM emits.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from nexus_mcp.servers.notification.schemas import (
    InteractiveButton,
    InteractiveCtaUrl,
    InteractiveList,
    InteractiveListRow,
    SendInteractiveInput,
)


def _conv_id() -> uuid.UUID:
    return uuid.UUID("11111111-1111-4111-8111-111111111111")


class TestExactlyOneComponent:
    def test_no_component_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            SendInteractiveInput(conversation_id=_conv_id(), body="hola")
        assert "EXACTLY ONE" in str(exc.value)

    def test_two_components_is_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            SendInteractiveInput(
                conversation_id=_conv_id(),
                body="hola",
                buttons=[InteractiveButton(id="a", title="Sí")],
                cta_url=InteractiveCtaUrl(text="Ir", url="https://x.com"),
            )
        assert "EXACTLY ONE" in str(exc.value)

    def test_buttons_alone_is_accepted(self) -> None:
        m = SendInteractiveInput(
            conversation_id=_conv_id(),
            body="hola",
            buttons=[
                InteractiveButton(id="a", title="Sí"),
                InteractiveButton(id="b", title="No"),
            ],
        )
        assert m.buttons is not None
        assert len(m.buttons) == 2

    def test_list_alone_is_accepted_via_python_attr(self) -> None:
        m = SendInteractiveInput(
            conversation_id=_conv_id(),
            body="elige",
            list_block=InteractiveList(
                button="Ver opciones",
                items=[InteractiveListRow(id="x", title="Uno")],
            ),
        )
        assert m.list_block is not None
        assert m.list_block.items[0].title == "Uno"

    def test_list_alone_is_accepted_via_json_alias(self) -> None:
        """The LLM-facing JSON key is ``list`` (the SKILL.md docs the
        flat shape). Pydantic accepts the alias because the model sets
        ``populate_by_name``; the Python attribute remains
        ``list_block`` to avoid the ``list``-builtin collision in the
        class body."""
        m = SendInteractiveInput.model_validate(
            {
                "conversation_id": str(_conv_id()),
                "body": "elige",
                "list": {
                    "button": "Ver",
                    "items": [{"id": "x", "title": "Uno"}],
                },
            }
        )
        assert m.list_block is not None

    def test_cta_url_alone_is_accepted(self) -> None:
        m = SendInteractiveInput(
            conversation_id=_conv_id(),
            body="pagas aquí",
            cta_url=InteractiveCtaUrl(text="Pagar", url="https://x.com/c"),
        )
        assert m.cta_url is not None


class TestButtonLimits:
    def test_4_buttons_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            SendInteractiveInput(
                conversation_id=_conv_id(),
                body="?",
                buttons=[
                    InteractiveButton(id=f"b{i}", title=f"t{i}")
                    for i in range(4)
                ],
            )
        assert "between 1 and 3" in str(exc.value)

    def test_button_title_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InteractiveButton(id="x", title="x" * 21)

    def test_3_buttons_accepted(self) -> None:
        m = SendInteractiveInput(
            conversation_id=_conv_id(),
            body="?",
            buttons=[
                InteractiveButton(id=f"b{i}", title=f"t{i}")
                for i in range(3)
            ],
        )
        assert len(m.buttons or []) == 3


class TestListLimits:
    def test_11_items_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InteractiveList(
                button="Ver",
                items=[
                    InteractiveListRow(id=f"r{i}", title=f"t{i}")
                    for i in range(11)
                ],
            )

    def test_row_title_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InteractiveListRow(id="x", title="x" * 25)


class TestBodyLimits:
    def test_body_over_1024_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SendInteractiveInput(
                conversation_id=_conv_id(),
                body="x" * 1025,
                buttons=[InteractiveButton(id="a", title="t")],
            )
