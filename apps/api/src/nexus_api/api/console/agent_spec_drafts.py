"""El AgentSpec en el borrador de un agente — spec 047, T080 (requisitos 3, 16 y 17.7).

Lo comparten la ruta del borrador (``PATCH …/draft`` con ``spec``), las
respuestas al constructor y aplicar una propuesta:

- :func:`spec_of` lee el AgentSpec de una versión; una de antes de la 047 no lo
  tiene y se lee en modo «instrucciones» (``legacy.spec_from_version``), que
  compila los mismos bytes;
- :func:`write_spec` lo escribe en el borrador (lo crea si hace falta), compila
  su prompt con la ficha del cliente, sincroniza las herramientas, la política de
  modelo y la decisión del aviso de IA con lo que lee el runtime, y marca las
  pruebas del agente como no ejecutadas (17.7). La revisión del borrador se mueve
  como en cualquier escritura (``If-Match``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nexus_api.db.models import Agent, AgentConfig
from nexus_api.services.agent_console_policy import POLICY_KEY, AiDisclosurePolicy
from nexus_api.services.agent_spec.compiler import compile_spec
from nexus_api.services.agent_spec.legacy import (
    _TOOL,
    runtime_model_policy,
    spec_from_version,
)
from nexus_api.services.agent_spec.schema import AgentSpec, dump
from nexus_api.services.business.compilation import load_facts
from nexus_api.services.proposal_state import canonical_hash
from nexus_api.services.reception import tools_with_handoff
from nexus_api.services.testing.suites import mark_stale

from .agent_drafts import draft_written, ensure_draft, load_view
from .deps import ClientScope


def spec_of(cfg: AgentConfig | None, agent: Agent) -> AgentSpec | None:
    if cfg is None:
        return None
    if cfg.spec:
        return AgentSpec.model_validate(cfg.spec)
    return spec_from_version(
        agent_name=agent.name,
        system_prompt_rendered=cfg.system_prompt_rendered or "",
        tools=list(cfg.tools or []),
        policies=dict(cfg.policies or {}),
    )


def spec_state_hash(spec: AgentSpec | None) -> str:
    """La huella del documento sobre el que se hace una propuesta."""
    return canonical_hash(dump(spec) if spec is not None else None)


async def current_spec(scope: ClientScope) -> tuple[AgentSpec | None, AgentConfig | None]:
    """El AgentSpec del borrador, o de la versión de la que partiría."""
    agent = await scope.session.get(Agent, scope.agent_id)
    assert agent is not None
    view = await load_view(scope)
    return spec_of(view.target, agent), view.target


def _sync_disclosure(policies: dict[str, Any], spec: AgentSpec, *, actor: str) -> dict[str, Any]:
    out = dict(policies)
    console = dict(out.get(POLICY_KEY) or {}) if isinstance(out.get(POLICY_KEY), dict) else {}
    disclosure = spec.ai_disclosure
    if disclosure.decided:
        console["ai_disclosure"] = AiDisclosurePolicy(
            enabled=disclosure.mode is not None,
            disclosure_message=disclosure.text or "",
            decided_by=actor,
            decided_at=datetime.now(UTC),
        ).model_dump(mode="json")
    else:
        console.pop("ai_disclosure", None)
    if console:
        out[POLICY_KEY] = console
    else:
        out.pop(POLICY_KEY, None)
    return out


async def write_spec(
    scope: ClientScope, spec: AgentSpec, *, expected_revision: int | None
) -> AgentConfig:
    """Escribe ``spec`` en el borrador del agente de la ruta. El llamante ya lo
    validó (``validator.validate_spec``)."""
    session = scope.session
    agent = await session.get(Agent, scope.agent_id)
    assert agent is not None
    draft, _created = await ensure_draft(
        scope, expected_revision=expected_revision, disclosure_default=False
    )
    doc = dump(spec)
    previous = dict(draft.spec or {})
    if "test_suite" not in doc and previous.get("test_suite"):
        doc["test_suite"] = previous["test_suite"]
    draft.spec = doc
    draft.system_prompt_rendered = compile_spec(spec, await load_facts(session, agent))
    if spec.mode == "structured":
        draft.tools = list(spec.tools or [])
    else:
        # Una herramienta de antes sin la forma del catálogo sigue en la versión.
        legacy = [t for t in (draft.tools or []) if not _TOOL.match(t)]
        draft.tools = list(dict.fromkeys([*legacy, *(spec.tools or [])]))
    # Spec 047 (requisito 53.1): la sección Recepción pone y quita la herramienta
    # de derivar; nadie más la lleva en su lista.
    draft.tools = tools_with_handoff(draft.tools or [], doc)
    policies = dict(draft.policies or {})
    runtime = runtime_model_policy(spec)
    if runtime is None:
        policies.pop("model_policy", None)
    else:
        policies["model_policy"] = runtime
    draft.policies = _sync_disclosure(policies, spec, actor=scope.principal.actor)
    await mark_stale(session, agent.id)
    await draft_written(scope, draft)
    return draft


__all__ = ["current_spec", "spec_of", "spec_state_hash", "write_spec"]
