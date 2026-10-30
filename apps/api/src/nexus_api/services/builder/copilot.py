"""El copiloto del agente — spec 047, T099 (requisito 19; research D17).

Un panel lateral en las pantallas del agente que entiende peticiones en lenguaje
normal y responde con **propuestas revisables** (19.1), nunca con cambios hechos:

- **«¿Por qué dijo…?»** sobre una respuesta del playground o de una prueba (19.2):
  cita, con enlace, de dónde salió cada parte — la ficha, una instrucción, el
  conocimiento propio del agente o una herramienta que usó. La cita sale de
  comparar la respuesta con cada fuente (sin modelo): lo que no se puede atribuir
  se dice.
- **Una regla** («no ofrezcas descuentos») (19.3): la propone con su diff y con
  una prueba nueva que la comprueba (dos propuestas, que una persona aplica).
- **«Arreglar» un dato** de una prueba fallida (19.4): pregunta el alcance (el
  negocio o este agente) y no aplica nada hasta que la persona confirma
  (``apply_fix``).
- **Permisos** (19.5): a quien no puede escribir en el agente (analyst) le
  explica, pero no le propone cambios.

Los cambios de voz más corrientes («más formal», «de tú») se proponen sin modelo;
cualquier otra petición, con un modelo de la tarea ``build`` si lo hay, y siempre
pasando el validador antes de enseñarse.

Spec 047, enmienda del 2026-10-30 (65.3 y 65.7): el copiloto conoce las
herramientas disponibles para el cliente y lo que hace cada una, y no propone lo
que no tenemos. Una regla que promete algo que ninguna herramienta del agente hace
no se propone: si el cliente tiene una herramienta que lo haría, lo dice; si no la
tiene nadie, «No tenemos herramienta para: …», con ``missing_capabilities``.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.services import proposal_state
from nexus_api.services.agent_spec.missing import MissingCapability
from nexus_api.services.agent_spec.schema import AgentSpec, dump
from nexus_api.services.business.compilation import Facts

Complete = Callable[[list[dict[str, str]]], Awaitable[str]]
CitationKind = Literal["business", "instruction", "knowledge", "tool"]

_STOP: Final = frozenset(
    [
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "de",
        "del",
        "al",
        "a",
        "en",
        "y",
        "o",
        "que",
        "con",
        "por",
        "para",
        "es",
        "son",
        "se",
        "no",
        "si",
        "lo",
        "le",
        "les",
        "mi",
        "tu",
        "su",
        "sus",
        "te",
        "me",
        "nos",
        "os",
        "ya",
        "muy",
        "mas",
        "más",
        "hay",
        "está",
        "estan",
        "están",
        "este",
        "esta",
        "eso",
        "esto",
        "como",
        "cuando",
        "donde",
        "qué",
        "cuál",
        "cual",
        "quien",
        "quién",
        "hola",
        "gracias",
    ]
)
_WHY = re.compile(r"\bpor\s*qu[eé]\b|\bde d[oó]nde\b|\bpor que\b", re.I)
_RULE = re.compile(r"^\s*(no|nunca|jam[aá]s|siempre)\b|\bregla\b", re.I)
_FORMAL = re.compile(r"\b(m[aá]s formal|de usted|trata(r)? de usted)\b", re.I)
_INFORMAL = re.compile(r"\b(m[aá]s cercan[oa]|de t[uú]|tutea)\b", re.I)


def _plain(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c)
    )


def _tokens(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", _plain(text))
        if (t not in _STOP and len(t) > 2) or t.isdigit()
    }


@dataclass(frozen=True)
class Citation:
    kind: CitationKind
    label: str
    excerpt: str
    link: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "label": self.label, "excerpt": self.excerpt, "link": self.link}


@dataclass
class CopilotAnswer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    fix: dict[str, Any] | None = None
    #: 65.4: lo que la petición necesitaba y no tenemos (``contracts/console-api.md`` §11).
    missing: list[MissingCapability] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "citations": [c.to_json() for c in self.citations],
            "proposals": self.proposals,
            "fix": self.fix,
            "missing_capabilities": [m.to_json() for m in self.missing],
        }


def no_tool_text(missing: Sequence[MissingCapability]) -> str:
    return "No tenemos herramienta para: " + ", ".join(m.label for m in missing) + "."


async def _rule_without_tool(
    session: AsyncSession, rule: str, spec: AgentSpec, partner_id: uuid.UUID | None
) -> CopilotAnswer | None:
    """65.7: una regla que promete algo que ninguna herramienta del agente hace no
    se propone. Se mira lo que el cliente tiene disponible para decir si existe."""
    from nexus_api.api.console.capability_names import actions_of
    from nexus_api.services.agent_spec import missing
    from nexus_api.services.agent_spec.compiler import uncovered_promises
    from nexus_api.services.agent_spec.validator import load_context

    unkept = uncovered_promises(rule, spec.tools or [])
    if not unkept:
        return None
    ctx = await load_context(session, partner_id=partner_id)
    doable = actions_of(ctx.available_tools())
    lacking = [missing.action(p.key, p.label, None) for p in unkept if not p.needs & doable]
    if lacking:
        return CopilotAnswer(
            no_tool_text(lacking) + " El agente lo pasará a una persona; no te propongo la regla.",
            missing=lacking,
        )
    labels = ", ".join(p.label for p in unkept)
    return CopilotAnswer(
        f"Este agente no tiene ninguna herramienta para {labels}. Añádela en su "
        "especificación antes de pedírselo; no te propongo la regla."
    )


# ── «¿Por qué dijo…?» ───────────────────────────────────────────────────────


def _facts_sources(facts: Facts) -> list[tuple[str, str, str]]:
    """``(sección, etiqueta, texto)`` de cada dato de la ficha."""
    out: list[tuple[str, str, str]] = []
    if facts.hours:
        out.append(("hours", "Horario", facts.hours))
    for item in facts.special_dates:
        out.append(("special_dates", "Fechas especiales", item))
    for item in facts.locations:
        out.append(("locations", "Sedes", item))
    for item in facts.services:
        out.append(("services", "Servicios", item))
    for label, text in facts.policies:
        out.append(("policies", f"Política · {label}", text))
    for q, a in facts.faqs:
        out.append(("faqs", "Preguntas frecuentes", f"{q} {a}"))
    return out


def _spec_sources(spec: AgentSpec) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    if spec.instructions is not None:
        if spec.instructions.legacy_text:
            out.append(
                ("/instructions/legacy_text", "Instrucciones", spec.instructions.legacy_text)
            )
        for i, section in enumerate(spec.instructions.sections or []):
            out.append((f"/instructions/sections/{i}", section.title, section.body))
    for i, proc in enumerate(spec.procedures or []):
        out.append((f"/procedures/{i}", proc.title, f"{proc.when} {proc.steps}"))
    for i, rule in enumerate(spec.rules or []):
        out.append((f"/rules/{i}", "Regla", rule))
    return out


def cite(
    answer: str,
    *,
    spec: AgentSpec,
    facts: Facts,
    actions: Sequence[Mapping[str, Any]] = (),
) -> list[Citation]:
    """Las fuentes de una respuesta (19.2), de más a menos parecidas. Una fuente
    cuenta si comparte con la respuesta un número o al menos dos palabras con
    contenido."""
    said = _tokens(answer)
    numbers = {t for t in said if t.isdigit()}
    scored: list[tuple[float, Citation]] = []

    def score(text: str) -> float:
        theirs = _tokens(text)
        common = said & theirs
        if common & numbers:
            return len(common) + 2.0
        return float(len(common)) if len(common) >= 2 else 0.0

    for section, label, text in _facts_sources(facts):
        s = score(text)
        if s:
            scored.append(
                (s, Citation("business", label, text[:200], {"target": f"business/{section}"}))
            )
    for pointer, label, text in _spec_sources(spec):
        s = score(text)
        if s:
            scored.append(
                (
                    s,
                    Citation(
                        "instruction", label, text[:200], {"target": "agent", "pointer": pointer}
                    ),
                )
            )
    for i, faq in enumerate((spec.services.faqs if spec.services else None) or []):
        s = score(f"{faq.q} {faq.a}")
        if s:
            scored.append(
                (
                    s,
                    Citation(
                        "knowledge",
                        "Lo que sabe este agente",
                        f"{faq.q} {faq.a}"[:200],
                        {"target": "agent", "pointer": f"/services/faqs/{i}"},
                    ),
                )
            )
    out = [c for _s, c in sorted(scored, key=lambda x: -x[0])][:5]
    for action in actions:
        out.append(
            Citation(
                "tool",
                str(action.get("tool") or ""),
                str(action.get("phrase") or "")[:200],
                {"target": "capabilities", "tool": action.get("tool")},
            )
        )
    return out


# ── reglas, voz y arreglos ──────────────────────────────────────────────────


def _rule_text(message: str) -> str:
    text = re.sub(
        r"^\s*(añade|agrega|pon)\s+(una\s+)?regla\s*:?\s*", "", message.strip(), flags=re.I
    )
    text = text.strip().rstrip(".")
    return (text[:1].upper() + text[1:] + ".")[:300] if text else ""


def _rule_test(rule: str) -> dict[str, Any]:
    """Una prueba que comprueba la regla (19.3)."""
    plain = _plain(rule)
    if "descuento" in plain:
        first = "¿Me hacéis un descuento si vengo dos veces?"
    elif "precio" in plain:
        first = "¿Cuánto me cobras?"
    elif "cita" in plain or "reserva" in plain:
        first = "Quiero una cita para hoy mismo."
    else:
        first = "Hola, tengo una duda."
    return {
        "name": f"Regla: {rule}"[:120],
        "persona": "Cliente que pone a prueba la regla",
        "first_message": first,
        "plan": "Insiste una vez si el agente no responde lo que espera.",
        "expected_state": {},
        "criteria": [{"key": "rule", "text": rule}],
        "critical": False,
    }


async def _propose(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    kind: str,
    diff: dict[str, Any],
    state_hash: str,
    summary: str,
    actor: str,
) -> dict[str, Any]:
    p = await proposal_state.propose(
        session,
        agent_id=agent_id,
        kind=kind,
        author="copilot",
        diff=diff,
        state_hash=state_hash,
        summary=summary,
        created_by=actor,
    )
    return {
        "id": str(p.id),
        "kind": p.kind,
        "summary": p.summary,
        "diff": p.diff,
        "expires_at": p.expires_at.isoformat(),
    }


async def ask(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID,
    spec: AgentSpec,
    state_hash: str,
    facts: Facts,
    message: str,
    context: Mapping[str, Any] | None,
    can_write: bool,
    actor: str,
    partner_id: uuid.UUID | None = None,
    complete: Complete | None = None,
) -> CopilotAnswer:
    ctx = dict(context or {})
    answer_text = str(ctx.get("answer") or "")
    actions = list(ctx.get("actions") or [])

    # «¿Por qué dijo…?»
    if answer_text and (_WHY.search(message) or not message.strip()):
        citations = cite(answer_text, spec=spec, facts=facts, actions=actions)
        if not citations:
            return CopilotAnswer(
                "No encuentro de dónde sale esa respuesta en la ficha, las instrucciones ni lo "
                "que sabe el agente: puede ser algo que el modelo dedujo. Si no es correcto, "
                "añade el dato a la ficha o una regla."
            )
        kinds = {
            "business": "la ficha del negocio",
            "instruction": "sus instrucciones",
            "knowledge": "lo que sabe este agente",
            "tool": "una herramienta",
        }
        used = ", ".join(dict.fromkeys(kinds[c.kind] for c in citations))
        return CopilotAnswer(f"Lo dijo por {used}.", citations=citations)

    # «Arreglar» un dato de una prueba fallida: pide el alcance (19.4).
    if ctx.get("test_id") and re.search(r"\barregl|\bcorrig", _plain(message)):
        if not can_write:
            return CopilotAnswer("Esta prueba falla; quien edita el agente puede arreglarla.")
        return CopilotAnswer(
            "¿Dónde corrijo el dato? En la ficha lo sabrán todos los agentes; en «Solo este "
            "agente», solo este. No cambio nada hasta que lo confirmes.",
            fix={"test_id": str(ctx["test_id"]), "scopes": ["business", "agent"]},
        )

    if not can_write:
        # 19.5: a un analyst se le explica, no se le proponen cambios.
        return CopilotAnswer(
            "Puedo explicarte qué hace el agente y por qué respondió algo; los cambios los "
            "propone quien edita el agente."
        )

    doc = dump(spec)

    # Una regla, con su prueba (19.3).
    if _RULE.search(message):
        rule = _rule_text(message)
        refused = await _rule_without_tool(session, rule, spec, partner_id) if rule else None
        if refused is not None:
            return refused
        if rule:
            rules = list(doc.get("rules") or [])
            if rule not in rules:
                change = await _propose(
                    session,
                    agent_id=agent_id,
                    kind="agent_spec_patch",
                    diff={"ops": [{"op": "add", "path": "/rules/-", "value": rule}]},
                    state_hash=state_hash,
                    summary=f"Añadir la regla «{rule}»",
                    actor=actor,
                )
                test = await _propose(
                    session,
                    agent_id=agent_id,
                    kind="test_add",
                    diff={"test": _rule_test(rule)},
                    state_hash=state_hash,
                    summary=f"Una prueba que comprueba «{rule}»",
                    actor=actor,
                )
                return CopilotAnswer(
                    "Te propongo la regla y una prueba que la comprueba.", proposals=[change, test]
                )

    # La voz.
    for pattern, register, label in ((_FORMAL, "usted", "de usted"), (_INFORMAL, "tu", "de tú")):
        if pattern.search(message):
            voice = dict(doc.get("voice") or {"languages": ["es"]})
            voice["register"] = register
            change = await _propose(
                session,
                agent_id=agent_id,
                kind="agent_spec_patch",
                diff={"ops": [{"op": "add", "path": "/voice", "value": voice}]},
                state_hash=state_hash,
                summary=f"Que trate {label}",
                actor=actor,
            )
            return CopilotAnswer(f"Te propongo que trate {label}.", proposals=[change])

    if complete is not None:
        from nexus_api.services.builder.copilot_model import propose_with_model

        return await propose_with_model(
            session,
            complete=complete,
            agent_id=agent_id,
            spec=spec,
            state_hash=state_hash,
            message=message,
            actor=actor,
            partner_id=partner_id,
        )
    return CopilotAnswer(
        "Todavía no sé hacer ese cambio solo. Prueba con una regla («No ofrezcas descuentos»), "
        "con el trato («más formal») o edita el bloque directamente."
    )


__all__ = ["Citation", "CopilotAnswer", "ask", "cite"]
