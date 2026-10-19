"""Spec 035: TikTok is a channel, so its OAuth callback returns to Canales."""

from __future__ import annotations

import uuid

from nexus_api.api.admin.tiktok_authorize import _redirect_to_panel
from nexus_api.config import get_settings


def test_callback_lands_on_the_clients_channels() -> None:
    tenant_id = uuid.uuid4()
    base = get_settings().admin_panel_base_url.rstrip("/")
    res = _redirect_to_panel(tenant_id=tenant_id, status_key="connected")
    assert res.status_code == 303
    assert res.headers["location"] == f"{base}/tenants/{tenant_id}/channels?tiktok=connected"


def test_callback_without_a_client_lands_on_the_global_channels() -> None:
    base = get_settings().admin_panel_base_url.rstrip("/")
    res = _redirect_to_panel(tenant_id=None, status_key="state_expired")
    assert res.headers["location"] == f"{base}/channels?tiktok=state_expired"
