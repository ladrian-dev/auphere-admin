"""El puente, versión 2 — spec 002 (`contracts/device-bridge-v2.md`).

**No va bajo `/console`**, y no es cosmética: `/console/*` lo llama una persona con
una sesión, y lo audita `test_console_scope` con reglas pensadas para eso. Esto lo
llama una **máquina** con una credencial de dispositivo.

**Todo es respuesta a una llamada de la máquina.** No hay ninguna ruta que empuje
hacia la máquina del partner: ``poll`` devuelve lo que haya. Instalar esto no abre
un puerto en casa de nadie (001-R6.1).

**La credencial abre cinco operaciones y ninguna más** (Requisito 4.2): latir,
sondear, devolver resultado, renovar y declarar el directorio de un cliente. Más
el canje del código —``pair``—, que es la única ruta sin credencial porque el
código **es** la credencial de un solo uso.

**Ni el tenant ni el partner llegan del llamante.** El partner viaja dentro de la
firma; el tenant se resuelve desde un ``client_ref`` **dentro de ese partner**, y
la RLS decide después. Es §I aplicado a un canal sin persona detrás.

**`require_device` carga la fila en cada petición.** Es lo que hace verdadero el
«revocable por sí sola»: archivada → 403, generación vieja → 401, treinta días
sin latir → 403 ``pairing_required``. Quien tenía una credencial válida merece
saber por qué dejó de valer (§V); un token inválido sigue recibiendo 401 mudo.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.partner_context import apply_partner_to_session, partner_context
from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.models import (
    AuditLog,
    LocalExecution,
    Partner,
    PartnerDevice,
    PartnerTenant,
    Tenant,
)
from nexus_api.repositories.local_workstation import (
    DeviceClientLinkRepository,
    DevicePairingCodeRepository,
    LocalExecutionRepository,
    PartnerDeviceRepository,
)
from nexus_api.services.device_credential import (
    DeviceClaims,
    DeviceCredentialError,
    generation_is_acceptable,
    is_abandoned,
    issue_device_token,
    verify_device_token,
)
from nexus_api.services.device_pairing import (
    PairingRateLimited,
    PairingRateLimiter,
    normalize_code,
)
from nexus_api.services.local_dispatch import (
    ExecutionResult,
    claim_for_device,
    publish_result,
)

log = structlog.get_logger(__name__)

#: Techos con los que se entrega un comando. Son los de la 001
#: (``local-runner.ts``): el reloj absoluto y el de inactividad. Viajan en el
#: trabajo para que la máquina no tenga que conocerlos de memoria y para que
#: bajarlos sea un cambio de servidor, no un despliegue de la aplicación.
DEFAULT_EXECUTION_TIMEOUT_MS = 600_000
DEFAULT_EXECUTION_IDLE_MS = 300_000

router = APIRouter(prefix="/device", tags=["device-bridge"])


# ── rechazos con motivo (§V) ────────────────────────────────────────────


class DeviceRefused(Exception):
    """Un 403 que **sí** dice por qué: quien tenía una credencial válida merece saberlo."""

    def __init__(self, code: str, *, reason: str | None = None, status_code: int = 403) -> None:
        super().__init__(code)
        self.code = code
        self.reason = reason
        self.status_code = status_code


async def device_refused_handler(_: Request, exc: DeviceRefused) -> JSONResponse:
    body: dict[str, Any] = {"code": exc.code}
    if exc.reason:
        body["reason"] = exc.reason
    return JSONResponse(status_code=exc.status_code, content=body)


def _audit(
    session: AsyncSession, *, actor: str, action: str, partner_id: uuid.UUID, **after: Any
) -> None:
    session.add(
        AuditLog(
            tenant_id=None,
            actor=actor,
            action=action,
            target=f"partner:{partner_id}",
            after_json=after,
        )
    )


# ── la credencial en cada petición ──────────────────────────────────────


@dataclass
class DeviceContext:
    """La máquina resuelta, con la transacción abierta y **sin acotar todavía**.

    Cada operación elige su ámbito: ``scope_partner()`` para lo que es de la
    máquina (latir, sondear, renovar), ``scope_tenant()`` para lo que es de un
    cliente (cerrar un asiento, declarar un directorio). Acotar antes de saber
    a qué tenant pertenece un asiento haría invisible el asiento.
    """

    claims: DeviceClaims
    device: PartnerDevice
    session: AsyncSession

    async def scope_partner(self) -> None:
        await apply_partner_to_session(
            self.session, self.device.partner_id, principal_id=self.device.principal_id
        )

    async def scope_tenant(self, tenant_id: uuid.UUID) -> None:
        await apply_tenant_to_session(self.session, tenant_id)


def _bearer(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


async def require_device(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_db_session),
) -> AsyncIterator[DeviceContext]:
    """Resuelve qué máquina llama y comprueba su fila, en el orden del contrato:
    firma → archivada → generación → abandono. Deja la transacción abierta."""
    try:
        claims = verify_device_token(_bearer(authorization))
    except DeviceCredentialError as exc:
        # Se registra el intento (001-R6.4) sin filtrar el motivo al llamante.
        log.warning("device_bridge.rejected", reason=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from exc

    async with session.begin():
        device = await session.get(PartnerDevice, claims.device_id)
        if device is None or device.partner_id != claims.partner_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        if device.revoked_at is not None:
            raise DeviceRefused("device_archived", reason=device.revoked_reason)
        if not generation_is_acceptable(
            claims.generation,
            current=device.credential_generation,
            rotated_at=device.credential_rotated_at,
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        if is_abandoned(device.last_heartbeat_at):
            raise DeviceRefused("pairing_required")
        with partner_context(str(device.partner_id)):
            yield DeviceContext(claims=claims, device=device, session=session)


# ── esquemas ────────────────────────────────────────────────────────────


class PairIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    hostname: str = Field(min_length=1, max_length=255)
    platform: str = Field(pattern="^(macos|windows)$")
    app_version: str | None = Field(default=None, max_length=64)


class PairedOut(BaseModel):
    """Se devuelve **una sola vez**; la credencial no se puede volver a leer."""

    device_id: uuid.UUID
    credential: str
    generation: int
    expires_at: datetime
    partner_slug: str
    principal_id: str
    display_name: str


class HeartbeatIn(BaseModel):
    app_version: str | None = Field(default=None, max_length=64)


class LinkOut(BaseModel):
    client_ref: str
    client_name: str | None = None
    workdir: str | None = None
    needs_directory: bool


class PollOut(BaseModel):
    """Lo que la plataforma tiene para esta máquina. Vacío es una respuesta."""

    work: list[dict[str, Any]] = Field(default_factory=list)
    links: list[LinkOut] = Field(default_factory=list)


class ResultIn(BaseModel):
    execution_id: uuid.UUID
    outcome: str = Field(pattern="^(completada|expirada|terminada|denegada)$")
    exit_code: int | None = None
    children_reaped: int = 0
    #: Spec 003 — una muestra acotada de lo que el comando escribió, para que el
    #: teammate pueda leer el resultado de lo que pidió. **No se persiste**: va
    #: a Redis, de ahí al modelo marcada como dato no confiable, y se descarta.
    #: La auditoría sigue diciendo qué pasó, no qué dijo el comando (§III).
    stdout_sample: str | None = Field(default=None, max_length=2048)
    #: El motivo cuando la contención de la máquina denegó (001-R12).
    denial_code: str | None = Field(default=None, max_length=64)


class RenewedOut(BaseModel):
    credential: str
    generation: int
    expires_at: datetime


class DeclareChecks(BaseModel):
    exists: bool = False
    is_dir: bool = False
    resolves_within: bool = False
    readable: bool = False


class DeclareLinkIn(BaseModel):
    client_ref: str = Field(min_length=1, max_length=255)
    workdir: str = Field(min_length=1)
    checks: DeclareChecks = Field(default_factory=DeclareChecks)


# ── el canje del código: la única ruta sin credencial ───────────────────


@router.post("/pair", response_model=PairedOut, status_code=status.HTTP_201_CREATED)
async def pair(
    body: PairIn,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> PairedOut | JSONResponse:
    """Canjea el código por la credencial. Un solo uso; un solo cuerpo para todo fallo."""
    client_ip = request.client.host if request.client else "?"
    machine_key = f"{body.hostname}|{client_ip}"
    limiter = PairingRateLimiter(redis)
    try:
        await limiter.check(machine_key)
    except PairingRateLimited as exc:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"code": "pairing_rate_limited"},
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    async def deny(reason: str) -> JSONResponse:
        await limiter.record_failure(machine_key)
        async with session.begin():
            # Sin partner conocido no hay a quién colgárselo: fila de plataforma.
            session.add(
                AuditLog(
                    tenant_id=None,
                    actor="device:unpaired",
                    action="device.pair_denied",
                    target="platform:device-pairing",
                    after_json={"reason": reason, "hostname": body.hostname},
                )
            )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"code": "pairing_code_invalid"}
        )

    code = normalize_code(body.code)
    if code is None:
        return await deny("malformed")

    async with session.begin():
        row = await DevicePairingCodeRepository(session).consume(code)
        row_id = row.id if row is not None else None
        partner_id = row.partner_id if row is not None else None
        principal_id = row.principal_id if row is not None else None
    if row_id is None or partner_id is None or principal_id is None:
        return await deny("unknown_expired_or_used")

    async with session.begin():
        partner = await session.get(Partner, partner_id)
        if partner is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        slug = partner.slug
        await apply_partner_to_session(session, partner_id, principal_id=principal_id)
        with partner_context(str(partner_id)):
            device = await PartnerDeviceRepository(session).pair(
                principal_id=principal_id,
                display_name=body.hostname,
                hostname=body.hostname,
                platform=body.platform,
                app_version=body.app_version,
            )
            await DevicePairingCodeRepository(session).bind_device(row_id, device.id)
            token = issue_device_token(
                device_id=device.id, partner_id=partner_id, generation=device.credential_generation
            )
            _audit(
                session,
                actor=f"console:{principal_id}",
                action="device.paired",
                partner_id=partner_id,
                machine=device.display_name,
                device_id=str(device.id),
                hostname=body.hostname,
                platform=body.platform,
            )
            out = PairedOut(
                device_id=device.id,
                credential=token,
                generation=device.credential_generation,
                expires_at=_expires_at(token),
                partner_slug=slug,
                principal_id=principal_id,
                display_name=device.display_name,
            )
    await limiter.clear(machine_key)
    return out


def _expires_at(token: str) -> datetime:
    import jwt

    exp = jwt.decode(token, options={"verify_signature": False})["exp"]
    return datetime.fromtimestamp(int(exp), tz=UTC)


# ── las cinco operaciones ───────────────────────────────────────────────


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def heartbeat(body: HeartbeatIn, ctx: DeviceContext = Depends(require_device)) -> None:
    """Late. **Solo** mueve `last_heartbeat_at`: no hay estado que desincronizar."""
    await ctx.scope_partner()
    await PartnerDeviceRepository(ctx.session).record_heartbeat(ctx.device.id)


@router.get("/poll", response_model=PollOut)
async def poll(ctx: DeviceContext = Depends(require_device)) -> PollOut:
    """Devuelve el trabajo pendiente de **esta** máquina y sus vínculos.

    ``links`` es lo que la barra necesita para saber qué directorios faltan
    (002-R7). ``work`` es lo que la spec 003 añadió: las ejecuciones que un
    teammate dejó en cola para esta máquina.

    El trabajo se busca **cliente a cliente**: ``local_executions`` es una tabla
    de tenant y su RLS no se puede saltar «porque la máquina es del partner».
    Son tantas consultas como clientes tenga la máquina —dos o tres—, y esa es
    exactamente la razón por la que se puede hacer así.
    """
    await ctx.scope_partner()
    links = await DeviceClientLinkRepository(ctx.session).active_for_device(ctx.device.id)
    refs = await _refs_for(ctx.session, ctx.device.partner_id, [link.tenant_id for link in links])
    work: list[dict[str, Any]] = []
    for link in links:
        if link.tenant_id not in refs or link.workdir is None:
            # Sin directorio declarado no hay dónde ejecutar (002-R7.5): el
            # trabajo se queda en cola hasta que la persona lo declare.
            continue
        await ctx.scope_tenant(link.tenant_id)
        with tenant_context(link.tenant_id):
            claimed = await claim_for_device(ctx.session, ctx.device.id)
        for row in claimed:
            work.append(
                {
                    "execution_id": str(row.id),
                    "client_ref": refs[link.tenant_id][0],
                    "executable": row.executable,
                    "args": json.loads(row.argv_signature) if row.argv_signature else [],
                    "cwd_relative": None,
                    "timeout_ms": DEFAULT_EXECUTION_TIMEOUT_MS,
                    "idle_timeout_ms": DEFAULT_EXECUTION_IDLE_MS,
                }
            )
    # Se vuelve al ámbito del partner: lo de abajo es de la máquina, no de un cliente.
    await ctx.scope_partner()
    return PollOut(
        work=work,
        links=[
            LinkOut(
                client_ref=refs[link.tenant_id][0],
                client_name=refs[link.tenant_id][1],
                workdir=link.workdir,
                needs_directory=link.workdir is None,
            )
            for link in links
            if link.tenant_id in refs
        ],
    )


async def _refs_for(
    session: AsyncSession, partner_id: uuid.UUID, tenant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str | None]]:
    if not tenant_ids:
        return {}
    rows = await session.execute(
        select(
            PartnerTenant.tenant_id, PartnerTenant.external_client_ref, PartnerTenant.client_name
        ).where(PartnerTenant.partner_id == partner_id, PartnerTenant.tenant_id.in_(tenant_ids))
    )
    return {tenant_id: (ref, name) for tenant_id, ref, name in rows.all()}


@router.post("/result", status_code=status.HTTP_204_NO_CONTENT)
async def result(
    body: ResultIn,
    ctx: DeviceContext = Depends(require_device),
    redis: Redis = Depends(get_redis),
) -> None:
    """Cierra el asiento de auditoría. La salida del comando **no** viaja aquí.

    El asiento es de tenant: se localiza por id **antes** de acotar (acotado sería
    invisible), se comprueba que su tenant es del partner de la firma, y solo
    entonces se entra en el tenant para cerrarlo.
    """
    execution = await ctx.session.get(LocalExecution, body.execution_id)
    if execution is None:
        return
    tenant = await ctx.session.get(Tenant, execution.tenant_id)
    if tenant is None or tenant.partner_id != ctx.device.partner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await ctx.scope_tenant(execution.tenant_id)
    with tenant_context(execution.tenant_id):
        await LocalExecutionRepository(ctx.session).finish(
            body.execution_id,
            outcome=body.outcome,
            exit_code=body.exit_code,
            children_reaped=body.children_reaped,
            denial_reason=body.denial_code,
        )
    # Lo que el teammate esperaba. Va por Redis y **no** a la fila: la muestra
    # de salida es dato para el modelo, no auditoría (§III).
    await publish_result(
        redis,
        body.execution_id,
        ExecutionResult(
            outcome=body.outcome,
            exit_code=body.exit_code,
            stdout_sample=(body.stdout_sample or "")[:2048],
            denial_code=body.denial_code,
        ),
    )


@router.post("/renew", response_model=RenewedOut)
async def renew(ctx: DeviceContext = Depends(require_device)) -> RenewedOut:
    """Rota la generación. La anterior vale 60 s más y ni uno. Actor: la máquina."""
    await ctx.scope_partner()
    generation = await PartnerDeviceRepository(ctx.session).rotate_credential(ctx.device.id)
    token = issue_device_token(
        device_id=ctx.device.id, partner_id=ctx.device.partner_id, generation=generation
    )
    _audit(
        ctx.session,
        actor=f"device:{ctx.device.id}",
        action="device.renewed",
        partner_id=ctx.device.partner_id,
        machine=ctx.device.display_name,
        generation=generation,
    )
    return RenewedOut(credential=token, generation=generation, expires_at=_expires_at(token))


@router.post("/links", status_code=status.HTTP_204_NO_CONTENT)
async def declare_link(
    body: DeclareLinkIn, ctx: DeviceContext = Depends(require_device)
) -> Response:
    """Declara el directorio de un cliente. El tenant sale de ``client_ref`` **dentro
    del partner de la firma**; un ref ajeno es un 404 que deja asiento.

    Las denegaciones se devuelven, no se lanzan: una excepción dentro de la
    transacción abierta desharía el asiento que precisamente se quiere dejar.
    """
    mapping = await ctx.session.get(PartnerTenant, (ctx.device.partner_id, body.client_ref))
    if mapping is None:
        _audit(
            ctx.session,
            actor=f"device:{ctx.device.id}",
            action="device.link_denied",
            partner_id=ctx.device.partner_id,
            machine=ctx.device.display_name,
            client_ref=body.client_ref,
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND, content={"code": "client_unknown"}
        )
    await ctx.scope_tenant(mapping.tenant_id)
    with tenant_context(mapping.tenant_id):
        link = await DeviceClientLinkRepository(ctx.session).declare_workdir(
            device_id=ctx.device.id, workdir=body.workdir
        )
        if link is None:
            # Se vincula desde la consola; la máquina solo declara.
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, content={"code": "client_not_linked"}
            )
        # El asiento es del tenant del cliente: se escribe en su ámbito.
        ctx.session.add(
            AuditLog(
                tenant_id=mapping.tenant_id,
                actor=f"device:{ctx.device.id}",
                action="device.link_declared",
                target=f"partner:{ctx.device.partner_id}",
                after_json={
                    "machine": ctx.device.display_name,
                    "client": body.client_ref,
                    "checks": body.checks.model_dump(),
                },
            )
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
