"""The admin secret never reaches the audit trail, nor the partner's eyes.

``require_admin_token`` returns the bearer itself, and the channel-role
writer stored it whole as the actor of a client's row. These tests hold the
three layers of the fix: the writer, the model and the console.
"""

from __future__ import annotations

import pytest

from nexus_api.api.console.audit import _human_actor
from nexus_api.config import get_settings
from nexus_api.db.models import AuditLog


def test_the_model_turns_the_secret_into_its_short_form() -> None:
    secret = get_settings().admin_token
    row = AuditLog(tenant_id=None, actor=secret, action="x.y", target="t")
    assert row.actor == f"admin:{secret[:8]}"
    assert AuditLog(tenant_id=None, actor="console:ana@x.com", action="x", target="t").actor == (
        "console:ana@x.com"
    )


@pytest.mark.parametrize(
    "actor",
    [
        "system:connector_reconcile_cron",
        "budget_gate",
        "tiktok:oauth_callback",
        "device:7f0c",
        "a-raw-secret-that-matches-no-known-form",
    ],
)
def test_an_actor_of_no_known_form_reads_as_auphere(actor: str) -> None:
    assert _human_actor(actor) == "Auphere"


def test_people_still_read_as_people() -> None:
    assert _human_actor("console:ana@x.com") == "ana@x.com"
    uid = "0b7c1d2e-3f40-4a5b-8c6d-7e8f90a1b2c3"
    assert _human_actor(f"console:{uid}", {uid: "ana@x.com"}) == "ana@x.com"
    assert _human_actor("reviewer:+34600000000") == "+34600000000"
    assert _human_actor("admin:1a2b3c4d") == "Auphere"

