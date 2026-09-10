"""``/console/clients/{ref}/workstation`` — lo que del puesto de trabajo es del cliente.

**La lista blanca de ejecutables solo se modifica aquí.** Ése es el punto entero del
Requisito 2: un ejecutable ausente de la lista no se puede aprobar en caliente
durante una conversación; entra por esta puerta, con una persona detrás y su nombre
en la fila. Lo que sí se aprueba en el turno son *argumentos* de un ejecutable ya
permitido, y eso no se toca desde aquí.

Por eso ``workstation:write`` no lo tiene el rol *builder*: añadir un ejecutable es
una decisión de seguridad, no de configuración.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from redis.asyncio import Redis
from sqlalchemy import select

from nexus_api.api.deps import get_redis
from nexus_api.config import get_settings
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.models import PartnerDevice
from nexus_api.db.models.companion import CompanionAction
from nexus_api.db.models.local_workstation import DENIAL_DISPOSITIVO_AUSENTE
from nexus_api.repositories.local_workstation import (
    DeviceClientLinkRepository,
    LocalArgumentGrantRepository,
    LocalExecutableRepository,
    LocalExecutionRepository,
)
from nexus_api.services.local_dispatch import await_result, dispatch
from nexus_api.services.local_exec_gate import LocalExecGate
from nexus_api.services.local_exec_policy import LocalExecPolicyRepository

from .deps import ClientScope, client_scope
from .schemas_workstation import (
    DeviceOut,
    ExecutableIn,
    ExecutableOut,
    ExecutionIn,
    ExecutionOut,
    ExecutionOutcomeOut,
)

router = APIRouter(prefix="/clients/{ref}/workstation")

#: Requisito 4.2 — el latido se emite cada 10 s y la presencia caduca a los 30.
#: La convención es la de Kubernetes y Consul, y cabe dentro del minuto de CE-004.
PRESENCE_EXPIRY = timedelta(seconds=30)


def _presence(device: PartnerDevice, *, now: datetime | None = None) -> str:
    """Deriva la presencia. No hay columna que consultar, y es a propósito."""
    if device.last_heartbeat_at is None:
        return "ausente"
    reference = now or datetime.now(UTC)
    return "presente" if reference - device.last_heartbeat_at < PRESENCE_EXPIRY else "ausente"


# ── máquinas vinculadas a este cliente ────────────────────────────────
#
# Spec 002: la máquina es del partner y se da de alta emparejándola desde
# `/console/workstation`. Aquí solo se listan las que sirven a **este** cliente,
# y solo las que la persona puede ver (las suyas, o todas si gestiona).


@router.get("/devices", response_model=list[DeviceOut])
async def list_devices(
    scope: ClientScope = Depends(client_scope("workstation:read")),
) -> list[DeviceOut]:
    await apply_partner_to_session(
        scope.session,
        scope.principal.partner.id,
        principal_id=scope.principal.user_id,
        workstation_manager="workstation:write" in scope.principal.permissions,
    )
    links = await DeviceClientLinkRepository(scope.session).active_for_tenant()
    out: list[DeviceOut] = []
    for link in links:
        device = await scope.session.get(PartnerDevice, link.device_id)
        if device is None or device.revoked_at is not None:
            continue
        out.append(
            DeviceOut(
                id=device.id,
                display_name=device.display_name,
                platform=device.platform,
                workdir=link.workdir,
                app_version=device.app_version,
                last_heartbeat_at=device.last_heartbeat_at,
                presence=_presence(device),
                enrolled_at=device.enrolled_at,
            )
        )
    return out


# ── lista blanca ───────────────────────────────────────────────────────


@router.get("/executables", response_model=list[ExecutableOut])
async def list_executables(
    scope: ClientScope = Depends(client_scope("workstation:read")),
) -> list[ExecutableOut]:
    rows = await LocalExecutableRepository(scope.session).list_active()
    return [
        ExecutableOut(id=r.id, executable=r.executable, added_by=r.added_by, added_at=r.added_at)
        for r in rows
    ]


@router.post("/executables", response_model=ExecutableOut, status_code=status.HTTP_201_CREATED)
async def add_executable(
    payload: ExecutableIn,
    scope: ClientScope = Depends(client_scope("workstation:write")),
) -> ExecutableOut:
    """Añade un ejecutable a la lista blanca, con la persona que lo decidió."""
    row = await LocalExecutableRepository(scope.session).add(
        executable=payload.executable, added_by=scope.principal.user_id
    )
    return ExecutableOut(
        id=row.id, executable=row.executable, added_by=row.added_by, added_at=row.added_at
    )


@router.delete("/executables/{executable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_executable(
    executable_id: uuid.UUID,
    scope: ClientScope = Depends(client_scope("workstation:write")),
) -> None:
    await LocalExecutableRepository(scope.session).archive(executable_id)


# ── auditoría ──────────────────────────────────────────────────────────


@router.get("/executions", response_model=list[ExecutionOut])
async def recent_executions(
    scope: ClientScope = Depends(client_scope("workstation:read")),
) -> list[ExecutionOut]:
    """Qué se ejecutó y qué se denegó. **No** qué dijo el comando (§III)."""
    rows = await LocalExecutionRepository(scope.session).recent()
    return [
        ExecutionOut(
            id=r.id,
            executable=r.executable,
            outcome=r.outcome,
            denial_code=r.denial_reason,
            started_at=r.started_at,
            ended_at=r.ended_at,
            exit_code=r.exit_code,
            children_reaped=r.children_reaped,
        )
        for r in rows
    ]


# ── ejecutar en la máquina (spec 003, Requisitos 3.3 y 10) ─────────────
#
# **Esta es la única puerta.** La 001 dejó el puente saliente, el gate, la
# contención y la auditoría; lo que faltaba era quién pone trabajo en la cola.
# Aquí se junta todo, y en este orden:
#
#   1. ¿hay máquina presente con directorio para este cliente? (002-R7.5)
#   2. la lista blanca y los metacaracteres (001-R2) — lo que no está no se
#      aprueba en caliente;
#   3. las dos capas de la 003 (techo del partner, preferencia de la persona),
#      que **solo restringen**;
#   4. si hace falta permiso, se **contesta pidiéndolo** y no se despacha nada.
#
# La aplicación de una acción ya confirmada entra por aquí también: no lleva
# ninguna marca que el modelo pueda falsificar — se **busca** la acción
# confirmada con esta firma, que solo existe si una persona dijo que sí.


async def _approved_action(
    scope: ClientScope, *, executable: str, argv_signature: str
) -> CompanionAction | None:
    """La acción confirmada que autoriza justo esta invocación, si la hay.

    No se recibe un ``action_id`` por el cuerpo a propósito: sería un campo que
    el modelo podría rellenar. Se busca por contenido, y una acción confirmada
    solo existe si una persona la confirmó.
    """
    rows = (
        (
            await scope.session.execute(
                select(CompanionAction).where(
                    CompanionAction.kind == "local_exec",
                    CompanionAction.status.in_(("confirmed", "applying")),
                )
            )
        )
        .scalars()
        .all()
    )
    for action in rows:
        payload = action.payload or {}
        preview = payload.get("preview") or {}
        if (
            preview.get("executable") == executable
            and preview.get("argv_signature") == argv_signature
        ):
            return action
    return None


@router.post("/executions", response_model=ExecutionOutcomeOut)
async def run_execution(
    payload: ExecutionIn,
    scope: ClientScope = Depends(client_scope("teammates:use")),
    redis: Redis = Depends(get_redis),
) -> ExecutionOutcomeOut:
    """Ejecuta —o pide permiso, o deniega— en la máquina del partner."""
    settings = get_settings()
    principal_id = scope.principal.user_id

    # 1. La máquina. Sin presencia o sin directorio no hay dónde ejecutar, y eso
    #    es una espera diseñada, no un error (002-R7.5, 003-R3.5).
    device, link = await _machine_for(scope)
    if device is None or link is None:
        return ExecutionOutcomeOut(
            decision="denegada",
            executable=payload.executable,
            argv_signature="",
            denial_code=DENIAL_DISPOSITIVO_AUSENTE,
        )

    # 2 y 3. El gate, con las dos capas de encima ya resueltas.
    await apply_partner_to_session(
        scope.session, scope.principal.partner.id, principal_id=principal_id
    )
    policy = await LocalExecPolicyRepository(scope.session).for_invocation(
        partner_id=scope.principal.partner.id,
        principal_id=principal_id,
        executable=payload.executable,
    )
    await apply_tenant_to_session(scope.session, scope.mapping.tenant_id)
    with tenant_context(scope.mapping.tenant_id):
        gate = LocalExecGate(scope.session)
        decision = await gate.evaluate(
            executable=payload.executable,
            args=payload.args,
            cwd_relative=payload.cwd_relative,
            device_present=True,
            policy=policy,
        )

        approved = None
        if decision.outcome == "requiere_aprobacion":
            approved = await _approved_action(
                scope, executable=payload.executable, argv_signature=decision.argv_signature
            )
            if approved is not None and decision.executable_id is not None:
                # La persona dijo que sí: el permiso de argumentos se registra
                # como objeto durable con su identidad (001-R2.5). Es lo que
                # hace que el mismo comando exacto no vuelva a preguntar.
                grant_id = await LocalArgumentGrantRepository(scope.session).grant(
                    executable_id=decision.executable_id,
                    argv_signature=decision.argv_signature,
                    action_id=approved.id,
                )
                decision = replace(decision, outcome="permitida", grant_id=grant_id)

        if decision.outcome == "denegada":
            await LocalExecutionRepository(scope.session).record_denial(
                device_id=device.id,
                executable=payload.executable,
                argv_signature=decision.argv_signature,
                denial_reason=decision.denial_reason or DENIAL_DISPOSITIVO_AUSENTE,
            )
            _audit_execution(scope, "local_exec.denied_by_policy", decision, device)
            return ExecutionOutcomeOut(
                decision="denegada",
                executable=payload.executable,
                argv_signature=decision.argv_signature,
                denial_code=decision.denial_reason,
                capped=decision.capped,
                mode=policy.mode,
            )

        if decision.outcome == "requiere_aprobacion":
            # **No se despacha nada.** Quien llamó tiene que pedir permiso.
            return ExecutionOutcomeOut(
                decision="requiere_aprobacion",
                executable=payload.executable,
                argv_signature=decision.argv_signature,
                capped=decision.capped,
                mode=policy.mode,
            )

        # El despacho va en **su propia sesión y su propia transacción**: la de
        # esta petición no se cierra hasta que la ruta devuelve, y una fila que
        # nadie ve todavía no la puede recoger la máquina. Es el mismo patrón
        # que usa el cierre de un run del Companion, y por la misma razón.
        execution_id = await _dispatch_now(
            tenant_id=scope.mapping.tenant_id,
            device_id=device.id,
            executable=payload.executable,
            argv_signature=decision.argv_signature,
            grant_id=decision.grant_id,
            principal_id=principal_id,
        )
        _audit_execution(
            scope,
            "local_exec.allowed_by_policy" if decision.by_policy else "local_exec.allowed_once",
            decision,
            device,
        )

    # La espera va fuera de toda transacción: la máquina sondea, ejecuta y
    # contesta, y eso puede tardar minutos.
    result = await await_result(redis, execution_id, wait_seconds=settings.local_exec_wait_seconds)
    if result is None:
        return ExecutionOutcomeOut(
            decision="permitida",
            executable=payload.executable,
            argv_signature=decision.argv_signature,
            execution_id=execution_id,
            outcome="expirada",
            capped=decision.capped,
            mode=policy.mode,
        )
    return ExecutionOutcomeOut(
        decision="permitida",
        executable=payload.executable,
        argv_signature=decision.argv_signature,
        execution_id=execution_id,
        outcome=result.outcome,
        exit_code=result.exit_code,
        stdout_sample=result.stdout_sample or None,
        untrusted=True,
        denial_code=result.denial_code,
        capped=decision.capped,
        mode=policy.mode,
    )


async def _dispatch_now(
    *,
    tenant_id: uuid.UUID,
    device_id: uuid.UUID,
    executable: str,
    argv_signature: str,
    grant_id: uuid.UUID | None,
    principal_id: str,
) -> uuid.UUID:
    """Escribe la fila ``pendiente`` y la **confirma**, para que la máquina la vea."""
    from nexus_api.db.base import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_tenant_to_session(session, tenant_id)
        with tenant_context(tenant_id):
            row = await dispatch(
                session,
                device_id=device_id,
                executable=executable,
                argv_signature=argv_signature,
                grant_id=grant_id,
                principal_id=principal_id,
                teammate_id=None,
                task_id=None,
            )
            return row.id


async def _machine_for(scope: ClientScope) -> tuple[PartnerDevice | None, object | None]:
    """La máquina presente vinculada a este cliente, con su directorio."""
    await apply_partner_to_session(
        scope.session,
        scope.principal.partner.id,
        principal_id=scope.principal.user_id,
        workstation_manager="workstation:write" in scope.principal.permissions,
    )
    await apply_tenant_to_session(scope.session, scope.mapping.tenant_id)
    with tenant_context(scope.mapping.tenant_id):
        links = await DeviceClientLinkRepository(scope.session).active_for_tenant()
    for link in links:
        if link.workdir is None:
            continue
        device = await scope.session.get(PartnerDevice, link.device_id)
        if device is None or device.revoked_at is not None:
            continue
        if _presence(device) == "presente":
            return device, link
    return None, None


def _audit_execution(
    scope: ClientScope, action: str, decision: object, device: PartnerDevice
) -> None:
    """La persona es el actor. Nunca el teammate (Requisito 13.1)."""
    from nexus_api.db.models import AuditLog

    scope.session.add(
        AuditLog(
            tenant_id=scope.mapping.tenant_id,
            actor=scope.principal.actor,
            action=action,
            target=f"device:{device.id}",
            after_json={
                "executable": getattr(decision, "executable", ""),
                "machine": device.display_name,
            },
        )
    )
