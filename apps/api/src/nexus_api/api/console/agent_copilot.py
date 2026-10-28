"""El copiloto en la consola — spec 047, T099 (requisito 19; ``console-api.md`` §4).

- ``POST …/agents/{agent_id}/copilot`` [``agents:read``] ``{message, context?}``:
  responde con citas y propuestas. ``context`` puede traer la respuesta del
  playground que se pregunta (``answer`` y ``actions``) o una prueba
  (``test_id``: se toma su última respuesta). A quien no puede escribir en el
  agente solo le explica (19.5).
- ``POST …/copilot/fix`` [``agents:write``] ``{test_id, scope, value}``: la persona
  confirma el alcance de un arreglo (19.4) y entonces se aplica.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from nexus_api.db.models import Agent
from nexus_api.db.models.agent_spec import AgentTest, AgentTestResult
from nexus_api.services.agent_spec.patch import apply_ops
from nexus_api.services.agent_spec.schema import dump
from nexus_api.services.agent_spec.validator import load_context, problems_out, validate_spec
from nexus_api.services.builder import copilot as copilot_service
from nexus_api.services.builder.fixes import agent_fix_ops, business_fix
from nexus_api.services.business.compilation import load_facts
from nexus_api.services.business.sections import Actor
from nexus_api.services.testing.suites import ensure_suite

from .agent_draft_routes import agent_in_path
from .agent_spec_drafts import current_spec, spec_state_hash, write_spec
from .deps import ClientScope

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}/copilot")

_complete_override: Any | None = None


def set_copilot_model(complete: Any | None) -> None:
    """Gancho de pruebas: el modelo del copiloto."""
    global _complete_override
    _complete_override = complete


def _complete() -> Any | None:
    if _complete_override is not None:
        return _complete_override
    import os

    from nexus_worker.config import get_worker_settings

    settings = get_worker_settings()
    if settings.llm_use_inmemory:
        return None
    from nexus_worker.runtime.llm import LiteLLMProvider

    provider = LiteLLMProvider(context_management=None)
    model = os.environ.get("NEXUS_LLM_BUILD_MODEL") or settings.llm_respond_model

    async def complete(messages: list[dict[str, str]]) -> str:
        return str(
            await provider.acomplete(
                tenant_id=uuid.UUID(int=0), role="build", model=model, messages=messages
            )
        )

    return complete


class CopilotContextIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str | None = Field(default=None, max_length=4000)
    actions: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    test_id: uuid.UUID | None = None


class CopilotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(default="", max_length=1000)
    context: CopilotContextIn | None = None


class FixIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_id: uuid.UUID
    scope: Literal["business", "agent"]
    value: str = Field(min_length=1, max_length=2000)


async def _test(scope: ClientScope, test_id: uuid.UUID) -> AgentTest:
    assert scope.agent_id is not None
    suite = await ensure_suite(scope.session, scope.agent_id)
    test = await scope.session.get(AgentTest, test_id)
    if test is None or test.suite_id != suite.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "unknown_test"})
    return test


@router.post("")
async def ask(
    body: CopilotIn, scope: ClientScope = Depends(agent_in_path("agents:read"))
) -> dict[str, Any]:
    assert scope.agent_id is not None
    spec, _cfg = await current_spec(scope)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "no_version"})
    agent = await scope.session.get(Agent, scope.agent_id)
    assert agent is not None
    context: dict[str, Any] = body.context.model_dump(exclude_none=True) if body.context else {}
    if body.context and body.context.test_id is not None and not body.context.answer:
        test = await _test(scope, body.context.test_id)
        last = await scope.session.scalar(
            sa.select(AgentTestResult)
            .where(AgentTestResult.test_id == test.id)
            .order_by(AgentTestResult.created_at.desc(), AgentTestResult.attempt.desc())
            .limit(1)
        )
        if last is not None:
            agent_turns = [t for t in last.transcript or [] if t.get("role") == "agent"]
            if agent_turns:
                context["answer"] = " ".join(agent_turns[-1].get("bubbles") or [])
        context["test_id"] = str(test.id)
    answer = await copilot_service.ask(
        scope.session,
        agent_id=scope.agent_id,
        spec=spec,
        state_hash=spec_state_hash(spec),
        facts=await load_facts(scope.session, agent),
        message=body.message,
        context=context,
        can_write="agents:write" in scope.principal.permissions,
        actor=scope.principal.actor,
        partner_id=scope.principal.partner.id,
        complete=_complete(),
    )
    return answer.to_json()


@router.post("/fix")
async def fix(
    body: FixIn, scope: ClientScope = Depends(agent_in_path("agents:write"))
) -> dict[str, Any]:
    """La persona confirma dónde se corrige el dato (19.4)."""
    test = await _test(scope, body.test_id)
    if body.scope == "business":
        person = Actor(kind="partner_member", id=scope.principal.user_id, origin="console")
        return await business_fix(scope.session, test=test, value=body.value, actor=person)
    spec, _cfg = await current_spec(scope)
    assert spec is not None
    patched = apply_ops(dump(spec), agent_fix_ops(test, body.value))
    ctx = await load_context(scope.session, partner_id=scope.principal.partner.id)
    checked, problems = validate_spec(patched, ctx, author="person")
    if checked is None or problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_fix", "problems": problems_out(problems)},
        )
    await write_spec(scope, checked, expected_revision=None)
    return {"scope": "agent", "pointer": "/services/faqs"}


__all__ = ["router", "set_copilot_model"]
