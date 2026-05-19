"""Hand-maintained JSON Schema for UCM v1.0.0.

Mirror of `ts/src/json-schema.ts`. See that file for rationale.
"""

from __future__ import annotations

from typing import Any, Final

UCM_JSON_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://nexus.auphere.dev/schemas/ucm/1.0.0/ucm.json",
    "title": "UCM v1.0.0",
    "description": (
        "Universal Channel Message — channel-agnostic message format emitted by "
        "Nexus agents."
    ),
    "type": "object",
    "required": [
        "ucm_version",
        "message_id",
        "type",
        "fallback_text",
        "content",
    ],
    "properties": {
        "ucm_version": {"const": "1.0.0"},
        "message_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "type": {
            "enum": [
                "text",
                "quick_replies",
                "list",
                "cta_url",
                "media",
                "location",
                "flow",
                "composite",
            ]
        },
        "capabilities_required": {
            "type": "array",
            "items": {
                "enum": [
                    "text",
                    "text.markdown",
                    "interactive.buttons",
                    "interactive.list",
                    "interactive.cta_url",
                    "media.image",
                    "media.video",
                    "media.document",
                    "media.audio",
                    "location",
                    "flow",
                ]
            },
            "default": [],
        },
        "fallback_text": {"type": "string", "minLength": 1, "maxLength": 4096},
        "metadata": {"type": "object", "additionalProperties": True, "default": {}},
        "content": {"type": "object"},
    },
    "additionalProperties": False,
}

SUPPORTED_UCM_VERSIONS: Final[tuple[str, ...]] = ("1.0.0",)


def is_supported_ucm_version(v: Any) -> bool:
    return isinstance(v, str) and v in SUPPORTED_UCM_VERSIONS
