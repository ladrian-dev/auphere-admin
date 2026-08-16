"""The per-turn Composio registry view must inherit ``dry_run`` (and the
audit hook) from the base registry.

Regression for the /cso finding on the partner console playground: the
view was built with a bare ``MCPRegistry()``, so a Composio proxy in a
dry-run (QA Playground) turn would have executed the real side effect
against the client's CRM/calendar.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from nexus_mcp.registry import MCPRegistry

from nexus_worker.runtime import pipeline


class _Proxy:
    """Duck-typed proxy — the view only stores it under its name."""

    name = "crm.create_lead"
    side_effects = ("external_write",)


@pytest.mark.asyncio
async def test_composio_view_inherits_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    async def audit(name: str, args: dict[str, Any], synthetic: dict[str, Any]) -> None:
        del name, args, synthetic

    base = MCPRegistry(dry_run=True, dry_run_audit=audit)

    async def fake_load(tenant_id: uuid.UUID, *, whitelist: frozenset[str]) -> list[Any]:
        del tenant_id, whitelist
        return [object()]

    def fake_build(blueprints: list[Any]) -> list[Any]:
        del blueprints
        return [_Proxy()]

    import nexus_mcp.servers.composio_proxy as cp

    monkeypatch.setattr(cp, "load_blueprints_for_tenant", fake_load)
    monkeypatch.setattr(cp, "build_composio_proxies_for_tenant", fake_build)

    view, names = await pipeline._view_with_composio(
        registry=base, tenant_id=uuid.uuid4(), available_names=("crm.create_lead",)
    )
    assert view is not base
    assert names == ("crm.create_lead",)
    assert view.dry_run is True, "view lost dry_run — side effects would run for real"
    assert view._dry_run_audit is audit
    assert "crm.create_lead" in view.names()


@pytest.mark.asyncio
async def test_composio_view_stays_live_when_base_is_live(monkeypatch: pytest.MonkeyPatch) -> None:
    base = MCPRegistry(dry_run=False)

    async def fake_load(tenant_id: uuid.UUID, *, whitelist: frozenset[str]) -> list[Any]:
        del tenant_id, whitelist
        return [object()]

    import nexus_mcp.servers.composio_proxy as cp

    monkeypatch.setattr(cp, "load_blueprints_for_tenant", fake_load)
    monkeypatch.setattr(cp, "build_composio_proxies_for_tenant", lambda _b: [_Proxy()])
    view, _ = await pipeline._view_with_composio(
        registry=base, tenant_id=uuid.uuid4(), available_names=("crm.create_lead",)
    )
    assert view.dry_run is False
