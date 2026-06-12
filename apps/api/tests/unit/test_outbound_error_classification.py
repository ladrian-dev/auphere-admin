"""Block N — outbound dispatcher Meta error code classification.

Verifies that a MetaAPIError carrying a Meta error code (either the
structured ``.code`` attribute or a raw JSON ``.body`` such as
``{"error":{"code":131047,...}}``) is parsed correctly and that the
NO_RETRY_CODES / prefix logic identifies the right family. The actual
dispatcher loop is integration-tested elsewhere; here we only exercise
the pure helper.
"""

from __future__ import annotations

from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from nexus_worker.streams.outbound import (
    _NO_RETRY_CODES,
    _NO_RETRY_PREFIXES,
    _extract_meta_code,
)


def _err_with_body(code: int, http: int = 400) -> MetaAPIError:
    body = f'{{"error":{{"code":{code},"title":"x","detail":"y"}}}}'
    return MetaAPIError("bad request", status_code=http, body=body)


def test_extract_meta_code_prefers_structured_code() -> None:
    err = MetaAPIError("bad request", status_code=400, code=131047)
    assert _extract_meta_code(err) == "131047"


def test_extract_meta_code_handles_nested_error_object() -> None:
    assert _extract_meta_code(_err_with_body(131047)) == "131047"
    assert _extract_meta_code(_err_with_body(132012)) == "132012"


def test_extract_meta_code_handles_flat_shape() -> None:
    err = MetaAPIError("x", status_code=400, body='{"error_code":100}')
    assert _extract_meta_code(err) == "100"


def test_extract_meta_code_returns_empty_on_no_body() -> None:
    err = MetaAPIError("transport error", status_code=0)
    assert _extract_meta_code(err) == ""


def test_extract_meta_code_returns_empty_on_invalid_json() -> None:
    err = MetaAPIError("x", status_code=500, body="<html>upstream broken</html>")
    assert _extract_meta_code(err) == ""


def test_recipient_unable_is_no_retry() -> None:
    assert "131026" in _NO_RETRY_CODES


def test_outside_window_is_no_retry() -> None:
    assert "131047" in _NO_RETRY_CODES


def test_template_family_prefix_no_retry() -> None:
    code = "132099"
    assert any(code.startswith(p) for p in _NO_RETRY_PREFIXES)


def test_500_is_not_in_no_retry_codes() -> None:
    # 500 is retryable — the burst tracker uses it for storms.
    assert "500" not in _NO_RETRY_CODES
