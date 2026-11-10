"""``GET /console/search?q=`` — el buscador ⌘K de la consola (spec 047, T008, R47.2).

Devuelve cuatro listas:

- **clientes** del partner cuyo nombre (o referencia) contiene ``q``. El nicho
  llega con la ficha del negocio (bloque B); hasta entonces es ``None``;
- **agentes activos** cuyo nombre contiene ``q``, con su cliente;
- **pantallas** y **acciones**, como claves estables. Sus textos son de la
  consola (``shell.search.screen.<key>``, ``shell.search.action.<key>``), así
  que la API las devuelve **todas las permitidas** y es la consola la que las
  empareja con ``q`` por su texto.

El filtro de pantallas y acciones es el de la navegación de hoy
(``apps/console/src/components/shell/nav.ts``): el módulo que Auphere dio al
partner (spec 032) **y** el permiso del rol. Lo que la persona no puede hacer no
aparece (§V).

Los clientes salen de ``partner_tenants`` bajo el partner del principal (tablas
de plataforma). Los agentes viven en ``agents``, con RLS forzada por cliente, y
**no se leen sin cliente puesto**: una transacción con ``app.tenant_id`` por
cliente del partner, cada una en su sesión, con concurrencia acotada —el patrón
de ``console_home.tenant_snapshots``—. Un cliente cuya lectura falla se omite y
el resto responde. Si un partner llega a cientos de clientes, este es el bloque
que pasa a una función ``SECURITY DEFINER`` acotada al partner.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import (
    ConsolePrincipal,
    permissions_for,
    require_console_principal,
)
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, AgentStatus, PartnerTenant, Tenant

from .schemas import (
    SearchActionHit,
    SearchAgentHit,
    SearchClientHit,
    SearchOut,
    SearchScreenHit,
)

log = structlog.get_logger(__name__)

router = APIRouter()

#: Cuántos clientes y cuántos agentes devuelve como mucho.
CLIENT_LIMIT = 8
AGENT_LIMIT = 8
#: Cuántos clientes se leen a la vez para buscar sus agentes. Menos que el
#: Panel (``SNAPSHOT_CONCURRENCY``): ⌘K se consulta mientras se escribe, y cada
#: lectura en marcha es una conexión del pool.
SEARCH_CONCURRENCY = 4


@dataclass(frozen=True)
class Entry:
    """Una pantalla o una acción: su clave, a dónde lleva y qué la permite."""

    key: str
    href: str
    #: El módulo de la spec 032 sin el que no existe (``None``: siempre).
    module: str | None
    #: El permiso de ``core/console_auth`` sin el que no se ve.
    permission: str | None


#: Las pantallas, en el orden del menú.
SCREENS: tuple[Entry, ...] = (
    Entry("home", "/", "panel", None),
    Entry("clients", "/clients", "clients", "clients:read"),
    Entry("usage", "/usage", "usage", "usage:read"),
    Entry("audit", "/audit", "audit", "audit:read"),
    Entry("knowledge", "/knowledge", "knowledge", "playbook:read"),
    Entry("workstation", "/workstation", "workstation", "workstation:read"),
    Entry("team", "/team", "team", "team:read"),
    Entry("billing", "/billing", "billing", "billing:read"),
    Entry("keys", "/keys", "keys", "keys:read"),
    # La campana no es un módulo (spec 032): está para todos.
    Entry("notifications", "/notifications", None, None),
)

#: Las acciones de este bloque. Las que nombran un cliente («Nuevo agente en
#: {cliente}», «Asignar saldo a {cliente}») llegan con sus pantallas.
ACTIONS: tuple[Entry, ...] = (
    Entry("new_client", "/clients/new", "clients", "clients:write"),
    Entry("invite_member", "/team?invite=1", "team", "team:manage"),
    Entry("new_api_key", "/keys?new=1", "keys", "keys:manage"),
)


def _allowed(entries: Iterable[Entry], role: str, modules: Iterable[str]) -> list[Entry]:
    held = permissions_for(role)
    have = set(modules)
    return [
        e
        for e in entries
        if (e.module is None or e.module in have) and (e.permission is None or e.permission in held)
    ]


def allowed_screens(role: str, modules: Iterable[str]) -> list[SearchScreenHit]:
    return [SearchScreenHit(key=e.key, href=e.href) for e in _allowed(SCREENS, role, modules)]


def allowed_actions(role: str, modules: Iterable[str]) -> list[SearchActionHit]:
    return [SearchActionHit(key=e.key, href=e.href) for e in _allowed(ACTIONS, role, modules)]


def search_needle(q: str | None) -> str | None:
    """Lo que se busca: ``q`` sin espacios alrededor, o ``None`` si queda vacío."""
    needle = (q or "").strip()
    return needle or None


async def _clients(
    session: AsyncSession, partner_id: uuid.UUID, needle: str
) -> list[SearchClientHit]:
    """Platform tables, bounded by the principal's partner: the query cannot
    express another one. ``autoescape``: ``%`` and ``_`` are plain characters."""
    async with session.begin():
        rows = (
            await session.execute(
                sa.select(PartnerTenant.external_client_ref, Tenant.name)
                .join(Tenant, Tenant.id == PartnerTenant.tenant_id)
                .where(
                    PartnerTenant.partner_id == partner_id,
                    sa.or_(
                        Tenant.name.icontains(needle, autoescape=True),
                        PartnerTenant.client_name.icontains(needle, autoescape=True),
                        PartnerTenant.external_client_ref.icontains(needle, autoescape=True),
                    ),
                )
                .order_by(sa.func.lower(Tenant.name), PartnerTenant.external_client_ref)
                .limit(CLIENT_LIMIT)
            )
        ).all()
    return [SearchClientHit(ref=ref, name=name, niche=None) for ref, name in rows]


async def _agents(
    session: AsyncSession, partner_id: uuid.UUID, needle: str
) -> list[SearchAgentHit]:
    async with session.begin():
        mapped = (
            await session.execute(
                sa.select(PartnerTenant.tenant_id, PartnerTenant.external_client_ref, Tenant.name)
                .join(Tenant, Tenant.id == PartnerTenant.tenant_id)
                .where(PartnerTenant.partner_id == partner_id)
            )
        ).all()

    sm = get_sessionmaker()
    sem = asyncio.Semaphore(SEARCH_CONCURRENCY)

    async def _one(tenant_id: uuid.UUID, ref: str, client_name: str) -> list[SearchAgentHit]:
        async with sem:
            try:
                # One scoped transaction per client: RLS decides what exists.
                async with sm() as scoped, tenant_scoped_session(scoped, tenant_id):
                    rows = (
                        await scoped.execute(
                            sa.select(Agent.id, Agent.name)
                            .where(
                                Agent.tenant_id == tenant_id,
                                Agent.status == AgentStatus.ACTIVE.value,
                                Agent.name.icontains(needle, autoescape=True),
                            )
                            .order_by(sa.func.lower(Agent.name))
                            .limit(AGENT_LIMIT)
                        )
                    ).all()
            except Exception as exc:
                log.warning(
                    "console_search.agents_failed", tenant_id=str(tenant_id), error=str(exc)
                )
                return []
        return [
            SearchAgentHit(agent_id=aid, name=name, client_ref=ref, client_name=client_name)
            for aid, name in rows
        ]

    chunks = await asyncio.gather(*(_one(tid, ref, name) for tid, ref, name in mapped))
    hits = [hit for chunk in chunks for hit in chunk]
    hits.sort(key=lambda h: (h.name.lower(), h.client_name.lower(), h.client_ref))
    return hits[:AGENT_LIMIT]


@router.get("/search", response_model=SearchOut)
async def search(
    q: str | None = Query(default=None, max_length=120, description="What the person typed"),
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
    session: AsyncSession = Depends(get_db_session),
) -> SearchOut:
    modules = principal.partner.ordered_console_modules()
    out = SearchOut(
        screens=allowed_screens(principal.role, modules),
        actions=allowed_actions(principal.role, modules),
    )
    needle = search_needle(q)
    # Clients and their agents live under «Clientes»: without the module or
    # the permission there is nothing to open.
    if needle is None or "clients" not in modules:
        return out
    held = principal.permissions
    if "clients:read" in held:
        out.clients = await _clients(session, principal.partner.id, needle)
    if "agents:read" in held:
        out.agents = await _agents(session, principal.partner.id, needle)
    return out


__all__ = [
    "ACTIONS",
    "AGENT_LIMIT",
    "CLIENT_LIMIT",
    "SCREENS",
    "Entry",
    "allowed_actions",
    "allowed_screens",
    "router",
    "search_needle",
]
