"""Conectar Quédate comprueba la clave del cliente (spec 061, enmienda del 2026-11-16;
T040 y T050; requisitos 1.2-1.5, 1.8 y 6.1).

- Consola: una clave aceptada conecta. Una rechazada deja la conexión en
  ``needs_reauth`` sin activar nada. Si Quédate no responde, la conexión queda
  guardada sin comprobar. La respuesta nunca devuelve la clave.
- Panel: la misma comprobación al dar de alta por clave, y el resumen de los
  anfitriones vinculados, sin datos de nadie.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    ConnectorPartnerAccess,
    Customer,
    CustomerConnectorAccount,
    TenantCredentials,
)
from nexus_api.services.connectors import key_check

pytestmark = pytest.mark.asyncio

KEY = "9|operator-key-never-echoed"


async def _enable_for(db_session: AsyncSession, partner_id: uuid.UUID) -> None:
    await db_session.merge(
        ConnectorPartnerAccess(
            connector_slug="quedate", partner_id=partner_id, enabled=True, reason="t", set_by="t"
        )
    )
    await db_session.commit()


async def _needs_reauth(db_session: AsyncSession, tenant_id: uuid.UUID) -> bool | None:
    await db_session.commit()
    async with tenant_scoped_session(db_session, tenant_id):
        value = await db_session.scalar(
            sa.select(TenantCredentials.needs_reauth).where(
                TenantCredentials.tenant_id == tenant_id,
                TenantCredentials.integration == "quedate",
            )
        )
    await db_session.commit()
    return value


@pytest.fixture
def checker(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"outcome": "ok", "seen": [], "meta": []}

    async def fake(secrets: dict[str, Any], meta: dict[str, Any]) -> key_check.Outcome:
        state["seen"].append(secrets)
        state["meta"].append(meta)
        outcome: key_check.Outcome = state["outcome"]
        return outcome

    monkeypatch.setitem(key_check.CHECKERS, "quedate", fake)
    return state


async def test_console_connect_checks_the_operator_key(
    client: Any,
    console_world: dict[str, Any],
    db_session: AsyncSession,
    seeded_catalog: None,
    fake_composio: Any,
    checker: dict[str, Any],
) -> None:
    a = console_world["a"]
    await _enable_for(db_session, a["partner_id"])
    url = f"/console/clients/{a['ref']}/connectors/quedate/api-key"
    body = {"secrets": {"api_key": KEY}}

    ok = await client.post(url, headers=a["headers"](), json=body)
    assert ok.status_code == 201, ok.text
    assert ok.json()["status"] == "connected"
    assert ok.json()["last_sync"]["status"] == "ok"
    assert checker["seen"] == [{"api_key": KEY}]
    assert KEY not in ok.text

    checker["outcome"] = "unavailable"
    down = await client.post(url, headers=a["headers"](), json=body)
    assert down.json()["status"] == "connected"
    assert down.json()["last_sync"]["reason"] == "provider_unavailable"
    assert await _needs_reauth(db_session, a["tenant_id"]) is False

    checker["outcome"] = "rejected"
    rejected = await client.post(url, headers=a["headers"](), json=body)
    assert rejected.json()["status"] == "needs_reauth"
    assert rejected.json()["last_sync"]["reason"] == "auth_rejected"
    assert await _needs_reauth(db_session, a["tenant_id"]) is True
    assert KEY not in rejected.text

    # Corregir la clave deja la conexión como estaba: conectada y sin marca.
    checker["outcome"] = "ok"
    fixed = await client.post(url, headers=a["headers"](), json=body)
    assert fixed.json()["status"] == "connected"
    assert fixed.json()["last_sync"]["status"] == "ok"
    assert await _needs_reauth(db_session, a["tenant_id"]) is False


async def test_console_connect_passes_the_environment_to_the_check(
    client: Any,
    console_world: dict[str, Any],
    db_session: AsyncSession,
    seeded_catalog: None,
    fake_composio: Any,
    checker: dict[str, Any],
) -> None:
    """1.5: «dev» viaja sin cifrar en endpoint_meta y elige el entorno de la comprobación."""
    a = console_world["a"]
    await _enable_for(db_session, a["partner_id"])
    r = await client.post(
        f"/console/clients/{a['ref']}/connectors/quedate/api-key",
        headers=a["headers"](),
        json={"secrets": {"api_key": KEY}, "endpoint_meta": {"environment": "dev"}},
    )
    assert r.status_code == 201, r.text
    assert checker["seen"] == [{"api_key": KEY}]
    assert checker["meta"][-1].get("environment") == "dev"


async def test_admin_connect_marks_a_rejected_key(
    client: Any,
    admin_headers: Any,
    console_world: dict[str, Any],
    db_session: AsyncSession,
    seeded_catalog: None,
    fake_composio: Any,
    checker: dict[str, Any],
) -> None:
    a = console_world["a"]
    await _enable_for(db_session, a["partner_id"])
    checker["outcome"] = "rejected"
    r = await client.post(
        f"/admin/tenants/{a['tenant_id']}/connectors/quedate/connect-api-key",
        headers=admin_headers,
        json={"secrets": {"api_key": KEY}, "endpoint_meta": {"_": "admin"}},
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "needs_reauth"
    assert KEY not in r.text


async def test_the_panel_counts_linked_people_without_naming_them(
    client: Any,
    admin_headers: Any,
    console_world: dict[str, Any],
    db_session: AsyncSession,
    seeded_catalog: None,
) -> None:
    a = console_world["a"]
    url = f"/admin/tenants/{a['tenant_id']}/connectors/quedate/customer-accounts"
    empty = await client.get(url, headers=admin_headers)
    assert empty.status_code == 200, empty.text
    assert empty.json() == {
        "slug": "quedate",
        "linked": 0,
        "needs_review": 0,
        "last_linked_at": None,
    }

    await db_session.commit()
    async with tenant_scoped_session(db_session, a["tenant_id"]):
        for i, review in enumerate((False, True)):
            c = Customer(tenant_id=a["tenant_id"], identifier=f"58414000000{i}", name="María")
            db_session.add(c)
            await db_session.flush()
            db_session.add(
                CustomerConnectorAccount(
                    tenant_id=a["tenant_id"],
                    customer_id=c.id,
                    connector_slug="quedate",
                    external_user_id=f"ext-{i}",
                    needs_review=review,
                )
            )
    await db_session.commit()

    full = await client.get(url, headers=admin_headers)
    data = full.json()
    assert data["linked"] == 2 and data["needs_review"] == 1 and data["last_linked_at"]
    assert "María" not in full.text and "ext-0" not in full.text

    other = await client.get(
        f"/admin/tenants/{a['tenant_id']}/connectors/woocommerce/customer-accounts",
        headers=admin_headers,
    )
    assert other.status_code == 404
    assert other.json()["detail"] == "customer_accounts_not_supported"
