"""The signup and the webhook must derive the SAME channel identifier.

Regression for ``channel.unresolved_event``: signup stored the Graph API's
spaced ``display_phone_number`` ("+34 672 13 83 67") while the webhook
resolved by the payload's unspaced value ("34672138367"), so the channel
was never found and the agent went silent.
"""

from __future__ import annotations

import pytest

from nexus_channels.whatsapp_meta.phone import to_e164
from nexus_channels.whatsapp_meta.signup import _normalise_e164
from nexus_channels.whatsapp_meta.webhook_adapter import _to_e164, extract_business_phone

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+34 672 13 83 67", "+34672138367"),  # Graph API (spaced)
        ("34672138367", "+34672138367"),  # webhook (unspaced, no +)
        ("+34672138367", "+34672138367"),  # already canonical
        ("+58 424-912-5716", "+584249125716"),  # dashes + spaces
        ("", None),
        ("   ", None),
    ],
)
def test_to_e164_canonical(raw: str, expected: str | None) -> None:
    assert to_e164(raw) == expected


def test_to_e164_rejects_non_str() -> None:
    assert to_e164(None) is None
    assert to_e164(1234) is None  # type: ignore[arg-type]


def test_signup_and_webhook_agree() -> None:
    """The two surfaces that never agreed before now collapse to one value."""
    signup_value = _normalise_e164("+34 672 13 83 67")  # Graph API shape
    webhook_value = _to_e164("34672138367")  # webhook payload shape
    assert signup_value == webhook_value == "+34672138367"


def test_extract_business_phone_normalises_spaced_metadata() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {"changes": [{"value": {"metadata": {"display_phone_number": "+34 672 13 83 67"}}}]}
        ],
    }
    assert extract_business_phone(payload) == "+34672138367"
