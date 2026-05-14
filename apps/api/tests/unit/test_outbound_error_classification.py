"""Block N — outbound dispatcher Meta error code classification.

Verifies that a YCloudAPIError carrying a Meta error code in the body
(``{"error":{"code":131047,...}}``) is parsed correctly and that the
NO_RETRY_CODES / prefix logic identifies the right family. The actual
dispatcher loop is integration-tested elsewhere; here we only exercise
the pure helper.
"""

from __future__ import annotations

from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError
from nexus_worker.streams.outbound import (
    _NO_RETRY_CODES,
    _NO_RETRY_PREFIXES,
    _extract_meta_code,
)


def _err(code: int, http: int = 400) -> YCloudAPIError:
    body = f'{{"error":{{"code":{code},"title":"x","detail":"y"}}}}'
    return YCloudAPIError(http, "bad request", body=body)


def test_extract_meta_code_handles_nested_error_object():
    assert _extract_meta_code(_err(131047)) == "131047"
    assert _extract_meta_code(_err(132012)) == "132012"


def test_extract_meta_code_handles_flat_shape():
    err = YCloudAPIError(400, "x", body='{"error_code":100}')
    assert _extract_meta_code(err) == "100"


def test_extract_meta_code_returns_empty_on_no_body():
    err = YCloudAPIError(0, "transport error")
    assert _extract_meta_code(err) == ""


def test_extract_meta_code_returns_empty_on_invalid_json():
    err = YCloudAPIError(500, "x", body="<html>upstream broken</html>")
    assert _extract_meta_code(err) == ""


def test_recipient_unable_is_no_retry():
    assert "131026" in _NO_RETRY_CODES


def test_outside_window_is_no_retry():
    assert "131047" in _NO_RETRY_CODES


def test_template_family_prefix_no_retry():
    code = "132099"
    assert any(code.startswith(p) for p in _NO_RETRY_PREFIXES)


def test_500_is_not_in_no_retry_codes():
    # 500 is retryable — the burst tracker uses it for storms.
    assert "500" not in _NO_RETRY_CODES
