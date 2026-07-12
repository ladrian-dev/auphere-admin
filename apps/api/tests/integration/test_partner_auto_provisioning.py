"""Partner auto-provisioning + embed signup (ADR-028 Fase 2a/2b).

End-to-end over the public surfaces with the real DB and a respx-mocked
Graph API:

1. ``POST /v1/partners/clients`` with a blueprint partner leaves a
   PROMOTED agent_config (seeded from ``default_seed_template``) and a
   connected ``api_key`` connector behind — not just a bare tenant.
2. Re-provisioning never re-seeds the agent (idempotent) but rotates
   connector credentials.
3. ``POST /v1/embed/whatsapp/signup`` completes Embedded Signup from a
   widget JWT and flips the tenant PROVISIONING → ACTIVE when the
   partner has ``auto_activate`` and a promoted agent exists.
4. ``GET /admin/partners/{id}/usage`` aggregates the per-client rows the
   billing view needs.
"""

from __future__ import annotations

import uuid

import pytest
import respx
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL

from nexus_api.core.embed_jwt import mint_widget_token
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    EmbedAuditLog,
    Partner,
    PartnerApiKey,
    PartnerTenant,
    TenantConnector,
    TenantCredentials,
    TenantStatus,
)
from nexus_api.db.models import Tenant as TenantModel

pytestmark = pytest.mark.asyncio

SEED = "cobranza_v1"
CONNECTOR = "amigable_cobro"

# Tools the cobranza_v1 seed requires. The per-test DB cleanup deletes
# connector-linked tool_catalog rows, so each test re-seeds them (the
# connector row itself comes from apply_seeds).
_BILLING_TOOLS = (
    "billing.get_debtor_by_phone",
    "billing.list_overdue",
    "billing.get_account",
    "billing.register_payment",
    "billing.update_status",
    "billing.apply_discount",
    "billing.create_account",
    "billing.update_account",
)


@pytest.fixture(autouse=True)
async def amigable_catalog(db_session) -> None:
    """Connector row (from YAML seeds) + billing.* tool_catalog rows —
    what migrations 0045/0046 provide in a real deploy."""
    from nexus_api.db.models import Connector, ToolCatalog, ToolStatus
    from nexus_api.services.connectors.seed_loader import load_all_seeds
    from nexus_api.services.connectors.seed_runner import apply_seeds

    await apply_seeds(db_session, load_all_seeds())
    connector = await db_session.scalar(sa.select(Connector).where(Connector.slug == CONNECTOR))
    assert connector is not None, "amigable_cobro seed YAML missing"
    existing = set(
        (
            await db_session.scalars(
                sa.select(ToolCatalog.name).where(ToolCatalog.name.in_(_BILLING_TOOLS))
            )
        ).all()
    )
    for name in (t for t in _BILLING_TOOLS if t not in existing):
        db_session.add(
            ToolCatalog(
                name=name,
                description=f"test seed for {name}",
                mcp_server=f"internal:{CONNECTOR}",
                input_schema={},
                output_schema={},
                side_effects=[],
                capability_tags=["billing"],
                cost_estimate={},
                status=ToolStatus.ACTIVE,
                connector_id=connector.id,
                read_only=name
                in ("billing.get_debtor_by_phone", "billing.list_overdue", "billing.get_account"),
                destructive=False,
                requires_consent=False,
                default_mode="always",
            )
        )
    await db_session.commit()


async def _blueprint_partner(
    db_session,
    *,
    auto_activate: bool = True,
    seed: str | None = SEED,
    connector: str | None = CONNECTOR,
) -> dict:
    """Partner with the Fase 2b blueprint + one live key. No mapping —
    the provision call creates the tenant just-in-time."""
    partner_id = uuid.uuid4()
    generated = generate_api_key()
    key_id = uuid.uuid4()
    db_session.add(
        Partner(
            id=partner_id,
            name="Amigable Test",
            slug=f"amigable-{partner_id.hex[:6]}",
            default_seed_template=seed,
            default_connector_slug=connector,
            auto_activate=auto_activate,
        )
    )
    db_session.add(
        PartnerApiKey(
            id=key_id,
            partner_id=partner_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=["provision", "widget_sessions"],
            allowed_origins=["https://partner.example"],
        )
    )
    await db_session.commit()
    return {"partner_id": partner_id, "key": generated.plaintext, "key_id": key_id}


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _provision_body(ref: str = "negocio-42") -> dict:
    return {
        "external_client_ref": ref,
        "name": "Bodegón El Ávila",
        "timezone": "America/Caracas",
        "agent": {
            "placeholders": {
                "agent.name": "Mouna",
                "policies.admin_access.admin_phones": ["+584244095716"],
            }
        },
        "connector": {
            "credentials": {"entity_id": str(uuid.uuid4()), "token": "amigable-bearer-1"},
            "meta": {"business_uuid": str(uuid.uuid4())},
        },
    }


async def _mapped_tenant_id(db_session, partner_id: uuid.UUID, ref: str) -> uuid.UUID:
    mapping = await db_session.get(PartnerTenant, (partner_id, ref))
    assert mapping is not None
    return mapping.tenant_id


# ── provisioning blueprint ─────────────────────────────────────────────────


async def test_provision_blueprint_seeds_agent_and_connector(client, db_session) -> None:
    world = await _blueprint_partner(db_session)
    r = await client.post(
        "/v1/partners/clients", json=_provision_body(), headers=_auth(world["key"])
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agent"]["status"] == "provisioned"
    assert body["connector_connected"] is True
    assert body["whatsapp"]["status"] == "not_connected"

    tenant_id = await _mapped_tenant_id(db_session, world["partner_id"], "negocio-42")
    tenant = await db_session.get(TenantModel, tenant_id)
    assert tenant.status is TenantStatus.PROVISIONING  # no channel yet

    config = await db_session.scalar(
        sa.select(AgentConfig).where(AgentConfig.tenant_id == tenant_id)
    )
    assert config is not None
    assert config.status is AgentConfigStatus.ACTIVE  # promoted, not staged
    assert config.version == 1
    assert config.seed_template_ref == SEED
    assert "Mouna" in config.system_prompt_rendered
    assert "Bodegón El Ávila" in config.system_prompt_rendered
    assert "billing.get_debtor_by_phone" in config.tools
    assert config.policies["admin_access"]["admin_phones"] == ["+584244095716"]
    assert config.created_by.startswith("partner:")

    connector = await db_session.scalar(
        sa.select(TenantConnector).where(TenantConnector.tenant_id == tenant_id)
    )
    assert connector is not None and connector.status == "connected"
    creds = await db_session.scalar(
        sa.select(TenantCredentials).where(
            TenantCredentials.tenant_id == tenant_id,
            TenantCredentials.integration == CONNECTOR,
        )
    )
    assert creds is not None

    events = (
        await db_session.scalars(
            sa.select(EmbedAuditLog.event).where(EmbedAuditLog.tenant_id == tenant_id)
        )
    ).all()
    assert "client.provisioned" in events
    assert "client.agent_provisioned" in events
    assert "client.connector_connected" in events


async def test_reprovision_never_reseeds_agent(client, db_session) -> None:
    world = await _blueprint_partner(db_session)
    first = await client.post(
        "/v1/partners/clients", json=_provision_body(), headers=_auth(world["key"])
    )
    assert first.json()["agent"]["status"] == "provisioned"

    again = await client.post(
        "/v1/partners/clients", json=_provision_body(), headers=_auth(world["key"])
    )
    assert again.status_code == 200
    assert again.json()["agent"]["status"] == "already_provisioned"

    tenant_id = await _mapped_tenant_id(db_session, world["partner_id"], "negocio-42")
    versions = (
        await db_session.scalars(
            sa.select(AgentConfig.version).where(AgentConfig.tenant_id == tenant_id)
        )
    ).all()
    assert versions == [1]


async def test_provision_without_blueprint_stays_bare(client, db_session) -> None:
    world = await _blueprint_partner(db_session, seed=None, connector=None)
    body = _provision_body()
    body.pop("agent")
    body.pop("connector")
    r = await client.post("/v1/partners/clients", json=body, headers=_auth(world["key"]))
    assert r.status_code == 200, r.text
    assert r.json()["agent"]["status"] == "not_configured"
    assert r.json()["connector_connected"] is False

    tenant_id = await _mapped_tenant_id(db_session, world["partner_id"], "negocio-42")
    config = await db_session.scalar(
        sa.select(AgentConfig).where(AgentConfig.tenant_id == tenant_id)
    )
    assert config is None


async def test_provision_connector_requires_credentials_shape(client, db_session) -> None:
    world = await _blueprint_partner(db_session)
    body = _provision_body()
    body["connector"] = {"credentials": {}}
    r = await client.post("/v1/partners/clients", json=body, headers=_auth(world["key"]))
    # Pydantic rejects the empty credentials dict before the service runs.
    assert r.status_code == 422


# ── embed signup ───────────────────────────────────────────────────────────


def _widget_token(world: dict, tenant_id: uuid.UUID, *, scope: list[str] | None = None) -> str:
    token, _jti, _exp = mint_widget_token(
        tenant_id=tenant_id,
        partner_id=world["partner_id"],
        key_id=world["key_id"],
        scope=scope if scope is not None else ["widget:send", "widget:connect"],
        allowed_origins=["https://partner.example"],
    )
    return token


def _signup_body() -> dict:
    return {
        "code": "OAUTH_CODE_XYZ",
        "waba_id": "WABA_TEST",
        "phone_number_id": "PN_TEST",
        "business_id": "BIZ_TEST",
        "mode": "cloud_api",
    }


def _mock_graph_happy_path(mock: respx.MockRouter) -> None:
    mock.get("/oauth/access_token").respond(
        200, json={"access_token": "EAA-bisuat-test", "expires_in": 5_184_000}
    )
    mock.post("/PN_TEST/register").respond(200, json={"success": True})
    mock.post("/WABA_TEST/subscribed_apps").respond(200, json={"success": True})
    mock.get("/PN_TEST").respond(
        200,
        json={
            "display_phone_number": "58 424-4095716",
            "verified_name": "Bodegón El Ávila",
            "quality_rating": "GREEN",
        },
    )


async def _provisioned_world(client, db_session, **partner_kwargs) -> tuple[dict, uuid.UUID]:
    world = await _blueprint_partner(db_session, **partner_kwargs)
    r = await client.post(
        "/v1/partners/clients", json=_provision_body(), headers=_auth(world["key"])
    )
    assert r.status_code == 200, r.text
    tenant_id = await _mapped_tenant_id(db_session, world["partner_id"], "negocio-42")
    return world, tenant_id


async def test_embed_signup_connects_and_activates(client, db_session) -> None:
    world, tenant_id = await _provisioned_world(client, db_session)
    token = _widget_token(world, tenant_id)
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_graph_happy_path(mock)
        r = await client.post(
            "/v1/embed/whatsapp/signup", json=_signup_body(), headers=_auth(token)
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "connected"
    assert body["display_phone_number"].startswith("+58")
    assert body["tenant_activated"] is True

    tenant = await db_session.get(TenantModel, tenant_id)
    await db_session.refresh(tenant)
    assert tenant.status is TenantStatus.ACTIVE

    channel = await db_session.scalar(
        sa.select(Channel).where(Channel.tenant_id == tenant_id, Channel.provider == "meta")
    )
    assert channel is not None

    events = (
        await db_session.scalars(
            sa.select(EmbedAuditLog.event).where(EmbedAuditLog.tenant_id == tenant_id)
        )
    ).all()
    assert "whatsapp.signup.completed" in events
    assert "tenant.activated" in events

    # The embed status endpoint now reports connected — what gates the
    # partner's broadcast button.
    status_resp = await client.get("/v1/embed/status", headers=_auth(token))
    assert status_resp.json()["status"] == "connected"


async def test_embed_signup_requires_connect_scope(client, db_session) -> None:
    world, tenant_id = await _provisioned_world(client, db_session)
    send_only = _widget_token(world, tenant_id, scope=["widget:send"])
    r = await client.post(
        "/v1/embed/whatsapp/signup", json=_signup_body(), headers=_auth(send_only)
    )
    assert r.status_code == 403
    assert "widget:connect" in r.json()["detail"]


async def test_embed_signup_without_auto_activate_stays_provisioning(client, db_session) -> None:
    world, tenant_id = await _provisioned_world(client, db_session, auto_activate=False)
    token = _widget_token(world, tenant_id)
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_graph_happy_path(mock)
        r = await client.post(
            "/v1/embed/whatsapp/signup", json=_signup_body(), headers=_auth(token)
        )
    assert r.status_code == 201, r.text
    assert r.json()["tenant_activated"] is False
    tenant = await db_session.get(TenantModel, tenant_id)
    await db_session.refresh(tenant)
    assert tenant.status is TenantStatus.PROVISIONING


async def test_embed_signup_without_agent_stays_provisioning(client, db_session) -> None:
    """auto_activate=True but the partner has no seed blueprint → the
    tenant has no agent, so activation must NOT happen (an answered
    number with no agent behind it)."""
    world = await _blueprint_partner(db_session, seed=None, connector=None)
    body = _provision_body()
    body.pop("agent")
    body.pop("connector")
    r = await client.post("/v1/partners/clients", json=body, headers=_auth(world["key"]))
    assert r.status_code == 200
    tenant_id = await _mapped_tenant_id(db_session, world["partner_id"], "negocio-42")

    token = _widget_token(world, tenant_id)
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_graph_happy_path(mock)
        resp = await client.post(
            "/v1/embed/whatsapp/signup", json=_signup_body(), headers=_auth(token)
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["tenant_activated"] is False
    tenant = await db_session.get(TenantModel, tenant_id)
    await db_session.refresh(tenant)
    assert tenant.status is TenantStatus.PROVISIONING


# ── usage / billing view ───────────────────────────────────────────────────


async def test_partner_usage_aggregates_clients(client, db_session, admin_headers) -> None:
    world, tenant_id = await _provisioned_world(client, db_session)
    token = _widget_token(world, tenant_id)
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_graph_happy_path(mock)
        await client.post("/v1/embed/whatsapp/signup", json=_signup_body(), headers=_auth(token))

    r = await client.get(f"/admin/partners/{world['partner_id']}/usage", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["clients_total"] == 1
    assert body["clients_active"] == 1
    assert body["clients_whatsapp_connected"] == 1
    assert body["clients_with_agent"] == 1
    row = body["clients"][0]
    assert row["external_client_ref"] == "negocio-42"
    assert row["agent_version"] == 1
    assert row["agent_seed_template"] == SEED
    assert row["tenant_status"] == "active"
