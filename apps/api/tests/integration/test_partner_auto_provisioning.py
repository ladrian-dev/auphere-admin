"""Partner auto-provisioning + WhatsApp signup (ADR-028 Fase 2a/2b).

End-to-end over the public surfaces with the real DB and a respx-mocked
Graph API:

1. ``POST /v1/partners/clients`` with a blueprint partner leaves a
   PROMOTED agent_config (seeded from ``default_seed_template``) and a
   connected ``api_key`` connector behind — not just a bare tenant.
2. Re-provisioning never re-seeds the agent (idempotent) but rotates
   connector credentials.
3. ``POST /v1/partners/clients/{ref}/whatsapp/signup`` completes Embedded
   Signup from the partner's own backend and flips the tenant
   PROVISIONING → ACTIVE when the partner has ``auto_activate`` and a
   promoted agent exists.
4. ``GET /admin/partners/{id}/usage`` aggregates the per-client rows the
   billing view needs.
"""

from __future__ import annotations

import re
import uuid

import pytest
import respx
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL

from nexus_api.config import get_settings
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
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
    "billing.find_client",
    "billing.list_overdue",
    "billing.get_account",
    "billing.register_payment",
    "billing.add_charge",
    "billing.update_status",
    "billing.apply_discount",
    "billing.create_account",
    "billing.update_account",
    "billing.send_reminders",
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
            scopes=["provision", "broadcasts"],
            allowed_origins=["https://partner.example"],
        )
    )
    await db_session.commit()
    return {"partner_id": partner_id, "key": generated.plaintext, "key_id": key_id}


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


#: Every ``<<… pendiente>>`` default cobranza_v1 ships. Provisioning
#: refuses to promote an agent that still carries any of them, so a
#: realistic body fills them all.
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


async def test_provision_rejects_unfilled_business_data(client, db_session) -> None:
    """A ``<<… pendiente>>`` marker renders fine — and would put an agent in
    production quoting the placeholder as if it were the client's real data.
    Provisioning must refuse and name what's missing.

    (This used to leave a bank-detail placeholder unresolved. ``cobranza_v1``
    no longer carries payment data at all — see
    ``test_cobranza_seed_has_no_payment_data`` — so the marker now comes in
    through a placeholder the caller controls, which is the invariant the
    guard actually protects.)
    """
    world = await _blueprint_partner(db_session)
    body = _provision_body()
    body["agent"]["placeholders"]["agent.name"] = "<<nombre del agente — pendiente>>"
    r = await client.post("/v1/partners/clients", json=body, headers=_auth(world["key"]))
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "nombre del agente" in detail

    tenant_id = await _mapped_tenant_id(db_session, world["partner_id"], "negocio-42")
    config = await db_session.scalar(
        sa.select(AgentConfig).where(AgentConfig.tenant_id == tenant_id)
    )
    assert config is None  # nothing promoted


async def test_cobranza_seed_has_no_payment_data(client, db_session) -> None:
    """The rendered agent must not carry the business's bank details.

    They lived in the seed's ``policies.payment`` and were interpolated into
    the system prompt. Two things were wrong with that: the seed is shared by
    every Amigable Cobro client, and the fictional example values reached
    production verbatim — Muna's live agent quoted "Banesco … J-40123456-7"
    to admins as real. Amigable Cobro stores no payment data, so there is no
    source of truth to read; the agent says it does not have them instead.
    """
    world = await _blueprint_partner(db_session)
    r = await client.post(
        "/v1/partners/clients", json=_provision_body(), headers=_auth(world["key"])
    )
    assert r.status_code == 200, r.text

    tenant_id = await _mapped_tenant_id(db_session, world["partner_id"], "negocio-42")
    config = await db_session.scalar(
        sa.select(AgentConfig).where(AgentConfig.tenant_id == tenant_id)
    )
    assert config is not None
    assert "payment" not in (config.policies or {})
    prompt = config.system_prompt_rendered
    # Look for the SHAPE of payment data, not the words: the prompt still
    # names these instruments in order to refuse them.
    assert "Banesco" not in prompt
    assert not re.search(r"[JVEG]-\d{5,}", prompt), "a RIF/cédula reached the prompt"
    assert not re.search(r"\b\d{4}[ -]?\d{4}[ -]?\d{2}[ -]?\d{10}\b", prompt), (
        "a bank account number reached the prompt"
    )
    assert "<<" not in prompt, "an unresolved placeholder reached the prompt"
    # The prompt is wrapped, so compare against a whitespace-collapsed copy.
    flat = " ".join(prompt.lower().split())
    assert "no tengo los datos de pago del negocio cargados" in flat


async def test_provision_rejects_empty_admin_whitelist(client, db_session) -> None:
    """cobranza_v1 is ``admin_only``: with an empty whitelist the gate
    suppresses every sender, so the client's number would answer nobody."""
    world = await _blueprint_partner(db_session)
    body = _provision_body()
    body["agent"]["placeholders"]["policies.admin_access.admin_phones"] = []
    r = await client.post("/v1/partners/clients", json=body, headers=_auth(world["key"]))
    assert r.status_code == 422, r.text
    assert "admin_phones" in r.json()["detail"]


async def test_provision_rejects_unusable_admin_phone(client, db_session) -> None:
    """Too few digits to ever match a sender — same outcome as empty."""
    world = await _blueprint_partner(db_session)
    body = _provision_body()
    body["agent"]["placeholders"]["policies.admin_access.admin_phones"] = ["123"]
    r = await client.post("/v1/partners/clients", json=body, headers=_auth(world["key"]))
    assert r.status_code == 422, r.text


async def test_provision_connector_requires_credentials_shape(client, db_session) -> None:
    world = await _blueprint_partner(db_session)
    body = _provision_body()
    body["connector"] = {"credentials": {}}
    r = await client.post("/v1/partners/clients", json=body, headers=_auth(world["key"]))
    # Pydantic rejects the empty credentials dict before the service runs.
    assert r.status_code == 422


async def _provisioned_world(client, db_session, **partner_kwargs) -> tuple[dict, uuid.UUID]:
    """Blueprint partner + one provisioned client, ready for signup."""
    world = await _blueprint_partner(db_session, **partner_kwargs)
    r = await client.post(
        "/v1/partners/clients", json=_provision_body(), headers=_auth(world["key"])
    )
    assert r.status_code == 200, r.text
    tenant_id = await _mapped_tenant_id(db_session, world["partner_id"], "negocio-42")
    return world, tenant_id


# ── usage / billing view ───────────────────────────────────────────────────


async def test_partner_usage_aggregates_clients(client, db_session, admin_headers) -> None:
    world, _tenant_id = await _provisioned_world(client, db_session)
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_graph_coexistence(mock)
        await client.post(
            "/v1/partners/clients/negocio-42/whatsapp/signup",
            json={
                "code": "OAUTH_CODE_XYZ",
                "waba_id": "WABA_TEST",
                "phone_number_id": "PN_TEST",
                "mode": "coexistence",
            },
            headers=_auth(world["key"]),
        )

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


# ── partner self-serve: WhatsApp line + admin whitelist ─────────────────────


def _mock_graph_coexistence(mock: respx.MockRouter) -> None:
    """Coexistence skips /register (breaks the number) — only exchange,
    subscribe and the phone-metadata read are hit."""
    mock.get("/oauth/access_token").respond(
        200, json={"access_token": "EAA-bisuat-test", "expires_in": 5_184_000}
    )
    mock.post("/WABA_TEST/subscribed_apps").respond(200, json={"success": True})
    mock.get("/PN_TEST").respond(
        200,
        json={
            "display_phone_number": "58 424-4095716",
            "verified_name": "Bodegón El Ávila",
            "quality_rating": "GREEN",
        },
    )


async def test_partner_connects_client_whatsapp_coexistence(client, db_session) -> None:
    world, tenant_id = await _provisioned_world(client, db_session)
    body = {
        "code": "OAUTH_CODE_XYZ",
        "waba_id": "WABA_TEST",
        "phone_number_id": "PN_TEST",
        "business_id": "BIZ_TEST",
        "mode": "coexistence",
    }
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_graph_coexistence(mock)
        r = await client.post(
            "/v1/partners/clients/negocio-42/whatsapp/signup",
            json=body,
            headers=_auth(world["key"]),
        )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "connected"
    assert out["mode"] == "coexistence"
    assert out["display_phone_number"].startswith("+58")

    channel = await db_session.scalar(
        sa.select(Channel).where(Channel.tenant_id == tenant_id, Channel.provider == "meta")
    )
    assert channel is not None

    # The partner path must activate too — otherwise a client onboarded
    # entirely from the partner's app gets a live number and a silent
    # agent (PROVISIONING is inactive for the worker dispatcher).
    assert out["tenant_activated"] is True
    assert out["tenant_status"] == "active"
    assert out["activation_blocked_reason"] is None
    tenant = await db_session.get(TenantModel, tenant_id)
    await db_session.refresh(tenant)
    assert tenant.status is TenantStatus.ACTIVE

    events = (
        await db_session.scalars(
            sa.select(EmbedAuditLog.event).where(EmbedAuditLog.tenant_id == tenant_id)
        )
    ).all()
    assert "tenant.activated" in events


async def test_partner_signup_without_auto_activate_reports_operator_review(
    client, db_session
) -> None:
    world, tenant_id = await _provisioned_world(client, db_session, auto_activate=False)
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_graph_coexistence(mock)
        r = await client.post(
            "/v1/partners/clients/negocio-42/whatsapp/signup",
            json={
                "code": "OAUTH_CODE_XYZ",
                "waba_id": "WABA_TEST",
                "phone_number_id": "PN_TEST",
                "mode": "coexistence",
            },
            headers=_auth(world["key"]),
        )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["tenant_activated"] is False
    assert out["tenant_status"] == "provisioning"
    assert out["activation_blocked_reason"] == "operator_review"
    tenant = await db_session.get(TenantModel, tenant_id)
    await db_session.refresh(tenant)
    assert tenant.status is TenantStatus.PROVISIONING


async def test_partner_signup_without_agent_reports_no_agent(client, db_session) -> None:
    world = await _blueprint_partner(db_session, seed=None, connector=None)
    body = _provision_body()
    body.pop("agent")
    body.pop("connector")
    await client.post("/v1/partners/clients", json=body, headers=_auth(world["key"]))

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_graph_coexistence(mock)
        r = await client.post(
            "/v1/partners/clients/negocio-42/whatsapp/signup",
            json={
                "code": "OAUTH_CODE_XYZ",
                "waba_id": "WABA_TEST",
                "phone_number_id": "PN_TEST",
                "mode": "coexistence",
            },
            headers=_auth(world["key"]),
        )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["tenant_activated"] is False
    assert out["activation_blocked_reason"] == "no_agent"


async def test_partner_client_status_tracks_onboarding(client, db_session) -> None:
    world, _tenant_id = await _provisioned_world(client, db_session)

    before = await client.get("/v1/partners/clients/negocio-42", headers=_auth(world["key"]))
    assert before.status_code == 200, before.text
    b = before.json()
    assert b["status"] == "provisioning"
    assert b["agent_configured"] is True
    assert b["agent_version"] == 1
    assert b["agent_seed_template"] == SEED
    assert b["admins_count"] == 1
    assert b["whatsapp_connected"] is False
    assert b["ready"] is False
    assert b["missing"] == ["whatsapp"]

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        _mock_graph_coexistence(mock)
        await client.post(
            "/v1/partners/clients/negocio-42/whatsapp/signup",
            json={
                "code": "OAUTH_CODE_XYZ",
                "waba_id": "WABA_TEST",
                "phone_number_id": "PN_TEST",
                "mode": "coexistence",
            },
            headers=_auth(world["key"]),
        )

    after = await client.get("/v1/partners/clients/negocio-42", headers=_auth(world["key"]))
    a = after.json()
    assert a["status"] == "active"
    assert a["whatsapp_connected"] is True
    assert a["display_phone_number"].startswith("+58")
    assert a["ready"] is True
    assert a["missing"] == []


async def test_admin_patch_partner_blueprint_returns_200(client, db_session, admin_headers) -> None:
    """Regression: the PATCH committed and then blew up serialising the
    response (``updated_at`` is server-side ``onupdate``, so the flush
    expires it and reading it outside the async block raises
    MissingGreenlet). Operators saw a 500 on a change that HAD applied."""
    world = await _blueprint_partner(db_session, seed=None, connector=None)
    r = await client.patch(
        f"/admin/partners/{world['partner_id']}",
        json={
            "default_seed_template": SEED,
            "default_connector_slug": CONNECTOR,
            "auto_activate": True,
        },
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_seed_template"] == SEED
    assert body["default_connector_slug"] == CONNECTOR
    assert body["auto_activate"] is True

    token = get_settings().admin_token
    audit = (
        await db_session.execute(
            sa.select(AuditLog).where(
                AuditLog.action == "partner.update",
                AuditLog.target == f"partner:{world['partner_id']}",
            )
        )
    ).scalar_one()
    assert audit.tenant_id is None
    assert audit.actor == f"admin:{token[:8]}"
    assert token not in audit.actor
    assert audit.after_json is not None
    assert "plaintext" not in audit.after_json
    assert audit.after_json["default_seed_template"] == SEED


async def test_partner_client_status_unknown_ref_is_404(client, db_session) -> None:
    world = await _blueprint_partner(db_session)
    r = await client.get("/v1/partners/clients/nope", headers=_auth(world["key"]))
    assert r.status_code == 404


async def test_partner_whatsapp_signup_unknown_ref_is_404(client, db_session) -> None:
    world = await _blueprint_partner(db_session)
    r = await client.post(
        "/v1/partners/clients/does-not-exist/whatsapp/signup",
        json={"code": "X", "waba_id": "WABA_TEST"},
        headers=_auth(world["key"]),
    )
    assert r.status_code == 404


async def test_partner_signup_config_exposes_ids(client, db_session) -> None:
    world = await _blueprint_partner(db_session)
    r = await client.get("/v1/partners/whatsapp/signup-config", headers=_auth(world["key"]))
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["app_id"]
    assert cfg["coexistence_config_id"]
    assert cfg["cloud_api_config_id"]


async def test_partner_sets_and_reads_admins(client, db_session) -> None:
    world, tenant_id = await _provisioned_world(client, db_session)

    # Provisioning seeded admin_phones from the blueprint placeholders.
    r0 = await client.get("/v1/partners/clients/negocio-42/admins", headers=_auth(world["key"]))
    assert r0.status_code == 200, r0.text
    assert r0.json()["admin_only"] is True
    assert [a["phone"] for a in r0.json()["admins"]] == ["+584244095716"]

    # Replace the whitelist with two admins (formatting is normalised).
    r = await client.put(
        "/v1/partners/clients/negocio-42/admins",
        json={
            "admins": [
                {"phone": "+58 412 111 2233", "name": "Ana"},
                {"phone": "+584249990000"},
            ]
        },
        headers=_auth(world["key"]),
    )
    assert r.status_code == 200, r.text
    phones = {a["phone"] for a in r.json()["admins"]}
    assert phones == {"+584121112233", "+584249990000"}
    assert dict((a["phone"], a["name"]) for a in r.json()["admins"])["+584121112233"] == "Ana"

    # A fresh agent_config version is promoted carrying the new whitelist.
    active = await db_session.scalar(
        sa.select(AgentConfig).where(
            AgentConfig.tenant_id == tenant_id,
            AgentConfig.status == AgentConfigStatus.ACTIVE,
        )
    )
    assert active is not None
    assert active.version == 2
    assert set(active.policies["admin_access"]["admin_phones"]) == {
        "+584121112233",
        "+584249990000",
    }

    # GET reflects the update.
    r2 = await client.get("/v1/partners/clients/negocio-42/admins", headers=_auth(world["key"]))
    assert {a["phone"] for a in r2.json()["admins"]} == {
        "+584121112233",
        "+584249990000",
    }


async def test_partner_rejects_invalid_admin_phone(client, db_session) -> None:
    world, _tenant_id = await _provisioned_world(client, db_session)
    r = await client.put(
        "/v1/partners/clients/negocio-42/admins",
        json={"admins": [{"phone": "not-a-phone"}]},
        headers=_auth(world["key"]),
    )
    assert r.status_code == 400


async def test_partner_admin_roles_round_trip(client, db_session) -> None:
    from nexus_api.core.admin_gate import sender_role

    world, tenant_id = await _provisioned_world(client, db_session)
    r = await client.put(
        "/v1/partners/clients/negocio-42/admins",
        json={
            "admins": [
                {"phone": "+584249398142", "name": "Dueño", "role": "full"},
                {"phone": "+584249693698", "name": "Consulta", "role": "readonly"},
            ]
        },
        headers=_auth(world["key"]),
    )
    assert r.status_code == 200, r.text
    roles = {a["phone"]: a["role"] for a in r.json()["admins"]}
    assert roles == {"+584249398142": "full", "+584249693698": "readonly"}

    # GET reflects the roles.
    r2 = await client.get("/v1/partners/clients/negocio-42/admins", headers=_auth(world["key"]))
    assert {a["phone"]: a["role"] for a in r2.json()["admins"]} == roles

    # The active agent_config carries the per-admin roles, and the gate agrees.
    active = await db_session.scalar(
        sa.select(AgentConfig).where(
            AgentConfig.tenant_id == tenant_id,
            AgentConfig.status == AgentConfigStatus.ACTIVE,
        )
    )
    by_phone = {a["phone"]: a["role"] for a in active.policies["admin_access"]["admins"]}
    assert by_phone == {"+584249398142": "full", "+584249693698": "readonly"}
    assert sender_role(active.policies, "584249693698") == "readonly"
    assert sender_role(active.policies, "584249398142") == "full"


async def test_partner_admin_role_defaults_full(client, db_session) -> None:
    world, _tenant_id = await _provisioned_world(client, db_session)
    r = await client.put(
        "/v1/partners/clients/negocio-42/admins",
        json={"admins": [{"phone": "+584249398142"}]},  # no role
        headers=_auth(world["key"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["admins"][0]["role"] == "full"


def _assert_platform_audit(row: AuditLog, *, action: str, token: str) -> None:
    assert row.tenant_id is None
    assert row.action == action
    assert row.actor == f"admin:{token[:8]}"
    assert token not in row.actor
    if row.after_json is not None:
        assert "plaintext" not in row.after_json
        assert "key_hash" not in row.after_json


async def test_admin_partner_bodies_reject_extra_or_partner_id(
    client, db_session, admin_headers
) -> None:
    created = await client.post(
        "/admin/partners",
        headers=admin_headers,
        json={"name": "Agencia Extra", "slug": "agencia-extra", "ghost_field": "nope"},
    )
    assert created.status_code == 422

    created_pid = await client.post(
        "/admin/partners",
        headers=admin_headers,
        json={
            "name": "Agencia Extra",
            "slug": "agencia-extra",
            "partner_id": str(uuid.uuid4()),
        },
    )
    assert created_pid.status_code == 422

    world = await _blueprint_partner(db_session, seed=None, connector=None)
    pid = world["partner_id"]
    extra = await client.patch(
        f"/admin/partners/{pid}",
        headers=admin_headers,
        json={"name": "Nuevo", "ghost_field": "nope"},
    )
    assert extra.status_code == 422
    partner_id_body = await client.patch(
        f"/admin/partners/{pid}",
        headers=admin_headers,
        json={"name": "Nuevo", "partner_id": str(pid)},
    )
    assert partner_id_body.status_code == 422

    key_extra = await client.post(
        f"/admin/partners/{pid}/keys",
        headers=admin_headers,
        json={"type": "live", "partner_id": str(pid)},
    )
    assert key_extra.status_code == 422

    link_extra = await client.post(
        f"/admin/partners/{pid}/tenants",
        headers=admin_headers,
        json={
            "external_client_ref": "c1",
            "tenant_id": str(uuid.uuid4()),
            "partner_id": str(pid),
        },
    )
    assert link_extra.status_code == 422


async def test_admin_partner_create_update_and_keys_write_audit_log(
    client, admin_headers, db_session
) -> None:
    token = get_settings().admin_token
    created = await client.post(
        "/admin/partners",
        headers=admin_headers,
        json={"name": "Audit Agency", "slug": "audit-agency"},
    )
    assert created.status_code == 201, created.text
    partner_id = created.json()["id"]

    create_audit = (
        await db_session.execute(
            sa.select(AuditLog).where(
                AuditLog.action == "partner.create",
                AuditLog.target == f"partner:{partner_id}",
            )
        )
    ).scalar_one()
    _assert_platform_audit(create_audit, action="partner.create", token=token)
    assert create_audit.after_json is not None
    assert create_audit.after_json["slug"] == "audit-agency"

    patched = await client.patch(
        f"/admin/partners/{partner_id}",
        headers=admin_headers,
        json={"name": "Audit Agency 2"},
    )
    assert patched.status_code == 200, patched.text
    update_audit = (
        await db_session.execute(
            sa.select(AuditLog).where(
                AuditLog.action == "partner.update",
                AuditLog.target == f"partner:{partner_id}",
            )
        )
    ).scalar_one()
    _assert_platform_audit(update_audit, action="partner.update", token=token)
    assert update_audit.before_json is not None
    assert update_audit.before_json["name"] == "Audit Agency"
    assert update_audit.after_json is not None
    assert update_audit.after_json["name"] == "Audit Agency 2"

    minted = await client.post(
        f"/admin/partners/{partner_id}/keys",
        headers=admin_headers,
        json={"type": "live"},
    )
    assert minted.status_code == 201, minted.text
    key_id = minted.json()["id"]
    plaintext = minted.json()["plaintext"]

    rotated = await client.post(
        f"/admin/partners/{partner_id}/keys/{key_id}/rotate",
        headers=admin_headers,
        json={"grace_hours": 2},
    )
    assert rotated.status_code == 201, rotated.text
    new_key_id = rotated.json()["id"]
    rotate_audit = (
        await db_session.execute(sa.select(AuditLog).where(AuditLog.action == "key.rotate"))
    ).scalar_one()
    _assert_platform_audit(rotate_audit, action="key.rotate", token=token)
    assert rotate_audit.after_json is not None
    assert rotate_audit.after_json["id"] == new_key_id
    assert plaintext not in str(rotate_audit.after_json)
    assert rotated.json()["plaintext"] not in str(rotate_audit.after_json)

    revoked = await client.post(
        f"/admin/partners/{partner_id}/keys/{new_key_id}/revoke",
        headers=admin_headers,
        json={},
    )
    assert revoked.status_code == 200, revoked.text
    revoke_audit = (
        await db_session.execute(sa.select(AuditLog).where(AuditLog.action == "key.revoke"))
    ).scalar_one()
    _assert_platform_audit(revoke_audit, action="key.revoke", token=token)
    assert revoke_audit.after_json is not None
    assert revoke_audit.after_json["revoked_at"] is not None
