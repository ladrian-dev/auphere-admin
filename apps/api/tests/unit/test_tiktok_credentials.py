"""TikTok credential payload — serialisation and expiry arithmetic.

The expiry logic is what keeps the channel alive. A TikTok access token dies
in ~24 hours, so ``needs_refresh`` deciding "no" one time too many takes a
tenant's whole channel offline until someone notices.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from nexus_channels.tiktok_bm.credentials import REFRESH_LEEWAY, TikTokCredentials

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def creds(**overrides: object) -> TikTokCredentials:
    base: dict[str, object] = {
        "access_token": "act.1",
        "refresh_token": "rft.1",
        "business_id": "7123",
        "display_name": "Clínica Boreal",
        "access_token_expires_at": NOW + timedelta(hours=24),
        "refresh_token_expires_at": NOW + timedelta(days=365),
        "region": "VE",
        "webhook_config_id": "wh_1",
    }
    base.update(overrides)
    return TikTokCredentials(**base)  # type: ignore[arg-type]


def test_roundtrips_through_the_encrypted_payload_shape() -> None:
    original = creds()
    restored = TikTokCredentials.from_payload(original.to_payload())

    assert restored == original


def test_a_fresh_token_does_not_need_refreshing() -> None:
    assert creds().needs_refresh(now=NOW) is False


def test_a_token_inside_the_leeway_needs_refreshing() -> None:
    """The cron must act before the token actually dies, not after."""
    about_to_expire = creds(access_token_expires_at=NOW + REFRESH_LEEWAY - timedelta(minutes=1))

    assert about_to_expire.needs_refresh(now=NOW) is True


def test_an_expired_token_needs_refreshing() -> None:
    assert creds(access_token_expires_at=NOW - timedelta(hours=1)).needs_refresh(now=NOW) is True


def test_unknown_expiry_is_treated_as_needing_refresh() -> None:
    """TikTok always returns ``expires_in``; a missing value means the row is
    hand-written or predates a schema change, and refreshing is the safe
    reading."""
    assert creds(access_token_expires_at=None).needs_refresh(now=NOW) is True


def test_refresh_token_expiry_is_tracked_separately() -> None:
    """Only re-authorisation recovers from this — the cron cannot."""
    assert creds().refresh_token_expired(now=NOW) is False
    assert creds(refresh_token_expires_at=NOW - timedelta(days=1)).refresh_token_expired(now=NOW)


def test_naive_timestamps_from_an_old_row_are_read_as_utc() -> None:
    """A naive datetime would otherwise blow up at comparison time, far from
    the bad row that caused it."""
    payload = creds().to_payload().replace(b"+00:00", b"")
    restored = TikTokCredentials.from_payload(payload)

    assert restored.access_token_expires_at is not None
    assert restored.access_token_expires_at.tzinfo is not None
    assert restored.needs_refresh(now=NOW) is False


def test_unparseable_timestamp_degrades_to_needing_refresh() -> None:
    payload = json.dumps(
        {
            "access_token": "act.1",
            "refresh_token": "rft.1",
            "business_id": "7123",
            "access_token_expires_at": "not-a-date",
        }
    ).encode("utf-8")
    restored = TikTokCredentials.from_payload(payload)

    assert restored.access_token_expires_at is None
    assert restored.needs_refresh(now=NOW) is True


def test_optional_fields_survive_a_minimal_payload() -> None:
    minimal = TikTokCredentials(access_token="act.1", refresh_token="rft.1", business_id="7123")
    restored = TikTokCredentials.from_payload(minimal.to_payload())

    assert restored.display_name == ""
    assert restored.region is None
    assert restored.webhook_config_id is None
