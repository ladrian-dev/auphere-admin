"""Integraciones: autorizar una vez por cliente, activar por agente — spec 047,
T128 (requisitos 35 y 36; ``contracts/console-api.md`` §6).

- ``GET /clients/{ref}/agents/{agent_id}/integrations?q=&category=``: el catálogo
  que el partner puede usar, primero lo que piden las habilidades del agente, con
  el estado de la conexión del cliente y la activación del agente (35.2);
- ``POST /clients/{ref}/connections`` ``{integration, agent_id?, permission?}``:
  abre la autorización; al terminar, la integración queda activada para ese agente
  con ese permiso (35.3). Si ya estaba autorizada, no la vuelve a pedir (35.4);
- ``PUT /…/agents/{agent_id}/activations/{integration}``
  ``{permission, settings}``: activar o cambiar permiso y ajustes, validados con el
  esquema del catálogo (35.1, 35.5, 36.2);
- ``DELETE /…/agents/{agent_id}/activations/{integration}``: devuelve las
  habilidades afectadas (35.7);
- ``GET /clients/{ref}/connections/{id}``: la cuenta, la salud con la hora de la
  última comprobación, los agentes con su permiso y los ajustes (36.1);
- ``POST /…/connections/{id}/reconnect`` · ``POST /…/connections/{id}/disconnect``
  ``{confirm}``: «Desconectar para todos» lista lo afectado y pide confirmación
  (36.4).

Nunca devuelve credenciales.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from nexus_api.db.models import AgentConnectorActivation, Connector, TenantConnector
from nexus_api.services import activations as svc
from nexus_api.services.connectors import catalog as connector_catalog
from nexus_api.services.connectors import service as connector_service
from nexus_api.services.connectors.composio_client import ComposioClientProtocol
from nexus_api.services.connectors.runtime import get_composio_client

from .agent_draft_routes import agent_in_path
from .deps import ClientScope, client_scope
from .tools import _logo, start_consent

router = APIRouter(prefix="/clients/{ref}")

Permission = Literal["read", "ask_before_write", "read_write"]


class ConnectionStateOut(BaseModel):
    id: uuid.UUID
    status: str
    last_checked_at: datetime | None = None


class ActivationOut(BaseModel):
    permission: Permission
    settings: dict[str, Any] = Field(default_factory=dict)


class IntegrationOut(BaseModel):
    slug: str
    name: str
    category: str
    logo: str | None = None
    #: Cómo se autoriza: ``oauth_composio``, ``api_key``, ``browser_credentials``…
    auth_kind: str
    #: La piden las habilidades del agente (va primero, 35.2).
    needed: bool = False
    connection: ConnectionStateOut | None = None
    activation: ActivationOut | None = None
    settings_schema: dict[str, Any] | None = None


class ConnectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration: str = Field(min_length=1, max_length=80)
    agent_id: uuid.UUID | None = None
    permission: Permission = "read"


class ActivationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permission: Permission
    settings: dict[str, Any] = Field(default_factory=dict)


class AffectedOut(BaseModel):
    skills: list[str]
    procedures: list[str]


class AgentUseOut(BaseModel):
    agent_id: uuid.UUID
    name: str
    permission: Permission
    settings: dict[str, Any]


class ConnectionPageOut(BaseModel):
    id: uuid.UUID
    integration: str
    name: str
    logo: str | None = None
    status: str
    #: «Hay que volver a autorizar» (36.3).
    needs_reauth: bool
    account: str | None = None
    connected_at: datetime | None = None
    last_checked_at: datetime | None = None
    agents: list[AgentUseOut]
    settings_schema: dict[str, Any] | None = None


class DisconnectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = False


def _error(exc: svc.ActivationError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, **exc.extra})


# ── el catálogo del agente ─────────────────────────────────────────────────


@router.get("/agents/{agent_id}/integrations", response_model=list[IntegrationOut])
async def agent_integrations(
    q: str | None = Query(default=None, max_length=80),
    category: str | None = Query(default=None, max_length=40),
    scope: ClientScope = Depends(agent_in_path("agents:read")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> list[IntegrationOut]:
    assert scope.agent_id is not None
    entries = await connector_catalog.list_catalog(scope.session, composio, category=category)
    installs = {
        row.Connector.slug: row.TenantConnector
        for row in (
            await scope.session.execute(
                sa.select(Connector, TenantConnector).join(
                    TenantConnector, TenantConnector.connector_id == Connector.id
                )
            )
        ).all()
    }
    activations = {
        row.slug: row.AgentConnectorActivation
        for row in (
            await scope.session.execute(
                sa.select(Connector.slug, AgentConnectorActivation)
                .join(TenantConnector, TenantConnector.connector_id == Connector.id)
                .join(
                    AgentConnectorActivation,
                    AgentConnectorActivation.connector_id == TenantConnector.id,
                )
                .where(AgentConnectorActivation.agent_id == scope.agent_id)
            )
        ).all()
    }
    needed = await svc.needed_by(scope.session, scope.agent_id)
    needle = (q or "").strip().lower()
    out: list[IntegrationOut] = []
    for entry in entries:
        # WhatsApp y TikTok son canales (``channel_only``): viven en Canales,
        # como en el admin. Aquí salían «Sin conectar» con el número conectado.
        if (entry.provider_meta or {}).get("channel_only") is True:
            continue
        if needle and needle not in f"{entry.slug} {entry.display_name} {entry.vendor}".lower():
            continue
        install = installs.get(entry.slug)
        activation = activations.get(entry.slug)
        schema = (
            connector_catalog.SETTINGS_SCHEMAS.get(entry.slug)
            if entry.id is None
            else connector_catalog.settings_schema_of(
                await scope.session.get(Connector, entry.id)  # type: ignore[arg-type]
            )
        )
        out.append(
            IntegrationOut(
                slug=entry.slug,
                name=entry.display_name,
                category=entry.category,
                logo=_logo(entry.provider_meta),
                auth_kind=entry.auth_kind,
                needed=entry.slug in needed,
                connection=ConnectionStateOut(
                    id=install.id, status=install.status, last_checked_at=install.last_checked_at
                )
                if install is not None
                else None,
                activation=ActivationOut(
                    permission=activation.permission,
                    settings=dict(activation.settings or {}),
                )
                if activation is not None
                else None,
                settings_schema=schema,
            )
        )
    out.sort(key=lambda i: (not i.needed, i.connection is None, i.name.lower()))
    return out


# ── conectar y activar ─────────────────────────────────────────────────────


@router.post("/connections", status_code=status.HTTP_201_CREATED, response_model=None)
async def connect(
    body: ConnectIn,
    scope: ClientScope = Depends(client_scope("agents:write")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> Any:
    """Autorizar (35.3). Ya autorizada: activa en el agente sin volver a pedirla
    (35.4). Para OAuth devuelve la URL firmada; la activación queda pendiente en
    la conexión y se aplica cuando la autorización termina."""
    try:
        connector, install = await svc.connection_of(
            scope.session, scope.tenant.id, body.integration
        )
    except svc.ActivationError:
        connector, install = None, None
    if install is not None and install.status in svc.LIVE:
        if body.agent_id is None:
            return {"status": "connected", "connection_id": str(install.id)}
        try:
            await svc.activate(
                scope.session,
                tenant_id=scope.tenant.id,
                agent_id=body.agent_id,
                slug=body.integration,
                permission=body.permission,
                settings={},
                actor=scope.principal.actor,
            )
        except svc.ActivationError as exc:
            raise _error(exc) from None
        return {"status": "activated", "connection_id": str(install.id)}
    if connector is not None and connector.auth_kind != "oauth_composio":
        # Una clave o un formulario: la consola lo pide con el alta de siempre y
        # después activa (PUT …/activations).
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": {
                    "code": "authorize_with_form",
                    "auth_kind": connector.auth_kind,
                    "form": (connector.provider_meta or {}).get("credentials_form"),
                }
            },
        )
    consent = await start_consent(body.integration, scope=scope, composio=composio)
    if body.agent_id is not None:
        _, install = await svc.connection_of(scope.session, scope.tenant.id, body.integration)
        if install is not None:
            install.config = {
                **dict(install.config or {}),
                "pending_activation": {
                    "agent_id": str(body.agent_id),
                    "permission": body.permission,
                    "by": scope.principal.actor,
                },
            }
    return consent


@router.put("/agents/{agent_id}/activations/{integration}", response_model=ActivationOut)
async def put_activation(
    integration: str,
    body: ActivationIn,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
) -> ActivationOut:
    assert scope.agent_id is not None
    try:
        row = await svc.activate(
            scope.session,
            tenant_id=scope.tenant.id,
            agent_id=scope.agent_id,
            slug=integration,
            permission=body.permission,
            settings=body.settings,
            actor=scope.principal.actor,
        )
    except svc.ActivationError as exc:
        raise _error(exc) from None
    return ActivationOut(permission=row.permission, settings=dict(row.settings or {}))  # type: ignore[arg-type]


@router.delete("/agents/{agent_id}/activations/{integration}", response_model=AffectedOut)
async def delete_activation(
    integration: str, scope: ClientScope = Depends(agent_in_path("agents:write"))
) -> AffectedOut:
    assert scope.agent_id is not None
    try:
        affected = await svc.deactivate(
            scope.session,
            tenant_id=scope.tenant.id,
            agent_id=scope.agent_id,
            slug=integration,
            actor=scope.principal.actor,
        )
    except svc.ActivationError as exc:
        raise _error(exc) from None
    return AffectedOut(skills=affected.skills, procedures=affected.procedures)


# ── la página de la conexión ───────────────────────────────────────────────


async def _install(
    scope: ClientScope, connection_id: uuid.UUID
) -> tuple[TenantConnector, Connector]:
    install = await scope.session.get(TenantConnector, connection_id)
    if install is None or install.tenant_id != scope.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown connection")
    connector = await scope.session.get(Connector, install.connector_id)
    assert connector is not None
    return install, connector


def _account(install: TenantConnector) -> str | None:
    """Lo que identifica la cuenta sin enseñar credenciales."""
    ref = install.credentials_ref or {}
    meta = ref.get("endpoint_meta") or {}
    for key in ("account_label", "store_url", "email", "base_url"):
        value = ref.get(key) or (meta.get(key) if isinstance(meta, dict) else None)
        if isinstance(value, str) and value and value != "console":
            return value
    return None


@router.get("/connections/{connection_id}", response_model=ConnectionPageOut)
async def connection_page(
    connection_id: uuid.UUID, scope: ClientScope = Depends(client_scope("agents:read"))
) -> ConnectionPageOut:
    install, connector = await _install(scope, connection_id)
    return ConnectionPageOut(
        id=install.id,
        integration=connector.slug,
        name=connector.display_name,
        logo=_logo(connector.provider_meta),
        status=install.status,
        needs_reauth=install.status == "needs_reauth",
        account=_account(install),
        connected_at=install.connected_at,
        last_checked_at=install.last_checked_at,
        agents=[
            AgentUseOut(**u) for u in await svc.users_of(scope.session, scope.tenant.id, install)
        ],
        settings_schema=connector_catalog.settings_schema_of(connector),
    )


@router.post("/connections/{connection_id}/reconnect", response_model=None)
async def reconnect(
    connection_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("agents:write")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> Any:
    """«Reconectar»: vuelve a pedir la autorización; las activaciones se quedan."""
    _install_row, connector = await _install(scope, connection_id)
    if connector.auth_kind != "oauth_composio":
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": {"code": "authorize_with_form", "auth_kind": connector.auth_kind}},
        )
    return await start_consent(connector.slug, scope=scope, composio=composio)


@router.post("/connections/{connection_id}/disconnect", response_model=None)
async def disconnect_for_all(
    connection_id: uuid.UUID,
    body: DisconnectIn | None = None,
    scope: ClientScope = Depends(client_scope("agents:write")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> Any:
    """«Desconectar para todos» (36.4): sin ``confirm``, la lista de agentes y
    habilidades afectadas; con ``confirm``, se desconecta y se quitan las
    activaciones."""
    install, connector = await _install(scope, connection_id)
    impact = await svc.disconnect_impact(scope.session, scope.tenant.id, install)
    if not (body and body.confirm):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": {"code": "confirm_required", "affected": impact}},
        )
    await connector_service.disconnect_connector(
        scope.session,
        tenant=scope.tenant,
        connector_slug=connector.slug,
        composio=composio,
        actor=scope.principal.actor,
    )
    await scope.session.execute(
        sa.delete(AgentConnectorActivation).where(
            AgentConnectorActivation.tenant_id == scope.tenant.id,
            AgentConnectorActivation.connector_id == install.id,
        )
    )
    return {"status": "disconnected", "affected": impact}


__all__ = ["router"]
