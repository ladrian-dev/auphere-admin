"""La pantalla Calidad de un agente — spec 047, T147 (requisito 39;
``contracts/console-api.md`` §4).

- ``GET /clients/{ref}/agents/{agent_id}/quality``: la política actual, cada
  perfil con su línea, su precio estimado por mensaje y la diferencia con el
  actual, si se ofrece con «Solo UE» y si hay que comprobarlo; los modelos que se
  pueden fijar; el precio real de 7 días; y la propuesta de «Automático» a un
  agente migrado;
- ``POST …/quality/check`` ``{model_policy}`` [``agents:write``] → ``202
  {job_id, run_id}``: la suite del agente con esa política (39.9). Si pasa, sus
  modelos de conversación quedan certificados para el agente y la política se
  puede guardar por el borrador y la puerta.

Precios como el resto del dinero del contrato: ``{amount_micros, currency}`` en
cien milésimas de la moneda de la cuenta (USD, spec 027); nunca costes (C9). La
consola lite y la app no tienen esta pantalla (39.12).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.db.models.agent_spec import AgentTestRun
from nexus_api.services import agent_quality as svc
from nexus_api.services.router_catalog import load_snapshot

from .agent_draft_routes import agent_in_path
from .deps import ClientScope, require_build_room

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}")


class Money(BaseModel):
    #: Cien milésimas de la moneda (``contracts/console-api.md``, Convenciones).
    amount_micros: int
    currency: Literal["USD"] = "USD"


def _money(micro_usd: int | None) -> Money | None:
    """El router cuenta en micro-USD; el contrato, en cien milésimas."""
    if micro_usd is None:
        return None
    return Money(amount_micros=round(micro_usd / 10))


class CheckOut(BaseModel):
    status: Literal["none", "queued", "running", "passed", "failed"]
    job_id: uuid.UUID | None = None
    reasons: list[str] = Field(default_factory=list)


class ProfileOptionOut(BaseModel):
    profile: str
    line: str
    #: Se ofrece (con «Solo UE», solo si tiene modelo en la UE en cada tarea).
    offered: bool
    price_per_message: Money | None = None
    #: Diferencia con la opción actual (positiva: más caro).
    delta: Money | None = None
    current: bool = False
    #: Sus modelos de conversación ya están certificados para este agente.
    certified: bool = False
    check: CheckOut


class PinnableOut(BaseModel):
    deployment: str
    name: str
    provider: str
    residency: str
    price_per_message: Money | None = None
    delta: Money | None = None
    current: bool = False
    certified: bool = False
    check: CheckOut


class QualityOut(BaseModel):
    #: ``{kind: profile, profile}`` · ``{kind: pinned, deployment}`` · ``{kind: legacy}``.
    current: dict[str, Any]
    estimate_source: Literal["agent_30d", "sector"]
    profiles: list[ProfileOptionOut]
    pinnable: list[PinnableOut]
    pinned_line: str
    real_price_7d: Money | None = None
    #: Agente migrado (fijado en su modelo de hoy): se le propone «Automático» (39.11).
    suggest_auto: bool = False
    eu_only: bool = False
    allowed: list[Literal["change"]] = Field(default_factory=list)


class CheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_policy: dict[str, Any]


async def _facts(scope: ClientScope) -> tuple[svc.Facts, AgentConfig | None]:
    from nexus_worker.runtime.model_resolver import load_route_facts

    from nexus_api.metering.wallet import partner_id_for_tenant

    assert scope.agent_id is not None
    version = await scope.session.scalar(
        sa.select(AgentConfig)
        .where(
            AgentConfig.agent_id == scope.agent_id,
            AgentConfig.status == AgentConfigStatus.ACTIVE,
        )
        .limit(1)
    )
    partner_id = await partner_id_for_tenant(scope.session, scope.tenant.id)
    facts = await load_route_facts(scope.tenant.id, scope.agent_id, partner_id=partner_id)
    return (
        svc.Facts(
            tenant_id=scope.tenant.id,
            agent_id=scope.agent_id,
            agent_version=str(version.id) if version else None,
            eu_only=facts.eu_only,
            sovereign=facts.sovereign,
            partner_allowed=facts.partner_allowed,
            agent_certified=facts.agent_certified,
        ),
        version,
    )


async def _checks(scope: ClientScope) -> list[AgentTestRun]:
    return list(
        (
            await scope.session.scalars(
                sa.select(AgentTestRun)
                .where(
                    AgentTestRun.agent_id == scope.agent_id,
                    AgentTestRun.reason == "certification",
                )
                .order_by(AgentTestRun.created_at.desc())
                .limit(50)
            )
        ).all()
    )


def _check_of(runs: list[AgentTestRun], policy: dict[str, Any]) -> CheckOut:
    for run in runs:
        if not svc.same_policy(run.model_policy, policy):
            continue
        if run.status in {"queued", "running"}:
            return CheckOut(status=run.status, job_id=run.job_id)  # type: ignore[arg-type]
        verdict = (run.summary or {}).get("quality_check") or {}
        if run.status == "done" and verdict:
            return CheckOut(
                status="passed" if verdict.get("passed") else "failed",
                job_id=run.job_id,
                reasons=list(verdict.get("reasons") or []),
            )
        return CheckOut(status="failed", job_id=run.job_id, reasons=["run_failed"])
    return CheckOut(status="none")


@router.get("/quality", response_model=QualityOut)
async def get_quality(scope: ClientScope = Depends(agent_in_path("agents:read"))) -> QualityOut:
    assert scope.agent_id is not None
    facts, version = await _facts(scope)
    snapshot = await load_snapshot(scope.session, refresh_hop=False)
    profile = await svc.turn_profile(scope.session, scope.agent_id)
    raw = dict((version.policies or {}).get("model_policy") or {}) if version else {}
    current: dict[str, Any] = (
        raw if raw.get("kind") in {"profile", "pinned"} else {"kind": "legacy"}
    )
    current_price = (
        svc.estimate(snapshot, facts, profile, current) if current["kind"] != "legacy" else None
    )
    runs = await _checks(scope)

    def delta(price: int | None) -> int | None:
        return None if price is None or current_price is None else price - current_price

    profiles = []
    for name in svc.PROFILES:
        policy = {"kind": "profile", "profile": name}
        price = svc.estimate(snapshot, facts, profile, policy)
        uses = svc.conversation_deployments(snapshot, facts, policy)
        profiles.append(
            ProfileOptionOut(
                profile=name,
                line=svc.LINES[name],
                offered=svc.eu_servable(snapshot, facts, name),
                price_per_message=_money(price),
                delta=_money(delta(price)),
                current=svc.same_policy(current, policy),
                certified=bool(uses) and all(k in facts.agent_certified for k in uses),
                check=_check_of(runs, policy),
            )
        )
    pinnable = []
    for deployment in svc.pinnable(snapshot, facts):
        policy = {"kind": "pinned", "deployment": deployment.key}
        price = svc.estimate(snapshot, facts, profile, policy)
        pinnable.append(
            PinnableOut(
                deployment=deployment.key,
                name=deployment.display_name or deployment.model,
                provider=deployment.provider,
                residency=deployment.residency,
                price_per_message=_money(price),
                delta=_money(delta(price)),
                current=svc.same_policy(current, policy),
                certified=deployment.key in facts.agent_certified,
                check=_check_of(runs, policy),
            )
        )
    return QualityOut(
        current=current,
        estimate_source=profile.source,  # type: ignore[arg-type]
        profiles=profiles,
        pinnable=pinnable,
        pinned_line=svc.LINES["pinned"],
        real_price_7d=_money(await svc.real_price_7d(scope.session, scope.agent_id)),
        suggest_auto=current["kind"] == "legacy"
        or (current.get("kind") == "pinned" and current.get("deployment") == svc.LEGACY_DEPLOYMENT),
        eu_only=facts.eu_only,
        allowed=["change"] if "agents:write" in scope.principal.permissions else [],
    )


@router.post("/quality/check", status_code=status.HTTP_202_ACCEPTED)
async def check_quality(
    body: CheckIn, scope: ClientScope = Depends(agent_in_path("agents:write"))
) -> dict[str, str]:
    """«Comprobando la calidad…» (39.9): la suite del agente con esa política.
    Lo paga el partner, en «Construcción y pruebas».

    Suspendido por el requisito 64 (enmienda del 2026-10-29, D55): mientras la
    gestión de modelos no llegue al panel de operador, la consola no comprueba ni
    cambia la política de modelo: ``409 model_policy_managed``."""
    from nexus_api.services.agent_spec.model_policy import refuse_model_policy_change

    refuse_model_policy_change()
    from nexus_api.services.business.writes import _enqueue_after_commit
    from nexus_api.services.jobs import create_job
    from nexus_api.services.testing.runs import create_run, target_version
    from nexus_api.services.testing.suites import ensure_suite

    assert scope.agent_id is not None
    await require_build_room(scope.principal.partner.id)
    facts, _version = await _facts(scope)
    snapshot = await load_snapshot(scope.session, refresh_hop=False)
    policy = dict(body.model_policy)
    keys = {d.key for d in svc.pinnable(snapshot, facts)}
    if not svc.valid_policy(policy, keys):
        raise HTTPException(status_code=422, detail={"code": "invalid_model_policy"})
    if policy["kind"] == "profile" and not svc.eu_servable(snapshot, facts, str(policy["profile"])):
        raise HTTPException(status_code=409, detail={"code": "profile_not_eu_servable"})
    version = await target_version(scope.session, scope.agent_id)
    if version is None:
        raise HTTPException(status_code=409, detail={"code": "no_version"})
    suite = await ensure_suite(scope.session, scope.agent_id)
    job = await create_job(
        scope.session, kind="tests", agent_id=scope.agent_id, created_by=scope.principal.actor
    )
    run = await create_run(
        scope.session,
        agent_id=scope.agent_id,
        scope="all",
        reason="certification",
        paid_by="partner",
        created_by=scope.principal.actor,
        job_id=job.id,
        version=version,
    )
    run.model_policy = policy
    run.summary = {
        "check_deployments": svc.conversation_deployments(snapshot, facts, policy),
        "suite_revision": suite.revision,
    }
    _enqueue_after_commit(scope.session, job)
    return {"job_id": str(job.id), "run_id": str(run.id)}


__all__ = ["router"]
