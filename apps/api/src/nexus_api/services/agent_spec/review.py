"""La revisión automática de un borrador — spec 047, T088 (requisito 22; research D4).

Después de las pruebas, una revisión sin modelo dice lo que el borrador promete y
no puede cumplir. Cada hallazgo lleva su **gravedad** («bloquea» o «avisa») y,
cuando existe, su **arreglo**: un enlace a donde se arregla, o una propuesta que
una persona aplica (22.2). **Ningún «✓» es fijo** (22.3): la lista de
comprobaciones dice cuáles corrieron y con qué resultado.

Lo que comprueba (22.1):
- habilidades sin su integración conectada, con o sin alternativa;
- servicios sin precio, o reservables sin duración;
- horario ausente;
- contradicciones entre las instrucciones y la ficha;
- instrucciones que prometen acciones sin herramienta;
- referencias a herramientas que no existen;
- canales sin destinatarios de escalado;
- aviso de IA sin decidir (y «solo si preguntan» en un cliente de la UE, AI Act art. 50).

:func:`review` es pura; :func:`load_input` lee lo que necesita del cliente del
contexto.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.services.agent_spec.compiler import incoherences
from nexus_api.services.agent_spec.schema import AgentSpec
from nexus_api.services.agent_spec.validator import Context
from nexus_api.services.business.compilation import Facts

Severity = Literal["block", "warn"]

#: Las familias de herramientas que reservan: sin horario, un agente así no
#: puede trabajar (bloquea); uno que solo informa, avisa.
BOOKING_PREFIXES: Final = ("reservas.", "booking.")

CHECKS: Final = (
    "skills_integrations",
    "services",
    "hours",
    "contradictions",
    "promises",
    "tools_exist",
    "escalation_recipients",
    "ai_disclosure",
)


@dataclass(frozen=True)
class ServiceFact:
    id: str
    name: str
    bookable: bool
    duration_min: int | None
    has_price: bool


@dataclass(frozen=True)
class ChannelFact:
    id: str
    name: str
    recipients: int


@dataclass(frozen=True)
class ReviewInput:
    spec: AgentSpec
    facts: Facts
    ctx: Context
    services: tuple[ServiceFact, ...] = ()
    channels: tuple[ChannelFact, ...] = ()
    has_hours: bool = True
    eu_client: bool = False


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    pointer: str | None = None
    fix: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.pointer:
            out["pointer"] = self.pointer
        if self.fix:
            out["fix"] = self.fix
        return out


@dataclass(frozen=True)
class Review:
    findings: tuple[Finding, ...] = ()
    #: Cada comprobación que corrió y si encontró algo (22.3).
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "block"]


def _link(target: str, **extra: Any) -> dict[str, Any]:
    return {"kind": "link", "target": target, **extra}


def review(data: ReviewInput) -> Review:
    spec = data.spec
    found: dict[str, list[Finding]] = {name: [] for name in CHECKS}
    tools = set(spec.tools or [])

    # Habilidades sin su integración.
    for i, skill in enumerate(spec.skills or []):
        if not skill.enabled or skill.integration is None:
            continue
        connected = any(
            info.integration == skill.integration and info.connected
            for info in data.ctx.tools.values()
        )
        if connected:
            continue
        has_fallback = bool((skill.fallback or "").strip())
        found["skills_integrations"].append(
            Finding(
                "skill_without_integration",
                "warn" if has_fallback else "block",
                f"La habilidad «{skill.key}» necesita {skill.integration}, que no está conectada"
                + (" (mientras, hace lo de su alternativa)." if has_fallback else "."),
                pointer=f"/skills/{i}",
                fix=_link("integrations", integration=skill.integration),
            )
        )

    # Servicios.
    for svc in data.services:
        if svc.bookable and not svc.duration_min:
            found["services"].append(
                Finding(
                    "bookable_without_duration",
                    "block",
                    f"«{svc.name}» se reserva pero no dice cuánto dura.",
                    fix=_link("business/services", service_id=svc.id),
                )
            )
        if not svc.has_price:
            found["services"].append(
                Finding(
                    "service_without_price",
                    "warn",
                    f"«{svc.name}» no tiene precio: el agente dirá que lo confirma el equipo.",
                    fix=_link("business/services", service_id=svc.id),
                )
            )

    # Horario.
    if not data.has_hours:
        books = any(t.startswith(BOOKING_PREFIXES) for t in tools)
        found["hours"].append(
            Finding(
                "no_hours",
                "block" if books else "warn",
                "El negocio no tiene horario"
                + (
                    ": el agente no puede ofrecer citas."
                    if books
                    else ": el agente dirá que no lo sabe."
                ),
                fix=_link("business/hours"),
            )
        )

    # Incoherencias del compilador (16.5).
    catalog = list(data.ctx.tools)
    for inc in incoherences(spec, data.facts, catalog):
        if inc.code == "contradicts_business":
            found["contradictions"].append(
                Finding(
                    "contradicts_business",
                    "warn",
                    f"Las instrucciones dicen {inc.detail}, distinto de la ficha: manda la ficha.",
                    pointer=inc.pointer,
                    fix={"kind": "edit", "pointer": inc.pointer},
                )
            )
        elif inc.code == "promises_without_tool":
            found["promises"].append(
                Finding(
                    "promises_without_tool",
                    "warn",
                    f"Las instrucciones prometen {inc.detail} y el agente no tiene con qué.",
                    pointer=inc.pointer,
                    fix=_link("capabilities"),
                )
            )
        else:
            found["tools_exist"].append(
                Finding(
                    "unknown_tool",
                    "block",
                    f"Cita «{inc.detail}», que no es una herramienta del agente.",
                    pointer=inc.pointer,
                    fix={"kind": "proposal", "remove_tool": inc.detail, "pointer": inc.pointer},
                )
            )

    # Canales sin destinatarios de escalado.
    for channel in data.channels:
        if channel.recipients == 0:
            found["escalation_recipients"].append(
                Finding(
                    "channel_without_recipients",
                    "warn",
                    f"El canal {channel.name} no tiene a quién avisar cuando el agente pasa una conversación.",
                    fix=_link("channel", channel_id=channel.id),
                )
            )

    # Aviso de IA.
    disclosure = spec.ai_disclosure
    if not disclosure.decided:
        found["ai_disclosure"].append(
            Finding(
                "ai_disclosure_undecided",
                "block",
                "Falta decidir si el agente dice que es una IA.",
                pointer="/ai_disclosure",
                fix={"kind": "edit", "pointer": "/ai_disclosure"},
            )
        )
    elif data.eu_client and disclosure.mode == "on_ask":
        found["ai_disclosure"].append(
            Finding(
                "ai_disclosure_on_ask_eu",
                "warn",
                "En la UE el aviso debe darse al empezar, no solo si preguntan (AI Act, art. 50).",
                pointer="/ai_disclosure/mode",
                fix={"kind": "edit", "pointer": "/ai_disclosure/mode"},
            )
        )

    findings = tuple(f for name in CHECKS for f in found[name])
    checks = tuple(
        {"check": name, "ok": not found[name], "findings": len(found[name])} for name in CHECKS
    )
    return Review(findings=findings, checks=checks)


async def load_input(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    spec: AgentSpec,
    partner_id: uuid.UUID | None,
) -> ReviewInput:
    """Lo que la revisión necesita del cliente del contexto: la ficha del agente,
    sus servicios, sus canales y el catálogo con lo conectado."""
    import sqlalchemy as sa

    from nexus_api.core.tenant_context import require_current_tenant
    from nexus_api.db.models import Agent, Channel, ChannelEscalationRecipient, ChannelStatus
    from nexus_api.db.models.business import BusinessProfile
    from nexus_api.services.agent_spec.validator import load_context
    from nexus_api.services.business import hours as hours_service
    from nexus_api.services.business import services_catalog
    from nexus_api.services.business.compilation import load_facts

    tenant_id = require_current_tenant()
    agent = await session.get(Agent, agent_id)
    assert agent is not None
    facts = await load_facts(session, agent)
    business = await hours_service.load_hours(session)
    services = tuple(
        ServiceFact(
            id=str(s.id),
            name=s.name,
            bookable=bool(s.bookable),
            duration_min=s.duration_minutes,
            has_price=services_catalog.price_kind_of(s) in {"amount", "free"},
        )
        for s in await services_catalog.services_for_agent(session, agent_id)
    )
    # Los destinatarios de escalado de cada número (0191; requisito 33.6).
    recipients = (
        sa.select(sa.func.count())
        .select_from(ChannelEscalationRecipient)
        .where(ChannelEscalationRecipient.channel_id == Channel.id)
        .scalar_subquery()
    )
    channels = [
        ChannelFact(id=str(ch_id), name=str(identifier or ch_id), recipients=int(count or 0))
        for ch_id, identifier, count in (
            await session.execute(
                sa.select(Channel.id, Channel.provider_identifier, recipients).where(
                    Channel.tenant_id == tenant_id,
                    Channel.agent_id == agent_id,
                    Channel.provider != "qa_playground",
                    Channel.status != ChannelStatus.DISCONNECTED,
                )
            )
        ).all()
    ]
    profile = await session.get(BusinessProfile, tenant_id)
    eu = bool(profile.eu_only) if profile is not None else False
    return ReviewInput(
        spec=spec,
        facts=facts,
        ctx=await load_context(session, partner_id=partner_id),
        services=services,
        channels=tuple(channels),
        has_hours=business.week is not None,
        eu_client=eu,
    )


def findings_json(items: Sequence[Finding]) -> list[dict[str, Any]]:
    return [f.to_json() for f in items]


__all__ = [
    "CHECKS",
    "ChannelFact",
    "Finding",
    "Review",
    "ReviewInput",
    "ServiceFact",
    "findings_json",
    "load_input",
    "review",
]
