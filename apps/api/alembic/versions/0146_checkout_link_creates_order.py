"""``woocommerce.build_checkout_link`` creates the order it links to.

The tool used to build an ``add-to-cart`` URL and let the store fill the
cart. That relied on a snippet in the store and on a session cookie, and on
floryencanto.cl the customer landed on an empty cart (owner, 2026-10-05).
Now the tool creates the pending order through the REST API, tagged as a
WhatsApp sale, and returns the store's pay-for-order URL. The catalog row
says so: it mutates, it is no longer read-only, and its schemas match.

Revision ID: 0146_checkout_link_creates_order
Revises: 0145_audit_vocab_escalated
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0146_checkout_link_creates_order"
down_revision: str | Sequence[str] | None = "0145_audit_vocab_escalated"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TOOL = "woocommerce.build_checkout_link"

NEW_DESCRIPTION = (
    "Build the payment link for what the customer confirmed: creates the order "
    "in the store (pending payment, tagged as a WhatsApp sale, with the "
    "customer's phone when known) and returns the store's own pay-for-order "
    "URL, where the customer enters their address and pays with the store's "
    "gateways. Call it once the customer confirms what they buy. Each item "
    "needs the product_id (and variation_id when the product has sizes or "
    "colours). Do not ask for the address in chat."
)
OLD_DESCRIPTION = (
    "Build the checkout link: a URL that pre-fills the cart with the given "
    "products and opens the store's checkout page, where the customer enters "
    "their name + shipping address and pays. The order is created by the "
    "checkout when they pay, tagged as a WhatsApp sale (wa=1). Use this to "
    "send the payment link after the customer confirms — do NOT create the "
    "order yourself and do NOT ask for the address in chat."
)

ITEM = {
    "type": "object",
    "properties": {
        "product_id": {"type": "integer", "minimum": 1},
        "variation_id": {"type": "integer", "minimum": 1},
        "quantity": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 1},
    },
    "required": ["product_id"],
}
NEW_INPUT = {
    "type": "object",
    "properties": {"items": {"type": "array", "minItems": 1, "maxItems": 100, "items": ITEM}},
    "required": ["items"],
}
NEW_OUTPUT = {
    "type": "object",
    "properties": {
        "url": {"type": "string"},
        "order_id": {"type": "integer"},
        "order_number": {"type": "string"},
        "total": {"type": "string"},
    },
    "required": ["url", "order_id", "order_number", "total"],
}
OLD_ITEM = {k: v for k, v in ITEM.items()}
OLD_ITEM["properties"] = {k: v for k, v in ITEM["properties"].items() if k != "variation_id"}
OLD_INPUT = {
    **NEW_INPUT,
    "properties": {"items": {**NEW_INPUT["properties"]["items"], "items": OLD_ITEM}},
}
OLD_OUTPUT = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}


def _set(description: str, inp: dict, out: dict, *, read_only: bool, effects: list[str]) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE tool_catalog SET description = :d, input_schema = CAST(:i AS jsonb), "
            "output_schema = CAST(:o AS jsonb), read_only = :ro, "
            "side_effects = CAST(:se AS varchar[]), updated_at = now() WHERE name = :n"
        ),
        {
            "d": description,
            "i": json.dumps(inp),
            "o": json.dumps(out),
            "ro": read_only,
            "se": effects,
            "n": TOOL,
        },
    )


def upgrade() -> None:
    _set(
        NEW_DESCRIPTION,
        NEW_INPUT,
        NEW_OUTPUT,
        read_only=False,
        effects=["external_api", "mutates_db"],
    )


def downgrade() -> None:
    _set(OLD_DESCRIPTION, OLD_INPUT, OLD_OUTPUT, read_only=True, effects=[])
