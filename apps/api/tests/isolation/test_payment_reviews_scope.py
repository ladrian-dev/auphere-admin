"""Spec 025 · T-ISO: a payment review belongs to one business.

Reviews and notices are RLS-scoped; a reviewer's tap is resolved under the
tenant that owns the business number it arrived on, so a token from another
business resolves nothing — even when the same phone reviews for both.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import PaymentReview, PaymentReviewNotice
from nexus_api.services.payment_reviews import button_id, resolve_tap
from tests.unit.test_webhook_payment_review_tap import _seed_review

pytestmark = pytest.mark.asyncio


async def test_b_cannot_see_nor_resolve_a_review_of_a(db_session, seed_tenants) -> None:
    a, b = seed_tenants["a"], seed_tenants["b"]
    token = await _seed_review(db_session, a)

    async with tenant_scoped_session(db_session, b):
        assert (await db_session.scalars(sa.select(PaymentReview))).all() == []
        assert (await db_session.scalars(sa.select(PaymentReviewNotice))).all() == []
        # Same reviewer phone, but the tap arrived on B's number.
        out = await resolve_tap(db_session, payload_id=button_id(token, "ok"), sender="56991280655")
    assert out.handled and not out.resolved

    async with tenant_scoped_session(db_session, a):
        status = (await db_session.scalars(sa.select(PaymentReview.status))).one()
    assert status == "pending"
