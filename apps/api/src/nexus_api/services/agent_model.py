"""El modelo de cada agente — spec 065 (contracts/api.md).

Lo que la consola y el panel enseñan y cambian del modelo con el que responde un agente:

- **la elección** del agente (``agents.respond_model_*``), o ninguna;
- **el modelo efectivo**, resuelto con la única resolución (``core.respond_model.resolve``):
  elección → versión → modelo por defecto de Auphere, saltando lo que el agente no puede
  ejecutar;
- **las opciones**: lo ofrecido en este entorno (activo ∩ habilitado ∩ con perfil) ∩ la lista
  del partner, sin lo que el agente no pueda ejecutar, del más barato al más caro;
- **lo que costaría una respuesta** con cada uno (research.md §D14, «Estimación del
  selector»): la caché de cada proveedor según su documentación, los pesos de venta y el
  factor de gasto del perfil.

Todo corre en la sesión del cliente (la RLS de ``agents`` y ``usage_records``) con la GUC
del partner puesta para leer su lista. El servidor decide el cliente y el agente; nunca un
argumento del llamante (requisito 10.1).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.respond_catalog import (
    OFFERABLE_MODEL_ID_SET,
    RESPOND_MODELS,
    agent_respond_default,
)
from nexus_api.core.respond_model import AgentChoice, Resolved, resolve
from nexus_api.core.respond_profiles import ANTHROPIC_MCP, ANTHROPIC_SKILLS, can_run, profile_for
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, AuditLog
from nexus_api.db.models.model_profile import ModelProfile
from nexus_api.metering.sale_policy import SELL_USD_PER_MILLION

SetBy = Literal["partner", "operator"]

#: Cien milésimas por dólar (el dinero de la consola, «*_micros»).
MICROS_PER_USD: Final = Decimal(100_000)
#: La ventana del consumo que sirve de base (requisito 1.6).
WINDOW: Final = timedelta(days=7)
#: Las llamadas de conversación de un turno y la de clasificar (``usage_records.task``).
CONVERSATION_TASKS: Final = ("tool_turn", "answer")
CLASSIFY_TASK: Final = "classify"

#: Un turno típico, sin consumo del agente: el de un agente de recepción por WhatsApp (el
#: perfil medido de Jemma el 18-nov, research.md §D1), clasificado con Haiku 5.5.
NOMINAL_CONVERSATION: Final = {
    "llm.input_tokens": Decimal(20_000),
    "llm.cache_read": Decimal(10_000),
    "llm.output_tokens": Decimal(110),
}
NOMINAL_CLASSIFY: Final = {
    "anthropic/claude-haiku-5-5": {
        "llm.input_tokens": Decimal(1_600),
        "llm.cache_read": Decimal(400),
        "llm.output_tokens": Decimal(32),
    }
}

#: La gama de cada modelo con perfil, para la línea «para qué sirve» (requisito 1.5).
LINES: Final[dict[str, str]] = {
    "openai/gpt-5.6-sol": "max",
    "anthropic/claude-opus-5-5": "max",
    "openai/gpt-5.6-terra": "balanced",
    "anthropic/claude-sonnet-5-5": "balanced",
    "openai/gpt-5.6-luna": "economy",
    "anthropic/claude-haiku-5-5": "economy",
}


class UnknownModel(ValueError):
    """``422 unknown_model``: fuera de la oferta del partner, sin perfil o inactivo."""

    def __init__(self, model_id: str) -> None:
        super().__init__(model_id)
        self.model_id = model_id


class ModelUnavailableForAgent(ValueError):
    """``422 model_unavailable_for_agent``: el agente usa algo que ese modelo no ejecuta."""


# ── lo que el agente usa y su versión ──────────────────────────────────────


@dataclass(frozen=True)
class AgentFacts:
    agent: Agent
    choice: AgentChoice | None
    version_override: str | None
    needs: frozenset[str]


async def _facts(session: AsyncSession, agent_id: uuid.UUID) -> AgentFacts:
    agent = await session.get(Agent, agent_id)
    if agent is None:  # pragma: no cover - la ruta ya lo comprobó
        raise LookupError(agent_id)
    choice: AgentChoice | None = None
    if agent.respond_model_profile_id is not None:
        model_id = await session.scalar(
            sa.select(ModelProfile.model_id).where(
                ModelProfile.id == agent.respond_model_profile_id
            )
        )
        if model_id is not None:
            set_by: SetBy = "operator" if agent.respond_model_set_by == "operator" else "partner"
            choice = AgentChoice(str(model_id), set_by)
    cfg = (
        await session.execute(
            sa.select(
                AgentConfig.policies,
                AgentConfig.runtime_skills,
                AgentConfig.runtime_mcp_connector,
            ).where(
                AgentConfig.agent_id == agent_id,
                AgentConfig.status == AgentConfigStatus.ACTIVE,
            )
        )
    ).first()
    override: str | None = None
    needs: set[str] = set()
    if cfg is not None:
        llm = (cfg.policies or {}).get("llm")
        value = llm.get("respond_model") if isinstance(llm, dict) else None
        override = value if isinstance(value, str) and value else None
        if cfg.runtime_skills:
            needs.add(ANTHROPIC_SKILLS)
        if cfg.runtime_mcp_connector:
            needs.add(ANTHROPIC_MCP)
    return AgentFacts(agent, choice, override, frozenset(needs))


# ── la estimación (research.md §D14) ───────────────────────────────────────


@dataclass(frozen=True)
class TokenProfile:
    """Tokens por respuesta del agente: la conversación y, por modelo, la clasificación."""

    conversation: dict[str, Decimal]
    classify: dict[str, dict[str, Decimal]]
    basis: Literal["agent_7d", "nominal"]


async def token_profile(session: AsyncSession, agent_id: uuid.UUID) -> TokenProfile:
    """Lo que gastó el agente por respuesta en los últimos 7 días, solo en el canal."""
    since = datetime.now(UTC) - WINDOW
    rows = (
        await session.execute(
            sa.text(
                """
                SELECT task, model, meter, sum(quantity) AS qty, count(*) AS n
                  FROM usage_records
                 WHERE agent_id = :agent
                   AND source = 'channel'
                   AND occurred_at >= :since
                   AND task = ANY(:tasks)
                   AND meter IN ('llm.input_tokens', 'llm.cache_read', 'llm.output_tokens')
                 GROUP BY task, model, meter
                """
            ),
            {
                "agent": agent_id,
                "since": since,
                "tasks": [*CONVERSATION_TASKS, CLASSIFY_TASK],
            },
        )
    ).all()
    responses = sum(
        int(r.n) for r in rows if r.task == CLASSIFY_TASK and r.meter == "llm.output_tokens"
    )
    if responses == 0:
        return TokenProfile(dict(NOMINAL_CONVERSATION), dict(NOMINAL_CLASSIFY), "nominal")
    per = Decimal(responses)
    conversation: dict[str, Decimal] = dict.fromkeys(NOMINAL_CONVERSATION, Decimal(0))
    classify: dict[str, dict[str, Decimal]] = {}
    for r in rows:
        qty = Decimal(r.qty) / per
        if r.task in CONVERSATION_TASKS:
            conversation[r.meter] += qty
        elif r.model:
            bucket = classify.setdefault(
                str(r.model), dict.fromkeys(NOMINAL_CONVERSATION, Decimal(0))
            )
            bucket[r.meter] += qty
    return TokenProfile(conversation, classify, "agent_7d")


def _weights(profile: ModelProfile) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    lanes = (
        profile.quota_weight_input,
        profile.quota_weight_cache_read,
        profile.quota_weight_output,
    )
    if any(w is None for w in lanes):
        return None
    write = profile.quota_weight_cache_write
    return (
        Decimal(profile.quota_weight_input),  # type: ignore[arg-type]
        Decimal(profile.quota_weight_cache_read),  # type: ignore[arg-type]
        Decimal(write) if write is not None else Decimal(0),
        Decimal(profile.quota_weight_output),  # type: ignore[arg-type]
    )


def sale_usd(
    weights: tuple[Decimal, Decimal, Decimal, Decimal], tokens: dict[str, Decimal]
) -> Decimal:
    """Dólares de venta de ``tokens`` con unos pesos, según la caché del proveedor: lo leído a
    la tarifa de lectura y lo no leído a la de escritura si el modelo la tiene, o a la de
    entrada si no (un token solo se lee si antes se escribió)."""
    w_in, w_read, w_write, w_out = weights
    unread = max(
        tokens.get("llm.input_tokens", Decimal(0)) - tokens.get("llm.cache_read", Decimal(0)),
        Decimal(0),
    )
    units = (
        unread * (w_write if w_write > 0 else w_in)
        + tokens.get("llm.cache_read", Decimal(0)) * w_read
        + tokens.get("llm.output_tokens", Decimal(0)) * w_out
    )
    return units / Decimal(1_000_000) * SELL_USD_PER_MILLION


async def _profiles(session: AsyncSession, model_ids: set[str]) -> dict[str, ModelProfile]:
    if not model_ids:
        return {}
    rows = (
        await session.scalars(sa.select(ModelProfile).where(ModelProfile.model_id.in_(model_ids)))
    ).all()
    return {str(p.model_id): p for p in rows}


def _estimate(
    model_id: str,
    tokens: TokenProfile,
    profiles: dict[str, ModelProfile],
) -> dict[str, Any] | None:
    profile = profiles.get(model_id)
    weights = _weights(profile) if profile is not None else None
    if weights is None:
        return None
    factor = Decimal(str(p.estimate_factor)) if (p := profile_for(model_id)) else Decimal(1)
    usd = sale_usd(weights, tokens.conversation) * factor
    for classify_model, classify_tokens in tokens.classify.items():
        c_profile = profiles.get(classify_model)
        c_weights = _weights(c_profile) if c_profile is not None else None
        if c_weights is not None:
            usd += sale_usd(c_weights, classify_tokens)
    return {
        "amount_micros": int((usd * MICROS_PER_USD).quantize(Decimal(1))),
        "currency": "USD",
        "basis": tokens.basis,
    }


# ── la vista ───────────────────────────────────────────────────────────────


async def agent_model_view(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    allowed: frozenset[str] | None,
    can_change: bool,
) -> dict[str, Any]:
    """Lo que devuelve ``GET …/agents/{agent_id}/model``.

    ``allowed``: la lista del partner; ``None`` en el panel, donde Auphere elige entre todo
    lo habilitado."""
    facts = await _facts(session, agent_id)
    resolved: Resolved = resolve(
        facts.choice,
        facts.version_override,
        agent_respond_default(),
        agent_needs=facts.needs,
    )
    offered = [
        (model_id, label)
        for model_id, label in RESPOND_MODELS
        if (allowed is None or model_id in allowed) and can_run(model_id, facts.needs)
    ]
    tokens = await token_profile(session, agent_id)
    wanted = {m for m, _ in offered} | {resolved.model_id}
    if facts.choice is not None:
        wanted.add(facts.choice.model_id)
    wanted |= set(tokens.classify)
    profiles = await _profiles(session, wanted)

    def name(model_id: str) -> str:
        p = profiles.get(model_id)
        return str(p.display_name) if p is not None else model_id

    options: list[dict[str, Any]] = []
    for model_id, label in offered:
        call = profile_for(model_id)
        options.append(
            {
                "model_id": model_id,
                "display_name": label,
                "provider": call.family if call is not None else model_id.split("/", 1)[0],
                "line": LINES.get(model_id, "balanced"),
                "estimate": _estimate(model_id, tokens, profiles),
            }
        )
    options.sort(
        key=lambda o: (
            o["estimate"]["amount_micros"] if o["estimate"] else 1 << 62,
            o["model_id"],
        )
    )
    offered_ids = {o["model_id"] for o in options}
    outside: str | None = None
    if resolved.model_id not in offered_ids:
        outside = "operator" if resolved.model_id in OFFERABLE_MODEL_ID_SET else "retired"
    choice_out = None
    if facts.choice is not None:
        choice_out = {
            "model_id": facts.choice.model_id,
            "display_name": name(facts.choice.model_id),
            "set_by": facts.choice.set_by,
            "set_at": facts.agent.respond_model_set_at,
        }
    notice = None
    if facts.choice is not None and facts.choice.model_id in resolved.skipped:
        notice = "chosen_model_cannot_run_agent"
    return {
        "agent_id": agent_id,
        "choice": choice_out,
        "effective": {
            "model_id": resolved.model_id,
            "display_name": name(resolved.model_id),
            "source": resolved.source,
            "outside_offer": outside,
            "estimate": _estimate(resolved.model_id, tokens, profiles),
        },
        "options": options,
        "notice": notice,
        "can_change": can_change,
    }


# ── el cambio ──────────────────────────────────────────────────────────────


async def set_agent_model(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    model_id: str | None,
    set_by: SetBy,
    actor: str,
    allowed: frozenset[str] | None,
    action: str,
    reason: str | None = None,
) -> None:
    """Escribe la elección del agente y su auditoría, en la transacción de quien llama.

    ``allowed`` es la lista del partner (la consola); ``None`` en el panel, que puede elegir
    cualquier modelo habilitado aunque el partner no lo tenga (requisito 7.2)."""
    facts = await _facts(session, agent_id)
    agent = facts.agent
    before = facts.choice.model_id if facts.choice is not None else None
    profile_id: uuid.UUID | None = None
    if model_id is not None:
        offered = {m for m, _ in RESPOND_MODELS}
        if (
            model_id not in offered
            or profile_for(model_id) is None
            or (allowed is not None and model_id not in allowed)
        ):
            raise UnknownModel(model_id)
        row = (
            await session.execute(
                sa.select(ModelProfile.id).where(
                    ModelProfile.model_id == model_id, ModelProfile.status == "active"
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise UnknownModel(model_id)
        if not can_run(model_id, facts.needs):
            raise ModelUnavailableForAgent(model_id)
        profile_id = row
    agent.respond_model_profile_id = profile_id
    agent.respond_model_set_by = set_by if profile_id is not None else None
    agent.respond_model_set_at = datetime.now(UTC) if profile_id is not None else None
    after: dict[str, Any] = {"model_id": model_id, "set_by": set_by if model_id else None}
    if model_id is not None:
        display = await session.scalar(
            sa.select(ModelProfile.display_name).where(ModelProfile.model_id == model_id)
        )
        after["model"] = str(display or model_id)
    if reason:
        after["reason"] = reason
    session.add(
        AuditLog(
            # El cliente sale de la fila del agente, leída bajo la RLS de la sesión: nunca
            # de un argumento (rules/tenant-isolation.md).
            tenant_id=agent.tenant_id,
            actor=actor,
            action=action,
            target=f"agent:{agent_id}",
            before_json={"model_id": before},
            after_json=after,
        )
    )
    await session.flush()


__all__ = [
    "LINES",
    "ModelUnavailableForAgent",
    "TokenProfile",
    "UnknownModel",
    "agent_model_view",
    "sale_usd",
    "set_agent_model",
    "token_profile",
]
