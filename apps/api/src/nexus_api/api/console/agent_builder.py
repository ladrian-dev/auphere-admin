"""El constructor de agentes en la consola — spec 047, T080 (requisitos 15, 16 y
17; ``contracts/console-api.md`` §4).

- ``GET /clients/{ref}/agents/draft-options``: los ejemplos y las plantillas de
  «Nuevo agente», con la del partner primero y sin aplicarla (17.8, 17.9).
- ``POST /clients/{ref}/agents/draft-jobs`` [``agents:write``]: «Generar
  borrador» → ``202 {job_id}``. El agente **no** nace aquí sino con el primer
  borrador, en el trabajo (17.2). «Desde una plantilla» y «En blanco» crean el
  agente y su borrador al momento y responden con el trabajo ya terminado.
- ``POST /jobs/{job_id}/answers`` [``agents:write``]: las respuestas a las
  preguntas del constructor, cada una en la ficha (por defecto) o en «Solo este
  agente» (17.5). Cambian el borrador: sus pruebas quedan sin ejecutar (17.7).
- ``GET …/agents/{agent_id}/proposals`` y ``POST …/proposals/{id}/apply`` ·
  ``/reject``: lo que propusieron el constructor o el copiloto. Aplicar exige la
  misma huella del borrador y menos de 15 minutos; el validador vuelve a pasar.

Nada de esto depende del módulo ``companion`` (15.1).
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, Job, Partner, PartnerTenant, Proposal, Tenant
from nexus_api.services import agents as agent_service
from nexus_api.services import jobs as jobs_service
from nexus_api.services import proposal_state
from nexus_api.services.agent_spec.patch import PatchError, apply_ops
from nexus_api.services.agent_spec.schema import AgentSpec, dump
from nexus_api.services.agent_spec.validator import load_context, problems_out, validate_spec
from nexus_api.services.builder.agent_draft import (
    AGENT_TARGETS,
    BUSINESS_TARGETS,
    DraftInputInvalid,
    DraftRequest,
)
from nexus_api.services.builder.sectors import OTHER, TEMPLATE_SECTOR, sector_name
from nexus_api.services.business.sections import Actor
from nexus_api.services.templating.seed_templates import list_seed_templates, load_seed_template

from .agent_draft_routes import agent_in_path
from .agent_spec_drafts import current_spec, spec_state_hash, write_spec
from .deps import ClientScope, client_scope, require_build_room, resolve_mapping
from .jobs import _owned_tenant, unknown_job
from .schemas_agent_builder import (
    AnswerAppliedOut,
    AnswersIn,
    AnswersOut,
    DraftJobIn,
    DraftJobOut,
    DraftOptionsOut,
    ProposalDecisionOut,
    ProposalOut,
    TemplateOptionOut,
)

log = structlog.get_logger(__name__)

router = APIRouter()

ClientRef = Path(..., description="The client's external reference.")

#: Ejemplos para empezar (17.1): frases de negocio, no prompts.
EXAMPLES: tuple[str, ...] = (
    "Atiende las citas de la barbería por WhatsApp: busca hueco, reserva y recuerda "
    "la política de cancelación.",
    "Responde las dudas de la clínica sobre horarios, precios y cómo llegar, y pasa "
    "al equipo lo que no sepa.",
    "Toma los pedidos al por mayor, envía el catálogo y cobra con enlace.",
    "Recuerda a los clientes sus pagos pendientes con amabilidad y ofrece el enlace.",
)

_BLANK_DESCRIPTION = "Agente en blanco: describe aquí qué tiene que hacer y a quién atiende."


def _error(code: str, status_code: int, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, **extra})


# ── «Nuevo agente» ──────────────────────────────────────────────────────────


@router.get("/clients/{ref}/agents/draft-options", response_model=DraftOptionsOut)
async def draft_options(
    scope: ClientScope = Depends(client_scope("agents:read")),
) -> DraftOptionsOut:
    partner = await scope.session.get(Partner, scope.principal.partner.id)
    default = partner.default_seed_template if partner is not None else None
    templates: list[TemplateOptionOut] = []
    for name in list_seed_templates():
        try:
            tpl = load_seed_template(name)
        except Exception:  # una plantilla rota no tumba la pantalla
            continue
        group = TEMPLATE_SECTOR.get(name, OTHER)
        templates.append(
            TemplateOptionOut(
                id=name,
                name=tpl.display_name or name,
                group=sector_name(group),
                is_default=name == default,
            )
        )
    # 17.9: la del partner, la primera (y nunca aplicada sola).
    templates.sort(key=lambda t: (not t.is_default, t.group == "Otro", t.group, t.name))
    return DraftOptionsOut(
        examples=list(EXAMPLES),
        templates=templates,
        default_template=default if any(t.id == default for t in templates) else None,
    )


def _blank_spec(name: str, description: str) -> AgentSpec:
    return AgentSpec.model_validate(
        {
            "schema_version": "1",
            "mode": "structured",
            "identity": {"name": name, "description": description},
            "voice": {"languages": ["es"]},
            "instructions": {"sections": [{"title": "Qué haces", "body": description}]},
            "services": {"mode": "all"},
            "tools": [],
            "escalation": {"triggers": ["asks_for_human"], "failed_attempts": 2},
            "ai_disclosure": {"decided": False},
            "model_policy": {"kind": "pinned", "deployment": "nexus/current-binding"},
            "memory": {"scope": "shared"},
        }
    )


@router.post(
    "/clients/{ref}/agents/draft-jobs",
    response_model=DraftJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"description": "Unknown template."},
        409: {"description": "name_taken"},
        422: {"description": "name_length · description_length · template_required"},
    },
)
async def start_draft(
    body: DraftJobIn,
    ref: str = ClientRef,
    principal: ConsolePrincipal = Depends(require_console_principal("agents:write")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> DraftJobOut:
    """«Generar borrador», «Desde una plantilla» o «En blanco»."""
    await require_build_room(principal.partner.id)
    mapping = await resolve_mapping(session, principal, ref)
    if body.start == "describe":
        try:
            request = DraftRequest.clean(body.name, body.description or "")
        except DraftInputInvalid as exc:
            raise _error(exc.code, status.HTTP_422_UNPROCESSABLE_CONTENT) from exc
        async with tenant_scoped_session(session, mapping.tenant_id):
            # El nombre se comprueba antes de encolar: el trabajo no debe fallar
            # por algo que la pantalla puede decir al momento.
            if await _name_taken(session, request.name):
                raise _error("name_taken", status.HTTP_409_CONFLICT)
            job = await jobs_service.create_job(
                session, kind="agent_draft", created_by=principal.user_id
            )
            job.progress = {
                "step": None,
                "blocks": [],
                "input": {
                    "name": request.name,
                    "description": request.description,
                    "actor": principal.actor,
                },
            }
            await session.flush()
            out = DraftJobOut(job_id=job.id, status="queued")
        try:
            await jobs_service.enqueue_job(redis, job)
        except Exception as exc:  # la fila es la verdad: caduca y se reintenta
            log.warning("console.builder.enqueue_failed", error=type(exc).__name__)
        return out

    # «Desde una plantilla» y «En blanco»: el agente y su borrador, ya.
    async with tenant_scoped_session(session, mapping.tenant_id):
        tenant = await session.get(Tenant, mapping.tenant_id)
        assert tenant is not None
        scope = ClientScope(principal=principal, mapping=mapping, tenant=tenant, session=session)
        try:
            agent = await agent_service.create_agent(
                session, mapping.tenant_id, name=body.name, actor=principal.actor
            )
        except agent_service.AgentError as exc:
            raise _error(exc.code, exc.status) from None
        scoped = replace(scope, agent_id=agent.id)
        if body.start == "template":
            if not body.template_id:
                raise _error("template_required", status.HTTP_422_UNPROCESSABLE_CONTENT)
            from .seed_templates import stage_from_seed

            placeholders = await _placeholders_from_ficha(session, agent)
            await stage_from_seed(
                session, scoped, seed_template=body.template_id, placeholders=placeholders
            )
        else:
            description = (body.description or "").strip()
            if len(description) < 20:
                description = _BLANK_DESCRIPTION
            await write_spec(
                scoped, _blank_spec(agent.name, description[:1024]), expected_revision=None
            )
        job = await jobs_service.create_job(
            session, kind="agent_draft", agent_id=agent.id, created_by=principal.user_id
        )
        await jobs_service.start_job(session, job.id)
        await jobs_service.finish_job(
            session,
            job.id,
            result={
                "agent_id": str(agent.id),
                "start": body.start,
                "template_id": body.template_id,
                "questions": [],
                "discarded": {"count": 0, "reasons": []},
                "log": {"input": {"name": agent.name}, "decision": f"start_{body.start}"},
            },
        )
        return DraftJobOut(job_id=job.id, status="done", agent_id=agent.id)


async def _name_taken(session: AsyncSession, name: str) -> bool:
    clean = " ".join(name.split())
    found = await session.scalar(
        sa.select(Agent.id).where(
            sa.func.lower(Agent.name) == clean.lower(), Agent.status != "archived"
        )
    )
    return found is not None


async def _placeholders_from_ficha(session: AsyncSession, agent: Agent) -> dict[str, Any]:
    """Lo que una plantilla pide del negocio sale de la ficha, no de un formulario
    aparte: dirección y horario (con su frase), y el nombre del agente."""
    from nexus_api.services.business.compilation import load_facts

    facts = await load_facts(session, agent)
    address = (
        facts.locations[0].split(" · ")[1]
        if facts.locations and " · " in facts.locations[0]
        else ""
    )
    return {
        "agent.name": agent.name,
        "tenant.address": address or "Sin dirección registrada: atiende online.",
        "tenant.business_hours_label": facts.hours or "Sin horario registrado.",
    }


# ── las respuestas a las preguntas ──────────────────────────────────────────


def _agent_target(target: str, question: dict[str, Any], value: str) -> tuple[str, Any]:
    """Una respuesta de negocio guardada en «Solo este agente»: como regla o como
    pregunta frecuente propia."""
    if target == "/faqs/-":
        return "/services/faqs/-", {"q": question["text"][:300], "a": value[:2000]}
    if target.startswith("/policies/"):
        return "/rules/-", f"{question['text'][:120]} {value}"[:300]
    if target == "/voice/register":
        choice = value.strip().lower().replace("ú", "u")
        if choice not in {"tu", "usted", "vos"}:
            raise _error(
                "invalid_answer", status.HTTP_422_UNPROCESSABLE_CONTENT, question_id=question["id"]
            )
        return target, choice
    if target in {"/rules/-"}:
        return target, value[:300]
    if target == "/services/faqs/-":
        return target, {"q": question["text"][:300], "a": value[:2000]}
    return target, value[:500]


@router.post(
    "/jobs/{job_id}/answers",
    response_model=AnswersOut,
    responses={404: {"description": "Unknown job"}, 409: {"description": "job_not_ready"}},
)
async def answer_questions(
    body: AnswersIn,
    job_id: uuid.UUID = Path(...),
    principal: ConsolePrincipal = Depends(require_console_principal("agents:write")),
    session: AsyncSession = Depends(get_db_session),
) -> AnswersOut:
    from nexus_api.services.business import faqs as faq_service
    from nexus_api.services.business.profile_edits import update_policies

    tenant_id = await _owned_tenant(session, principal, job_id)
    if tenant_id is None:
        raise unknown_job()
    async with tenant_scoped_session(session, tenant_id):
        job = await session.get(Job, job_id, with_for_update=True)
        if job is None or job.kind != "agent_draft":
            raise unknown_job()
        if job.status != "done" or job.agent_id is None:
            raise _error("job_not_ready", status.HTTP_409_CONFLICT)
        questions = {q["id"]: q for q in (job.result or {}).get("questions") or []}
        mapping = await session.scalar(
            sa.select(PartnerTenant).where(
                PartnerTenant.partner_id == principal.partner.id,
                PartnerTenant.tenant_id == tenant_id,
            )
        )
        tenant = await session.get(Tenant, tenant_id)
        assert mapping is not None and tenant is not None
        scope = ClientScope(
            principal=principal,
            mapping=mapping,
            tenant=tenant,
            session=session,
            agent_id=job.agent_id,
        )
        person = Actor(kind="partner_member", id=principal.user_id, origin="console")
        ops: list[dict[str, Any]] = []
        applied: list[AnswerAppliedOut] = []
        for answer in body.answers:
            question = questions.get(answer.question_id)
            if question is None:
                raise _error(
                    "unknown_question",
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    question_id=answer.question_id,
                )
            target = str(question["target"])
            scope_of = answer.scope or question["scope"]
            if scope_of == "business" and target not in BUSINESS_TARGETS:
                scope_of = "agent"
            value = answer.value.strip()
            if scope_of == "business":
                if target == "/faqs/-":
                    await faq_service.create_faq(session, q=question["text"], a=value, actor=person)
                else:
                    await update_policies(
                        session,
                        {target.rsplit("/", 1)[1]: value},
                        actor=person,
                        audit_actor=principal.actor,
                    )
            else:
                path, item = _agent_target(target, question, value)
                if (
                    path not in AGENT_TARGETS
                    and not path.startswith("/rules")
                    and path != "/services/faqs/-"
                ):
                    raise _error(
                        "invalid_answer",
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        question_id=question["id"],
                    )
                ops.append({"op": "add", "path": path, "value": item})
            applied.append(
                AnswerAppliedOut(question_id=answer.question_id, scope=scope_of, target=target)
            )

        spec, _cfg = await current_spec(scope)
        assert spec is not None
        doc = dump(spec)
        if ops:
            try:
                doc = apply_ops(doc, ops)
            except PatchError as exc:
                raise _error(
                    "invalid_answer", status.HTTP_422_UNPROCESSABLE_CONTENT, pointer=exc.pointer
                ) from exc
        ctx = await load_context(session, partner_id=principal.partner.id)
        checked, problems = validate_spec(doc, ctx, author="person")
        if checked is None or problems:
            raise _error(
                "invalid_answer",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                problems=problems_out(problems),
            )
        # La ficha cambió o el borrador cambió: el borrador se compila con lo
        # nuevo y sus pruebas quedan sin ejecutar (17.7).
        draft = await write_spec(scope, checked, expected_revision=None)
        job.answers = {
            **(job.answers or {}),
            **{
                a.question_id: {"value": a.value, "scope": x.scope}
                for a, x in zip(body.answers, applied, strict=True)
            },
        }
        from nexus_api.services.testing.suites import get_suite, list_tests

        suite = await get_suite(session, job.agent_id)
        stale = sum(1 for t in await list_tests(session, suite) if t.stale) if suite else 0
        revision = await _draft_revision(session, job.agent_id)
        return AnswersOut(
            applied=applied,
            agent_id=draft.agent_id or job.agent_id,
            draft_revision=revision,
            tests_stale=stale,
        )


async def _draft_revision(session: AsyncSession, agent_id: uuid.UUID) -> int:
    agent = await session.get(Agent, agent_id, populate_existing=True)
    return int(agent.draft_revision) if agent is not None else 0


# ── propuestas ──────────────────────────────────────────────────────────────


def _proposal_out(p: Proposal, problems: list[dict[str, str]] | None = None) -> ProposalOut:
    return ProposalOut(
        id=p.id,
        kind=p.kind,
        author=p.author,
        summary=p.summary,
        diff=p.diff,
        status=p.status,
        created_at=p.created_at,
        expires_at=p.expires_at,
        problems=problems or [],
    )


@router.get("/clients/{ref}/agents/{agent_id}/proposals", response_model=list[ProposalOut])
async def list_proposals(
    scope: ClientScope = Depends(agent_in_path("agents:read")),
) -> list[ProposalOut]:
    await proposal_state.expire_open(scope.session)
    rows = (
        await scope.session.scalars(
            sa.select(Proposal)
            .where(
                Proposal.tenant_id == scope.tenant.id,
                Proposal.agent_id == scope.agent_id,
                Proposal.status == "open",
            )
            .order_by(Proposal.created_at.desc())
        )
    ).all()
    return [_proposal_out(p) for p in rows]


def _proposal_error(exc: proposal_state.ProposalError) -> HTTPException:
    return _error(exc.code, exc.status)


@router.post(
    "/clients/{ref}/agents/{agent_id}/proposals/{proposal_id}/apply",
    response_model=ProposalDecisionOut,
    responses={
        404: {"description": "Unknown proposal"},
        409: {"description": "proposal_stale · proposal_closed"},
        410: {"description": "proposal_expired"},
        422: {"description": "The patched spec does not pass the validator."},
    },
)
async def apply_proposal(
    proposal_id: uuid.UUID,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
) -> ProposalDecisionOut:
    """Aplicar es de una persona con permiso (15.2), sobre el estado sobre el que
    se hizo (15.3), y pasando otra vez el validador (15.4)."""
    proposal = await proposal_state.get_open(scope.session, proposal_id, agent_id=scope.agent_id)
    if proposal is None:
        raise _error("unknown_proposal", status.HTTP_404_NOT_FOUND)
    if proposal.kind not in {"agent_spec_patch", "fix", "test_add"}:
        raise _error("unsupported_proposal", status.HTTP_409_CONFLICT)
    spec, _cfg = await current_spec(scope)
    try:
        proposal_state.accept(
            proposal, current_state_hash=spec_state_hash(spec), actor=scope.principal.actor
        )
    except proposal_state.ProposalError as exc:
        raise _proposal_error(exc) from None
    revision: int | None = None
    if proposal.kind == "test_add":
        from nexus_api.services.testing.suites import add_test, ensure_suite

        suite = await ensure_suite(scope.session, scope.agent_id)  # type: ignore[arg-type]
        await add_test(
            scope.session, suite, dict(proposal.diff.get("test") or {}), kind="person", by="builder"
        )
    else:
        assert spec is not None
        try:
            doc = apply_ops(dump(spec), list(proposal.diff.get("ops") or []))
        except PatchError as exc:
            raise _error(
                "invalid_proposal", status.HTTP_422_UNPROCESSABLE_CONTENT, pointer=exc.pointer
            ) from exc
        ctx = await load_context(scope.session, partner_id=scope.principal.partner.id)
        checked, problems = validate_spec(doc, ctx, author=proposal.author)  # type: ignore[arg-type]
        if checked is None or problems:
            raise _error(
                "invalid_proposal",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                problems=problems_out(problems),
            )
        await write_spec(scope, checked, expected_revision=None)
        revision = await _draft_revision(scope.session, scope.agent_id)  # type: ignore[arg-type]
    return ProposalDecisionOut(id=proposal.id, status=proposal.status, draft_revision=revision)


@router.post(
    "/clients/{ref}/agents/{agent_id}/proposals/{proposal_id}/reject",
    response_model=ProposalDecisionOut,
)
async def reject_proposal(
    proposal_id: uuid.UUID,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
) -> ProposalDecisionOut:
    proposal = await proposal_state.get_open(scope.session, proposal_id, agent_id=scope.agent_id)
    if proposal is None:
        raise _error("unknown_proposal", status.HTTP_404_NOT_FOUND)
    try:
        proposal_state.reject(proposal, actor=scope.principal.actor)
    except proposal_state.ProposalError as exc:
        raise _proposal_error(exc) from None
    return ProposalDecisionOut(id=proposal.id, status=proposal.status)


__all__ = ["EXAMPLES", "router"]
