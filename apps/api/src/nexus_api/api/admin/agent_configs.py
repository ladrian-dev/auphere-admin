from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis, scoped_session_from_path
from nexus_api.config import get_settings
from nexus_api.core.errors import AgentConfigConflict
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    Channel,
    Connector,
    ConnectorToolMode,
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.schemas.agent_config import (
    AgentConfigBundle,
    AgentConfigOut,
    AgentConfigStageIn,
    RuntimeCapabilitiesIn,
)
from nexus_api.schemas.evals import PromoteOverrideIn
from nexus_api.services import AgentConfigService
from nexus_api.services.evals import has_passing_recent_run
from nexus_api.services.prompt_improver import (
    SUPPORTED_MODES,
    AgentContext,
    ImproveResult,
    LiteLLMPromptImproverProvider,
    MalformedResponseError,
    PromptImproverError,
    PromptImproverProvider,
    PromptTooLongError,
    improve_prompt,
)
from nexus_api.services.templating import (
    SeedTemplateNotFound,
    SeedTemplatePlaceholderMissing,
    list_seed_templates,
    load_seed_template,
    render_seed_template,
)
from nexus_api.services.test_agent import (
    LiteLLMTestAgentProvider,
    TestAgentError,
    TestAgentProvider,
    TestTurnResult,
    run_test_turn,
)

router = APIRouter()
log = structlog.get_logger()


# Pub/sub channel that the worker subscribes to in order to invalidate its
# AgentLoader cache. Centralised here so the worker imports the same constant
# (architecture/agent-isolation.md, garantía 5 — promote without redeploy).
PROMOTE_CHANNEL = "nexus:agent_config:promote"


async def _publish_promote(redis: Redis, tenant_id: uuid.UUID) -> None:
    try:
        await redis.publish(PROMOTE_CHANNEL, str(tenant_id))
    except Exception as exc:
        # Stale-cache risk only — log and move on. The promote already
        # committed; worst case the worker keeps the previous version until
        # its next miss.
        log.warning("agent_config.promote_publish_failed", tenant_id=str(tenant_id), error=str(exc))


@router.get(
    "/tenants/{tenant_id}/agent-config",
    response_model=AgentConfigBundle,
    dependencies=[Depends(require_admin_token)],
)
async def get_agent_config(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> AgentConfigBundle:
    svc = AgentConfigService(session)
    versions = await svc.list_versions()
    active = await svc.get_active()
    return AgentConfigBundle(
        active=AgentConfigOut.model_validate(active) if active else None,
        versions=[AgentConfigOut.model_validate(v) for v in versions],
    )


@router.put(
    "/tenants/{tenant_id}/agent-config",
    response_model=AgentConfigOut,
    status_code=status.HTTP_201_CREATED,
)
async def stage_agent_config(
    tenant_id: uuid.UUID,
    body: AgentConfigStageIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    svc = AgentConfigService(session)
    try:
        config = await svc.stage_new_version(
            actor=f"admin:{actor[:8]}",
            system_prompt_rendered=body.system_prompt_rendered,
            channels=body.channels,
            tools=body.tools,
            policies=body.policies,
            seed_template_ref=body.seed_template_ref,
            kg_schema_id=body.kg_schema_id,
        )
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AgentConfigOut.model_validate(config)


@router.post(
    "/tenants/{tenant_id}/agent-config/{version}/promote",
    response_model=AgentConfigOut,
)
async def promote_agent_config(
    tenant_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    actor: str = Depends(require_admin_token),
    body: PromoteOverrideIn | None = None,
) -> AgentConfigOut:
    """Promote a staged ``agent_config`` version to ACTIVE.

    Block P (eval gate): when ``Tenant.eval_required=true``, the
    promote is blocked unless one of these is true:

    - There's an :class:`EvalRun` with ``status='passed'`` for the
      candidate version in the last 24h.
    - The body sets ``override=true`` with a non-empty ``reason``;
      an audit row records the override.
    """
    tenant = (
        await session.execute(sa.select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"tenant {tenant_id} not found")

    if tenant.eval_required:
        override = bool(body and body.override)
        reason = (body.reason if body else None) or ""
        if not override:
            passing = await has_passing_recent_run(
                session,
                tenant_id=tenant_id,
                agent_config_version=version,
            )
            if passing is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"eval gate: no passing eval_run for v{version} in the "
                        "last 24h. Run evals first, or pass {override: true, "
                        "reason: '…'} to bypass with an audited reason."
                    ),
                )
        else:
            if not reason.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="override=true requires a non-empty reason",
                )
            session.add(
                AuditLog(
                    tenant_id=tenant_id,
                    actor=f"admin:{actor[:8]}",
                    action="agent_config.promote.override",
                    target=f"agent_config:v{version}",
                    before_json=None,
                    after_json={"version": version, "reason": reason},
                )
            )

    svc = AgentConfigService(session)
    try:
        config = await svc.promote(version, actor=f"admin:{actor[:8]}")
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    out = AgentConfigOut.model_validate(config)
    # Notify any running worker so its AgentLoader cache picks up the new
    # active version on the next turn. Best-effort; see _publish_promote.
    await _publish_promote(redis, tenant_id)
    return out


@router.post(
    "/tenants/{tenant_id}/agent-config/{version}/rollback",
    response_model=AgentConfigOut,
)
async def rollback_agent_config(
    tenant_id: uuid.UUID,
    version: int,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    svc = AgentConfigService(session)
    try:
        config = await svc.rollback(version, actor=f"admin:{actor[:8]}")
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    out = AgentConfigOut.model_validate(config)
    await _publish_promote(redis, tenant_id)
    return out


@router.patch(
    "/tenants/{tenant_id}/agent-config/{version}/runtime",
    response_model=AgentConfigOut,
)
async def update_runtime_capabilities(
    tenant_id: uuid.UUID,
    version: int,
    body: RuntimeCapabilitiesIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    """Update the runtime feature flags + skills + MCP servers of a
    STAGED agent_config.

    The endpoint refuses ACTIVE / ARCHIVED versions on purpose: runtime
    capabilities are part of the config's identity and must travel
    through STAGED → ACTIVE so the rollback story stays atomic and the
    audit_log keeps a record of who/when each feature was turned on.

    To change capabilities on a tenant whose only version is ACTIVE,
    the operator first stages a new version (PUT
    /tenants/:id/agent-config), then patches the runtime fields on the
    new staged row.
    """
    # Look up by tenant + version (uq_agent_configs_tenant_version
    # makes the pair unique).
    config = (
        await session.execute(
            sa.select(AgentConfig).where(
                AgentConfig.tenant_id == tenant_id,
                AgentConfig.version == version,
            )
        )
    ).scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"agent_config v{version} not found for tenant {tenant_id}",
        )
    if config.status != AgentConfigStatus.STAGED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"agent_config v{version} is {config.status.value!s}; runtime "
                "capabilities can only be changed on a STAGED draft. Stage a "
                "new version first."
            ),
        )

    before = {
        "runtime_memory_tool": config.runtime_memory_tool,
        "runtime_outcome_grader": config.runtime_outcome_grader,
        "runtime_mcp_connector": config.runtime_mcp_connector,
        "runtime_skills": config.runtime_skills,
        "runtime_mcp_servers": config.runtime_mcp_servers,
    }
    config.runtime_memory_tool = body.runtime_memory_tool
    config.runtime_outcome_grader = body.runtime_outcome_grader
    config.runtime_mcp_connector = body.runtime_mcp_connector
    config.runtime_skills = (
        [s.model_dump() for s in body.runtime_skills] if body.runtime_skills else None
    )
    config.runtime_mcp_servers = (
        [s.model_dump() for s in body.runtime_mcp_servers] if body.runtime_mcp_servers else None
    )

    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=f"admin:{actor[:8]}",
            action="agent_config.runtime.update",
            target=f"agent_config:v{version}",
            before_json=before,
            after_json={
                "runtime_memory_tool": body.runtime_memory_tool,
                "runtime_outcome_grader": body.runtime_outcome_grader,
                "runtime_mcp_connector": body.runtime_mcp_connector,
                "runtime_skills": [s.model_dump() for s in body.runtime_skills],
                "runtime_mcp_servers": [s.model_dump() for s in body.runtime_mcp_servers],
            },
        )
    )
    # Build the response payload from the body + the row's stable
    # identity fields. We avoid ``model_validate(config)`` because
    # SQLAlchemy may attempt lazy attribute loads on the not-yet-
    # committed row, tripping the asyncpg greenlet check.
    return AgentConfigOut(
        id=config.id,
        tenant_id=config.tenant_id,
        version=config.version,
        status=config.status.value if hasattr(config.status, "value") else str(config.status),
        system_prompt_rendered=config.system_prompt_rendered,
        channels=config.channels or [],
        tools=config.tools or [],
        policies=config.policies or {},
        seed_template_ref=config.seed_template_ref,
        kg_schema_id=config.kg_schema_id,
        created_by=config.created_by,
        promoted_at=config.promoted_at,
        promoted_by=config.promoted_by,
        created_at=config.created_at,
        updated_at=config.updated_at,
        runtime_memory_tool=body.runtime_memory_tool,
        runtime_outcome_grader=body.runtime_outcome_grader,
        runtime_mcp_connector=body.runtime_mcp_connector,
        runtime_skills=list(body.runtime_skills) or None,
        runtime_mcp_servers=list(body.runtime_mcp_servers) or None,
    )


# ── Seed-template bootstrap (Block J) ──────────────────────────────────────
#
# Phase 1 onboarding: after the wizard creates the tenant + connects
# WhatsApp, Lee opens /tenants/[id]/agent and clicks "Aplicar plantilla
# barbershop_v1". The panel posts the placeholders gathered by the form
# (tenant.address, tenant.business_hours_label, optional overrides) and
# the backend renders the seed prompt + recommended tools + merged
# policies, then stages the result as agent_config v1. Lee reviews and
# promotes from the same UI. There is no auto-promote — the operator
# always has the last word.


class SeedTemplateOut(BaseModel):
    name: str
    version: str
    display_name: str
    tools_required: list[str]
    policies_default: dict[str, Any]


class FromSeedIn(BaseModel):
    """POST /agent-config/from-seed payload."""

    model_config = ConfigDict(extra="forbid")

    seed_template_ref: str = Field(min_length=1, max_length=80)
    placeholders: dict[str, Any] = Field(default_factory=dict)


@router.get(
    "/seed-templates",
    response_model=list[SeedTemplateOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_seed_templates_endpoint() -> list[SeedTemplateOut]:
    """List the seed templates the wizard can apply.

    Phase 1 ships only ``barbershop_v1`` (Cultor Barber). New verticals
    drop YAML files in ``services/templating/seeds/`` — no code change.
    """
    out: list[SeedTemplateOut] = []
    for name in list_seed_templates():
        tpl = load_seed_template(name)
        out.append(
            SeedTemplateOut(
                name=tpl.name,
                version=tpl.version,
                display_name=tpl.display_name,
                tools_required=tpl.tools_required,
                policies_default=tpl.policies_default,
            )
        )
    return out


@router.post(
    "/tenants/{tenant_id}/agent-config/from-seed",
    response_model=AgentConfigOut,
    status_code=status.HTTP_201_CREATED,
)
async def stage_agent_config_from_seed(
    tenant_id: uuid.UUID,
    body: FromSeedIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgentConfigOut:
    """Render the seed template and stage the result as a new version.

    The output is ``status='staged'`` — Lee promotes from /tenants/[id]/
    agent after reviewing the rendered prompt. ``seed_template_ref`` is
    persisted on the row so future audits know which template seeded it.
    """
    try:
        template = load_seed_template(body.seed_template_ref)
    except SeedTemplateNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"seed template {body.seed_template_ref!r} not found",
        ) from exc

    try:
        rendered = render_seed_template(template, placeholders=body.placeholders)
    except SeedTemplatePlaceholderMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Union the seed's required tools with the read-only ("always" mode)
    # tools of every connector this tenant has installed — BUG-E2E-02.
    # Without this, an operator who connects WooCommerce / Calendly /
    # Google Calendar BEFORE applying a seed lands on an editor where
    # the connector tools are visible but UNSELECTED, and the agent
    # silently can't use the connector until they tick each one. The
    # union mirrors the same "always-mode" filter that
    # ``auto_enable_connector_tools`` uses when the order is reversed
    # (seed first, then connect) — keeping both orderings symmetric.
    connector_tools = await _safe_connector_tools_for_tenant(session, tenant_id)
    merged_tools = sorted(set(rendered.tools) | connector_tools)

    svc = AgentConfigService(session)
    try:
        config = await svc.stage_new_version(
            actor=f"admin:{actor[:8]}",
            system_prompt_rendered=rendered.system_prompt,
            channels=[],
            tools=merged_tools,
            policies=rendered.policies,
            seed_template_ref=rendered.seed_template_ref,
        )
    except AgentConfigConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AgentConfigOut.model_validate(config)


# Statuses where a tenant's installed connector should still contribute
# tools to a freshly-seeded agent_config. ``paused`` and ``needs_reauth``
# are included because the install is still "present" — the operator
# expects to resume it; we don't want a seed-apply to silently strip the
# tool list. Mirrors ``canSelect`` in the admin editor.
_USABLE_CONNECTOR_STATUSES: tuple[str, ...] = (
    TenantConnectorStatus.CONNECTED.value,
    TenantConnectorStatus.PARTIAL.value,
    TenantConnectorStatus.PAUSED.value,
    TenantConnectorStatus.NEEDS_REAUTH.value,
)


async def _safe_connector_tools_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> set[str]:
    """Return the names of read-only ("always"-mode) tools the tenant's
    installed connectors contribute.

    Used by ``stage_agent_config_from_seed`` to pre-tick connector tools
    in a fresh seed apply (BUG-E2E-02). Filters mirror
    ``auto_enable_connector_tools`` so seed-then-connect and
    connect-then-seed produce equivalent whitelists:

    - The connector must declare ``auto_enable_on_connect=true`` (a few
      experimental connectors set this to false and require explicit
      opt-in per tool).
    - The install must be in a usable state (connected / partial /
      paused / needs_reauth).
    - The tool must be active and ``default_mode='always'`` —
      destructive tools left at ``blocked`` stay unticked, the operator
      enables them deliberately.

    Returns an empty set when no installed connector contributes
    tools — the union with ``rendered.tools`` then degrades to the
    seed's required set, preserving the legacy behaviour.
    """
    rows = (
        await session.scalars(
            sa.select(ToolCatalog.name)
            .join(Connector, Connector.id == ToolCatalog.connector_id)
            .join(
                TenantConnector,
                TenantConnector.connector_id == Connector.id,
            )
            .where(
                TenantConnector.tenant_id == tenant_id,
                TenantConnector.status.in_(_USABLE_CONNECTOR_STATUSES),
                Connector.auto_enable_on_connect.is_(True),
                ToolCatalog.default_mode == ConnectorToolMode.ALWAYS.value,
                ToolCatalog.status == ToolStatus.ACTIVE,
            )
        )
    ).all()
    return {str(name) for name in rows}


# ── Block N: "Mejorar prompt" ──────────────────────────────────────────────


class ImprovePromptIn(BaseModel):
    """POST /agent-config/improve-prompt payload.

    Body validation only — the heavy lifting (LLM call, parsing) lives
    in ``services/prompt_improver``. ``mode`` defaults to ``general``
    which runs the full four-step pipeline; focused modes (``shorter``,
    ``edge_cases``, …) narrow the rewrite scope so the operator gets
    predictable edits when iterating.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=200_000)
    mode: str = Field(default="general")
    feedback: str | None = Field(default=None, max_length=2_000)


class ImprovePromptOut(BaseModel):
    improved_prompt: str
    summary_of_changes: list[str]
    mode: str
    meta_prompt_version: str
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None


# DI hook so tests can inject ``FakePromptImproverProvider``. Production
# resolves to the LiteLLM-backed singleton.
_improver_singleton: PromptImproverProvider | None = None


async def _bind_operator_proxy(session: Any, tenant_id: uuid.UUID, provider: Any) -> Any:
    """503 if the live LiteLLM hop cannot resolve the partner virtual key."""
    if not type(provider).__name__.startswith("LiteLLM"):
        return None
    from nexus_api.core.llm_proxy import (
        LLMProxyUnavailable,
        llm_proxy_partner_scope,
        resolve_litellm_proxy_optional,
    )
    from nexus_api.metering.wallet import partner_id_for_tenant

    partner_id = await partner_id_for_tenant(session, tenant_id)
    try:
        target = resolve_litellm_proxy_optional(partner_id)
    except LLMProxyUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_proxy_unavailable"},
        ) from exc
    # Sin proxy el scope sigue abriéndose: identifica al partner para el
    # metering y para el resto de la cadena, no solo para elegir la clave.
    scoped = target.partner_id if target is not None else partner_id
    if scoped is None:
        return None
    return llm_proxy_partner_scope(scoped)


def get_prompt_improver_provider() -> PromptImproverProvider:
    global _improver_singleton
    if _improver_singleton is None:
        _improver_singleton = LiteLLMPromptImproverProvider()
    return _improver_singleton


def set_prompt_improver_provider(
    provider: PromptImproverProvider | None,
) -> None:
    """Test hook — swap the singleton. Production callers never use this."""
    global _improver_singleton
    _improver_singleton = provider


def _infer_channel(channels: list[Channel]) -> str:
    """Best-effort: the agent context block records ONE channel. We pick
    WhatsApp when present (the dominant channel in Phase 1) and fall back
    to whatever else is wired."""
    types = [ch.type.value for ch in channels if ch.status.value == "active"]
    if "whatsapp" in types:
        return "whatsapp"
    if types:
        return types[0]
    return "whatsapp"  # Phase 1 default


def _infer_language(market: str | None) -> str:
    """Cheap mapping market → IETF tag. The improver only uses this as a
    hint; the real source of truth is the draft text itself."""
    if not market:
        return "es"
    mapping = {
        "CL": "es-CL",
        "AR": "es-AR",
        "MX": "es-MX",
        "VE": "es-VE",
        "CO": "es-CO",
        "PE": "es-PE",
        "ES": "es-ES",
        "US": "en-US",
        "BR": "pt-BR",
    }
    return mapping.get(market.upper(), "es")


async def _build_agent_context(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> AgentContext:
    """Pull the tenant + the most recent agent_config (active or latest
    of any status) + the active channels and squash them into the flat
    ``AgentContext`` the improver consumes.

    We deliberately don't bail when there's no config: the improver is
    useful for greenfield prompts too. Missing context becomes ``None``
    in the meta-prompt block and the model treats it as "unknown".
    """
    tenant = (
        await session.execute(sa.select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tenant {tenant_id} not found",
        )

    config = (
        await session.execute(
            sa.select(AgentConfig)
            .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            .order_by(AgentConfig.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if config is None:
        config = (
            await session.execute(
                sa.select(AgentConfig).order_by(AgentConfig.version.desc()).limit(1)
            )
        ).scalar_one_or_none()

    seed_ref = config.seed_template_ref if config else None
    tools = tuple(config.tools) if config else ()

    channels = list(
        (await session.execute(sa.select(Channel).where(Channel.tenant_id == tenant_id))).scalars()
    )

    business_hours_label: str | None = None
    if tenant.business_hours and isinstance(tenant.business_hours, dict):
        label_field = tenant.business_hours.get("label")
        if isinstance(label_field, str) and label_field:
            business_hours_label = label_field

    agent_name: str | None = None
    if config and isinstance(config.policies, dict):
        agent_raw = config.policies.get("agent")
        if isinstance(agent_raw, dict):
            name_field = agent_raw.get("name")
            if isinstance(name_field, str) and name_field:
                agent_name = name_field

    return AgentContext(
        tenant_name=tenant.name,
        use_case=seed_ref or "generic",
        channel=_infer_channel(channels),
        language=_infer_language(tenant.market),
        available_tools=tools,
        business_hours=business_hours_label,
        agent_name=agent_name,
        timezone=tenant.timezone,
        market=tenant.market,
    )


@router.post(
    "/tenants/{tenant_id}/agent-config/improve-prompt",
    response_model=ImprovePromptOut,
)
async def improve_agent_prompt(
    tenant_id: uuid.UUID,
    body: ImprovePromptIn,
    session: AsyncSession = Depends(get_db_session),
    provider: PromptImproverProvider = Depends(get_prompt_improver_provider),
    actor: str = Depends(require_admin_token),
) -> ImprovePromptOut:
    """Block N — operator-facing prompt improver.

    Takes the draft the operator has open in the editor, builds a
    tenant-aware meta-prompt and asks Sonnet 4.6 (via LiteLLM) for a
    structured improvement. Returns the new prompt + a bullet summary
    of changes the panel renders in a diff view.

    The tenant + agent_config + channel reads run inside a tenant-scoped
    session so RLS applies; the Tenant row itself is global so we open
    the scope right before the lookup.
    """
    settings = get_settings()

    if body.mode not in SUPPORTED_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"unsupported mode {body.mode!r}; supported: {SUPPORTED_MODES}"),
        )

    from nexus_api.core.tenant_context import (
        _current_tenant,
        apply_tenant_to_session,
    )

    token = _current_tenant.set(tenant_id)
    try:
        await apply_tenant_to_session(session, tenant_id)
        context = await _build_agent_context(session, tenant_id=tenant_id)
    finally:
        _current_tenant.reset(token)

    from nexus_api.core.llm_proxy import LLMProxyUnavailable

    scope = await _bind_operator_proxy(session, tenant_id, provider)
    try:
        if scope is not None:
            with scope:
                result: ImproveResult = await improve_prompt(
                    tenant_id=tenant_id,
                    draft_prompt=body.prompt,
                    mode=body.mode,
                    feedback=body.feedback,
                    context=context,
                    provider=provider,
                    model=settings.llm_improve_model,
                    timeout_s=settings.llm_improve_timeout_s,
                    max_input_chars=settings.improve_prompt_max_input_chars,
                    max_output_tokens=settings.improve_prompt_max_output_tokens,
                )
        else:
            result = await improve_prompt(
                tenant_id=tenant_id,
                draft_prompt=body.prompt,
                mode=body.mode,
                feedback=body.feedback,
                context=context,
                provider=provider,
                model=settings.llm_improve_model,
                timeout_s=settings.llm_improve_timeout_s,
                max_input_chars=settings.improve_prompt_max_input_chars,
                max_output_tokens=settings.improve_prompt_max_output_tokens,
            )
    except LLMProxyUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_proxy_unavailable"},
        ) from exc
    except PromptTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except MalformedResponseError as exc:
        log.warning(
            "prompt_improver.malformed_response",
            tenant_id=str(tenant_id),
            reason=exc.reason,
            actor=actor[:8],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "the model returned a malformed response — retry, or "
                "switch modes. raw output preserved in logs."
            ),
        ) from exc
    except PromptImproverError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ImprovePromptOut(
        improved_prompt=result.improved_prompt,
        summary_of_changes=list(result.summary_of_changes),
        mode=result.mode,
        meta_prompt_version=result.meta_prompt_version,
        model=result.model,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cached_input_tokens=result.cached_input_tokens,
    )


# ── Block O: "Probar agente" sandbox ───────────────────────────────────────


class TestTurnIn(BaseModel):
    """POST /agent-config/test payload.

    The sandbox runs against a specific version: if ``version`` is given
    we use it explicitly; otherwise we pick the latest STAGED draft, or
    the ACTIVE version if no staged draft exists. This matches the
    operator's natural intent — "test what I just saved" → "test what's
    live".
    """

    model_config = ConfigDict(extra="forbid")

    user_message: str = Field(min_length=1, max_length=20_000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=40)
    version: int | None = Field(default=None, ge=1)


class PlannedToolCallOut(BaseModel):
    name: str
    arguments: dict[str, Any]
    tool_call_id: str
    dry_run_result: str
    iteration: int


class TestTurnOut(BaseModel):
    version_tested: int
    version_status: str
    assistant_message: str
    planned_tool_calls: list[PlannedToolCallOut]
    model: str
    iterations: int
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None


_test_agent_singleton: TestAgentProvider | None = None


def get_test_agent_provider() -> TestAgentProvider:
    global _test_agent_singleton
    if _test_agent_singleton is None:
        _test_agent_singleton = LiteLLMTestAgentProvider()
    return _test_agent_singleton


def set_test_agent_provider(provider: TestAgentProvider | None) -> None:
    """Test hook — production callers never use this."""
    global _test_agent_singleton
    _test_agent_singleton = provider


def _build_tool_defs(whitelist: list[str], tools_in_catalog: list[Any]) -> list[dict[str, Any]]:
    """Project the catalog rows to the OpenAI/Anthropic tool definition
    shape. We only include tools that are BOTH in the agent's whitelist
    AND have a row in tool_catalog — anything else would be hallucinated
    if the model tried to call it."""
    by_name = {t.name: t for t in tools_in_catalog}
    defs: list[dict[str, Any]] = []
    for name in whitelist:
        tool = by_name.get(name)
        if tool is None:
            continue
        defs.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema or {"type": "object"},
                },
            }
        )
    return defs


async def _resolve_test_version(session: AsyncSession, *, version: int | None) -> AgentConfig:
    """Resolve which agent_config version the sandbox will run against."""
    if version is not None:
        config = (
            await session.execute(sa.select(AgentConfig).where(AgentConfig.version == version))
        ).scalar_one_or_none()
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"agent_config version {version} not found",
            )
        return config

    # Default: latest STAGED draft → else latest ACTIVE.
    staged = (
        await session.execute(
            sa.select(AgentConfig)
            .where(AgentConfig.status == AgentConfigStatus.STAGED)
            .order_by(AgentConfig.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if staged is not None:
        return staged
    active = (
        await session.execute(
            sa.select(AgentConfig)
            .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            .order_by(AgentConfig.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if active is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=("no agent_config exists for this tenant — apply a seed template first"),
        )
    return active


def _validate_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for i, msg in enumerate(history):
        role = msg.get("role")
        content = msg.get("content")
        if role not in {"user", "assistant"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(f"history[{i}].role must be 'user' or 'assistant', got {role!r}"),
            )
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"history[{i}].content must be a non-empty string",
            )
        cleaned.append({"role": role, "content": content})
    return cleaned


@router.post(
    "/tenants/{tenant_id}/agent-config/test",
    response_model=TestTurnOut,
)
async def test_agent_turn(
    tenant_id: uuid.UUID,
    body: TestTurnIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    provider: TestAgentProvider = Depends(get_test_agent_provider),
    actor: str = Depends(require_admin_token),
) -> TestTurnOut:
    """Block O — operator-facing sandbox for an agent_config draft.

    Hard invariants (see ADR-014):

    - NO tool dispatch — tools are passed to the LLM as definitions and
      any tool_use blocks are captured, never executed. Synthetic
      dry-run results are fed back so the model can produce a final
      text response.
    - NO conversation / message / customer rows are written.
    - Same model + system prompt + whitelist as production.

    Version resolution: ``body.version`` if given, else latest STAGED,
    else latest ACTIVE. 404 when no agent_config exists yet.
    """
    settings = get_settings()
    history = _validate_history(body.history)

    config = await _resolve_test_version(session, version=body.version)

    # Build tool defs from the whitelist + tool_catalog rows.
    tool_catalog_rows: list[Any] = []
    if config.tools:
        result_rows = await session.execute(
            sa.select(ToolCatalog).where(ToolCatalog.name.in_(config.tools))
        )
        tool_catalog_rows = list(result_rows.scalars())
    tool_defs = _build_tool_defs(config.tools, tool_catalog_rows)

    from nexus_api.core.llm_proxy import LLMProxyUnavailable

    scope = await _bind_operator_proxy(session, tenant_id, provider)
    try:
        if scope is not None:
            with scope:
                result: TestTurnResult = await run_test_turn(
                    tenant_id=tenant_id,
                    system_prompt=config.system_prompt_rendered,
                    history=history,
                    user_message=body.user_message,
                    tool_defs=tool_defs,
                    provider=provider,
                    model=settings.llm_improve_model,
                    timeout_s=settings.llm_improve_timeout_s,
                    max_output_tokens=settings.improve_prompt_max_output_tokens,
                )
        else:
            result = await run_test_turn(
                tenant_id=tenant_id,
                system_prompt=config.system_prompt_rendered,
                history=history,
                user_message=body.user_message,
                tool_defs=tool_defs,
                provider=provider,
                model=settings.llm_improve_model,
                timeout_s=settings.llm_improve_timeout_s,
                max_output_tokens=settings.improve_prompt_max_output_tokens,
            )
    except LLMProxyUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_proxy_unavailable"},
        ) from exc
    except TestAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        # The sandbox path touches LiteLLM, the model provider, and the
        # database — any of these can throw something we didn't predict
        # (timeouts, provider 5xx, key misconfig, etc). Surface a useful
        # message to the operator instead of letting FastAPI emit a
        # bare 500 with no detail (the 2026-05-13 review caught this
        # exact failure mode on a freshly-templated tenant: toast said
        # "error 500" with nothing actionable). 502 is closer in spirit
        # since the failure is downstream of our handler.
        log.exception(
            "test_agent.unhandled_error",
            tenant_id=str(tenant_id),
            actor=actor[:8],
            version=config.version,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"sandbox falló al correr la versión {config.version}: {type(exc).__name__} — {exc}"
            ),
        ) from exc

    log.info(
        "test_agent.invoke",
        tenant_id=str(tenant_id),
        actor=actor[:8],
        version=config.version,
        version_status=config.status.value,
        planned_tool_calls=len(result.planned_tool_calls),
    )

    return TestTurnOut(
        version_tested=config.version,
        version_status=config.status.value,
        assistant_message=result.assistant_message,
        planned_tool_calls=[
            PlannedToolCallOut(
                name=p.name,
                arguments=p.arguments,
                tool_call_id=p.tool_call_id,
                dry_run_result=p.dry_run_result,
                iteration=p.iteration,
            )
            for p in result.planned_tool_calls
        ],
        model=result.model,
        iterations=result.iterations,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cached_input_tokens=result.cached_input_tokens,
    )
