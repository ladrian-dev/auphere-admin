"""Guardar es publicar, con red — spec 047, T093 (requisitos 23 y 24; research D6).

**La puerta** decide si un borrador puede llegar a clientes reales. Publica solo
si se cumplen todas estas condiciones (23.1):

1. el **validador** da 0 errores;
2. las pruebas **críticas** pasan 3 de 3 —en una pasada de **esta** versión: con
   pruebas y sin ella, ``tests_not_run``—; un agente estructurado sin ninguna
   prueba que aplique no pasa (``no_applicable_tests``, requisito 65.9);
3. la tasa global **no baja más de 2 puntos** frente a la versión activa;
4. el **aviso de IA** está decidido;
5. la **revisión** no tiene bloqueantes.

Y qué se puede hacer cuando no:

- el validador o el aviso de IA no se saltan nunca: se arreglan;
- una prueba **normal** en rojo deja «Guardar igualmente», con confirmación (23.2);
- una **crítica**, unas pruebas sin pasar, la regresión o un **bloqueante** solo
  lo salta un owner o un admin (o una persona de Auphere), escribiendo el
  motivo, que queda en la versión y en la auditoría (23.3).

**Después** de publicar (24): el siguiente mensaje usa la versión nueva (23.6),
hay 10 minutos para **deshacer**, y el historial deja **restaurar** cualquier
versión, que vuelve como borrador y pasa la puerta antes de publicarse. La
política de modelo va dentro de la versión (24.4). El rollback de antes solo
vuelve a una versión que estuvo activa: un borrador nunca se publica así
(``RollbackTargetNeverPublished``).

La usan los tres sitios que publican (23.7): la consola, el panel de operador y
la API de partners.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, AuditLog
from nexus_api.db.models.agent_spec import AgentTestRun
from nexus_api.services.agent_console_policy import has_disclosure_decision
from nexus_api.services.reception import sync_reception_flag

UNDO_WINDOW: Final = timedelta(minutes=10)
MAX_REGRESSION_POINTS: Final = 2.0
#: Quién puede saltar una prueba crítica, la regresión o un bloqueante (23.3).
OVERRIDE_ROLES: Final = frozenset({"owner", "admin", "operator"})

Condition = Literal["validator", "critical_tests", "regression", "ai_disclosure", "review"]


class GateBlocked(Exception):
    code = "gate_blocked"

    def __init__(self, gate: GateResult) -> None:
        super().__init__(self.code)
        self.gate = gate


class OverrideForbidden(Exception):
    code = "override_forbidden"


class UndoWindowClosed(Exception):
    code = "undo_window_closed"


class NothingToPublish(Exception):
    code = "no_draft"


@dataclass
class GateResult:
    """Lo que decidió la puerta, condición a condición."""

    conditions: list[dict[str, Any]] = field(default_factory=list)
    #: Lo que no se salta nunca (validador, aviso de IA).
    hard: list[dict[str, Any]] = field(default_factory=list)
    #: Lo que solo salta un owner o un admin con motivo.
    overridable: list[dict[str, Any]] = field(default_factory=list)
    #: Las pruebas normales en rojo: «Guardar igualmente».
    normal_failures: list[str] = field(default_factory=list)
    #: Lo que se avisa sin bloquear (agentes de antes de un partner sin la
    #: consola nueva: ver ``evaluate_gate``).
    warnings: list[dict[str, Any]] = field(default_factory=list)
    strict: bool = True
    rate: float | None = None
    reference_rate: float | None = None

    @property
    def clean(self) -> bool:
        return not (self.hard or self.overridable or self.normal_failures)

    def to_json(self) -> dict[str, Any]:
        return {
            "conditions": self.conditions,
            "hard": self.hard,
            "overridable": self.overridable,
            "normal_failures": self.normal_failures,
            "warnings": self.warnings,
            "strict": self.strict,
            "rate": self.rate,
            "reference_rate": self.reference_rate,
        }


# ── la puerta ──────────────────────────────────────────────────────────────


async def _last_full_run(
    session: AsyncSession, agent_id: uuid.UUID, version_id: uuid.UUID
) -> AgentTestRun | None:
    return (
        await session.scalars(
            sa.select(AgentTestRun)
            .where(
                AgentTestRun.tenant_id == require_current_tenant(),
                AgentTestRun.agent_id == agent_id,
                AgentTestRun.agent_config_id == version_id,
                AgentTestRun.status == "done",
                # Una comprobación de calidad corre con otra política de modelo.
                AgentTestRun.reason != "certification",
            )
            .order_by(AgentTestRun.finished_at.desc().nullslast(), AgentTestRun.created_at.desc())
            .limit(1)
        )
    ).first()


async def evaluate_gate(
    session: AsyncSession,
    *,
    agent: Agent,
    version: AgentConfig,
    active: AgentConfig | None,
    partner_id: uuid.UUID | None,
    strict: bool | None = None,
    tests_will_run: bool = False,
) -> GateResult:
    """Las cinco condiciones del requisito 23.1 sobre ``version``, sin publicar
    nada. Las pruebas son las de la última pasada de **esa** versión.

    ``tests_will_run``: quien pregunta pasará las pruebas antes de decidir (la
    vista previa de «Guardar», que publica por el trabajo ``publish``); entonces
    no haberlas pasado todavía no es un bloqueo que enseñar.

    **Estricta** con un agente «structured» o de un partner con la consola nueva.
    Con un agente de antes («instructions») de un partner que aún no la tiene, lo
    que hoy no bloqueaba —una integración sin conectar, un bloqueante de la
    revisión— se avisa sin bloquear: la activación es partner a partner y lo que
    ya existe sigue funcionando (historia 13, D38). Las pruebas, el aviso de IA y
    el resto del validador valen igual para todos."""
    from nexus_api.api.console.agent_spec_drafts import spec_of
    from nexus_api.services.agent_spec.missing import strip_spec
    from nexus_api.services.agent_spec.review import load_input, review
    from nexus_api.services.agent_spec.validator import Problem, load_context, validate_spec
    from nexus_api.services.testing.runs import suite_view

    gate = GateResult()

    # 1. El validador.
    spec = spec_of(version, agent)
    if strict is None:
        strict = (spec is not None and spec.mode == "structured") or await _partner_on_v2(
            session, partner_id
        )
    gate.strict = strict
    legacy_chars = (
        len(spec.instructions.legacy_text or "")
        if spec is not None and spec.mode == "instructions" and spec.instructions
        else None
    )
    problems: list[Any] = []
    if spec is not None:
        ctx = await load_context(session, partner_id=partner_id, legacy_chars=legacy_chars)
        # Spec 047, enmienda del 2026-10-30 (D72): la misma lectura que la consola.
        # Una habilidad o una petición de conexión con algo que no tenemos (de un
        # borrador de antes de la enmienda) no hace nada en el turno y la consola
        # no la puede editar: no bloquea, como no bloquea al editar.
        spec, _lacking = strip_spec(spec, ctx)
        _checked, problems = validate_spec(spec, ctx, author="person")
    if not (version.system_prompt_rendered or "").strip():
        problems.append(Problem("", "empty_prompt", "El prompt está vacío."))
    lenient = {"tool_not_connected", "end_customer_argument"}
    hard_problems = [p for p in problems if strict or p.code not in lenient]
    for p in problems:
        item = {
            "condition": "validator",
            "code": p.code,
            "message": p.message,
            "pointer": p.pointer,
        }
        # Spec 048: a retired tool says which one replaces it.
        if getattr(p, "replacement", None):
            item["replacement"] = p.replacement
        (gate.hard if p in hard_problems else gate.warnings).append(item)
    gate.conditions.append({"condition": "validator", "ok": not hard_problems})

    # 2 y 3. Las pruebas: críticas 3/3 y la regresión.
    tests, outcomes, _summary = await suite_view(session, agent.id)
    run = await _last_full_run(session, agent.id, version.id)
    # Con pruebas y sin pasada propia, la versión no se ha probado, y «no se
    # probó» no es «pasa» (cuenta en la condición de las críticas). El trabajo
    # ``publish`` las pasa antes de decidir, así que solo lo ve quien publica sin
    # él —la ruta de antes de la consola, el panel de operador—: lo salta un
    # owner o un admin con motivo.
    applicable = [t for t in tests if not t.not_applicable_reason]
    # Spec 047, enmienda del 2026-10-30 (65.9, enmienda el 23.1): «sin pruebas»
    # no es «aprobado». Un agente estructurado sin ninguna prueba que aplique no
    # se publica, y nadie lo salta: se añade una.
    no_tests = spec is not None and spec.mode == "structured" and not applicable
    if no_tests:
        gate.hard.append(
            {
                "condition": "critical_tests",
                "code": "no_applicable_tests",
                "message": "Este agente no tiene ninguna prueba que aplique: añade una antes "
                "de guardar.",
            }
        )
    untested = bool(applicable) and run is None and not tests_will_run
    if untested:
        gate.overridable.append(
            {
                "condition": "critical_tests",
                "code": "tests_not_run",
                "message": "Esta versión no ha pasado sus pruebas: pruébala antes de guardar.",
            }
        )
    critical_bad: list[str] = []
    for test in tests:
        if test.not_applicable_reason:
            continue
        out = outcomes[test.id]
        ran_here = run is not None and out.status != "not_run"
        if test.critical and ran_here and out.status != "passed":
            critical_bad.append(test.name)
        elif not test.critical and ran_here and out.status in {"failed", "flaky"}:
            gate.normal_failures.append(test.name)
    for name in critical_bad:
        gate.overridable.append(
            {
                "condition": "critical_tests",
                "code": "critical_test_failing",
                "message": f"La prueba crítica «{name}» no pasa 3 de 3.",
            }
        )
    gate.conditions.append(
        {"condition": "critical_tests", "ok": not (critical_bad or untested or no_tests)}
    )
    gate.rate = (run.summary or {}).get("rate") if run is not None else None
    if active is not None and active.id != version.id:
        reference = await _last_full_run(session, agent.id, active.id)
        gate.reference_rate = (
            (reference.summary or {}).get("rate") if reference is not None else None
        )
    regression = (
        gate.rate is not None
        and gate.reference_rate is not None
        and gate.reference_rate - gate.rate > MAX_REGRESSION_POINTS + 1e-9
    )
    if regression:
        gate.overridable.append(
            {
                "condition": "regression",
                "code": "regression",
                "message": f"La tasa baja de {gate.reference_rate} a {gate.rate} (más de 2 puntos).",
            }
        )
    gate.conditions.append({"condition": "regression", "ok": not regression})

    # 4. El aviso de IA.
    decided = (spec.ai_disclosure.decided if spec is not None and version.spec else False) or (
        has_disclosure_decision(version.policies)
    )
    if not decided:
        gate.hard.append(
            {
                "condition": "ai_disclosure",
                "code": "ai_disclosure_undecided",
                "message": "Falta decidir si el agente dice que es una IA.",
            }
        )
    gate.conditions.append({"condition": "ai_disclosure", "ok": decided})

    # 5. La revisión.
    blockers: list[Any] = []
    if spec is not None:
        data = await load_input(session, agent_id=agent.id, spec=spec, partner_id=partner_id)
        blockers = [f for f in review(data).blocking if f.code != "ai_disclosure_undecided"]
    for f in blockers:
        item = {"condition": "review", "code": f.code, "message": f.message}
        # 65.5: «Arreglar en el borrador» lleva al texto que promete.
        if f.pointer:
            item["pointer"] = f.pointer
        (gate.overridable if strict else gate.warnings).append(item)
    gate.conditions.append({"condition": "review", "ok": not (blockers and strict)})

    # 6. La calidad (39.9): cambiar la política de modelo de un agente publicado
    # exige haberla comprobado con su suite («Comprobando la calidad…»).
    new_policy = dict((version.policies or {}).get("model_policy") or {})
    if active is not None and active.id != version.id and new_policy:
        from nexus_api.services.agent_quality import same_policy

        old_policy = dict((active.policies or {}).get("model_policy") or {})
        if not same_policy(new_policy, old_policy):
            checked = await _policy_checked(session, agent.id, new_policy)
            if not checked:
                gate.hard.append(
                    {
                        "condition": "quality",
                        "code": "model_policy_unchecked",
                        "message": "La calidad nueva aún no está comprobada: pásala por "
                        "«Comprobar la calidad» antes de guardar.",
                    }
                )
            gate.conditions.append({"condition": "quality", "ok": checked})
    return gate


async def _policy_checked(
    session: AsyncSession, agent_id: uuid.UUID, policy: dict[str, Any]
) -> bool:
    """La política pasó su comprobación, o el modelo fijado ya está certificado
    para este agente (42.3)."""
    from nexus_api.services.agent_quality import same_policy

    runs = (
        await session.scalars(
            sa.select(AgentTestRun)
            .where(
                AgentTestRun.tenant_id == require_current_tenant(),
                AgentTestRun.agent_id == agent_id,
                AgentTestRun.reason == "certification",
                AgentTestRun.status == "done",
            )
            .order_by(AgentTestRun.created_at.desc())
            .limit(20)
        )
    ).all()
    for run in runs:
        if same_policy(run.model_policy, policy):
            return bool(((run.summary or {}).get("quality_check") or {}).get("passed"))
    if policy.get("kind") == "pinned":
        found = await session.scalar(
            sa.text(
                "SELECT 1 FROM agent_model_certifications c JOIN model_profiles p "
                "ON p.id = c.deployment_id WHERE c.agent_id = :a AND p.model_id = :m "
                "AND c.passed AND c.invalidated_at IS NULL LIMIT 1"
            ),
            {"a": agent_id, "m": str(policy.get("deployment"))},
        )
        return found is not None
    return False


async def _partner_on_v2(session: AsyncSession, partner_id: uuid.UUID | None) -> bool:
    if partner_id is None:
        return False
    from nexus_api.db.models import Partner

    enabled = await session.scalar(
        sa.select(Partner.console_v2_enabled_at).where(Partner.id == partner_id)
    )
    return enabled is not None


# ── publicar, deshacer, restaurar ──────────────────────────────────────────


async def _versions(
    session: AsyncSession, agent_id: uuid.UUID
) -> tuple[AgentConfig | None, AgentConfig | None]:
    rows = (
        await session.scalars(
            sa.select(AgentConfig).where(
                AgentConfig.tenant_id == require_current_tenant(), AgentConfig.agent_id == agent_id
            )
        )
    ).all()
    staged = next((r for r in rows if r.status is AgentConfigStatus.STAGED), None)
    active = next((r for r in rows if r.status is AgentConfigStatus.ACTIVE), None)
    return staged, active


@dataclass
class Published:
    version: AgentConfig
    gate: GateResult
    previous: AgentConfig | None
    undo_until: datetime


async def publish(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    actor: str,
    role: str,
    partner_id: uuid.UUID | None,
    note: str | None = None,
    accept_normal_failures: bool = False,
    override_reason: str | None = None,
    origin: str = "console",
    version: AgentConfig | None = None,
) -> Published:
    """Pasa el borrador (o ``version``) por la puerta y, si pasa, lo publica."""
    from nexus_api.services.agent_config_service import AgentConfigService

    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NothingToPublish()
    staged, active = await _versions(session, agent_id)
    target = version or staged
    if target is None:
        raise NothingToPublish()
    gate = await evaluate_gate(
        session, agent=agent, version=target, active=active, partner_id=partner_id
    )
    reason = " ".join((override_reason or "").split()) or None
    if gate.hard:
        raise GateBlocked(gate)
    if gate.overridable:
        if reason is None:
            raise GateBlocked(gate)
        if role not in OVERRIDE_ROLES:
            raise OverrideForbidden()
    if gate.normal_failures and not (accept_normal_failures or reason):
        raise GateBlocked(gate)

    service = AgentConfigService(session)
    published = await service.promote(target.version, actor=actor, origin=origin)
    now = datetime.now(UTC)
    published.gate = gate.to_json()
    published.override_reason = reason
    published.published_by = actor
    published.published_at = now
    published.undo_until = now + UNDO_WINDOW
    if note is not None:
        published.note = note.strip() or published.note
    # Spec 047 (requisito 53.1): «es Recepción» lo dice la versión publicada.
    await sync_reception_flag(session, agent_id)
    session.add(
        AuditLog(
            tenant_id=require_current_tenant(),
            actor=actor,
            action="agent.publish",
            target=f"agent:{agent_id}",
            before_json={"version": active.agent_version_number} if active else None,
            after_json={
                "version": published.agent_version_number,
                "origin": origin,
                "override_reason": reason,
                "accepted_normal_failures": sorted(gate.normal_failures)
                if gate.normal_failures
                else [],
            },
        )
    )
    await session.flush()
    return Published(version=published, gate=gate, previous=active, undo_until=published.undo_until)


async def undo(session: AsyncSession, *, agent_id: uuid.UUID, actor: str) -> AgentConfig:
    """«Deshacer», dentro de los 10 minutos (24.1): vuelve la versión anterior."""
    from nexus_api.services.agent_config_service import AgentConfigService

    _staged, active = await _versions(session, agent_id)
    now = datetime.now(UTC)
    if active is None or active.undo_until is None or active.undo_until < now:
        raise UndoWindowClosed()
    previous = (
        await session.scalars(
            sa.select(AgentConfig)
            .where(
                AgentConfig.tenant_id == require_current_tenant(),
                AgentConfig.agent_id == agent_id,
                AgentConfig.status == AgentConfigStatus.ARCHIVED,
                AgentConfig.id != active.id,
                AgentConfig.promoted_at.is_not(None),
            )
            .order_by(AgentConfig.promoted_at.desc())
            .limit(1)
        )
    ).first()
    if previous is None:
        raise UndoWindowClosed()
    restored = await AgentConfigService(session).rollback(previous.version, actor=actor)
    # Deshacer no se encadena: ni la que se deshizo ni la que vuelve se deshacen.
    active.undo_until = None
    restored.undo_until = None
    await sync_reception_flag(session, agent_id)
    session.add(
        AuditLog(
            tenant_id=require_current_tenant(),
            actor=actor,
            action="agent.publish_undone",
            target=f"agent:{agent_id}",
            before_json={"version": active.agent_version_number},
            after_json={"version": restored.agent_version_number},
        )
    )
    await session.flush()
    return restored


async def restore(
    session: AsyncSession, *, agent_id: uuid.UUID, number: int, actor: str
) -> AgentConfig:
    """«Restaurar» (24.3): la versión ``number`` vuelve como borrador, con su
    prompt, sus herramientas, su AgentSpec y su política de modelo (24.4). Pasa la
    puerta antes de publicarse."""
    from nexus_api.services.agent_config_service import AgentConfigService

    source = await session.scalar(
        sa.select(AgentConfig).where(
            AgentConfig.tenant_id == require_current_tenant(),
            AgentConfig.agent_id == agent_id,
            AgentConfig.agent_version_number == number,
        )
    )
    if source is None:
        raise LookupError("unknown_version")
    service = AgentConfigService(session)
    write = await service.open_draft(actor=actor, agent_id=agent_id)
    draft = write.draft
    draft.system_prompt_rendered = source.system_prompt_rendered
    draft.tools = list(source.tools or [])
    draft.policies = dict(source.policies or {})
    draft.spec = dict(source.spec) if source.spec else None
    draft.base_version_id = source.id
    draft.note = f"Restaurada desde v{number}"
    await service.finish_draft(write, actor=actor)
    from nexus_api.services.testing.suites import mark_stale

    await mark_stale(session, agent_id)
    return draft


def history_entry(cfg: AgentConfig, previous: AgentConfig | None) -> dict[str, Any]:
    """Una versión del historial (24.2): número, autor, fecha, nota, el diff con la
    anterior y el resultado de sus pruebas."""
    from nexus_api.services.agent_spec.patch import diff_ops

    before = dict(previous.spec or {}) if previous is not None else {}
    after = dict(cfg.spec or {})
    changed = [op["path"].lstrip("/") for op in diff_ops(before, after)]
    if previous is not None and previous.system_prompt_rendered != cfg.system_prompt_rendered:
        changed.append("prompt")
    if previous is not None and sorted(previous.tools or []) != sorted(cfg.tools or []):
        changed.append("tools")
    if previous is not None and (previous.policies or {}).get("model_policy") != (
        cfg.policies or {}
    ).get("model_policy"):
        changed.append("model_policy")
    gate = dict(cfg.gate or {})
    return {
        "number": cfg.agent_version_number,
        "status": cfg.status.value,
        "author": cfg.created_by,
        "created_at": cfg.created_at,
        "published_at": cfg.published_at or cfg.promoted_at,
        "published_by": cfg.published_by or cfg.promoted_by,
        "note": cfg.note,
        "changed": sorted(dict.fromkeys(changed)),
        "model_policy": (cfg.policies or {}).get("model_policy"),
        "tests": {"rate": gate.get("rate"), "conditions": gate.get("conditions", [])}
        if gate
        else None,
        "override_reason": cfg.override_reason,
    }


def ordered_history(versions: Sequence[AgentConfig]) -> list[dict[str, Any]]:
    by_number = sorted(versions, key=lambda v: v.agent_version_number)
    out: list[dict[str, Any]] = []
    for i, cfg in enumerate(by_number):
        out.append(history_entry(cfg, by_number[i - 1] if i else None))
    return list(reversed(out))


__all__ = [
    "MAX_REGRESSION_POINTS",
    "OVERRIDE_ROLES",
    "UNDO_WINDOW",
    "GateBlocked",
    "GateResult",
    "NothingToPublish",
    "OverrideForbidden",
    "Published",
    "UndoWindowClosed",
    "evaluate_gate",
    "history_entry",
    "ordered_history",
    "publish",
    "restore",
    "undo",
]
