"""«Guardar» en la consola — spec 047, T093 (requisitos 23 y 24; ``console-api.md`` §4).

- ``GET …/agents/{agent_id}/publish-preview`` [``agents:read``]: lo que diría el
  botón («Guardar», «Guardar y conectar un canal» o «Guardar cambios», 23.4 y
  23.5), el diff en lenguaje llano y la puerta tal como está ahora;
- ``POST …/publish`` [``agents:write``] ``{note?, accept_normal_failures?,
  override_reason?}`` → ``202 {job_id}``: prueba, revisa, decide y publica en el
  worker. Saltar la puerta es de owner o admin (``override_forbidden``, 23.3);
- ``POST …/publish/undo``: «Deshacer», durante 10 minutos (24.1);
- ``GET …/history`` y ``POST …/versions/{n}/restore``: el historial con su diff y
  sus pruebas (24.2), y restaurar como borrador, que pasa la puerta (24.3).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, Channel
from nexus_api.services import jobs as jobs_service
from nexus_api.services import publishing

from .agent_draft_routes import agent_in_path
from .deps import ClientScope, resolve_mapping

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}")

PROMOTE_CHANNEL = "nexus:agent_config:promote"

#: Las partes del AgentSpec, dichas para el partner (23.5).
PART_NAMES: dict[str, str] = {
    "identity": "Nombre y descripción",
    "voice": "Cómo habla",
    "instructions": "Instrucciones",
    "procedures": "Procedimientos",
    "services": "Servicios que atiende",
    "skills": "Habilidades",
    "tools": "Lo que puede hacer",
    "connection_requests": "Conectores que pide",
    "escalation": "Cuándo pasa a una persona",
    "rules": "Reglas",
    "team_access": "Personas del equipo",
    "ai_disclosure": "Aviso de IA",
    "model_policy": "Calidad (modelo)",
    "memory": "Memoria",
    "reception": "Recepción",
    "prompt": "Instrucciones",
}


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)
    accept_normal_failures: bool = False
    override_reason: str | None = Field(default=None, max_length=500)


class PublishAcceptedOut(BaseModel):
    job_id: uuid.UUID


class PreviewOut(BaseModel):
    action: Literal["save", "save_and_connect", "save_changes"]
    has_draft: bool
    has_channels: bool
    diff: list[dict[str, Any]]
    gate: dict[str, Any] | None
    can_override: bool


class UndoOut(BaseModel):
    number: int


def _plain_diff(active: AgentConfig | None, draft: AgentConfig) -> list[dict[str, Any]]:
    from nexus_api.services.agent_spec.patch import diff_ops

    before = dict(active.spec or {}) if active is not None else {}
    after = dict(draft.spec or {})
    rows: list[dict[str, Any]] = []
    for op in diff_ops(before, after):
        key = op["path"].lstrip("/")
        if key == "test_suite":
            continue
        row: dict[str, Any] = {"part": key, "label": PART_NAMES.get(key, key), "change": op["op"]}
        if key == "tools":
            old, new = set(before.get("tools") or []), set(after.get("tools") or [])
            row["added"], row["removed"] = sorted(new - old), sorted(old - new)
        rows.append(row)
    if not draft.spec and active is not None:
        if active.system_prompt_rendered != draft.system_prompt_rendered:
            rows.append({"part": "prompt", "label": PART_NAMES["prompt"], "change": "replace"})
        if sorted(active.tools or []) != sorted(draft.tools or []):
            old, new = set(active.tools or []), set(draft.tools or [])
            rows.append(
                {
                    "part": "tools",
                    "label": PART_NAMES["tools"],
                    "change": "replace",
                    "added": sorted(new - old),
                    "removed": sorted(old - new),
                }
            )
    return rows


async def _versions(scope: ClientScope) -> tuple[AgentConfig | None, AgentConfig | None]:
    rows = (
        await scope.session.scalars(
            sa.select(AgentConfig).where(
                AgentConfig.tenant_id == scope.tenant.id, AgentConfig.agent_id == scope.agent_id
            )
        )
    ).all()
    staged = next((r for r in rows if r.status is AgentConfigStatus.STAGED), None)
    active = next((r for r in rows if r.status is AgentConfigStatus.ACTIVE), None)
    return staged, active


@router.get("/publish-preview", response_model=PreviewOut)
async def publish_preview(scope: ClientScope = Depends(agent_in_path("agents:read"))) -> PreviewOut:
    staged, active = await _versions(scope)
    channels = await scope.session.scalar(
        sa.select(sa.func.count())
        .select_from(Channel)
        .where(
            Channel.tenant_id == scope.tenant.id,
            Channel.agent_id == scope.agent_id,
            Channel.provider != "qa_playground",
        )
    )
    has_channels = bool(channels)
    gate = None
    if staged is not None:
        agent = await scope.session.get(Agent, scope.agent_id)
        assert agent is not None
        result = await publishing.evaluate_gate(
            scope.session,
            agent=agent,
            version=staged,
            active=active,
            partner_id=scope.principal.partner.id,
        )
        gate = result.to_json()
    action: Literal["save", "save_and_connect", "save_changes"] = (
        "save_changes" if has_channels else "save_and_connect"
    )
    return PreviewOut(
        action=action if staged is not None else "save",
        has_draft=staged is not None,
        has_channels=has_channels,
        diff=_plain_diff(active, staged) if staged is not None else [],
        gate=gate,
        can_override=scope.principal.role in publishing.OVERRIDE_ROLES,
    )


@router.post("/publish", response_model=PublishAcceptedOut, status_code=status.HTTP_202_ACCEPTED)
async def publish(
    body: PublishIn,
    ref: str = Path(...),
    agent_id: uuid.UUID = Path(...),
    principal: ConsolePrincipal = Depends(require_console_principal("agents:write")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> PublishAcceptedOut:
    if (body.override_reason or "").strip() and principal.role not in publishing.OVERRIDE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"code": "override_forbidden"}
        )
    mapping = await resolve_mapping(session, principal, ref)
    async with tenant_scoped_session(session, mapping.tenant_id):
        agent = await session.get(Agent, agent_id)
        if agent is None or agent.tenant_id != mapping.tenant_id or agent.status != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
        staged = await session.scalar(
            sa.select(AgentConfig.id).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED
            )
        )
        if staged is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "no_draft"})
        job = await jobs_service.create_job(
            session,
            kind="publish",
            agent_id=agent_id,
            created_by=principal.user_id,
            draft_revision=agent.draft_revision,
        )
        job.progress = {
            "step": None,
            "blocks": [],
            "input": {
                "actor": principal.actor,
                "role": principal.role,
                "partner_id": str(principal.partner.id),
                "note": body.note,
                "accept_normal_failures": body.accept_normal_failures,
                "override_reason": body.override_reason,
                "origin": "console",
            },
        }
        await session.flush()
        out = PublishAcceptedOut(job_id=job.id)
    try:
        await jobs_service.enqueue_job(redis, job)
    except Exception as exc:
        log.warning("console.publish.enqueue_failed", error=type(exc).__name__)
    return out


@router.post("/publish/undo", response_model=UndoOut)
async def undo_publish(
    scope: ClientScope = Depends(agent_in_path("agents:write")),
    redis: Redis = Depends(get_redis),
) -> UndoOut:
    assert scope.agent_id is not None
    try:
        restored = await publishing.undo(
            scope.session, agent_id=scope.agent_id, actor=scope.principal.actor
        )
    except publishing.UndoWindowClosed as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "undo_window_closed"}
        ) from exc
    try:
        await redis.publish(PROMOTE_CHANNEL, f"{scope.tenant.id}:{scope.agent_id}")
    except Exception:  # la caché caduca sola
        log.warning("console.publish.undo_invalidate_failed")
    return UndoOut(number=restored.agent_version_number)


@router.get("/history")
async def history(
    scope: ClientScope = Depends(agent_in_path("agents:read")),
) -> list[dict[str, Any]]:
    rows = (
        await scope.session.scalars(
            sa.select(AgentConfig).where(
                AgentConfig.tenant_id == scope.tenant.id, AgentConfig.agent_id == scope.agent_id
            )
        )
    ).all()
    return publishing.ordered_history(list(rows))


@router.post("/versions/{number}/restore")
async def restore_version(
    number: int, scope: ClientScope = Depends(agent_in_path("agents:write"))
) -> dict[str, Any]:
    assert scope.agent_id is not None
    try:
        draft = await publishing.restore(
            scope.session, agent_id=scope.agent_id, number=number, actor=scope.principal.actor
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "unknown_version"}
        ) from exc
    agent = await scope.session.get(Agent, scope.agent_id, populate_existing=True)
    return {
        "draft_number": draft.agent_version_number,
        "restored_from": number,
        "revision": agent.draft_revision if agent else None,
    }


__all__ = ["router"]
