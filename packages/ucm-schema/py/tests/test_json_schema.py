from __future__ import annotations

from ucm_schema import SUPPORTED_UCM_VERSIONS, UCM_JSON_SCHEMA


def test_json_schema_is_object():
    assert UCM_JSON_SCHEMA["type"] == "object"
    assert "ucm_version" in UCM_JSON_SCHEMA["properties"]


def test_supported_versions_includes_current():
    assert "1.0.0" in SUPPORTED_UCM_VERSIONS


def test_json_schema_has_all_types_in_enum():
    enum = UCM_JSON_SCHEMA["properties"]["type"]["enum"]
    assert set(enum) == {
        "text", "quick_replies", "list", "cta_url",
        "media", "location", "flow", "composite",
    }
