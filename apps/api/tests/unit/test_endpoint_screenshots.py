"""Tests for the ``/admin/screenshots/:tenant_id/:audit_id`` proxy."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from nexus_api.config import get_settings
from nexus_api.db.models import AuditLog

pytestmark = pytest.mark.asyncio


def _bearer() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().admin_token}"}


async def _seed_audit(
    db_session,
    *,
    tenant_id: uuid.UUID,
    after_json: dict,
) -> uuid.UUID:
    audit = AuditLog(
        tenant_id=tenant_id,
        actor="system:test",
        action="integration.agendapro.bootstrap",
        target=f"tenant:{tenant_id}",
        before_json=None,
        after_json=after_json,
    )
    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(audit)
        await db_session.flush()
        await db_session.refresh(audit)
    return audit.id


async def test_returns_404_when_audit_row_missing(client, seed_tenants):
    tid = seed_tenants["a"]
    audit_id = uuid.uuid4()
    r = await client.get(f"/admin/screenshots/{tid}/{audit_id}", headers=_bearer())
    assert r.status_code == 404
    assert r.headers.get("X-Screenshot-Backend") == "audit_row_not_found_under_tenant"


async def test_returns_404_when_no_screenshot_recorded(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    audit_id = await _seed_audit(db_session, tenant_id=tid, after_json={"context_id": "xyz"})
    r = await client.get(f"/admin/screenshots/{tid}/{audit_id}", headers=_bearer())
    assert r.status_code == 404
    assert r.headers.get("X-Screenshot-Backend") == "no_screenshot_recorded"


async def test_returns_404_when_local_file_missing(
    client, db_session, seed_tenants, tmp_path, monkeypatch
):
    tid = seed_tenants["a"]
    monkeypatch.setenv("NEXUS_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    audit_id = await _seed_audit(
        db_session,
        tenant_id=tid,
        after_json={"screenshot_url": f"file://{tmp_path}/missing.png"},
    )
    r = await client.get(f"/admin/screenshots/{tid}/{audit_id}", headers=_bearer())
    assert r.status_code == 404
    assert r.headers.get("X-Screenshot-Backend") == "local_disk_file_missing"


async def test_serves_local_file_under_root(
    client, db_session, seed_tenants, tmp_path, monkeypatch
):
    tid = seed_tenants["a"]
    monkeypatch.setenv("NEXUS_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    png_path = tmp_path / "ok.png"
    fake_png = b"\x89PNG\r\n\x1a\nfake-bytes"
    png_path.write_bytes(fake_png)

    audit_id = await _seed_audit(
        db_session,
        tenant_id=tid,
        after_json={"screenshot_url": f"file://{png_path}"},
    )
    r = await client.get(f"/admin/screenshots/{tid}/{audit_id}", headers=_bearer())
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers.get("X-Screenshot-Backend") == "local-disk"
    assert r.content == fake_png


async def test_rejects_path_traversal_outside_root(
    client, db_session, seed_tenants, tmp_path, monkeypatch
):
    """``file:///etc/passwd`` must NOT escape the configured root."""
    tid = seed_tenants["a"]
    monkeypatch.setenv("NEXUS_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    audit_id = await _seed_audit(
        db_session,
        tenant_id=tid,
        after_json={"screenshot_url": "file:///etc/passwd"},
    )
    r = await client.get(f"/admin/screenshots/{tid}/{audit_id}", headers=_bearer())
    assert r.status_code == 404
    assert r.headers.get("X-Screenshot-Backend") == "local_disk_path_invalid"


async def test_redirects_when_https_url(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    audit_id = await _seed_audit(
        db_session,
        tenant_id=tid,
        after_json={"screenshot_url": "https://example.com/signed.png"},
    )
    r = await client.get(
        f"/admin/screenshots/{tid}/{audit_id}",
        headers=_bearer(),
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "https://example.com/signed.png"


async def test_rejects_unknown_scheme(client, db_session, seed_tenants):
    tid = seed_tenants["a"]
    audit_id = await _seed_audit(
        db_session,
        tenant_id=tid,
        after_json={"screenshot_url": "ftp://example.com/x.png"},
    )
    r = await client.get(f"/admin/screenshots/{tid}/{audit_id}", headers=_bearer())
    assert r.status_code == 404
    assert r.headers.get("X-Screenshot-Backend") == "unknown_scheme"


async def test_isolates_across_tenants(client, db_session, seed_tenants, tmp_path, monkeypatch):
    """Audit row of tenant A cannot be read by passing tenant B in the path."""
    tid_a = seed_tenants["a"]
    tid_b = seed_tenants["b"]
    monkeypatch.setenv("NEXUS_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    png_path = tmp_path / "leak.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    audit_id = await _seed_audit(
        db_session,
        tenant_id=tid_a,
        after_json={"screenshot_url": f"file://{png_path}"},
    )

    # tenant_a path → ok
    r_ok = await client.get(f"/admin/screenshots/{tid_a}/{audit_id}", headers=_bearer())
    assert r_ok.status_code == 200

    # tenant_b path → 404 (RLS filter on the SELECT means no row)
    r_blocked = await client.get(f"/admin/screenshots/{tid_b}/{audit_id}", headers=_bearer())
    assert r_blocked.status_code == 404
    assert r_blocked.headers.get("X-Screenshot-Backend") == "audit_row_not_found_under_tenant"


async def test_requires_bearer(client, seed_tenants):
    tid = seed_tenants["a"]
    audit_id = uuid.uuid4()
    r = await client.get(f"/admin/screenshots/{tid}/{audit_id}")
    assert r.status_code == 401
