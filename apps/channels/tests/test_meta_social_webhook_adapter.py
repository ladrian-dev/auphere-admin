"""Spec 049 — parsers for ``object=instagram`` and ``object=page`` webhooks."""

from __future__ import annotations

from nexus_channels.base import InboundMessageKind
from nexus_channels.meta_social.webhook_adapter import (
    COMMENT_PREFIX,
    PROVIDER_INSTAGRAM,
    PROVIDER_MESSENGER,
    URL_MEDIA_PREFIX,
    entry_account_ids,
    iter_events,
    provider_for,
)

IG = "17841400000000001"
PAGE = "105000000000001"
IGSID = "530000000000001"


def _messaging(obj: str, account: str, item: dict) -> dict:
    return {"object": obj, "entry": [{"id": account, "time": 1730200000000, "messaging": [item]}]}


def _msg(message: dict, *, sender: str = IGSID, account: str = IG) -> dict:
    return {
        "sender": {"id": sender},
        "recipient": {"id": account},
        "timestamp": 1730200000000,
        "message": message,
    }


def test_provider_for_objects() -> None:
    assert provider_for({"object": "instagram"}) == PROVIDER_INSTAGRAM
    assert provider_for({"object": "page"}) == PROVIDER_MESSENGER
    assert provider_for({"object": "whatsapp_business_account"}) is None


def test_instagram_text_dm() -> None:
    [ev] = iter_events(
        _messaging("instagram", IG, _msg({"mid": "m_1", "text": "Hi, what time do you open?"}))
    )
    assert ev.kind == "message"
    assert ev.account_id == IG
    inbound = ev.inbound
    assert inbound is not None
    assert inbound.provider == PROVIDER_INSTAGRAM
    assert inbound.provider_identifier == IG
    assert inbound.sender_identifier == IGSID
    assert inbound.kind == InboundMessageKind.TEXT
    assert inbound.text == "Hi, what time do you open?"
    assert inbound.provider_message_id == "m_1"


def test_messenger_text_dm() -> None:
    [ev] = iter_events(
        _messaging(
            "page", PAGE, _msg({"mid": "m_2", "text": "hola"}, sender="PSID_1", account=PAGE)
        )
    )
    assert ev.inbound is not None
    assert ev.inbound.provider == PROVIDER_MESSENGER
    assert ev.inbound.sender_identifier == "PSID_1"
    assert ev.inbound.provider_identifier == PAGE


def test_echo_never_becomes_a_turn() -> None:
    [ev] = iter_events(
        _messaging(
            "instagram", IG, _msg({"mid": "m_3", "text": "our reply", "is_echo": True}, sender=IG)
        )
    )
    assert ev.kind == "echo"
    assert ev.inbound is None


def test_message_from_the_account_itself_is_ignored() -> None:
    [ev] = iter_events(_messaging("instagram", IG, _msg({"mid": "m_4", "text": "x"}, sender=IG)))
    assert ev.inbound is None


def test_image_attachment_is_a_url_reference() -> None:
    url = "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=1&signature=abc"
    [ev] = iter_events(
        _messaging(
            "instagram",
            IG,
            _msg({"mid": "m_5", "attachments": [{"type": "image", "payload": {"url": url}}]}),
        )
    )
    assert ev.inbound is not None
    assert ev.inbound.kind == InboundMessageKind.IMAGE
    assert ev.inbound.media is not None
    assert ev.inbound.media.provider_media_id == f"{URL_MEDIA_PREFIX}{url}"


def test_share_without_text_is_unsupported_not_dropped() -> None:
    [ev] = iter_events(
        _messaging(
            "instagram",
            IG,
            _msg(
                {
                    "mid": "m_6",
                    "attachments": [{"type": "ig_reel", "payload": {"reel_video_id": "1"}}],
                }
            ),
        )
    )
    assert ev.inbound is not None
    assert ev.inbound.kind == InboundMessageKind.UNSUPPORTED
    assert ev.inbound.raw_event_type == "ig_reel"


def test_quick_reply_and_postback_are_interactive() -> None:
    [qr] = iter_events(
        _messaging(
            "page",
            PAGE,
            _msg(
                {"mid": "m_7", "text": "Yes", "quick_reply": {"payload": "YES"}},
                sender="P",
                account=PAGE,
            ),
        )
    )
    assert qr.inbound is not None and qr.inbound.interactive is not None
    assert qr.inbound.interactive.payload_id == "YES"

    item = {
        "sender": {"id": "P"},
        "recipient": {"id": PAGE},
        "timestamp": 1,
        "postback": {"mid": "m_8", "title": "Book", "payload": "BOOK"},
    }
    [pb] = iter_events(_messaging("page", PAGE, item))
    assert pb.inbound is not None and pb.inbound.interactive is not None
    assert pb.inbound.interactive.payload_id == "BOOK"
    assert pb.inbound.provider_message_id == "m_8"


def test_reply_to_is_the_context() -> None:
    [ev] = iter_events(
        _messaging(
            "instagram", IG, _msg({"mid": "m_9", "text": "this one", "reply_to": {"mid": "m_1"}})
        )
    )
    assert ev.inbound is not None
    assert ev.inbound.context_message_id == "m_1"


def test_reaction_and_read() -> None:
    react = {
        "sender": {"id": IGSID},
        "recipient": {"id": IG},
        "timestamp": 5,
        "reaction": {"mid": "m_1", "action": "react", "reaction": "love", "emoji": "❤"},
    }
    [ev] = iter_events(_messaging("instagram", IG, react))
    assert ev.inbound is not None
    assert ev.inbound.kind == InboundMessageKind.REACTION
    assert ev.inbound.reaction is not None and ev.inbound.reaction.target_message_id == "m_1"

    read = {
        "sender": {"id": IGSID},
        "recipient": {"id": IG},
        "timestamp": 5,
        "read": {"mid": "m_1"},
    }
    [r] = iter_events(_messaging("instagram", IG, read))
    assert r.kind == "read" and r.inbound is None


def test_comment_is_a_turn_with_its_reference() -> None:
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": IG,
                "time": 1730200000,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "from": {"id": IGSID, "username": "maria"},
                            "media": {"id": "MEDIA_1", "media_product_type": "FEED"},
                            "id": "C_1",
                            "text": "Price?",
                        },
                    }
                ],
            }
        ],
    }
    [ev] = iter_events(payload)
    assert ev.kind == "comment"
    inbound = ev.inbound
    assert inbound is not None
    assert inbound.context_message_id == f"{COMMENT_PREFIX}C_1"
    assert inbound.provider_message_id == f"{COMMENT_PREFIX}C_1"
    assert inbound.sender_identifier == IGSID
    assert inbound.sender_name == "maria"
    assert inbound.text == "Price?"


def test_business_own_comment_never_reaches_the_agent() -> None:
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": IG,
                "changes": [
                    {
                        "field": "comments",
                        "value": {"from": {"id": IG}, "id": "C_2", "text": "Thanks!"},
                    }
                ],
            }
        ],
    }
    [ev] = iter_events(payload)
    assert ev.inbound is None
    assert ev.kind == "echo"


def test_entry_account_ids_in_order() -> None:
    payload = {"object": "page", "entry": [{"id": "A"}, {"id": "B"}, {"id": "A"}]}
    assert entry_account_ids(payload) == ["A", "B"]
