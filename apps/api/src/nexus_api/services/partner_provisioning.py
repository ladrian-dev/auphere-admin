"""Partner auto-provisioning (ADR-028 Fase 2b).

Turns ``POST /v1/partners/clients`` into a *complete* onboarding, not
just a bare tenant: for a partner configured with a blueprint
(``partners.default_seed_template`` / ``default_connector_slug``), the
provision call renders the seed template into a promoted agent_config v1
and installs the ``api_key`` connector with the credentials the partner
sent. The tenant stays PROVISIONING (the inbound pipeline ignores it)
until its WhatsApp signup completes, at which point
:func:`activate_tenant_if_ready` flips it ACTIVE.

Every function here assumes the caller already holds a tenant-scoped
transaction: ``app.tenant_id`` applied to the session AND the
``_current_tenant`` contextvar set (AgentConfigRepository reads it).
``/v1/partners/clients`` and the client signup endpoint wrap the calls
themselves.

Isolation note: nothing in this module chooses a tenant_id — callers
resolve it through ``partner_tenants``, the only sanctioned path.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.admin_gate import usable_admin_phones
from nexus_api.core.errors import AgentConfigConflict
from nexus_api.db.models import AgentConfig, Partner, Tenant, TenantStatus
from nexus_api.repositories.partner import EmbedAuditRepository
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.connectors.service import (
    IncompatibleAuthKind,
    bootstrap_api_key,
)
from nexus_api.services.templating.seed_templates import (
    SeedTemplateNotFound,
    SeedTemplatePlaceholderMissing,
    load_seed_template,
    render_seed_template,
)

log = structlog.get_logger(__name__)


class ProvisioningError(Exception):
    """Blueprint execution failed for a reason the partner can fix
    (missing placeholder, wrong credential fields). Maps to HTTP 400/422
    at the surface."""


#: Seed templates spell unresolved business data as ``<<…>>`` defaults
#: (bank account, shipping policy, …). They render fine — which is the
#: problem: the agent would go live quoting a literal
#: "<<transferencia banco — pendiente>>" to a real admin. Provisioning
#: refuses instead, naming every one so the partner can send it.
_PENDING_MARKER = re.compile(r"<<([^<>]{1,160})>>")


@dataclass(frozen=True)
class ProvisioningResult:
    """What the blueprint left behind — echoed (without internals) in
    the provision response and the audit trail."""

    agent_provisioned: bool
    agent_version: int | None
    connector_connected: bool


async def provision_client_blueprint(
    session: AsyncSession,
    *,
    partner: Partner,
    tenant: Tenant,
    placeholders: dict[str, Any] | None,
    connector_credentials: dict[str, str] | None,
    connector_meta: dict[str, Any] | None,
    api_key_id: uuid.UUID,
    ip: str | None,
) -> ProvisioningResult:
    """Execute the partner's blueprint for a freshly-resolved client.

    Idempotent by design:
    - the connector install rotates credentials in place on re-provision
      (``bootstrap_api_key`` semantics);
    - the agent is only seeded when the tenant has NO agent_config yet —
      a re-provision never stomps operator (or partner) customisations.
    """
    actor = f"partner:{partner.slug}"
    audit = EmbedAuditRepository(session)

    connector_connected = False
    if partner.default_connector_slug and connector_credentials:
        try:
            await bootstrap_api_key(
                session,
                tenant=tenant,
                connector_slug=partner.default_connector_slug,
                secret_payload=connector_credentials,
                endpoint_meta=connector_meta or {},
                actor=actor,
            )
        except (IncompatibleAuthKind, ValueError) as exc:
            raise ProvisioningError(str(exc)) from exc
        connector_connected = True
        await audit.record(
            event="client.connector_connected",
            partner_id=partner.id,
            api_key_id=api_key_id,
            tenant_id=tenant.id,
            payload={"connector": partner.default_connector_slug},
            ip=ip,
        )

    agent_provisioned = False
    agent_version: int | None = None
    if partner.default_seed_template:
        svc = AgentConfigService(session)
        existing = await svc.list_versions()
        if not existing:
            config = await _seed_agent(
                session,
                seed_template_ref=partner.default_seed_template,
                tenant=tenant,
                placeholders=placeholders or {},
                actor=actor,
            )
            agent_provisioned = True
            agent_version = config.version
            await audit.record(
                event="client.agent_provisioned",
                partner_id=partner.id,
                api_key_id=api_key_id,
                tenant_id=tenant.id,
                payload={
                    "seed_template": partner.default_seed_template,
                    "version": config.version,
                },
                ip=ip,
            )
            log.info(
                "partner.agent_provisioned",
                partner=partner.slug,
                tenant_id=str(tenant.id),
                seed=partner.default_seed_template,
                version=config.version,
            )

    return ProvisioningResult(
        agent_provisioned=agent_provisioned,
        agent_version=agent_version,
        connector_connected=connector_connected,
    )


def _pending_placeholders(system_prompt: str, policies: dict[str, Any]) -> list[str]:
    """Every ``<<…>>`` marker left in the rendered agent, deduped."""
    blob = f"{system_prompt}\n{json.dumps(policies, ensure_ascii=False)}"
    return sorted({m.group(1).strip() for m in _PENDING_MARKER.finditer(blob)})


def _assert_business_data_complete(*, system_prompt: str, policies: dict[str, Any]) -> None:
    """Refuse to promote an agent that cannot do its job on day one.

    Two failure modes, both silent until a real admin hits them:

    1. **Unfilled business data** — the agent quotes ``<<… pendiente>>``
       (bank details, policies) as if it were fact.
    2. **Empty admin whitelist on an ``admin_only`` agent** — the gate
       suppresses EVERY sender, so the client's brand-new number never
       answers anyone and nothing in the logs looks broken.

    Both are the partner's to fix by sending placeholders, so they surface
    as 422 with the exact keys missing.
    """
    pending = _pending_placeholders(system_prompt, policies)
    if pending:
        listed = ", ".join(pending)
        raise ProvisioningError(
            "Faltan datos del negocio para armar el agente. Envíalos en "
            f"agent.placeholders. Pendientes: {listed}"
        )

    access = (policies or {}).get("admin_access") or {}
    admin_only = isinstance(access, dict) and bool(access.get("admin_only"))
    if admin_only and not usable_admin_phones(access.get("admin_phones")):
        raise ProvisioningError(
            "Este agente solo responde a administradores autorizados y la "
            "whitelist quedó vacía: nadie podría hablar con él. Envía "
            "agent.placeholders['policies.admin_access.admin_phones'] con "
            "al menos un teléfono (E.164, mínimo 7 dígitos)."
        )


async def _seed_agent(
    session: AsyncSession,
    *,
    seed_template_ref: str,
    tenant: Tenant,
    placeholders: dict[str, Any],
    actor: str,
) -> AgentConfig:
    """Render the seed and leave it PROMOTED (the partner flow has no
    operator review step — that is exactly what ``auto_activate`` and
    the blueprint opt-in on the partner row consent to)."""
    try:
        template = load_seed_template(seed_template_ref)
    except SeedTemplateNotFound as exc:
        # Partner row misconfigured — an operator problem, not the
        # partner's. Surface as 500-ish via generic exception.
        raise ProvisioningError(
            f"seed template {seed_template_ref!r} configured for this partner does not exist"
        ) from exc

    # The tenant row is authoritative for its own facts; the partner can
    # override anything else (agent.name, policies.*, …) but not inject a
    # different tenant identity into the prompt.
    resolved: dict[str, Any] = dict(placeholders)
    resolved["tenant.name"] = tenant.name
    resolved["tenant.timezone"] = tenant.timezone

    try:
        rendered = render_seed_template(template, placeholders=resolved)
    except SeedTemplatePlaceholderMissing as exc:
        raise ProvisioningError(str(exc)) from exc

    # Rendering succeeded, but "renders" is not "works" — a seed's own
    # defaults can leave the agent quoting placeholders or unable to talk
    # to anyone. Fail here, before anything is promoted.
    _assert_business_data_complete(
        system_prompt=rendered.system_prompt,
        policies=rendered.policies,
    )

    # Union with tools contributed by connectors already installed on
    # this tenant (the blueprint installs the connector first) — mirrors
    # the from-seed admin endpoint so both paths stay symmetric.
    from nexus_api.api.admin.agent_configs import _safe_connector_tools_for_tenant

    connector_tools = await _safe_connector_tools_for_tenant(session, tenant.id)
    merged_tools = sorted(set(rendered.tools) | connector_tools)

    svc = AgentConfigService(session)
    try:
        config = await svc.stage_new_version(
            actor=actor,
            system_prompt_rendered=rendered.system_prompt,
            channels=[],
            tools=merged_tools,
            policies=rendered.policies,
            seed_template_ref=rendered.seed_template_ref,
        )
        return await svc.promote(config.version, actor=actor)
    except AgentConfigConflict as exc:
        raise ProvisioningError(str(exc)) from exc


async def activate_tenant_if_ready(
    session: AsyncSession,
    *,
    partner: Partner,
    tenant_id: uuid.UUID,
    api_key_id: uuid.UUID | None = None,
    jti: str | None = None,
) -> bool:
    """PROVISIONING → ACTIVE once the tenant can actually operate.

    Called after a successful embed WhatsApp signup. Gates:
    - the partner opted into ``auto_activate``;
    - the tenant is still PROVISIONING (never touches PAUSED/ARCHIVED —
      those are operator decisions);
    - an ACTIVE agent_config exists (activating an agent-less tenant
      would put an unanswered number in production).

    Returns True when the flip happened.
    """
    if not partner.auto_activate:
        return False
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.status is not TenantStatus.PROVISIONING:
        return False
    active_config = await AgentConfigService(session).get_active()
    if active_config is None:
        log.info(
            "partner.activation_skipped_no_agent",
            partner=partner.slug,
            tenant_id=str(tenant_id),
        )
        return False

    tenant.status = TenantStatus.ACTIVE
    await session.flush()
    await EmbedAuditRepository(session).record(
        event="tenant.activated",
        partner_id=partner.id,
        api_key_id=api_key_id,
        tenant_id=tenant_id,
        payload={"agent_config_version": active_config.version},
        jti=jti,
    )
    log.info(
        "partner.tenant_activated",
        partner=partner.slug,
        tenant_id=str(tenant_id),
        agent_version=active_config.version,
    )
    return True
