"""La página de cada canal y su menú — spec 047, T112 y T114 (requisitos 32, 33
y 34; ``contracts/console-api.md`` §5).

- ``GET /clients/{ref}/channels/{channel_id}``: las cinco secciones (a quién
  responde, excepciones, escalado, mensaje de espera y comprobaciones), los
  disparadores del agente en solo lectura, la ``revision`` y el ``ETag`` (32.1,
  33.5);
- ``PUT …/config`` [``channels:write``]: exige ``If-Match``; vale desde el
  siguiente mensaje (32.7);
- ``POST …/config/undo``: deshacer durante 10 minutos (32.7);
- ``GET …/history``: el historial con antes y después (32.7);
- ``POST …/move`` ``{to_agent_id}``: el número pasa a otro agente, con su
  configuración y sus conversaciones; el destino no tiene que estar atendiendo
  (34.2);
- ``POST …/pause`` · ``…/resume``: los mensajes se siguen guardando y esperan a
  una persona con «Canal en pausa» (27);
- ``GET /clients/{ref}/agents/{agent_id}/channels``: los números del agente con
  su estado visible (29).

Desconectar sigue en ``channels.py`` (confirmación en la consola; con
«Reintentar» si Meta falla, sin tocar la suscripción de otro entorno: 34.3 y 34.4).

Un canal de otro cliente es un 404 opaco (garantía 9). Ninguna respuesta lleva
mensajes de clientes finales ni costes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.core.tenant_resolver import invalidate_tenant_cache
from nexus_api.db.models import (
    Agent,
    AuditLog,
    Channel,
    ChannelConfigChange,
    ChannelSignupLink,
    ChannelStatus,
)
from nexus_api.services import channel_config as svc
from nexus_api.services.agent_lifecycle import ChannelFacts, channel_visible_state

from .agent_draft_routes import agent_in_path, etag, parse_revision
from .deps import ClientScope, client_scope

router = APIRouter(prefix="/clients/{ref}")

Action = Literal["configure", "move", "pause", "resume", "disconnect"]


# ── formas ─────────────────────────────────────────────────────────────────


class AudienceIO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["unset", "team_only", "everyone"]
    test_numbers: list[str] = Field(default_factory=list, max_length=svc.MAX_NUMBERS)
    exceptions: list[str] = Field(default_factory=list, max_length=svc.MAX_NUMBERS)


class RecipientIO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    via: Literal["whatsapp", "email", "inbox"]
    phone_e164: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    client_user_id: str | None = Field(default=None, max_length=160)


class EscalationIO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipients: list[RecipientIO] = Field(default_factory=list, max_length=50)
    summary: bool = True


class ChannelConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience: AudienceIO
    escalation: EscalationIO = Field(default_factory=EscalationIO)
    wait_message: str | None = Field(default=None, max_length=2000)


class ChannelConfigOut(ChannelConfigIn):
    model_config = ConfigDict(extra="ignore")

    #: Solo lectura: de qué número sale el aviso por WhatsApp (33.3).
    notify_from: Literal["channel", "auphere"]


class VisibleOut(BaseModel):
    code: str
    tone: str
    reason: str | None = None


class CheckOut(BaseModel):
    code: str
    ok: bool
    level: Literal["warn", "block"]
    fix: str | None = None


class AgentRefOut(BaseModel):
    id: uuid.UUID
    name: str


class ChannelPageOut(BaseModel):
    id: uuid.UUID
    type: str
    identifier: str
    #: Spec 047, enmienda del 2026-10-29 (requisito 63.1, D56): cómo se conectó el
    #: número, para «WhatsApp · {método} · canal de {agente}». ``None`` si no se sabe.
    method: Literal["coexistence", "cloud_api"] | None = None
    status: str
    problem_reason: str | None = None
    visible_state: VisibleOut
    agent: AgentRefOut | None = None
    config: ChannelConfigOut
    #: El agente usa una plantilla de solo administradores: «A todos» no se
    #: puede elegir, y la página dice por qué (32.5).
    admin_only_template: bool = False
    #: Los disparadores del escalado, del agente y en solo lectura (33.5).
    triggers: list[Any] = Field(default_factory=list)
    #: Tras cuántos intentos fallidos escala (el disparador ``failed_attempts``).
    failed_attempts: int | None = None
    #: Lo que quedó por deshacer en Meta al desconectar: con algo, «Reintentar» (34.3).
    unlink_pending: list[str] = Field(default_factory=list)
    checks: list[CheckOut] = Field(default_factory=list)
    revision: int
    undo_until: datetime | None = None
    move_targets: list[AgentRefOut] = Field(default_factory=list)
    allowed: list[Action] = Field(default_factory=list)


class ChangeOut(BaseModel):
    id: uuid.UUID
    at: datetime
    actor: str
    origin: str
    before: dict[str, Any] | None = None
    after: dict[str, Any]
    undo_until: datetime | None = None
    undone_at: datetime | None = None


class MoveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_agent_id: uuid.UUID


class AgentChannelOut(BaseModel):
    id: uuid.UUID
    type: str
    identifier: str
    visible_state: VisibleOut
    #: Lo que el menú ⋯ puede ofrecer (34.1), sin pedir la página de cada número.
    allowed: list[Action] = Field(default_factory=list)


class AgentChannelsOut(BaseModel):
    channels: list[AgentChannelOut]
    pending_link: dict[str, Any] | None = None


# ── ayudas ─────────────────────────────────────────────────────────────────


def _kind(channel: Channel) -> str:
    return channel.type.value if hasattr(channel.type, "value") else str(channel.type)


def _status(channel: Channel) -> str:
    return channel.status.value if hasattr(channel.status, "value") else str(channel.status)


def visible_of(channel: Channel) -> VisibleOut:
    state = channel_visible_state(
        ChannelFacts(
            status=_status(channel),
            audience_mode=channel.audience_mode,
            problem_reason=channel.problem_reason if _status(channel) == "degraded" else None,
        )
    )
    return VisibleOut(code=state.code, tone=state.tone, reason=state.reason)


async def _channel(scope: ClientScope, channel_id: uuid.UUID) -> Channel:
    channel = await scope.session.get(Channel, channel_id, populate_existing=True)
    if channel is None or channel.tenant_id != scope.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown channel")
    return channel


def _error(exc: svc.ChannelConfigError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, **exc.extra})


def _required_revision(if_match: str | None) -> int:
    revision = parse_revision(if_match)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail={"code": "revision_required"},
        )
    return revision


async def _move_targets(scope: ClientScope, channel: Channel) -> list[AgentRefOut]:
    """Los otros agentes del cliente que no son borradores (34.1)."""
    query = sa.select(Agent.id, Agent.name).where(
        Agent.tenant_id == scope.tenant.id, Agent.lifecycle.in_(["published", "paused"])
    )
    current = channel.agent_id or (
        agent.id if (agent := await svc._agent_of(scope.session, channel)) else None
    )
    if current is not None:
        query = query.where(Agent.id != current)
    rows = (
        await scope.session.execute(
            query.order_by(Agent.is_default.desc(), Agent.created_at, Agent.id)
        )
    ).all()
    return [AgentRefOut(id=r.id, name=r.name) for r in rows]


async def _undo_until(scope: ClientScope, channel: Channel) -> datetime | None:
    found: datetime | None = await scope.session.scalar(
        sa.select(ChannelConfigChange.undo_until)
        .where(
            ChannelConfigChange.channel_id == channel.id,
            ChannelConfigChange.undone_at.is_(None),
            ChannelConfigChange.undo_until > datetime.now(UTC),
        )
        .order_by(ChannelConfigChange.at.desc())
        .limit(1)
    )
    return found


def method_of(channel: Channel) -> Literal["coexistence", "cloud_api"] | None:
    """«Coexistencia» si el número sigue en la app de WhatsApp Business (la columna
    o el modo con que se dio de alta); «Cloud API» si se dio de alta así. Sin dato,
    ``None``: la consola no lo inventa (§V)."""
    if channel.provider != "meta":
        return None
    mode = (channel.config or {}).get("mode")
    if channel.coexistence or mode == "coexistence":
        return "coexistence"
    if mode == "cloud_api":
        return "cloud_api"
    return None


async def page(scope: ClientScope, channel: Channel) -> ChannelPageOut:
    session = scope.session
    agent = await svc._agent_of(session, channel)
    move_targets = await _move_targets(scope, channel)
    allowed: list[Action] = []
    disconnected = channel.status is ChannelStatus.DISCONNECTED
    if "channels:write" in scope.principal.permissions and not disconnected:
        allowed = ["configure"]
        if move_targets:
            allowed.append("move")
        allowed.append("resume" if channel.status is ChannelStatus.PAUSED else "pause")
        allowed.append("disconnect")
    return ChannelPageOut(
        id=channel.id,
        type=_kind(channel),
        identifier=channel.provider_identifier,
        method=method_of(channel),
        status=_status(channel),
        problem_reason=channel.problem_reason,
        visible_state=visible_of(channel),
        agent=AgentRefOut(id=agent.id, name=agent.name) if agent is not None else None,
        config=ChannelConfigOut.model_validate(await svc.read_config(session, channel)),
        admin_only_template=await svc.admin_only_template(session, channel),
        triggers=await svc.escalation_triggers(session, channel),
        failed_attempts=await svc.escalation_failed_attempts(session, channel),
        unlink_pending=[str(x) for x in (channel.config or {}).get("unlink_pending") or []],
        checks=[CheckOut.model_validate(c) for c in await svc.checks(session, channel)],
        revision=channel.config_revision,
        undo_until=await _undo_until(scope, channel),
        move_targets=move_targets,
        allowed=allowed,
    )


def _audit(scope: ClientScope, channel: Channel, action: str, after: dict[str, Any]) -> AuditLog:
    return AuditLog(
        tenant_id=channel.tenant_id,
        actor=scope.principal.actor,
        action=action,
        target=f"channel:{channel.id}",
        after_json=after,
    )


# ── rutas ──────────────────────────────────────────────────────────────────


@router.get("/channels/{channel_id}", response_model=ChannelPageOut)
async def get_channel(
    channel_id: uuid.UUID,
    response: Response,
    scope: ClientScope = Depends(client_scope("channels:read")),
) -> ChannelPageOut:
    out = await page(scope, await _channel(scope, channel_id))
    response.headers["ETag"] = etag(out.revision)
    return out


@router.put(
    "/channels/{channel_id}/config",
    response_model=ChannelPageOut,
    responses={
        409: {"description": "agent_not_published, bag_empty, audience_admin_only_template"},
        412: {"description": "revision_conflict"},
        422: {"description": "channel_test_numbers_required, invalid_phone, too_many_recipients"},
        428: {"description": "revision_required"},
    },
)
async def put_config(
    channel_id: uuid.UUID,
    body: ChannelConfigIn,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> ChannelPageOut:
    revision = _required_revision(if_match)
    channel = await _channel(scope, channel_id)
    payload = svc.ConfigIn(
        mode=body.audience.mode,
        test_numbers=body.audience.test_numbers,
        exceptions=body.audience.exceptions,
        recipients=[
            svc.Recipient(
                name=r.name,
                via=r.via,
                phone_e164=r.phone_e164,
                email=r.email,
                client_user_id=r.client_user_id,
            )
            for r in body.escalation.recipients
        ],
        summary=body.escalation.summary,
        wait_message=body.wait_message,
    )
    try:
        await svc.write_config(
            scope.session, channel, payload, revision=revision, actor=scope.principal.actor
        )
    except svc.ChannelConfigError as exc:
        raise _error(exc) from None
    out = await page(scope, channel)
    response.headers["ETag"] = etag(out.revision)
    return out


@router.post("/channels/{channel_id}/config/undo", response_model=ChannelPageOut)
async def undo_config(
    channel_id: uuid.UUID,
    response: Response,
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> ChannelPageOut:
    channel = await _channel(scope, channel_id)
    try:
        await svc.undo(scope.session, channel, actor=scope.principal.actor)
    except svc.ChannelConfigError as exc:
        raise _error(exc) from None
    out = await page(scope, channel)
    response.headers["ETag"] = etag(out.revision)
    return out


@router.get("/channels/{channel_id}/history", response_model=list[ChangeOut])
async def get_history(
    channel_id: uuid.UUID, scope: ClientScope = Depends(client_scope("channels:read"))
) -> list[ChangeOut]:
    channel = await _channel(scope, channel_id)
    return [
        ChangeOut(
            id=c.id,
            at=c.at,
            actor=c.actor,
            origin=c.origin,
            before=c.before,
            after=c.after,
            undo_until=c.undo_until,
            undone_at=c.undone_at,
        )
        for c in await svc.history(scope.session, channel)
    ]


@router.post("/channels/{channel_id}/move", response_model=ChannelPageOut)
async def move_channel(
    channel_id: uuid.UUID,
    body: MoveIn,
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> ChannelPageOut:
    """Pasar el número a otro agente (34.2): vale desde el siguiente mensaje y
    conserva la configuración del canal y las conversaciones. El destino puede
    estar en pausa; un borrador o un archivado no."""
    channel = await _channel(scope, channel_id)
    target = await scope.session.get(Agent, body.to_agent_id)
    if (
        target is None
        or target.tenant_id != scope.tenant.id
        or target.lifecycle not in {"published", "paused"}
    ):
        raise HTTPException(status_code=422, detail={"code": "unknown_target_agent"})
    before = channel.agent_id
    if before == target.id:
        return await page(scope, channel)
    channel.agent_id = target.id
    await scope.session.flush()
    # «A todos» no puede llevar a un agente de solo administradores (32.5): un
    # número abierto no se mueve a uno de esos; antes se pasa a «Solo mi equipo».
    if channel.audience_mode == "everyone" and await svc.admin_only_template(
        scope.session, channel
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "audience_admin_only_template", "fix": "team_only"},
        )
    scope.session.add(
        _audit(
            scope,
            channel,
            "channel.moved",
            {"from": str(before) if before else None, "to": str(target.id)},
        )
    )
    await scope.session.flush()
    return await page(scope, channel)


@router.post("/channels/{channel_id}/pause", response_model=ChannelPageOut)
async def pause_channel(
    channel_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("channels:write")),
    redis: Redis = Depends(get_redis),
) -> ChannelPageOut:
    """Pausar el número: lo que llega se guarda y espera a una persona con
    «Canal en pausa»; ni respuesta ni ticks azules (27)."""
    channel = await _channel(scope, channel_id)
    try:
        changed = await svc.pause_channel(
            scope.session,
            channel,
            by_kind="partner_member",
            by_id=scope.principal.user_id,
            origin="console",
            actor=scope.principal.actor,
        )
    except svc.ChannelConfigError as exc:
        raise _error(exc) from None
    if changed:
        await _drop_cache(scope, redis, channel)
        _tell_client(scope, "channel.paused", channel)
    return await page(scope, channel)


async def _drop_cache(scope: ClientScope, redis: Redis, channel: Channel) -> None:
    """Tira la caché del número ya y otra vez tras el commit: un turno que la
    vuelva a llenar entre medias con el estado viejo no la deja así hasta que
    caduque."""
    from nexus_api.services.business.writes import after_commit

    provider, identifier = channel.provider, channel.provider_identifier
    await invalidate_tenant_cache(redis, provider, identifier)

    async def _again() -> None:
        await invalidate_tenant_cache(redis, provider, identifier)

    after_commit(scope.session, _again)


def _tell_client(scope: ClientScope, kind: str, channel: Channel) -> None:
    """Lo que hace el partner con un número, a las personas del cliente
    (events.md §3). Tras el commit."""
    from nexus_api.services.business.writes import after_commit

    tenant_id, by = scope.tenant.id, scope.principal.actor
    data = {"channel_id": str(channel.id), "by": by, "origin": "console"}
    if channel.agent_id is not None:
        data["agent_id"] = str(channel.agent_id)

    async def _send() -> None:
        await svc.announce(
            tenant_id=tenant_id, kind=kind, data=data, to_client=True, to_partner=False
        )

    after_commit(scope.session, _send)


@router.post("/channels/{channel_id}/resume", response_model=ChannelPageOut)
async def resume_channel(
    channel_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("channels:write")),
    redis: Redis = Depends(get_redis),
) -> ChannelPageOut:
    channel = await _channel(scope, channel_id)
    if await svc.resume_channel(
        scope.session, channel, origin="console", actor=scope.principal.actor
    ):
        await _drop_cache(scope, redis, channel)
        _tell_client(scope, "channel.resumed", channel)
    return await page(scope, channel)


@router.get("/agents/{agent_id}/channels", response_model=AgentChannelsOut)
async def agent_channels(
    scope: ClientScope = Depends(agent_in_path("channels:read")),
) -> AgentChannelsOut:
    """Los números del agente (29) y el enlace del dueño pendiente, si hay. El
    agente por defecto también atiende los números sin agente (spec 030)."""
    assert scope.agent_id is not None
    agent = await scope.session.get(Agent, scope.agent_id)
    assert agent is not None
    owned = Channel.agent_id == agent.id
    if agent.is_default:
        owned = sa.or_(owned, Channel.agent_id.is_(None))
    from .channels import INTERNAL_PROVIDERS

    rows = (
        await scope.session.scalars(
            sa.select(Channel)
            .where(
                Channel.tenant_id == scope.tenant.id,
                owned,
                Channel.status != ChannelStatus.DISCONNECTED,
                Channel.provider.not_in(INTERNAL_PROVIDERS),
            )
            .order_by(Channel.created_at, Channel.id)
        )
    ).all()
    link = await scope.session.scalar(
        sa.select(ChannelSignupLink).where(
            ChannelSignupLink.tenant_id == scope.tenant.id,
            ChannelSignupLink.agent_id == agent.id,
            ChannelSignupLink.consumed_at.is_(None),
            ChannelSignupLink.revoked_at.is_(None),
        )
    )
    pending = None
    if link is not None and link.expires_at > datetime.now(UTC):
        pending = {"id": str(link.id), "mode": link.mode, "expires_at": link.expires_at.isoformat()}
    can_write = "channels:write" in scope.principal.permissions
    others = bool(
        await scope.session.scalar(
            sa.select(sa.func.count())
            .select_from(Agent)
            .where(
                Agent.tenant_id == scope.tenant.id,
                Agent.id != agent.id,
                Agent.lifecycle.in_(["published", "paused"]),
            )
        )
    )

    def allowed_of(c: Channel) -> list[Action]:
        if not can_write or c.status is ChannelStatus.DISCONNECTED:
            return []
        out: list[Action] = ["configure"]
        if others:
            out.append("move")
        out.append("resume" if c.status is ChannelStatus.PAUSED else "pause")
        out.append("disconnect")
        return out

    return AgentChannelsOut(
        channels=[
            AgentChannelOut(
                id=c.id,
                type=_kind(c),
                identifier=c.provider_identifier,
                visible_state=visible_of(c),
                allowed=allowed_of(c),
            )
            for c in rows
        ],
        pending_link=pending,
    )


class OwnerLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["coexistence", "cloud_api", "whatsapp_login"] = "coexistence"
    #: «Revocar y crear»: revoca el pendiente del agente y crea otro (31.2).
    replace: bool = False


class OwnerLinkOut(BaseModel):
    id: uuid.UUID
    #: Solo en esta respuesta: se guarda la huella, nunca el enlace (31.1).
    url: str
    mode: str
    expires_at: datetime


@router.post(
    "/agents/{agent_id}/channels/owner-links",
    response_model=OwnerLinkOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "link_pending_exists, whatsapp_login_unavailable"}},
)
async def create_owner_link(
    body: OwnerLinkIn, scope: ClientScope = Depends(agent_in_path("channels:write"))
) -> OwnerLinkOut:
    """El enlace para que el dueño conecte el número desde su teléfono u
    ordenador, ya para este agente (31.1)."""
    from nexus_api.services.channel_signup_links import mint_link

    minted = await mint_link(
        scope.session,
        tenant_id=scope.tenant.id,
        mode=body.mode,
        actor=scope.principal.actor,
        agent_id=scope.agent_id,
        replace=body.replace,
    )
    return OwnerLinkOut(
        id=minted.link.id, url=minted.url, mode=minted.link.mode, expires_at=minted.link.expires_at
    )


@router.delete(
    "/agents/{agent_id}/channels/owner-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_owner_link(
    link_id: uuid.UUID, scope: ClientScope = Depends(agent_in_path("channels:write"))
) -> Response:
    from nexus_api.services.channel_signup_links import revoke_link

    link = await scope.session.get(ChannelSignupLink, link_id)
    if link is None or link.tenant_id != scope.tenant.id or link.agent_id != scope.agent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown link")
    await revoke_link(scope.session, link, actor=scope.principal.actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["page", "router", "visible_of"]
