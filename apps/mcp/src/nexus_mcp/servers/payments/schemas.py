"""Schemas for ``payments.request_review`` (spec 025)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel

_SHORT = 120


class RequestPaymentReviewInput(InputModel):
    conversation_id: uuid.UUID = Field(
        description="UUID of the live conversation with the paying customer.",
    )
    method: Literal["transfer", "link"] = Field(
        description=(
            "'transfer' when the customer sent a bank-transfer receipt; 'link' when "
            "they say they paid through the store checkout link."
        ),
    )
    product: str | None = Field(default=None, max_length=_SHORT, description="What they bought.")
    modality: str | None = Field(
        default=None, max_length=_SHORT, description="Delivery or store pickup, as agreed."
    )
    place: str | None = Field(
        default=None, max_length=_SHORT, description="Delivery comuna, or the pickup place."
    )
    date: str | None = Field(
        default=None, max_length=_SHORT, description="Delivery or pickup date."
    )
    slot: str | None = Field(
        default=None, max_length=_SHORT, description="Delivery range or pickup time."
    )
    total: str | None = Field(default=None, max_length=_SHORT, description="Total to pay, as told.")
    customer_name: str | None = Field(default=None, max_length=_SHORT)
    order_id: str | None = Field(
        default=None,
        max_length=40,
        description="Store order number (only for 'link', from woocommerce.list_orders).",
    )
    order_status: str | None = Field(
        default=None,
        max_length=40,
        description="Store order status as read (only for 'link'), e.g. 'processing'.",
    )


class RequestPaymentReviewOutput(OutputModel):
    review_id: uuid.UUID
    status: Literal["pending", "informed"]
    notified: int = Field(description="Reviewers the notice was queued for.")
    unreachable: int = Field(
        description="Reviewers that could not be reached (their 24h window is closed)."
    )
    already_pending: bool = Field(
        description="True when a review was already open: the new receipt was added to it."
    )
    message_to_customer: str = Field(
        description="What to tell the customer now. Never mention the reviewers."
    )
