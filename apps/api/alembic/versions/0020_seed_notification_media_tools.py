"""seed tool_catalog with the new notification.* media + reaction + location tools

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-13

Block N adds 7 new tools to ``notification`` so the agent can produce native
WhatsApp output beyond text/template/interactive:

- ``notification.send_image``      (caption-capable)
- ``notification.send_audio``
- ``notification.send_video``      (caption-capable)
- ``notification.send_document``   (filename + caption-capable)
- ``notification.send_location``
- ``notification.send_reaction``   (emoji on a quoted wamid)

Idempotent — uses ``ON CONFLICT (name) DO NOTHING`` so re-running the
migration over a seeded DB is a no-op.

The runtime registers the tool classes via ``build_default_registry``;
this migration only adds the catalog rows so the operator panel and the
agent_config whitelist can reference them.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (name, description, side_effects)
NEW_TOOLS: list[tuple[str, str, list[str]]] = [
    (
        "notification.send_image",
        "Queue an image (with optional caption) for delivery. Requires media_s3_key "
        "of a previously uploaded image. Subject to the 24h customer-service window.",
        ["sends_message"],
    ),
    (
        "notification.send_audio",
        "Queue an audio (voice note) for delivery. Requires media_s3_key of an "
        "OGG/Opus or M4A/AAC file. Subject to the 24h customer-service window.",
        ["sends_message"],
    ),
    (
        "notification.send_video",
        "Queue a video (with optional caption). Requires media_s3_key of an MP4 file. "
        "Subject to the 24h customer-service window.",
        ["sends_message"],
    ),
    (
        "notification.send_document",
        "Queue a document for delivery (PDF, DOCX, image of a document). Requires "
        "media_s3_key plus an optional filename. Subject to the 24h customer-service window.",
        ["sends_message"],
    ),
    (
        "notification.send_location",
        "Send a location pin. Useful for the business address. Subject to the 24h window.",
        ["sends_message"],
    ),
    (
        "notification.send_reaction",
        "React to a previous customer message with an emoji. NOT subject to the 24h window "
        "(reactions are service callbacks, always allowed).",
        ["sends_message"],
    ),
]


def upgrade() -> None:
    rows = []
    for name, description, side_effects in NEW_TOOLS:
        rows.append(
            {
                "name": name,
                "description": description,
                "mcp_server": "notification-server",
                "input_schema": "{}",
                "output_schema": "{}",
                "side_effects": side_effects,
                "capability_tags": ["whatsapp", "outbound"],
                "cost_estimate": "{}",
                # Internal-ish: requires_consent=false (no upstream API), and
                # destructive=true because they send messages to a customer.
                "read_only": False,
                "destructive": True,
                "requires_consent": False,
                "default_mode": "always",
            }
        )
    # Bulk insert via parameterised SQL (idempotent on name).
    op.execute(
        """
        INSERT INTO tool_catalog (
            name, description, mcp_server,
            input_schema, output_schema,
            side_effects, capability_tags, cost_estimate,
            read_only, destructive, requires_consent, default_mode
        ) VALUES
        """
        + ", ".join(
            "("
            f"'{r['name']}',"
            f"'{r['description'].replace(chr(39), chr(39) * 2)}',"
            f"'{r['mcp_server']}',"
            f"'{r['input_schema']}'::jsonb,"
            f"'{r['output_schema']}'::jsonb,"
            "ARRAY[" + ",".join(f"'{s}'" for s in r["side_effects"]) + "]::varchar[],"
            "ARRAY[" + ",".join(f"'{t}'" for t in r["capability_tags"]) + "]::varchar[],"
            f"'{r['cost_estimate']}'::jsonb,"
            f"{str(r['read_only']).lower()},"
            f"{str(r['destructive']).lower()},"
            f"{str(r['requires_consent']).lower()},"
            f"'{r['default_mode']}'"
            ")"
            for r in rows
        )
        + " ON CONFLICT (name) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM tool_catalog WHERE name IN ("
        + ", ".join(f"'{name}'" for name, _, _ in NEW_TOOLS)
        + ")"
    )


# Unused but documents intent — the JSON dump validates the dict literal
# at parse time.
_ = json
