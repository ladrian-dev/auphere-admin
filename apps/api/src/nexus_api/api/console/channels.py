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

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta.credentials import (
    ChannelCredentialsRepository,
    MetaCredentials,
    MetaCredentialsRepository,
)
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError, MetaTransientError
from nexus_channels.whatsapp_meta.meta_client import MetaClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from nexus_api.api.deps import get_redis
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, ChannelStatus, ChannelType, Connector
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.channel_routing import channel_agent_enabled, channel_role
from nexus_api.services.meta_signup_service import build_meta_client as _build_meta_client

from .deps import ClientScope, client_scope
from .schemas import ChannelOut
from .schemas_channels import (
    CatalogErrorOut,
    CatalogListOut,
    CatalogOut,
    CatalogSetIn,
    CatalogState,
    CatalogSummaryOut,
    ChannelDetailOut,
    ChannelRoleIn,
    ChannelsOverviewOut,
)

log = structlog.get_logger(__name__)

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


def _catalog_of(cfg: dict[str, Any]) -> CatalogOut | None:
    cid = cfg.get("catalog_id")
    if not isinstance(cid, str) or not cid:
        return None
    checked = cfg.get("catalog_checked_at")
    return CatalogOut(
        id=cid,
        name=cfg.get("catalog_name") if isinstance(cfg.get("catalog_name"), str) else None,
        checked_at=datetime.fromisoformat(checked) if isinstance(checked, str) else None,
    )


def _catalog_error_of(cfg: dict[str, Any]) -> CatalogErrorOut | None:
    raw = cfg.get("catalog_error")
    if not isinstance(raw, dict) or not raw.get("code"):
        return None
    at = raw.get("at")
    return CatalogErrorOut(
        code=str(raw["code"]),
        message=str(raw.get("message") or "") or None,
        at=datetime.fromisoformat(at) if isinstance(at, str) else None,
    )


def _detail(
    ch: Channel,
    logos: dict[str, str | None] | None = None,
    catalog_state: CatalogState | None = None,
) -> ChannelDetailOut:
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
        catalog=_catalog_of(cfg),
        catalog_state=catalog_state or ("linked" if cfg.get("catalog_id") else "none"),
        catalog_error=_catalog_error_of(cfg),
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
    redis: Redis = Depends(get_redis),
) -> ChannelsOverviewOut:
    rows = await _all_channels(scope.session)
    used = sum(1 for c in rows if c.status is not ChannelStatus.DISCONNECTED)
    limit = scope.principal.partner.max_channels_per_client
    creds = await MetaCredentialsRepository(scope.session).get()
    logos = await channel_logos(scope.session)
    states = await reconcile_catalogs(scope.session, rows, redis)
    return ChannelsOverviewOut(
        channels=[_detail(c, logos, states.get(c.id)) for c in rows],
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


def build_meta_client() -> MetaClient:
    """Costura para los tests: se sustituye por un Meta simulado."""
    return _build_meta_client()


#: Lo que conectar hizo en Meta, en el orden en que se deshace. ``unsubscribe``
#: solo entra cuando el número era el último vivo de su WABA en el cliente:
#: la suscripción es por cuenta, no por número (spec 021, R2.3).
UNLINK_STEPS: tuple[str, ...] = ("deregister", "unsubscribe")

# Lo que Meta contesta a ``deregister`` sobre un número en coexistencia
# («API solution for SMB»): 400, code 100. Medido en producción el
# 2026-09-30 con el +34672138367.
_DEREGISTER_NOT_APPLICABLE = "deregister endpoint is not available"


def deregister_not_applicable(exc: MetaAPIError) -> bool:
    """¿Meta dice que este número no se puede dar de baja porque nunca estuvo
    registrado por Cloud API? Es el rechazo de un número en coexistencia."""
    return (
        getattr(exc, "code", None) == 100
        and _DEREGISTER_NOT_APPLICABLE in str(getattr(exc, "message", "") or str(exc)).lower()
    )


# ── el catálogo de Commerce Manager (spec 022) ───────────────────────────
#
# Un catálogo se enlaza a la **cuenta** de WhatsApp Business, no al número,
# así que dos números del mismo cliente en la misma cuenta lo comparten. La
# consola lo guarda en el canal para que el motor lo inyecte al enviar
# tarjetas, y **adopta lo que Meta tenga** (research D3): la pantalla dice la
# verdad de Meta, no la de nuestra base.

CATALOG_CACHE_TTL = 300
# 10 = permiso denegado · 200 = permiso que la app no tiene · 190 = token
# inválido. Los tres se arreglan igual: volver a conectar el número.
_PERMISSION_CODES = frozenset({10, 200, 190})


def catalog_permission_missing(exc: MetaAPIError) -> bool:
    """¿Meta rechazó por permiso (o token)? Se arregla reconectando el número."""
    return getattr(exc, "code", None) in _PERMISSION_CODES


def _cache_key(waba_id: str) -> str:
    return f"nexus:catalog:waba:{waba_id}"


async def _creds_for(session: AsyncSession, ch: Channel) -> MetaCredentials | None:
    creds = await ChannelCredentialsRepository(session).get(ch.id)
    if creds is None:
        creds = await MetaCredentialsRepository(session).get()
    return creds


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_catalog(cfg: dict[str, Any], found: dict[str, Any] | None) -> None:
    """Deja en ``cfg`` lo que Meta tiene: un catálogo, o nada."""
    if found and isinstance(found.get("id"), str):
        cfg["catalog_id"] = found["id"]
        if isinstance(found.get("name"), str):
            cfg["catalog_name"] = found["name"]
        else:
            cfg.pop("catalog_name", None)
    else:
        cfg.pop("catalog_id", None)
        cfg.pop("catalog_name", None)
    cfg["catalog_checked_at"] = _now()


async def reconcile_catalogs(
    session: AsyncSession, rows: list[Channel], redis: Redis
) -> dict[uuid.UUID, CatalogState]:
    """Para cada número vivo con credencial, qué catálogo tiene su cuenta en
    Meta — una llamada por cuenta cada ``CATALOG_CACHE_TTL`` s — y la base se
    pone a lo que Meta diga. Sin credencial no se pregunta. Si Meta no
    responde, lo guardado se enseña como «sin comprobar» y no se borra."""
    states: dict[uuid.UUID, CatalogState] = {}
    by_waba: dict[str, list[Channel]] = {}
    for ch in rows:
        if ch.type is not ChannelType.WHATSAPP or ch.status is ChannelStatus.DISCONNECTED:
            continue
        waba = (ch.config or {}).get("waba_id")
        if isinstance(waba, str) and waba:
            by_waba.setdefault(waba, []).append(ch)
    if not by_waba:
        return states

    client: MetaClient | None = None
    try:
        for waba, channels in by_waba.items():
            creds = await _creds_for(session, channels[0])
            if creds is None:
                continue
            cached = await redis.get(_cache_key(waba))
            verdict: dict[str, Any]
            if cached:
                verdict = json.loads(cached)
            else:
                if client is None:
                    client = build_meta_client()
                try:
                    found = await client.get_linked_catalog(waba_id=waba, access_token=creds.bisuat)
                    verdict = {"catalog": found}
                except MetaAPIError as exc:
                    if catalog_permission_missing(exc):
                        verdict = {"permission_missing": True}
                    else:
                        log.warning("channel.catalog.check_failed", waba_id=waba, error=str(exc))
                        for ch in channels:
                            states[ch.id] = "unchecked"
                        continue
                await redis.set(_cache_key(waba), json.dumps(verdict), ex=CATALOG_CACHE_TTL)

            for ch in channels:
                cfg = dict(ch.config or {})
                if verdict.get("permission_missing"):
                    states[ch.id] = "permission_missing"
                    continue
                found = verdict.get("catalog")
                if (found or {}).get("id") != cfg.get("catalog_id") or not cfg.get(
                    "catalog_checked_at"
                ):
                    _write_catalog(cfg, found if isinstance(found, dict) else None)
                    cfg.pop("catalog_error", None)
                    ch.config = cfg
                    flag_modified(ch, "config")
                states[ch.id] = "linked" if cfg.get("catalog_id") else "none"
    finally:
        if client is not None:
            await client.close()
    return states


def _meta_refusal(exc: MetaAPIError) -> HTTPException:
    if isinstance(exc, MetaTransientError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "meta_unavailable"}
        )
    if catalog_permission_missing(exc):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "catalog_permission_missing"}
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "catalog_meta_rejected",
            "message": getattr(exc, "message", str(exc))[:200],
        },
    )


async def _channel_with_creds(
    session: AsyncSession, channel_id: uuid.UUID
) -> tuple[Channel, MetaCredentials, str, str]:
    ch = await session.get(Channel, channel_id)
    if ch is None:  # RLS → 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")
    creds = await _creds_for(session, ch)
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "channel_has_no_credentials"}
        )
    cfg = ch.config or {}
    waba_id = str(cfg.get("waba_id") or creds.waba_id or "")
    business_id = str(cfg.get("business_id") or creds.business_id or "")
    if not waba_id or not business_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "channel_has_no_credentials"}
        )
    return ch, creds, waba_id, business_id


@router.get("/{channel_id}/catalogs", response_model=CatalogListOut)
async def list_channel_catalogs(
    channel_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("channels:read")),
) -> CatalogListOut:
    """Los catálogos del negocio dueño del token del canal — solo esos."""
    ch, creds, _waba, business_id = await _channel_with_creds(scope.session, channel_id)
    client = build_meta_client()
    try:
        rows = await client.list_catalogs(business_id=business_id, access_token=creds.bisuat)
    except MetaAPIError as exc:
        raise _meta_refusal(exc) from exc
    finally:
        await client.close()
    return CatalogListOut(
        items=[
            CatalogSummaryOut(
                id=str(r.get("id")),
                name=r.get("name") if isinstance(r.get("name"), str) else None,
                product_count=r.get("product_count")
                if isinstance(r.get("product_count"), int)
                else None,
            )
            for r in rows
            if r.get("id")
        ],
        linked_id=(ch.config or {}).get("catalog_id"),
    )


@router.put("/{channel_id}/catalog", response_model=ChannelDetailOut)
async def set_channel_catalog(
    channel_id: uuid.UUID,
    body: CatalogSetIn,
    scope: ClientScope = Depends(client_scope("channels:write")),
    redis: Redis = Depends(get_redis),
) -> ChannelDetailOut:
    """Enlazar un catálogo a la cuenta del número (o cambiarlo).

    Con otro ya enlazado, primero se desenlaza y luego se enlaza el nuevo
    (research D4). Si el segundo paso falla, el canal queda **sin** catálogo
    y con el motivo: honesto y reversible. Meta primero y base después es
    seguro aquí porque la conciliación al listar adopta lo que Meta tenga.
    """
    ch, creds, waba_id, business_id = await _channel_with_creds(scope.session, channel_id)
    cfg = dict(ch.config or {})
    before = _catalog_of(cfg)
    client = build_meta_client()
    meta: dict[str, Any] = {}
    try:
        try:
            owned = await client.list_catalogs(business_id=business_id, access_token=creds.bisuat)
        except MetaAPIError as exc:
            raise _meta_refusal(exc) from exc
        chosen = next((r for r in owned if str(r.get("id")) == body.catalog_id), None)
        if chosen is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail={"code": "catalog_not_owned"}
            )
        if before is not None and before.id == body.catalog_id:
            return _detail(ch, await channel_logos(scope.session), "linked")

        if before is not None:
            try:
                await client.unlink_catalog(
                    waba_id=waba_id, catalog_id=before.id, access_token=creds.bisuat
                )
            except MetaAPIError as exc:
                raise _meta_refusal(exc) from exc
            meta["unlinked"] = before.id
            _write_catalog(cfg, None)
        try:
            await client.link_catalog(
                waba_id=waba_id, catalog_id=body.catalog_id, access_token=creds.bisuat
            )
        except MetaAPIError as exc:
            if isinstance(exc, MetaTransientError) and before is None:
                raise _meta_refusal(exc) from exc
            # El viejo ya no está y el nuevo no entró: se dice, no se finge.
            cfg["catalog_error"] = {
                "code": "catalog_permission_missing"
                if catalog_permission_missing(exc)
                else "catalog_meta_rejected",
                "message": getattr(exc, "message", str(exc))[:200],
                "at": _now(),
            }
            meta["error"] = cfg["catalog_error"]
            log.warning("channel.catalog.link_failed", channel_id=str(ch.id), error=str(exc))
        else:
            _write_catalog(cfg, chosen)
            cfg.pop("catalog_error", None)
            meta["linked"] = body.catalog_id
    finally:
        await client.close()

    ch.config = cfg
    flag_modified(ch, "config")
    await redis.delete(_cache_key(waba_id))
    after = _catalog_of(cfg)
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action="console.channel.catalog",
        target=f"channel:{ch.id}",
        before={"catalog": before.model_dump(mode="json") if before else None},
        after={"catalog": after.model_dump(mode="json") if after else None, "meta": meta},
    )
    return _detail(ch, await channel_logos(scope.session), "linked" if after else "none")


@router.delete("/{channel_id}/catalog", response_model=ChannelDetailOut)
async def clear_channel_catalog(
    channel_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("channels:write")),
    redis: Redis = Depends(get_redis),
) -> ChannelDetailOut:
    """Desenlazar el catálogo. Si Meta rechaza, el catálogo sigue y se dice:
    borrar a ciegas dejaría a Meta enseñando productos que la consola no ve."""
    ch = await scope.session.get(Channel, channel_id)
    if ch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")
    cfg = dict(ch.config or {})
    before = _catalog_of(cfg)
    if before is None:
        return _detail(ch, await channel_logos(scope.session), "none")
    creds = await _creds_for(scope.session, ch)
    waba_id = str(cfg.get("waba_id") or (creds.waba_id if creds else "") or "")
    meta: dict[str, Any] = {}
    if creds is not None and waba_id:
        client = build_meta_client()
        try:
            await client.unlink_catalog(
                waba_id=waba_id, catalog_id=before.id, access_token=creds.bisuat
            )
            meta["unlinked"] = before.id
        except MetaAPIError as exc:
            cfg["catalog_error"] = {
                "code": "catalog_permission_missing"
                if catalog_permission_missing(exc)
                else "catalog_meta_rejected",
                "message": getattr(exc, "message", str(exc))[:200],
                "at": _now(),
            }
            ch.config = cfg
            flag_modified(ch, "config")
            log.warning("channel.catalog.unlink_failed", channel_id=str(ch.id), error=str(exc))
            return _detail(ch, await channel_logos(scope.session), "linked")
        finally:
            await client.close()
    else:
        # Sin credencial no hay nada que deshacer en Meta: se anota.
        meta["skipped"] = "no_credentials"
    _write_catalog(cfg, None)
    cfg.pop("catalog_error", None)
    ch.config = cfg
    flag_modified(ch, "config")
    if waba_id:
        await redis.delete(_cache_key(waba_id))
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action="console.channel.catalog",
        target=f"channel:{ch.id}",
        before={"catalog": before.model_dump(mode="json")},
        after={"catalog": None, "meta": meta},
    )
    return _detail(ch, await channel_logos(scope.session), "none")


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
        # Un número en coexistencia sigue registrado desde la app WhatsApp
        # Business del partner: el alta **no** lo registró (Meta contesta
        # CallingNotAllowed), así que tampoco hay nada que dar de baja. Medido
        # en staging el 2026-09-29 con el número real: `deregister` sobre él
        # fue rechazado. Lo simétrico del alta es no pedirlo (research D5).
        coexistencia = str(cfg.get("mode") or "") == "coexistence"
        if fila.status is ChannelStatus.DISCONNECTED:
            before = ChannelStatus.DISCONNECTED.value
            pending = [
                str(x)
                for x in (cfg.get("unlink_pending") or [])
                if not (coexistencia and str(x) == "deregister")
            ]
        else:
            before = fila.status.value
            waba_id = cfg.get("waba_id")
            hermanos = 0
            if waba_id:
                # En **toda** la plataforma, no solo en este cliente: los
                # números propios de Auphere comparten cuenta entre clientes,
                # y desuscribir la aplicación es por cuenta. La función solo
                # devuelve cuántos (migración 0133); nunca cuáles ni de quién.
                hermanos = int(
                    await s1.scalar(
                        sa.text("SELECT count_live_channels_for_waba(:w, :c)"),
                        {"w": str(waba_id), "c": str(channel_id)},
                    )
                    or 0
                )
            pending = ([] if coexistencia else ["deregister"]) + (
                ["unsubscribe"] if hermanos == 0 else []
            )
            fila.status = ChannelStatus.DISCONNECTED
            cfg["unlink_pending"] = pending
            fila.config = cfg
            flag_modified(fila, "config")
            await s1.flush()
        if not pending and before == ChannelStatus.DISCONNECTED.value:
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
                    except MetaAPIError as exc:
                        if step == "deregister" and deregister_not_applicable(exc):
                            # Meta lo dice con estas palabras cuando el número
                            # está en coexistencia (medido en producción el
                            # 2026-09-30): nunca lo registramos por Cloud API,
                            # así que no hay nada que dar de baja. Se anota el
                            # modo para que el diálogo y el próximo reintento
                            # lo sepan, y se sigue con la desuscripción.
                            skipped.append(step)
                            pending.remove(step)
                            cfg["mode"] = "coexistence"
                            continue
                        # Queda pendiente, y los que vienen detrás también: no
                        # tiene sentido desuscribir lo que no se pudo dar de baja.
                        # El motivo se guarda para el registro y el log — no
                        # para la pantalla (constitución III): en staging el
                        # primer rechazo real llegó sin rastro de por qué.
                        motivo = {
                            "step": step,
                            "status_code": getattr(exc, "status_code", None),
                            "code": getattr(exc, "code", None),
                            "message": str(exc)[:300],
                        }
                        cfg["unlink_error"] = motivo
                        log.warning(
                            "channel.unlink.step_failed",
                            channel_id=str(channel_id),
                            **motivo,
                        )
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
                cfg.pop("unlink_error", None)
            fila.config = cfg
            flag_modified(fila, "config")
            meta: dict[str, object] = {"done": done, "pending": pending}
            if skipped:
                meta["skipped"] = skipped
            if cfg.get("unlink_error"):
                meta["error"] = cfg["unlink_error"]
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
