"""Errors of the Instagram and Messenger channels.

Transport errors reuse the WhatsApp hierarchy (:class:`MetaAPIError`,
:class:`TokenInvalidatedError`, …) because both speak the same Graph API
error envelope. What is specific to these channels is *what a given code
means for the business*, and that is classified here so the dispatcher and
the connection flow say the same thing.

Sources (Meta, 2026-10): Messenger Send API error codes and the Instagram
Unified Login troubleshooting page.
"""

from __future__ import annotations

from typing import Literal

from nexus_channels.whatsapp_meta.exceptions import MetaAPIError

# ``(#10) This message is sent outside of allowed window`` — subcode 2018278
# on Messenger; Instagram answers code 10 or 551 with the same meaning.
_WINDOW_SUBCODES = frozenset({2018278, 2534022})
# ``(#551) This person isn't available right now`` — the user blocked the
# business or cannot receive messages.
_UNAVAILABLE_CODES = frozenset({551})


class MetaSocialError(Exception):
    """Base for errors raised by this package that are not Graph transport."""


class MetaSocialConnectError(MetaSocialError):
    """The connection cannot finish. ``reason`` is a stable key the console
    translates into the exact step the business has to take."""

    def __init__(
        self,
        reason: Literal[
            "code_exchange_failed",
            "no_business_portfolio",
            "no_instagram_account",
            "no_page",
            "messages_disabled",
            "missing_permission",
            "page_messaging_task_missing",
            "already_connected_elsewhere",
            "subscribe_failed",
            "pending_expired",
        ],
        detail: str | None = None,
    ) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class MetaSocialWindowClosed(MetaSocialError):
    """The send is outside the window Meta allows (24 h for the agent, 7 days
    for a person, 7 days for a private reply). Terminal: never retried."""


def is_window_error(exc: BaseException) -> bool:
    return isinstance(exc, MetaAPIError) and (
        exc.subcode in _WINDOW_SUBCODES
        or (exc.code == 10 and "window" in (exc.message or "").lower())
    )


def is_recipient_unavailable(exc: BaseException) -> bool:
    return isinstance(exc, MetaAPIError) and exc.code in _UNAVAILABLE_CODES


def is_messages_disabled(exc: BaseException) -> bool:
    """``(#200)`` on an Instagram account means «Allow access to messages» is
    off in the app (Settings → Messages and story replies → Connected tools)."""
    return isinstance(exc, MetaAPIError) and exc.code == 200


def is_permission_error(exc: BaseException) -> bool:
    return isinstance(exc, MetaAPIError) and exc.code in {10, 200, 230, 298}
