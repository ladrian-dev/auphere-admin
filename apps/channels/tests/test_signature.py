import pytest

from nexus_channels.whatsapp_ycloud.signature import (
    YCloudSignatureError,
    sign_ycloud_request,
    verify_ycloud_signature,
)


def test_round_trip_signs_and_verifies():
    secret = "whsec_abc"
    body = b'{"type":"whatsapp.inbound_message.received"}'
    header = sign_ycloud_request(secret, body, timestamp=1_700_000_000)
    verify_ycloud_signature(secret, body, header, now=1_700_000_005)


def test_rejects_wrong_secret():
    body = b'{"type":"x"}'
    header = sign_ycloud_request("right", body, timestamp=1_700_000_000)
    with pytest.raises(YCloudSignatureError):
        verify_ycloud_signature("wrong", body, header, now=1_700_000_005)


def test_rejects_tampered_body():
    body = b'{"type":"x"}'
    header = sign_ycloud_request("k", body, timestamp=1_700_000_000)
    with pytest.raises(YCloudSignatureError):
        verify_ycloud_signature("k", b'{"type":"y"}', header, now=1_700_000_005)


def test_rejects_old_timestamp():
    body = b"{}"
    header = sign_ycloud_request("k", body, timestamp=1_700_000_000)
    with pytest.raises(YCloudSignatureError, match="drift"):
        verify_ycloud_signature("k", body, header, tolerance_seconds=60, now=1_700_001_000)


def test_rejects_malformed_header():
    with pytest.raises(YCloudSignatureError):
        verify_ycloud_signature("k", b"{}", "not-a-header", now=0)
    with pytest.raises(YCloudSignatureError):
        verify_ycloud_signature("k", b"{}", "", now=0)


def test_rejects_non_numeric_timestamp():
    with pytest.raises(YCloudSignatureError):
        verify_ycloud_signature("k", b"{}", "t=abc,s=deadbeef", now=0)


def test_tolerates_whitespace_and_ordering():
    body = b"{}"
    sig = sign_ycloud_request("k", body, timestamp=1_700_000_000)
    ts, sig_value = sig.split(",")
    reordered = f" {sig_value} , {ts} "
    verify_ycloud_signature("k", body, reordered, now=1_700_000_005)
