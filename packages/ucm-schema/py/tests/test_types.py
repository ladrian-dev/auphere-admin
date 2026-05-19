"""Shape-level UCM parsing — every fixture round-trips."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ucm_schema import (
    UCM_TYPES,
    UCM_VERSION,
    is_supported_ucm_version,
    parse_ucm,
)


@pytest.mark.parametrize("key", [
    "text_plain", "text_markdown", "quick_replies_3", "quick_replies_5",
    "list_small", "cta_url", "media_image", "location", "flow", "composite",
])
def test_valid_fixtures_parse(valid_fixtures, key):
    ucm = parse_ucm(valid_fixtures[key])
    assert ucm.ucm_version == UCM_VERSION
    assert ucm.type in UCM_TYPES


def test_composite_recursion(valid_fixtures):
    ucm = parse_ucm(valid_fixtures["composite"])
    assert ucm.type == "composite"
    assert len(ucm.content.children) == 2
    assert ucm.content.children[0].type == "text"
    assert ucm.content.children[1].type == "quick_replies"


@pytest.mark.parametrize("key", [
    "wrong_version", "missing_fallback", "empty_buttons", "bad_lat",
    "bad_url", "unknown_type",
])
def test_invalid_fixtures_reject(invalid_fixtures, key):
    with pytest.raises(ValidationError):
        parse_ucm(invalid_fixtures[key])


def test_supported_versions():
    assert is_supported_ucm_version("1.0.0")
    assert not is_supported_ucm_version("0.9.0")
    assert not is_supported_ucm_version(None)
    assert not is_supported_ucm_version("2.0.0")
