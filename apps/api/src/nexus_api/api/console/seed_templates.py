"""Seed templates for the console's client wizard (CP-10).

``GET /console/seed-templates`` — the catalogue: name, vertical, and the
placeholders the partner must/may fill, described (required? secret?
kind? example) **without** the prompt text itself: the prompt is Auphere's
material and the partner reviews the *rendered* draft afterwards, in the
agent tab.

``POST /console/clients/{ref}/agent/from-seed`` — render the seed with
the partner's placeholders (the tenant's own name/timezone are always
taken from the tenant row) and stage it as version 1, a DRAFT. Nothing is
published here; publishing is the agent lane's ``.../publish``. Only
allowed while the client has no versions at all (409 otherwise): the
wizard applies a seed once, edits happen in the editor.

The staged policies always carry an explicit
``console.ai_disclosure = {enabled: true}`` decision (CP-31 default), so
publishing right after the wizard does not stall on the disclosure rule.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.console_auth import require_console_principal
from nexus_api.core.errors import AgentConfigConflict
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.agent_console_policy import with_disclosure_default
from nexus_api.services.templating.seed_templates import (
    SeedTemplate,
    SeedTemplateNotFound,
    SeedTemplatePlaceholderMissing,
    list_seed_templates,
    load_seed_template,
    render_seed_template,
)

from .agents import _version_out
from .deps import ClientScope, client_scope
from .schemas import AgentVersionOut
from .schemas_onboarding import FromSeedIn, SeedPlaceholderOut, SeedTemplateOut

router = APIRouter()

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_.]*)\}")
_PENDING_RE = re.compile(r"<<[^>]*>>")
#: Filled from the tenant row, never asked.
_AUTO_KEYS = frozenset({"tenant.name", "tenant.timezone"})
#: Policy keys whose value is payment/contact data of the client: the UI
#: asks for them without echo (``secret``).
_SECRET_WORDS = re.compile(
    r"(payment|pago|bank|banco|cuenta|account|cedula|rif|pay_id|iban|admin_phones|"
    r"secret|token|password|api_key)",
    re.IGNORECASE,
)


def _walk(node: Any, parts: list[str]) -> Any:
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    return node


def _flatten(node: Any, prefix: str, out: dict[str, Any]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            _flatten(v, f"{prefix}.{k}" if prefix else str(k), out)
    else:
        out[prefix] = node


def _kind(value: Any) -> Literal["text", "number", "list"]:
    if isinstance(value, bool):
        return "text"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, list):
        return "list"
    return "text"


def describe_placeholders(template: SeedTemplate) -> list[SeedPlaceholderOut]:
    """Pure: which values a seed needs from the partner.

    - ``tenant.name`` / ``tenant.timezone`` are never listed (tenant row).
    - ``agent.*`` with a default → optional, example = default.
    - ``policies.*`` with a default → optional (example = default), EXCEPT
      when the default is a ``<<… pendiente>>`` marker: then it is
      required, and secret when it looks like payment/contact data.
    - ``policies.admin_access.admin_phones`` when ``admin_only`` → required
      list (an empty whitelist means the agent answers nobody).
    - anything else referenced by the prompt → required text.
    Order: required first, then optional, each in first-seen order.
    """
    seen: dict[str, SeedPlaceholderOut] = {}
    keys = list(dict.fromkeys(_PLACEHOLDER_RE.findall(template.system_prompt)))
    # Pending markers in policies not referenced by the prompt still block
    # a useful agent — surface them too.
    flat: dict[str, Any] = {}
    _flatten(template.policies_default, "", flat)
    for k, v in flat.items():
        if isinstance(v, str) and _PENDING_RE.search(v) and f"policies.{k}" not in keys:
            keys.append(f"policies.{k}")
    access = template.policies_default.get("admin_access")
    if isinstance(access, dict) and access.get("admin_only") and not access.get("admin_phones"):
        keys.append("policies.admin_access.admin_phones")

    for key in keys:
        if key in _AUTO_KEYS or key in seen:
            continue
        if key.startswith("agent."):
            default = template.agent_defaults.get(key.removeprefix("agent."))
            seen[key] = SeedPlaceholderOut(
                key=key, required=default is None, example=default, kind="text"
            )
            continue
        if key.startswith("policies."):
            default = _walk(template.policies_default, key.removeprefix("policies.").split("."))
            pending = isinstance(default, str) and bool(_PENDING_RE.search(default))
            empty_list = isinstance(default, list) and not default
            required = default is None or pending or empty_list
            example: str | None = None
            if default is not None and not pending and not empty_list:
                example = (
                    ", ".join(map(str, default)) if isinstance(default, list) else str(default)
                )
            seen[key] = SeedPlaceholderOut(
                key=key,
                required=required,
                secret=bool(_SECRET_WORDS.search(key)) and required,
                kind="list" if isinstance(default, list) else _kind(default),
                example=example,
            )
            continue
        # Business facts the prompt states out loud (address, opening
        # hours, front-desk phone…) — public by nature, never secret.
        seen[key] = SeedPlaceholderOut(key=key, required=True, kind="text")
    ordered = sorted(seen.values(), key=lambda p: (not p.required,))
    return ordered


def _vertical(name: str) -> str:
    return name.rsplit("_v", 1)[0] if "_v" in name else name


def _template_out(tpl: SeedTemplate) -> SeedTemplateOut:
    return SeedTemplateOut(
        name=tpl.name,
        display_name=tpl.display_name,
        version=tpl.version,
        vertical=_vertical(tpl.name),
        tools_count=len(tpl.tools_required),
        placeholders=describe_placeholders(tpl),
    )


@router.get("/seed-templates", response_model=list[SeedTemplateOut])
async def list_console_seed_templates(
    _principal: object = Depends(require_console_principal("agents:read")),
) -> list[SeedTemplateOut]:
    """Every seed on disk, described for the wizard. No prompt text."""
    return [_template_out(load_seed_template(name)) for name in list_seed_templates()]


def _coerce(placeholders: dict[str, Any], described: list[SeedPlaceholderOut]) -> dict[str, Any]:
    """Comma-separated strings → lists for ``kind=list`` keys; drop empties
    so a blank optional field falls back to the seed default."""
    kinds = {p.key: p.kind for p in described}
    out: dict[str, Any] = {}
    for key, value in placeholders.items():
        # Only the placeholders the seed DESCRIBES are accepted: the
        # renderer would honour any ``policies.<x>`` key (a backoffice
        # feature), which from the console would let a partner write
        # platform keys such as ``llm.respond_model``.
        if key not in kinds:
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if kinds.get(key) == "list" and isinstance(value, str):
            out[key] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            out[key] = value
    return out


async def stage_from_seed(
    session: AsyncSession,
    scope: ClientScope,
    *,
    seed_template: str,
    placeholders: dict[str, Any],
) -> AgentVersionOut:
    """Shared by the endpoint and ``POST /console/clients`` (``seed_template``).
    Must run inside the client's scoped transaction."""
    try:
        template = load_seed_template(seed_template)
    except SeedTemplateNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"seed template {seed_template!r} not found",
        ) from None
    service = AgentConfigService(session)
    if await service.list_versions():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this client already has agent versions; edit them in the agent tab",
        )
    resolved = _coerce(placeholders, describe_placeholders(template))
    # The tenant row is authoritative for its own identity.
    resolved["tenant.name"] = scope.tenant.name
    resolved["tenant.timezone"] = scope.tenant.timezone
    try:
        rendered = render_seed_template(template, placeholders=resolved)
    except SeedTemplatePlaceholderMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"missing placeholder: {exc.key}",
        ) from exc
    policies = with_disclosure_default(rendered.policies, actor=scope.principal.actor)
    try:
        cfg = await service.stage_new_version(
            actor=scope.principal.actor,
            system_prompt_rendered=rendered.system_prompt,
            channels=[],
            tools=list(rendered.tools),
            policies=policies,
            seed_template_ref=rendered.seed_template_ref,
        )
    except AgentConfigConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _version_out(cfg)


@router.post(
    "/clients/{ref}/agent/from-seed",
    response_model=AgentVersionOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Unknown client or seed template."},
        409: {"description": "The client already has agent versions."},
        422: {"description": "A required placeholder is missing."},
    },
)
async def stage_agent_from_seed(
    body: FromSeedIn,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> AgentVersionOut:
    return await stage_from_seed(
        scope.session, scope, seed_template=body.seed_template, placeholders=body.placeholders
    )


__all__ = ["describe_placeholders", "router", "stage_from_seed"]
