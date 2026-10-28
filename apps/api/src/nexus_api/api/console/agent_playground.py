"""El playground de un agente — spec 047, T085 (historia 8; requisito 20;
``contracts/console-api.md`` §4).

Conversar con el **borrador** —o con una versión que se elija— como si fuera un
cliente, con hora y agenda de mentira:

- ``POST …/agents/{agent_id}/playground/sessions`` [``agents:write``]
  ``{version?: "draft" | n, now?}`` → la sesión: la versión, la hora simulada en
  la zona del negocio y la agenda sembrada desde la ficha;
- ``POST …/sessions/{id}/messages`` [``agents:write``] ``{text}`` → las burbujas
  de WhatsApp (y si hubo más de una, 20.4), «Lo que habría hecho» (20.3) y la
  agenda como queda;
- ``PATCH …/sessions/{id}`` [``agents:write``] ``{now}``: cambiar la hora (20.2);
- ``GET …/sessions`` y ``GET …/sessions/{id}`` [``agents:read``]: el analyst lo ve
  en solo lectura (20.5);
- ``DELETE …/sessions/{id}``: cerrar y borrar la conversación simulada.

Corre el mismo grafo que el canal (``nexus_worker.simulation``), sin efectos
fuera (20.1). Cada turno se mide en la partida «Construcción y pruebas» (20.6,
``source = qa``). La sesión vive en Redis dos horas: el texto es de prueba,
escrito por el propio partner, nunca de un cliente final (C8).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.db.models import AgentConfig, AgentConfigStatus

from .agent_draft_routes import agent_in_path
from .deps import ClientScope, require_build_room

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}/playground")

SESSION_TTL_S = 2 * 60 * 60
MAX_TEXT = 1000


def _key(tenant_id: uuid.UUID, agent_id: uuid.UUID, session_id: uuid.UUID | str) -> str:
    return f"nexus:playground:{tenant_id}:{agent_id}:{session_id}"


class SessionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["draft"] | int = "draft"
    #: La hora simulada; sin zona, la del negocio.
    now: datetime | None = None


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_TEXT)


class SessionPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    now: datetime


class ActionOut(BaseModel):
    tool: str
    phrase: str


class TurnOut(BaseModel):
    role: Literal["customer", "agent"]
    bubbles: list[str]
    several_bubbles: bool = False
    actions: list[ActionOut] = Field(default_factory=list)


class SessionOut(BaseModel):
    session_id: uuid.UUID
    version_number: int
    is_draft: bool
    timezone: str
    now: datetime
    agenda: list[dict[str, Any]]
    services: list[dict[str, Any]]
    transcript: list[TurnOut]
    created_by: str | None = None
    allowed: list[Literal["send", "set_time", "close"]] = Field(default_factory=list)


class MessageOut(BaseModel):
    turn: TurnOut
    now: datetime
    agenda: list[dict[str, Any]]


def _error(code: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


async def _version(scope: ClientScope, wanted: Literal["draft"] | int) -> AgentConfig:
    stmt = sa.select(AgentConfig).where(
        AgentConfig.tenant_id == scope.tenant.id, AgentConfig.agent_id == scope.agent_id
    )
    if wanted == "draft":
        rows = (await scope.session.scalars(stmt)).all()
        staged = next((r for r in rows if r.status is AgentConfigStatus.STAGED), None)
        active = next((r for r in rows if r.status is AgentConfigStatus.ACTIVE), None)
        found = staged or active
    else:
        found = (
            await scope.session.scalars(stmt.where(AgentConfig.agent_version_number == wanted))
        ).first()
    if found is None:
        raise _error("unknown_version", status.HTTP_404_NOT_FOUND)
    return found


def _allowed(scope: ClientScope) -> list[Literal["send", "set_time", "close"]]:
    if "agents:write" in scope.principal.permissions:
        return ["send", "set_time", "close"]
    return []


def _out(scope: ClientScope, sid: uuid.UUID, data: dict[str, Any]) -> SessionOut:
    from nexus_worker.simulation.world import World

    world = World.from_dict(data["world"])
    return SessionOut(
        session_id=sid,
        version_number=int(data["version_number"]),
        is_draft=bool(data["is_draft"]),
        timezone=world.timezone,
        now=world.local_now(),
        agenda=world.agenda(),
        services=[
            {
                "name": s.name,
                "bookable": s.bookable,
                "duration_min": s.duration_min,
                "price": s.price,
            }
            for s in world.services
        ],
        transcript=[TurnOut(**t) for t in data.get("transcript") or []],
        created_by=data.get("created_by"),
        allowed=_allowed(scope),
    )


async def _load(redis: Redis, scope: ClientScope, sid: uuid.UUID) -> dict[str, Any]:
    assert scope.agent_id is not None
    raw = await redis.get(_key(scope.tenant.id, scope.agent_id, sid))
    if raw is None:
        raise _error("unknown_session", status.HTTP_404_NOT_FOUND)
    data: dict[str, Any] = json.loads(raw)
    return data


async def _save(redis: Redis, scope: ClientScope, sid: uuid.UUID, data: dict[str, Any]) -> None:
    assert scope.agent_id is not None
    await redis.set(_key(scope.tenant.id, scope.agent_id, sid), json.dumps(data), ex=SESSION_TTL_S)


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def open_session(
    body: SessionIn,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
    redis: Redis = Depends(get_redis),
) -> SessionOut:
    await require_build_room(scope.principal.partner.id)
    from nexus_worker.simulation.runner import open_conversation
    from nexus_worker.simulation.world import seed_world

    assert scope.agent_id is not None
    cfg = await _version(scope, body.version)
    world = await seed_world(scope.session, scope.agent_id, now=body.now)
    if body.now is not None:
        world.set_now(body.now)
    # La conversación simulada se escribe en su propia transacción: la de la
    # petición es la de la consola y no puede ver la del grafo.
    conv = await open_conversation(scope.tenant.id)
    sid = uuid.uuid4()
    data = {
        "version_id": str(cfg.id),
        "version_number": cfg.agent_version_number,
        "is_draft": cfg.status is AgentConfigStatus.STAGED,
        "conv": {
            "channel_id": str(conv.channel_id),
            "conversation_id": str(conv.conversation_id),
            "customer_id": str(conv.customer_id),
            "identifier": conv.identifier,
        },
        "world": world.to_dict(),
        "transcript": [],
        "created_by": scope.principal.actor,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await _save(redis, scope, sid, data)
    return _out(scope, sid, data)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    scope: ClientScope = Depends(agent_in_path("agents:read")),
    redis: Redis = Depends(get_redis),
) -> list[SessionOut]:
    assert scope.agent_id is not None
    out: list[SessionOut] = []
    async for key in redis.scan_iter(match=_key(scope.tenant.id, scope.agent_id, "*")):
        raw = await redis.get(key)
        if raw is None:
            continue
        sid = uuid.UUID(str(key).rsplit(":", 1)[1])
        out.append(_out(scope, sid, json.loads(raw)))
    return sorted(out, key=lambda s: s.now, reverse=True)


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: uuid.UUID,
    scope: ClientScope = Depends(agent_in_path("agents:read")),
    redis: Redis = Depends(get_redis),
) -> SessionOut:
    return _out(scope, session_id, await _load(redis, scope, session_id))


@router.patch("/sessions/{session_id}", response_model=SessionOut)
async def set_time(
    session_id: uuid.UUID,
    body: SessionPatchIn,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
    redis: Redis = Depends(get_redis),
) -> SessionOut:
    from nexus_worker.simulation.world import World

    data = await _load(redis, scope, session_id)
    world = World.from_dict(data["world"])
    world.set_now(body.now)
    data["world"] = world.to_dict()
    await _save(redis, scope, session_id, data)
    return _out(scope, session_id, data)


@router.post("/sessions/{session_id}/messages", response_model=MessageOut)
async def send_message(
    session_id: uuid.UUID,
    body: MessageIn,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
    redis: Redis = Depends(get_redis),
) -> MessageOut:
    await require_build_room(scope.principal.partner.id)
    from nexus_worker.metering.collector import SOURCE_QA, usage_turn
    from nexus_worker.simulation.runner import SimConversation, run_turn
    from nexus_worker.simulation.world import World

    assert scope.agent_id is not None
    lock = f"{_key(scope.tenant.id, scope.agent_id, session_id)}:turn"
    if not await redis.set(lock, "1", nx=True, ex=180):
        raise _error("turn_in_progress", status.HTTP_409_CONFLICT)
    try:
        data = await _load(redis, scope, session_id)
        world = World.from_dict(data["world"])
        conv = SimConversation(
            channel_id=uuid.UUID(data["conv"]["channel_id"]),
            conversation_id=uuid.UUID(data["conv"]["conversation_id"]),
            customer_id=uuid.UUID(data["conv"]["customer_id"]),
            identifier=data["conv"]["identifier"],
        )
        turn_no = len(data.get("transcript") or []) // 2 + 1
        try:
            async with usage_turn(
                tenant_id=scope.tenant.id,
                turn_id=f"playground:{session_id}:{turn_no}",
                source=SOURCE_QA,
                agent_id=scope.agent_id,
            ):
                outcome = await run_turn(
                    tenant_id=scope.tenant.id,
                    version_id=uuid.UUID(data["version_id"]),
                    world=world,
                    conv=conv,
                    text=body.text,
                )
        except LookupError as exc:
            raise _error("unknown_version", status.HTTP_404_NOT_FOUND) from exc
        except TimeoutError as exc:
            raise _error("turn_timeout", status.HTTP_504_GATEWAY_TIMEOUT) from exc
        turn = TurnOut(
            role="agent",
            bubbles=outcome.bubbles,
            several_bubbles=outcome.several_bubbles,
            actions=[ActionOut(**a) for a in outcome.actions],
        )
        transcript = list(data.get("transcript") or [])
        transcript.append(
            {"role": "customer", "bubbles": [body.text], "several_bubbles": False, "actions": []}
        )
        transcript.append(turn.model_dump())
        data["transcript"] = transcript
        data["world"] = world.to_dict()
        await _save(redis, scope, session_id, data)
        return MessageOut(turn=turn, now=world.local_now(), agenda=world.agenda())
    finally:
        await redis.delete(lock)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_session(
    session_id: uuid.UUID,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
    redis: Redis = Depends(get_redis),
) -> Response:
    from nexus_worker.simulation.runner import SimConversation, close_conversation

    assert scope.agent_id is not None
    data = await _load(redis, scope, session_id)
    conv = SimConversation(
        channel_id=uuid.UUID(data["conv"]["channel_id"]),
        conversation_id=uuid.UUID(data["conv"]["conversation_id"]),
        customer_id=uuid.UUID(data["conv"]["customer_id"]),
        identifier=data["conv"]["identifier"],
    )
    await close_conversation(scope.tenant.id, conv)
    await redis.delete(_key(scope.tenant.id, scope.agent_id, session_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
