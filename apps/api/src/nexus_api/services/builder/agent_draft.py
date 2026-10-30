"""Crear un agente describiéndolo — el motor del constructor (spec 047, T079;
requisitos 15, 16 y 17; research D17).

Corre en el worker como el trabajo ``agent_draft`` (``nexus_worker.jobs.handlers.agent_draft``),
que pone el modelo de la tarea ``build`` y la medición en la partida
«Construcción y pruebas». Aquí vive lo que no es del worker:

1. **Leer** la ficha del cliente (como datos), el catálogo de herramientas con lo
   que el cliente tiene conectado, y la descripción que escribió la persona. La
   descripción, la información del negocio y lo leído de la web van **vallados**
   (``core/guardrails/untrusted.py``): son datos, nunca órdenes (§III, 15.5).
2. **Pedir** al modelo un borrador con salida JSON (``prompts/agent_draft.md``,
   solo patrones de Auphere: 15.6).
3. **Sanear**: el nombre y la descripción son los de la persona, nunca los del
   modelo; el aviso de IA queda sin decidir (16.6); cada herramienta pasa el
   validador sin modelo (15.4) y la que necesita una integración sin conectar
   se convierte en «Conectar {integración}» (17.6); como mucho 5 preguntas, con
   su porqué, y se dice cuántas se descartaron y por qué (17.4).
4. **Contar** el avance por bloques (17.3) y **escribir**: el agente nace aquí,
   con el primer borrador (17.2), su versión ``staged`` con el AgentSpec y el
   prompt compilado, y su suite con las pruebas del caso.

El borrador de un agente **nuevo** se escribe directamente: lo pidió una persona
al pulsar «Generar borrador» y no habla con nadie hasta pasar la puerta
(requisito 23). Sobre un agente que ya existe, el constructor solo propone
(``services/proposal_state``).

Sin respuesta útil del modelo, :class:`BuilderUnavailable`: la consola ofrece
«Desde una plantilla» y «En blanco» sin perder lo escrito (15.8).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus_api.core.guardrails.untrusted import fence
from nexus_api.core.tenant_context import require_current_tenant, tenant_scoped_session
from nexus_api.services.agent_spec import missing
from nexus_api.services.agent_spec.compiler import compile_spec, uncovered_promises
from nexus_api.services.agent_spec.legacy import LEGACY_DEPLOYMENT
from nexus_api.services.agent_spec.missing import MissingCapability, Source
from nexus_api.services.agent_spec.retired import RETIRED_TOOLS
from nexus_api.services.agent_spec.schema import TOOL_NAME_PATTERN, AgentSpec, dump
from nexus_api.services.agent_spec.validator import Context, load_context, validate_spec
from nexus_api.services.builder.guides import generated as guides_generated
from nexus_api.services.builder.guides import render as render_guide
from nexus_api.services.builder.guides import resolve as guides_resolve
from nexus_api.services.builder.guides.resolve import ResolvedGuide
from nexus_api.services.builder.guides.roles import patterns_text, roles_for
from nexus_api.services.business.compilation import Facts, render_facts

log = structlog.get_logger(__name__)

NAME_MAX: Final = 40
DESCRIPTION_MIN: Final = 20
DESCRIPTION_MAX: Final = 1024
MAX_QUESTIONS: Final = 5
CASE_TESTS: Final = 8

#: Los bloques del borrador, en el orden en que la pantalla los pinta.
BLOCKS: Final = (
    "identity",
    "voice",
    "instructions",
    "procedures",
    "services",
    "skills",
    "escalation",
    "rules",
    "tests",
    "questions",
)

#: Dónde puede ir una respuesta. «business» = la ficha (por defecto); «agent» =
#: «Solo este agente», en su AgentSpec (17.5).
BUSINESS_TARGETS: Final = frozenset(
    {
        "/policies/cancellation",
        "/policies/payments",
        "/policies/deposit",
        "/policies/no_show",
        "/faqs/-",
    }
)
AGENT_TARGETS: Final = frozenset(
    {"/rules/-", "/services/faqs/-", "/voice/register", "/escalation/message", "/identity/goal"}
)

PROMPT_FILE: Final = Path(__file__).with_name("prompts") / "agent_draft.md"
#: Where a version keeps what the builder left out (``policies["builder"]``).
BUILDER_POLICY: Final = "builder"

Complete = Callable[[list[dict[str, str]]], Awaitable[str]]
Progress = Callable[..., Awaitable[bool]]


class BuilderUnavailable(Exception):
    """El modelo no respondió o no devolvió un borrador que se pueda leer."""

    code = "builder_unavailable"


class FactsUnavailable(Exception):
    """Spec 047, enmienda del 2026-10-30 (65.12): la ficha del negocio no se pudo
    leer. Sin ella no se escribe un borrador genérico: el trabajo falla con su
    código y la consola lo explica."""

    code = "facts_unavailable"


class DraftInputInvalid(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DraftRequest:
    name: str
    description: str

    @classmethod
    def clean(cls, name: str, description: str) -> DraftRequest:
        name = " ".join((name or "").split())
        description = (description or "").strip()
        if not 1 <= len(name) <= NAME_MAX:
            raise DraftInputInvalid("name_length")
        if not DESCRIPTION_MIN <= len(description) <= DESCRIPTION_MAX:
            raise DraftInputInvalid("description_length")
        return cls(name=name, description=description)


@dataclass
class Draft:
    """Lo que sale del constructor, ya saneado."""

    spec: AgentSpec
    questions: list[dict[str, Any]] = field(default_factory=list)
    discarded: dict[str, Any] = field(default_factory=lambda: {"count": 0, "reasons": []})
    tests: list[dict[str, Any]] = field(default_factory=list)
    connect: list[dict[str, str]] = field(default_factory=list)
    dropped_tools: list[dict[str, str]] = field(default_factory=list)
    #: Spec 047, enmienda del 2026-10-30 (65.3 y 65.4): lo que se quedó fuera por
    #: no tenerlo, más las promesas sin herramienta del borrador.
    lacking: list[MissingCapability] = field(default_factory=list)

    @property
    def missing(self) -> list[dict[str, Any]]:
        """Lo que falta, como lo lee la consola (``contracts/console-api.md`` §11)."""
        return [m.to_json() for m in missing.merge(missing.from_promises(self.spec), self.lacking)]

    @property
    def builder_missing(self) -> list[dict[str, Any]]:
        """Lo que el constructor dejó fuera, para guardarlo en la versión: las
        promesas del AgentSpec se calculan en cada lectura del borrador."""
        return [m.to_json() for m in self.lacking]


# ── lo que se le da al modelo ───────────────────────────────────────────────


def _mapping(value: Any) -> Mapping[str, Any]:
    """Lo que el modelo devolvió como objeto, o un objeto vacío."""
    return value if isinstance(value, Mapping) else {}


AGENDA_PREFIX: Final = "reservas."
_TOOL_NAME: Final = re.compile(TOOL_NAME_PATTERN)


def _catalog_lines(ctx: Context) -> list[str]:
    """Lo que el constructor ve del catálogo: cada herramienta que puede usar, con
    lo que hace (``capability_names``) y si este cliente la tiene. Una con un
    nombre que el AgentSpec no admite (las de Composio, en mayúsculas y sin punto)
    no se enseña: si el modelo la eligiera, el borrador entero no validaría."""
    from nexus_api.api.console.capability_names import description_of

    lines = []
    for name in sorted(ctx.tools):
        info = ctx.tools[name]
        if (
            info.status in {"internal", "deprecated"}
            or not info.integration_offered
            or name in RETIRED_TOOLS
            or not _TOOL_NAME.fullmatch(name)
        ):
            continue
        if info.integration is None:
            state = "nativa"
        elif info.connected:
            state = f"necesita {info.integration}: conectada"
        elif info.activatable:
            state = f"necesita {info.integration}: SIN CONECTAR"
        else:
            # D67: lo que no es un conector (el módulo Reservas, el catálogo de
            # Meta del canal) no se conecta desde el agente: está o no está.
            state = f"necesita {info.integration}: SIN ACTIVAR para este cliente, no la uses"
        what = description_of(name, "tool", "es")
        lines.append(f"- {name} ({state})" + (f": {what}" if what else ""))
    return lines


def available_lines(ctx: Context, *, only: Iterable[str] | None = None) -> list[str]:
    """Spec 047, enmienda del 2026-10-30 (65.7): las herramientas disponibles para
    el cliente (65.2), con lo que hace cada una según ``capability_names``. Las
    reciben el copiloto y el constructor del cliente; ``only`` las limita (las del
    agente)."""
    from nexus_api.api.console.capability_names import description_of

    wanted = set(only) if only is not None else None
    lines = []
    for name in ctx.available_tools():
        if wanted is not None and name not in wanted:
            continue
        info = ctx.tools[name]
        state = "" if info.connected else f" (pendiente de conectar {info.integration})"
        what = description_of(name, "tool", "es")
        lines.append(f"- {name}{state}" + (f": {what}" if what else ""))
    return lines


def _guide_block(guide: ResolvedGuide | None) -> str:
    """La guía del sector (58.2): vallada siempre, porque la generada sale de un
    modelo alimentado con una etiqueta que no es de fiar (§III)."""
    if guide is None or guide.guide is None:
        return ""
    title = f"Guía del sector: {guide.label}"
    if guide.source == "generated":
        title += " (generada para este cliente)"
    return fence(render_guide(guide.guide), tag="guia_del_sector", title=title)


def build_messages(
    request: DraftRequest,
    facts: Facts,
    ctx: Context,
    *,
    guide: ResolvedGuide | None = None,
    roles: list[str] | None = None,
) -> list[dict[str, str]]:
    """Lo que recibe el constructor (58.2): la descripción y la ficha valladas, la
    guía del sector guardado, los patrones de papel que encajan con la descripción
    (ejemplos combinables, no papeles fijos) y el catálogo con lo que este cliente
    tiene y lo que hace cada herramienta. La identidad sale de la ficha y la
    descripción, nunca de la guía ni de los patrones."""
    system = PROMPT_FILE.read_text(encoding="utf-8")
    chosen = roles or roles_for(request.description)
    user = "\n\n".join(
        part
        for part in (
            f"Nombre del agente: {request.name}",
            fence(request.description, tag="descripcion", title="¿Qué tiene que hacer?"),
            fence(render_facts(facts), tag="ficha", title="Ficha del negocio"),
            _guide_block(guide),
            "<patrones_del_papel>\n" + patterns_text(chosen) + "\n</patrones_del_papel>",
            "<herramientas>\n" + "\n".join(_catalog_lines(ctx)) + "\n</herramientas>",
        )
        if part
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_output(text: str) -> dict[str, Any]:
    """El JSON del modelo, aunque venga entre ```json … ```. Cualquier otra cosa
    es :class:`BuilderUnavailable`."""
    raw = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.S)
    if fenced:
        raw = fenced.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise BuilderUnavailable("no_json")
    try:
        out = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise BuilderUnavailable("bad_json") from exc
    if not isinstance(out, dict):
        raise BuilderUnavailable("not_an_object")
    return out


# ── sanear ──────────────────────────────────────────────────────────────────


def _str(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit] if not isinstance(value, dict) else ""


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


_ID = re.compile(r"[^a-z0-9_]+")
_TRIGGERS: Final = frozenset(
    {"asks_for_human", "failed_attempts", "complaint", "payment_issue", "emergency", "out_of_scope"}
)


def _policy_filled(facts: Facts, pointer: str) -> bool:
    labels = {
        "/policies/cancellation": "Cancelación",
        "/policies/payments": "Pagos",
        "/policies/deposit": "Señal",
        "/policies/no_show": "Si no se presenta",
    }
    label = labels.get(pointer)
    return label is not None and any(lbl == label for lbl, _t in facts.policies)


def sanitize(
    raw: Mapping[str, Any],
    request: DraftRequest,
    ctx: Context,
    facts: Facts,
    *,
    model_policy: Mapping[str, str] | None,
) -> Draft:
    """De lo que dijo el modelo a un AgentSpec que pasa el validador. Lo que no
    cabe se quita y se cuenta; nada de lo que dijo el modelo sobre la identidad,
    el aviso de IA o la plataforma sobrevive.

    Spec 047, enmienda del 2026-10-30 (65.3 y 65.4): lo que no tenemos no entra.
    Una integración que no es un conector ofrecido, un módulo apagado, una
    herramienta que no existe y un procedimiento o una regla que prometen algo que
    ninguna herramienta del agente hace salen del borrador y se anotan en
    ``missing``; nunca acaban en «Conectar {X}». El agente se queda con su
    alternativa: pasar a una persona (la sección de límites del prompt, 65.6)."""
    dropped: list[dict[str, str]] = []
    connect: dict[str, str] = {}
    lacking: list[MissingCapability] = []
    offered = ctx.offered_connectors()
    skill_ok = ctx.skill_integrations()

    def lack(slug: str, source: Source, skill: str | None = None) -> None:
        if slug in skill_ok and source != "skill":
            return  # lo tiene el cliente y no se conecta: nada que pedir ni que decir
        lacking.append(
            missing.not_offered(
                slug, module=slug in missing.MODULE_LABELS, source=source, skill=skill
            )
        )

    def usable(name: str) -> bool:
        # Spec 048 (CE-004): ningún agente nuevo nace con ``booking.*``.
        if name in RETIRED_TOOLS:
            dropped.append({"tool": name, "why": "tool_retired"})
            return False
        info = ctx.tools.get(name)
        if info is None:
            dropped.append({"tool": name, "why": "tool_unknown"})
            lacking.append(missing.tool(name))
            return False
        if (
            info.status in {"internal", "deprecated"}
            or not info.integration_offered
            or not _TOOL_NAME.fullmatch(name)
        ):
            dropped.append({"tool": name, "why": "tool_not_allowed"})
            return False
        if info.integration is not None and not info.connected:
            # Spec 047, enmienda del 2026-10-29 (requisito 62.1, D53 y D62): con un
            # conector con activación, se guarda «pendiente de conexión», con su
            # petición; el runtime no la ve hasta que la conexión exista y esté
            # activada para el agente (garantías 2 y 9, ``activations.tool_policy``).
            if info.activatable and info.integration in offered:
                connect.setdefault(info.integration, f"Para usar {name}")
                return True
            # Sin activación que la retenga (el módulo Reservas apagado, el
            # catálogo de Meta sin enlazar), fuera, y se dice qué falta (65.3).
            dropped.append({"tool": name, "why": "tool_not_connected"})
            lack(info.integration, "tool")
            return False
        return True

    raw_tools = [str(t) for t in (raw.get("tools") or []) if isinstance(t, str)]
    tools = [t for t in dict.fromkeys(raw_tools) if usable(t)]
    # Ninguna herramienta que deje elegir a un cliente final (garantía 8): se
    # comprueba con el validador del constructor, que es más estricto.
    probe_ctx = Context(tools=ctx.tools)
    keep: list[str] = []
    for name in tools:
        _s, problems = validate_spec(_skeleton(request, [name]), probe_ctx, author="builder")
        if any(p.code == "end_customer_argument" for p in problems):
            dropped.append({"tool": name, "why": "end_customer_argument"})
        else:
            keep.append(name)
    tools = keep[:60]

    def promises(text: str) -> bool:
        """65.4: lo que promete algo que ninguna de sus herramientas hace se queda
        fuera, anotado."""
        found = uncovered_promises(text, tools)
        lacking.extend(missing.action(p.key, p.label, None) for p in found)
        return bool(found)

    procedures = []
    for i, proc in enumerate(raw.get("procedures") or []):
        if not isinstance(proc, Mapping):
            continue
        pid = _ID.sub("_", _str(proc.get("id") or proc.get("title") or f"p{i}", 40).lower()).strip(
            "_"
        )
        steps = _text(proc.get("steps"), 2000)
        title = _str(proc.get("title"), 80)
        when = _str(proc.get("when"), 300)
        if not (pid and steps and title and when):
            continue
        cited = [t for t in dict.fromkeys(str(x) for x in proc.get("tools") or []) if t in tools]
        if promises(f"{when}. {steps}"):
            continue
        item: dict[str, Any] = {"id": pid[:40], "title": title, "when": when, "steps": steps}
        if cited:
            item["tools"] = cited[:10]
        procedures.append(item)

    sections = []
    budget = 8000
    for section in raw.get("instructions") or []:
        if not isinstance(section, Mapping):
            continue
        title, body = _str(section.get("title"), 80), _text(section.get("body"), 8000)
        if title and body and len(body) <= budget:
            sections.append({"title": title, "body": body})
            budget -= len(body)
    if not sections:
        # 65.12: sin instrucciones no hay borrador genérico; es un fallo del
        # constructor y la consola ofrece «Desde una plantilla» o «En blanco».
        raise BuilderUnavailable("no_instructions")

    for req in raw.get("connection_requests") or []:
        slug = str(req.get("integration") or "") if isinstance(req, Mapping) else ""
        if not re.fullmatch(r"[a-z0-9_]{1,40}", slug):
            continue
        if slug in offered:
            connect.setdefault(slug, _str(req.get("reason"), 200) or "Lo pide una habilidad")
        else:
            lack(slug, "connection_request")
    skills = []
    for skill in raw.get("skills") or []:
        if not isinstance(skill, Mapping):
            continue
        key = re.sub(r"[^a-z0-9_.]+", "_", _str(skill.get("key"), 60).lower()).strip("_.")
        if not key:
            continue
        integ = skill.get("integration")
        integ = (
            str(integ)
            if isinstance(integ, str) and re.fullmatch(r"[a-z0-9_]{1,40}", integ)
            else None
        )
        if integ is not None and integ not in skill_ok:
            lack(integ, "skill", key)
            continue
        item = {"key": key[:60], "enabled": bool(skill.get("enabled", True)), "integration": integ}
        if skill.get("fallback"):
            item["fallback"] = _str(skill.get("fallback"), 300)
        if integ is not None and integ in connect:
            item.setdefault("fallback", "Pasa la conversación al equipo.")
        skills.append(item)
    for integ in connect:
        if not any(s.get("integration") == integ for s in skills):
            skills.append(
                {
                    "key": integ,
                    "enabled": True,
                    "integration": integ,
                    "fallback": "Mientras no esté conectada, pasa la conversación al equipo.",
                }
            )

    esc_raw = _mapping(raw.get("escalation"))
    triggers: list[Any] = []
    for trig in esc_raw.get("triggers") or ["asks_for_human", "failed_attempts", "complaint"]:
        if isinstance(trig, str) and trig in _TRIGGERS and trig not in triggers:
            triggers.append(trig)
        elif isinstance(trig, Mapping) and trig.get("custom"):
            triggers.append({"custom": _str(trig["custom"], 300)})
    try:
        attempts = min(5, max(1, int(esc_raw.get("failed_attempts") or 2)))
    except (TypeError, ValueError):
        attempts = 2
    escalation: dict[str, Any] = {"triggers": triggers[:20], "failed_attempts": attempts}
    if esc_raw.get("message"):
        escalation["message"] = _str(esc_raw["message"], 500)

    voice_raw = _mapping(raw.get("voice"))
    voice: dict[str, Any] = {}
    if voice_raw.get("tone"):
        voice["tone"] = _str(voice_raw["tone"], 200)
    langs = [
        str(lang)
        for lang in voice_raw.get("languages") or []
        if isinstance(lang, str) and re.fullmatch(r"[a-z]{2,3}(-[A-Z]{2})?", lang)
    ]
    voice["languages"] = list(dict.fromkeys(langs))[:5] or ["es"]
    if voice_raw.get("register") in {"tu", "usted", "vos"}:
        voice["register"] = voice_raw["register"]
    if voice_raw.get("greeting"):
        voice["greeting"] = _str(voice_raw["greeting"], 300)

    faqs = [
        {"q": _str(f.get("q"), 300), "a": _text(f.get("a"), 2000)}
        for f in raw.get("faqs") or []
        if isinstance(f, Mapping) and f.get("q") and f.get("a")
    ][:100]
    rules = [
        rule
        for rule in (
            _str(r, 300) for r in raw.get("rules") or [] if isinstance(r, str) and r.strip()
        )
        if not promises(rule)
    ][:30]

    doc: dict[str, Any] = {
        "schema_version": "1",
        "mode": "structured",
        "identity": {"name": request.name, "description": request.description},
        "voice": voice,
        "instructions": {"sections": sections[:20]},
        "procedures": procedures[:30],
        "services": {"mode": "all", **({"faqs": faqs} if faqs else {})},
        "skills": skills[:30],
        "tools": tools,
        "connection_requests": [
            {"integration": k, "reason": v} for k, v in list(connect.items())[:10]
        ],
        "escalation": escalation,
        "rules": rules,
        # 16.6: lo decide una persona. Lo que diga el modelo no cuenta.
        "ai_disclosure": {"decided": False},
        "model_policy": dict(model_policy)
        if model_policy
        else {"kind": "pinned", "deployment": LEGACY_DEPLOYMENT},
        "memory": {"scope": "shared"},
    }
    goal = _str(raw.get("goal"), 500)
    if goal:
        doc["identity"]["goal"] = goal
    for key in ("procedures", "skills", "connection_requests", "rules"):
        if not doc[key]:
            del doc[key]
    spec, problems = validate_spec(doc, ctx, author="builder")
    if spec is None or problems:
        # Lo que el saneado no supo arreglar no se enseña: se quita lo que falla.
        log.warning("builder.draft.problems", codes=[p.code for p in problems])
        for p in problems:
            if p.pointer.startswith("/rules/") or p.pointer.startswith("/instructions/"):
                doc.pop("rules", None)
        spec, problems = validate_spec(doc, ctx, author="builder")
        if spec is None or problems:
            raise BuilderUnavailable("invalid_draft")

    questions, discarded = _questions(raw, facts)
    return Draft(
        spec=spec,
        questions=questions,
        discarded=discarded,
        tests=_tests(raw),
        connect=[{"integration": k, "reason": v} for k, v in connect.items()],
        dropped_tools=dropped,
        lacking=missing.merge(lacking),
    )


def _skeleton(request: DraftRequest, tools: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "mode": "structured",
        "identity": {"name": request.name, "description": request.description},
        "voice": {"languages": ["es"]},
        "instructions": {"sections": [{"title": "x", "body": "x"}]},
        "services": {"mode": "all"},
        "tools": tools,
        "escalation": {},
        "ai_disclosure": {"decided": False},
        "model_policy": {"kind": "pinned", "deployment": LEGACY_DEPLOYMENT},
        "memory": {"scope": "shared"},
    }


def _questions(raw: Mapping[str, Any], facts: Facts) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    reasons: list[str] = []
    model_discarded = _mapping(raw.get("discarded"))
    try:
        count = max(0, int(model_discarded.get("count") or 0))
    except (TypeError, ValueError):
        count = 0
    reasons.extend(_str(r, 200) for r in model_discarded.get("reasons") or [] if isinstance(r, str))
    seen: set[str] = set()
    for i, q in enumerate(raw.get("questions") or []):
        if not isinstance(q, Mapping):
            continue
        target = str(q.get("target") or "")
        scope = (
            "business"
            if target in BUSINESS_TARGETS
            else "agent"
            if target in AGENT_TARGETS
            else None
        )
        text = _str(q.get("text"), 300)
        why = _str(q.get("why"), 300)
        if scope is None or not text or not why:
            count += 1
            reasons.append("No se puede guardar en ningún sitio de la ficha ni del agente.")
            continue
        if scope == "business" and _policy_filled(facts, target):
            count += 1
            reasons.append("Ya estaba en la ficha del negocio.")
            continue
        if target in seen and not target.endswith("/-"):
            count += 1
            reasons.append("Repetía otra pregunta.")
            continue
        if len(kept) >= MAX_QUESTIONS:
            count += 1
            reasons.append("Como mucho se hacen 5 preguntas: no hace falta para empezar.")
            continue
        seen.add(target)
        options = [_str(o, 120) for o in q.get("options") or [] if isinstance(o, str) and o.strip()]
        kept.append(
            {
                "id": _ID.sub("_", _str(q.get("id") or f"q{i + 1}", 40).lower()).strip("_")
                or f"q{i + 1}",
                "text": text,
                "why": why,
                "options": options[:6] or None,
                "target": target,
                "scope": scope,
                # 17.5: dice dónde se guarda la respuesta y si se puede cambiar.
                "can_be_agent_only": scope == "business",
            }
        )
    return kept, {"count": count, "reasons": list(dict.fromkeys(reasons))}


def _tests(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in raw.get("tests") or []:
        if not isinstance(t, Mapping):
            continue
        name, first = _str(t.get("name"), 120), _text(t.get("first_message"), 2000)
        if not name or not first:
            continue
        criteria = [
            {
                "key": _ID.sub("_", _str(c.get("key") or f"c{j}", 40).lower()) or f"c{j}",
                "text": _str(c.get("text"), 300),
            }
            for j, c in enumerate(t.get("criteria") or [])
            if isinstance(c, Mapping) and c.get("text")
        ][:6]
        expected = _mapping(t.get("expected_state"))
        out.append(
            {
                "kind": "case",
                "name": name,
                "persona": _text(t.get("persona"), 500),
                "first_message": first,
                "plan": _text(t.get("plan"), 1000),
                "expected_state": dict(expected),
                "criteria": criteria,
                "critical": bool(t.get("critical", False)),
            }
        )
        if len(out) >= CASE_TESTS:
            break
    return out


# ── sin modelo (desarrollo local con ``llm_use_inmemory``) ──────────────────

_BOOKING = re.compile(r"\b(cita|citas|reserv\w*|agend\w*|turno)\b", re.I)
_PAYING = re.compile(r"\b(cobr\w*|pago|pagos|deuda\w*)\b", re.I)
_USTED = re.compile(r"\busted\b", re.I)


def offline_output(
    request: DraftRequest,
    facts: Facts,
    ctx: Context,
    *,
    guide: ResolvedGuide | None = None,
    tools_hint: list[str] | None = None,
) -> dict[str, Any]:
    """Un borrador determinista a partir de la descripción, del catálogo y, si la
    hay, de la guía del sector: para recorrer el flujo entero en local sin claves
    de ningún proveedor, y para «Desde una plantilla» (58.6), que pasa las
    herramientas de su plantilla en ``tools_hint``. Nunca se usa con un proveedor
    de verdad."""
    text = request.description
    booking = bool(_BOOKING.search(text))
    paying = bool(_PAYING.search(text))
    # 65.2: solo lo disponible para el cliente; la agenda, solo con Reservas
    # encendido (un módulo apagado no se «conecta»: se queda fuera).
    available = ctx.available_tools()
    tools: list[str] = []
    procedures: list[dict[str, Any]] = []
    if tools_hint is not None:
        tools = [n for n in dict.fromkeys(tools_hint) if n in available]
    agenda = [n for n in available if n.startswith(AGENDA_PREFIX)]
    books = booking and any(n in agenda for n in ("reservas.create", "reservas.answer_offer"))
    if books:
        tools += agenda[:6]
        procedures.append(
            {
                "id": "reservar",
                "title": "Reservar una cita",
                "when": "Cuando alguien pide una cita o pregunta por huecos",
                "steps": "Pregunta el servicio y el día. Busca huecos, ofrece dos y confirma "
                "con fecha y hora en palabras. Recuerda la política de cancelación.",
                "tools": [n for n in agenda if n in ("reservas.find_slots", "reservas.create")],
            }
        )
    elif booking:
        # 65.4: sin agenda, la alternativa y no la promesa.
        procedures.append(
            {
                "id": "pedir_cita",
                "title": "Pedir una cita",
                "when": "Cuando alguien pide una cita o pregunta por huecos",
                "steps": "Toma el servicio, el día y la hora que prefiere, y pasa la "
                "conversación al equipo para que se la confirme. No prometas ninguna hora.",
            }
        )
    if guide is not None and guide.guide is not None:
        have = {p["id"] for p in procedures}
        for proc in guide.guide.procedures[:6]:
            pid = _ID.sub("_", proc.title.lower()).strip("_")[:40]
            if not pid or pid in have:
                continue
            have.add(pid)
            procedures.append(
                {
                    "id": pid,
                    "title": proc.title[:80],
                    "when": proc.when or proc.title,
                    "steps": proc.steps,
                }
            )
    if paying:
        # Lo que de verdad cobra o lleva los cobros, y la revisión de un
        # comprobante. Nunca una integración inventada (65.3).
        from nexus_api.api.console.capability_names import TOOL_ACTIONS

        tools += [
            n
            for n in available
            if n == "payments.request_review"
            or TOOL_ACTIONS.get(n, frozenset()) & {"charge", "collect"}
        ][:4]
    questions: list[dict[str, Any]] = []
    discarded = {"count": 0, "reasons": []}
    if booking:
        questions.append(
            {
                "id": "cancelacion",
                "text": "¿Con cuánto tiempo hay que avisar para cancelar una cita?",
                "why": "El agente lo dirá al confirmar cada cita.",
                "options": [
                    "24 horas antes",
                    "2 horas antes",
                    "Se puede cancelar en cualquier momento",
                ],
                "scope": "business",
                "target": "/policies/cancellation",
            }
        )
    if _USTED.search(text):
        discarded = {"count": 1, "reasons": ["El trato ya estaba en la descripción."]}
    else:
        questions.append(
            {
                "id": "trato",
                "text": "¿Cómo trata el agente a los clientes?",
                "why": "Cambia todas sus respuestas.",
                "options": ["tu", "usted"],
                "scope": "agent",
                "target": "/voice/register",
            }
        )
    tests = [
        {
            "name": "Pregunta el horario",
            "persona": "Cliente habitual",
            "first_message": "¿A qué hora abrís mañana?",
            "plan": "Pregunta el horario de mañana.",
            "expected_state": {"answered_from": "hours"},
            "criteria": [{"key": "hours", "text": "Dice el horario de la ficha, sin inventar."}],
            "critical": True,
        },
        {
            "name": "Pide hablar con una persona",
            "persona": "Cliente con prisa",
            "first_message": "Quiero hablar con alguien, por favor.",
            "plan": "Insiste en hablar con una persona.",
            "expected_state": {"escalated": True},
            "criteria": [{"key": "escalates", "text": "Pasa la conversación al equipo."}],
            "critical": True,
        },
        {
            "name": "Pregunta un precio",
            "persona": "Cliente nuevo",
            "first_message": "¿Cuánto cuesta?",
            "plan": "Pregunta el precio de un servicio.",
            "expected_state": {},
            "criteria": [
                {
                    "key": "price",
                    "text": "Da el precio de la ficha o dice que lo confirma el equipo.",
                }
            ],
            "critical": False,
        },
        {
            "name": "Se queja",
            "persona": "Cliente molesto",
            "first_message": "La última vez me atendieron fatal.",
            "plan": "Expresa una queja.",
            "expected_state": {"escalated": True},
            "criteria": [{"key": "empathy", "text": "Se disculpa y pasa la queja al equipo."}],
            "critical": False,
        },
        {
            "name": "Pide algo que no le toca",
            "persona": "Curioso",
            "first_message": "¿Me recomiendas un restaurante?",
            "plan": "Pide algo fuera de su trabajo.",
            "expected_state": {},
            "criteria": [{"key": "scope", "text": "Dice amablemente que no le toca."}],
            "critical": False,
        },
        {
            "name": "Pregunta la dirección",
            "persona": "Cliente nuevo",
            "first_message": "¿Dónde estáis?",
            "plan": "Pregunta la dirección.",
            "expected_state": {},
            "criteria": [
                {"key": "address", "text": "Da la dirección de la ficha o dice que no la tiene."}
            ],
            "critical": True,
        },
    ]
    if books:
        tests += [
            {
                "name": "Pide cita para mañana",
                "persona": "Cliente habitual",
                "first_message": "Hola, ¿tienes hueco mañana por la tarde?",
                "plan": "Acepta el primer hueco que le ofrezcan.",
                "expected_state": {"booking": {"created": True}},
                "criteria": [{"key": "booked", "text": "Crea la cita en un hueco que existe."}],
                "critical": True,
            },
            {
                "name": "Cancela su cita",
                "persona": "Cliente con imprevisto",
                "first_message": "No puedo ir a mi cita, ¿la puedo cancelar?",
                "plan": "Pide cancelar.",
                "expected_state": {},
                "criteria": [{"key": "policy", "text": "Recuerda la política de cancelación."}],
                "critical": False,
            },
        ]
    elif booking:
        tests.append(
            {
                "name": "Pide cita sin agenda",
                "persona": "Cliente habitual",
                "first_message": "Hola, ¿me das cita para mañana por la tarde?",
                "plan": "Pide una cita y espera la respuesta.",
                "expected_state": {"escalated": True},
                "criteria": [
                    {
                        "key": "no_promise",
                        "text": "Toma los datos y pasa la cita al equipo, sin prometer hora.",
                    }
                ],
                "critical": True,
            }
        )
    return {
        "voice": {
            "tone": "Cercano y claro",
            "languages": ["es"],
            **({"register": "usted"} if _USTED.search(text) else {}),
        },
        "goal": "Que cada persona que escribe salga con lo que necesita, o con alguien del equipo.",
        "instructions": [
            {"title": "Qué haces", "body": request.description},
            {
                "title": "Cómo atiendes",
                "body": "Responde en frases cortas. Usa solo los datos de la ficha "
                "del negocio. Si no sabes algo, dilo y ofrece pasar la consulta al equipo.",
            },
        ],
        "procedures": procedures,
        "tools": list(dict.fromkeys(tools)),
        "escalation": {
            "triggers": ["asks_for_human", "failed_attempts", "complaint"],
            "failed_attempts": 2,
            "message": "Te paso con alguien del equipo, enseguida te escriben.",
        },
        "rules": ["No inventes precios, horarios ni direcciones: usa la ficha del negocio."],
        "questions": questions,
        "discarded": discarded,
        "tests": tests[:CASE_TESTS],
    }


# ── el trabajo ──────────────────────────────────────────────────────────────


def summarize_block(key: str, spec: AgentSpec, draft: Draft) -> dict[str, Any]:
    """Lo que la pantalla pinta de cada bloque mientras llega (17.3)."""
    doc = dump(spec)
    if key == "tests":
        return {"key": key, "count": len(draft.tests)}
    if key == "questions":
        return {"key": key, "count": len(draft.questions), "discarded": draft.discarded["count"]}
    if key == "skills":
        return {"key": key, "value": doc.get("skills", []), "connect": draft.connect}
    return {"key": key, "value": doc.get(key)}


async def _partner_of(session: AsyncSession) -> uuid.UUID | None:
    from nexus_api.db.models import PartnerTenant

    found: uuid.UUID | None = await session.scalar(
        sa.select(PartnerTenant.partner_id).where(
            PartnerTenant.tenant_id == require_current_tenant()
        )
    )
    return found


async def build_agent_draft(
    *,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    request: DraftRequest,
    complete: Complete | None,
    progress: Progress,
    actor: str,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> dict[str, Any]:
    """El trabajo entero. ``complete=None`` usa el generador sin modelo (local).
    Devuelve el resultado del trabajo; lanza :class:`BuilderUnavailable` si no hay
    borrador que enseñar."""
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.services.router_catalog import default_model_policy

    sm = sessionmaker or get_sessionmaker()
    await progress(step="reading")
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        ctx = await load_context(session, partner_id=await _partner_of(session))
        facts = await _business_facts(session)
        model_policy = await default_model_policy(session)
        guide = await guides_resolve.for_client(session)

    await progress(step="writing")
    # 58.4: sin guía del sector, primero la del cliente, solo con su etiqueta.
    guide = await ensure_client_guide(sm, tenant_id, guide, complete=complete, job_id=job_id)
    roles = roles_for(request.description)
    if complete is None:
        raw = offline_output(request, facts, ctx, guide=guide)
    else:
        try:
            text = await complete(build_messages(request, facts, ctx, guide=guide, roles=roles))
        except BuilderUnavailable:
            raise
        except Exception as exc:  # el proveedor no respondió
            raise BuilderUnavailable("provider_failed") from exc
        raw = parse_output(text)
    draft = sanitize(raw, request, ctx, facts, model_policy=model_policy)

    for key in BLOCKS:
        await progress(step="writing", block=summarize_block(key, draft.spec, draft))

    from nexus_api.services.agents import AgentError

    try:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            agent_id = await write_new_agent(
                session, draft, actor=actor, job_id=job_id, guide=guide
            )
    except AgentError as exc:  # el nombre se ocupó mientras se construía
        raise DraftInputInvalid(exc.code) from exc
    log.info(
        "builder.job",
        tenant_id=str(tenant_id),
        agent_id=str(agent_id),
        job_id=str(job_id),
        kind="agent_draft",
        status="done",
        validator_errors=0,
    )
    return {
        "agent_id": str(agent_id),
        "questions": draft.questions,
        "discarded": draft.discarded,
        "connect": draft.connect,
        "dropped_tools": draft.dropped_tools,
        # 65.4: «No tenemos herramienta para: …» (contracts/console-api.md §11).
        "missing_capabilities": draft.missing,
        "sector_guide": _guide_summary(guide),
        "roles": roles,
        "blocks": list(BLOCKS),
        "tests": {"case": len(draft.tests)},
        # 15.9: el registro de cada uso, resumido; nunca la descripción entera.
        "log": {
            "input": {"name": request.name, "description_chars": len(request.description)},
            "decision": "draft_written",
        },
    }


async def _business_facts(session: AsyncSession) -> Facts:
    """La ficha para un agente que aún no existe: atiende todos los servicios.

    Una ficha incompleta no impide construir (``load_facts`` la lee como esté);
    una que no se puede leer, sí (65.12): :class:`FactsUnavailable`, nunca un
    borrador sobre una ficha vacía."""
    from nexus_api.db.models import Agent
    from nexus_api.services.business import compilation

    probe = Agent(id=uuid.uuid4(), tenant_id=require_current_tenant(), name="·")
    probe.serves_all_services = True
    try:
        return await compilation.load_facts(session, probe)
    except Exception as exc:
        log.warning("builder.facts_unavailable", error=type(exc).__name__)
        raise FactsUnavailable() from exc


def _guide_summary(guide: ResolvedGuide | None) -> dict[str, Any] | None:
    if guide is None:
        return None
    return {"source": guide.source, "label": guide.label}


async def ensure_client_guide(
    sm: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    guide: ResolvedGuide | None,
    *,
    complete: Complete | None,
    job_id: uuid.UUID | None,
) -> ResolvedGuide | None:
    """Si el sector del cliente no tiene guía (``missing``), la genera **para ese
    cliente** con su etiqueta y la guía genérica (58.4, ``guides/generated.py``) y
    la guarda; si ya la tiene, la devuelve tal cual."""
    if guide is None or guide.source != "missing":
        return guide
    built, tests, from_model = await guides_generated.generate(guide.label, complete)
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = await guides_generated.store(
            session, label=guide.label, guide=built, tests=tests, job_id=job_id
        )
        resolved = await guides_resolve.for_client(session)
    log.info(
        "builder.guide_generated",
        tenant_id=str(tenant_id),
        guide_id=str(row.id),
        label_key=row.label_key,
        from_model=from_model,
    )
    return resolved


async def write_new_agent(
    session: AsyncSession,
    draft: Draft,
    *,
    actor: str,
    job_id: uuid.UUID | None,
    guide: ResolvedGuide | None = None,
) -> uuid.UUID:
    """El agente nace con su primer borrador (17.2): la versión ``staged`` con el
    AgentSpec y el prompt compilado, y la suite con las pruebas del caso y las del
    sector (la guía resuelta del cliente: de Auphere o generada para él)."""
    from nexus_api.db.models import Job
    from nexus_api.services import agents as agent_service
    from nexus_api.services.agent_config_service import AgentConfigService
    from nexus_api.services.agent_spec.legacy import runtime_model_policy
    from nexus_api.services.business.compilation import load_facts
    from nexus_api.services.testing.sector_catalog import add_sector_tests
    from nexus_api.services.testing.suites import ensure_suite, replace_case_tests

    tenant_id = require_current_tenant()
    agent = await agent_service.create_agent(
        session, tenant_id, name=draft.spec.identity.name, actor=actor
    )
    facts = await load_facts(session, agent)
    prompt = compile_spec(draft.spec, facts)
    policies: dict[str, Any] = {}
    runtime_policy = runtime_model_policy(draft.spec)
    if runtime_policy is not None:
        policies["model_policy"] = runtime_policy
    # 65.4: lo que el constructor dejó fuera por no tenerlo, para el borrador
    # (las promesas del AgentSpec se calculan al leerlo).
    policies[BUILDER_POLICY] = {"missing_capabilities": draft.builder_missing}
    service = AgentConfigService(session)
    cfg = await service.stage_new_version(
        actor=actor,
        system_prompt_rendered=prompt,
        channels=[],
        tools=list(draft.spec.tools or []),
        policies=policies,
        agent_id=agent.id,
        note="Borrador del constructor",
    )
    suite = await ensure_suite(session, agent.id)
    await replace_case_tests(session, suite, draft.tests)
    # 21.1 y 58.4: las 12 del sector del cliente, de su guía. 65.8: las que
    # necesitan una acción que sus herramientas no hacen, «No aplica».
    await add_sector_tests(session, suite, guide=guide, tools=list(draft.spec.tools or []))
    cfg.spec = {
        **dump(draft.spec),
        "test_suite": {"suite_id": str(suite.id), "revision": suite.revision},
    }
    if job_id is not None:
        await session.execute(
            sa.update(Job)
            .where(Job.tenant_id == tenant_id, Job.id == job_id)
            .values(agent_id=agent.id)
        )
    await session.flush()
    return agent.id


# ── «Desde una plantilla» (58.6) ────────────────────────────────────────────


def _template_description(display_name: str, tools: list[str]) -> str:
    """Lo que hace un agente de esa plantilla, en palabras de negocio, cuando la
    persona no lo escribió: decide qué herramientas pide (D67). Solo dice lo que
    hacen las herramientas que el cliente tiene (65.5): sin agenda, ni una cita."""
    from nexus_api.api.console.capability_names import actions_of

    does = actions_of(tools)
    jobs = ["responde las dudas del negocio con su ficha"]
    if "book" in does:
        jobs.append("da citas")
    if "modify_booking" in does:
        jobs.append("cambia y cancela citas")
    if any(t.startswith(("woocommerce.", "catalog.")) for t in tools):
        jobs.append("vende los productos del catálogo")
    if any(t.startswith("billing.") for t in tools):
        jobs.append("recuerda los pagos pendientes")
    if any(t.startswith("inventory.") for t in tools):
        jobs.append("consulta las existencias")
    return f"Agente de {display_name} por WhatsApp: " + ", ".join(jobs) + "."


async def draft_from_template(
    session: AsyncSession,
    *,
    template_id: str,
    name: str,
    description: str | None,
    actor: str,
) -> uuid.UUID:
    """«Empezar desde una plantilla» como el constructor (58.6): un AgentSpec
    estructurado salido de la guía del sector de la plantilla y de sus herramientas
    (las que este cliente tiene, D67), con las pruebas del caso y las del sector del
    cliente. Sin modelo: es la alternativa cuando el constructor no responde (15.8).
    Dentro de la transacción del cliente. ``SeedTemplateNotFound`` si no existe."""
    from nexus_api.services.builder.guides.catalog import (
        auphere_guide,
        generic_guide,
        template_tools,
    )
    from nexus_api.services.builder.guides.schema import label_key
    from nexus_api.services.builder.sectors import OTHER, TEMPLATE_SECTOR
    from nexus_api.services.router_catalog import default_model_policy
    from nexus_api.services.templating.seed_templates import load_seed_template

    template = load_seed_template(template_id)
    ctx = await load_context(session, partner_id=await _partner_of(session))
    facts = await _business_facts(session)
    # 65.2: de la plantilla, solo lo que el cliente tiene disponible; la
    # descripción no promete lo que no podrá hacer.
    available = set(ctx.available_tools())
    hint = [t for t in template_tools((template_id,)) if t in available]
    text = (description or "").strip()
    if len(text) < DESCRIPTION_MIN:
        text = _template_description(template.display_name or template_id, hint)
    request = DraftRequest.clean(name, text[:DESCRIPTION_MAX])
    model_policy = await default_model_policy(session)
    found = auphere_guide(TEMPLATE_SECTOR.get(template_id, OTHER)) or generic_guide()
    template_guide = ResolvedGuide(
        source="template", label=found.label, label_key=label_key(found.label), guide=found.guide
    )
    raw = offline_output(request, facts, ctx, guide=template_guide, tools_hint=hint)
    draft = sanitize(raw, request, ctx, facts, model_policy=model_policy)
    client_guide = await guides_resolve.for_client(session)
    if client_guide is not None and client_guide.source == "missing":
        built, tests, _from_model = await guides_generated.generate(client_guide.label, None)
        await guides_generated.store(
            session, label=client_guide.label, guide=built, tests=tests, job_id=None
        )
        client_guide = await guides_resolve.for_client(session)
    return await write_new_agent(session, draft, actor=actor, job_id=None, guide=client_guide)


__all__ = [
    "AGENT_TARGETS",
    "BLOCKS",
    "BUSINESS_TARGETS",
    "CASE_TESTS",
    "MAX_QUESTIONS",
    "BuilderUnavailable",
    "Draft",
    "DraftInputInvalid",
    "DraftRequest",
    "FactsUnavailable",
    "available_lines",
    "build_agent_draft",
    "build_messages",
    "draft_from_template",
    "ensure_client_guide",
    "offline_output",
    "parse_output",
    "sanitize",
    "write_new_agent",
]
