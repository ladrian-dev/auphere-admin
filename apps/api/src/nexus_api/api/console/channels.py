"""``/console/clients/{ref}/channels`` — channel metadata for a client
(CP-17: overview + roles; connecting lives in ``whatsapp.py``).

What a partner sees per channel: type, provider, identifier (the
WhatsApp number they already know), status, role and the Meta health
snapshot kept in ``channels.config`` (quality rating, messaging tier,
verified name). Never ``config`` as a whole (it holds provider ids)
and never ``config_encrypted``.

Roles: ``services/channel_routing.py`` refuses a role-based send when
a tenant has more than one active WhatsApp channel and none carries
the requested role — so the console must make tagging obvious.
``PATCH .../channels/{channel_id}/role`` writes ``config.role`` through
the same vocabulary (``CHANNEL_ROLES``) the router reads.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta.credentials import (
    ChannelCredentialsRepository,
    MetaCredentialsRepository,
)
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, ChannelStatus, ChannelType, Connector
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.channel_routing import channel_agent_enabled, channel_role
from nexus_api.services.meta_signup_service import build_meta_client as _build_meta_client

from .deps import ClientScope, client_scope
from .schemas import ChannelOut
from .schemas_channels import ChannelDetailOut, ChannelRoleIn, ChannelsOverviewOut

router = APIRouter(prefix="/clients/{ref}/channels")

#: Platform-internal pseudo-channels (the QA playground's ``web`` channel,
#: ``api/qa.py::_QA_CHANNEL_PROVIDER``). Not the partner's, never shown,
#: never counted against ``max_channels_per_client``.
INTERNAL_PROVIDERS: frozenset[str] = frozenset({"qa_playground"})


#: De qué conector del catálogo sale el logotipo de cada tipo de canal. Los
#: conectores «solo canal» están fuera de la lista que ve la consola —no se
#: conectan desde Conectores, se conectan desde Canales—, así que su logotipo
#: tiene que llegar por aquí o no llega.
CHANNEL_CONNECTOR_SLUG: dict[str, str] = {"whatsapp": "whatsapp_meta"}


async def channel_logos(session: AsyncSession) -> dict[str, str | None]:
    """Logotipo por tipo de canal, leído del catálogo una vez por petición."""
    slugs = set(CHANNEL_CONNECTOR_SLUG.values())
    if not slugs:
        return {}
    filas = (
        await session.execute(
            sa.select(Connector.slug, Connector.provider_meta).where(Connector.slug.in_(slugs))
        )
    ).all()
    por_slug: dict[str, str | None] = {}
    for slug, meta in filas:
        meta = meta or {}
        url = next(
            (
                meta[k]
                for k in ("logo_url", "logo", "icon_url")
                if isinstance(meta.get(k), str) and meta[k]
            ),
            None,
        )
        por_slug[slug] = url
    return {tipo: por_slug.get(slug) for tipo, slug in CHANNEL_CONNECTOR_SLUG.items()}


def _detail(ch: Channel, logos: dict[str, str | None] | None = None) -> ChannelDetailOut:
    cfg = ch.config or {}

    def _s(key: str) -> str | None:
        v = cfg.get(key)
        return v if isinstance(v, str) and v else None

    return ChannelDetailOut(
        id=ch.id,
        type=ch.type.value,
        provider=ch.provider,
        provider_identifier=ch.provider_identifier,
        status=ch.status.value,
        role=channel_role(ch),
        last_health_check_at=ch.last_health_check_at,
        created_at=ch.created_at,
        quality_rating=_s("quality_rating"),
        messaging_tier=_s("messaging_tier"),
        verified_name=_s("verified_name"),
        mode=_s("mode"),
        # Un canal desvinculado no atiende, diga lo que diga ``config``: el
        # despachador lo descarta por su estado, y la tarjeta tiene que decir
        # lo mismo que hace el sistema (constitución §V).
        agent_enabled=channel_agent_enabled(ch) and ch.status is not ChannelStatus.DISCONNECTED,
        logo_url=(logos or {}).get(ch.type.value),
        unlink_pending=[str(x) for x in (cfg.get("unlink_pending") or [])],
    )


async def _all_channels(session: AsyncSession) -> list[Channel]:
    return list(
        (
            await session.execute(
                sa.select(Channel)
                .where(Channel.provider.not_in(INTERNAL_PROVIDERS))
                .order_by(Channel.created_at)
            )
        )
        .scalars()
        .all()
    )


async def count_connected_channels(session: AsyncSession) -> int:
    """Channels that count against ``partners.max_channels_per_client``:
    every row that is not ``disconnected``. Must run inside the tenant scope."""
    return int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(Channel)
            .where(
                Channel.status != ChannelStatus.DISCONNECTED,
                Channel.provider.not_in(INTERNAL_PROVIDERS),
            )
        )
        or 0
    )


def roles_required(channels: list[Channel]) -> bool:
    """The refusal condition of ``channel_routing``: >1 active WhatsApp
    channel and at least one untagged."""
    active = [
        c for c in channels if c.type is ChannelType.WHATSAPP and c.status is ChannelStatus.ACTIVE
    ]
    return len(active) > 1 and any(channel_role(c) is None for c in active)


@router.get("", response_model=list[ChannelOut])
async def list_channels(
    scope: ClientScope = Depends(client_scope("channels:read")),
) -> list[ChannelOut]:
    rows = await _all_channels(scope.session)
    return [
        ChannelOut(
            id=ch.id,
            type=ch.type.value,
            provider=ch.provider,
            provider_identifier=ch.provider_identifier,
            status=ch.status.value,
            role=channel_role(ch),
            last_health_check_at=ch.last_health_check_at,
            created_at=ch.created_at,
        )
        for ch in rows
    ]


@router.get("/overview", response_model=ChannelsOverviewOut)
async def channels_overview(
    scope: ClientScope = Depends(client_scope("channels:read")),
) -> ChannelsOverviewOut:
    rows = await _all_channels(scope.session)
    used = sum(1 for c in rows if c.status is not ChannelStatus.DISCONNECTED)
    limit = scope.principal.partner.max_channels_per_client
    creds = await MetaCredentialsRepository(scope.session).get()
    logos = await channel_logos(scope.session)
    return ChannelsOverviewOut(
        channels=[_detail(c, logos) for c in rows],
        max_channels=limit,
        used_channels=used,
        can_connect=used < limit,
        roles_required=roles_required(rows),
        meta_connected=creds is not None,
    )


@router.patch("/{channel_id}/role", response_model=ChannelDetailOut)
async def set_channel_role(
    channel_id: uuid.UUID,
    body: ChannelRoleIn,
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> ChannelDetailOut:
    ch = await scope.session.get(Channel, channel_id)
    if ch is None:  # RLS hides other tenants' rows → same 404 as "no such row"
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")
    if ch.type is not ChannelType.WHATSAPP:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="roles apply to WhatsApp channels only"
        )
    before = channel_role(ch)
    cfg = dict(ch.config or {})
    if body.role is None:
        cfg.pop("role", None)
    else:
        cfg["role"] = body.role
    ch.config = cfg
    flag_modified(ch, "config")
    await scope.session.flush()
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action="console.channel.role",
        target=f"channel:{ch.id}",
        before={"role": before},
        after={"role": body.role, "identifier": ch.provider_identifier},
    )
    return _detail(ch, await channel_logos(scope.session))


def build_meta_client():
    """Costura para los tests: se sustituye por un Meta simulado."""
    return _build_meta_client()


#: Lo que conectar hizo en Meta, en el orden en que se deshace. ``unsubscribe``
#: solo entra cuando el número era el último vivo de su WABA en el cliente:
#: la suscripción es por cuenta, no por número (spec 021, R2.3).
UNLINK_STEPS: tuple[str, ...] = ("deregister", "unsubscribe")


@router.post("/{channel_id}/disconnect", response_model=ChannelDetailOut)
async def disconnect_channel(
    channel_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> ChannelDetailOut:
    """Soltar un número: el agente deja de atender por él, y Meta lo suelta.

    Conectar era autoservicio y desconectar no existía — el partner que se
    equivocaba de número tenía que escribirnos. Y desvincular, cuando llegó
    (spec 019), solo apagaba: el número seguía registrado bajo nuestra app y
    ningún otro cliente podía conectarlo (spec 021).

    **Dos transacciones, y el orden importa.** Primero se escribe el estado —
    ``disconnected`` y qué queda por deshacer en Meta— y se commitea. Solo
    después se llama a Meta, paso a paso, quitando cada uno al terminar. Si el
    proceso muere entre medias, la fila ya dice qué falta y el mismo endpoint
    lo reintenta. Al revés —Meta primero, base después— un fallo entre ambos
    dejaría el número dado de baja sin que la base lo supiera: el silencio
    que R3 prohíbe.

    Por eso no se escribe por ``scope.session``: el scope envuelve el endpoint
    entero en una sola transacción. Se abren sesiones propias con el mismo
    scope de tenant, como hace ``AgentLoader``.

    **Un fallo de Meta no es un error HTTP.** El canal queda desvinculado en la
    consola pase lo que pase —es lo que el partner pidió— y lo que falló se lee
    en ``unlink_pending``.

    **Lo que NO hace**: sacar el número de la cuenta de Meta del partner. Es su
    activo y se hace en su Business Manager; la consola lo dice.

    La fila se conserva: el número se puede volver a conectar (el alta hace
    *upsert* sobre ella) y su historial sigue teniendo a qué apuntar. Lo que
    dejó de hacer es ocupar el número (índice parcial, migración 0132).
    """
    ch = await scope.session.get(Channel, channel_id)
    if ch is None:  # RLS esconde las filas de otro tenant → el mismo 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")
    tenant_id = scope.tenant.id
    sm = get_sessionmaker()

    # ── 1 · el estado, antes que Meta ───────────────────────────────────
    async with sm() as s1, tenant_scoped_session(s1, tenant_id):
        fila = await s1.get(Channel, channel_id)
        assert fila is not None
        cfg = dict(fila.config or {})
        if fila.status is ChannelStatus.DISCONNECTED:
            before = ChannelStatus.DISCONNECTED.value
            pending = [str(x) for x in (cfg.get("unlink_pending") or [])]
        else:
            before = fila.status.value
            waba_id = cfg.get("waba_id")
            hermanos = 0
            if waba_id:
                hermanos = int(
                    await s1.scalar(
                        sa.select(sa.func.count())
                        .select_from(Channel)
                        .where(
                            Channel.id != channel_id,
                            Channel.status != ChannelStatus.DISCONNECTED,
                            Channel.config["waba_id"].astext == str(waba_id),
                        )
                    )
                    or 0
                )
            pending = ["deregister"] + (["unsubscribe"] if hermanos == 0 else [])
            fila.status = ChannelStatus.DISCONNECTED
            cfg["unlink_pending"] = pending
            fila.config = cfg
            flag_modified(fila, "config")
            await s1.flush()
        if not pending:
            # Ya estaba hecho del todo: quien pulsa dos veces no merece un error.
            return _detail(fila, await channel_logos(s1))

    # ── 2 · Meta, paso a paso, quitando cada uno al terminar ───────────
    client = build_meta_client()
    done: list[str] = []
    skipped: list[str] = []
    try:
        async with sm() as s2, tenant_scoped_session(s2, tenant_id):
            fila = await s2.get(Channel, channel_id)
            assert fila is not None
            cfg = dict(fila.config or {})
            creds = await ChannelCredentialsRepository(s2).get(channel_id)
            if creds is None:
                creds = await MetaCredentialsRepository(s2).get()
            if creds is None:
                # Sin credencial no hay nada atado a nuestra app: no se puede
                # deshacer lo que nunca se hizo. Se anota, no se deja pendiente
                # para siempre.
                skipped, pending = list(pending), []
            else:
                token = creds.bisuat
                waba_id = str(cfg.get("waba_id") or creds.waba_id or "")
                phone_number_id = str(cfg.get("phone_number_id") or creds.phone_number_id or "")
                for step in list(pending):
                    try:
                        if step == "deregister":
                            await client.deregister_phone(
                                phone_number_id=phone_number_id, access_token=token
                            )
                        elif step == "unsubscribe":
                            await client.unsubscribe_app(waba_id=waba_id, access_token=token)
                    except MetaAPIError:
                        # Queda pendiente, y los que vienen detrás también: no
                        # tiene sentido desuscribir lo que no se pudo dar de baja.
                        break
                    done.append(step)
                    pending.remove(step)
                    if step == "deregister":
                        fila.config_encrypted = None
                    elif step == "unsubscribe":
                        await MetaCredentialsRepository(s2).delete()
            if pending:
                cfg["unlink_pending"] = pending
            else:
                cfg.pop("unlink_pending", None)
            fila.config = cfg
            flag_modified(fila, "config")
            meta: dict[str, list[str]] = {"done": done, "pending": pending}
            if skipped:
                meta["skipped"] = skipped
            await AuditRepository(s2).record(
                actor=scope.principal.actor,
                action="console.channel.disconnect",
                target=f"channel:{fila.id}",
                before={"status": before},
                after={
                    "status": fila.status.value,
                    "identifier": fila.provider_identifier,
                    "meta": meta,
                },
            )
            await s2.flush()
            return _detail(fila, await channel_logos(s2))
    finally:
        await client.close()


__all__ = ["count_connected_channels", "roles_required", "router"]
