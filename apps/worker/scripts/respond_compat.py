"""La batería de compatibilidad contra los proveedores reales — spec 065, T055 (research.md §D9.2).

Llama de verdad a OpenAI y a Anthropic (< US$ 1 la pasada completa). **Solo a mano y solo en
staging** (T064): se niega a correr con ``--env prod`` antes de importar nada que pueda llamar
a un proveedor.

    cd apps/worker && uv run python scripts/respond_compat.py --env staging --models all

Cada turno es el de producción: el manejador de ``pipeline.py`` con ``LLMRouter`` y
``LiteLLMProvider`` reales, un agente de prueba con tres herramientas simuladas (historial,
huecos y reserva, que no tocan ninguna base) y los seis modelos habilitados en el catálogo del
proceso, para que la reserva de la otra familia entre como entraría habilitada. Corre en modo
estricto: ``prefix_mismatch_behavior = "error"``, así que cualquier cambio de lo ya enviado a
mitad de turno es un 400 visible y no un bloque descartado en silencio (research.md §D4.3).

Escenarios por modelo (requisito 4.9):

- ``no_tools``: una respuesta sin herramientas;
- ``three_tools``: una cadena de tres herramientas (historial, huecos, reserva);
- ``image``: un mensaje con una imagen;
- ``switch_between_turns``: el turno anterior lo respondió la otra familia;
- ``fallback_mid_turn``: la segunda llamada del modelo falla y la reserva termina el turno
  (con los seis, cubre las dos direcciones);
- ``cross_after_tools``: GPT-5.6 llama a una herramienta, cae, y Sonnet 5.5 sigue con el
  razonamiento apagado (solo modelos de OpenAI);
- ``booking_brake_retry``: el freno de reservas para el primer borrador y el turno reintenta.
  En modo estricto también dice si la nota del freno, que LiteLLM sube al ``system`` como un
  bloque al final, cuenta como edición para Anthropic;
- ``long_turn_to_close``: las herramientas no encuentran nada y el turno llega al cierre.

Y tres hechos del proveedor que el servidor de eco no puede probar:

- ``openai_cache_write_reported``: GPT-5.6 devuelve
  ``usage.prompt_tokens_details.cache_write_tokens`` por Chat Completions a través de LiteLLM;
- ``prompt_tokens_include_writes``: ``prompt_tokens`` incluye lo escrito en caché;
- ``cache_marker_is_not_an_edit``: la caché hacia Claude (la marca del ``system`` y el
  ``cache_control`` de arriba) no dispara el control de historial en modo estricto.

El informe da, por modelo, el resultado de cada escenario, el p95 de las llamadas, el coste
(con el mapa de LiteLLM fijado por la puerta) y el factor de gasto frente a Sol. Va a la
salida estándar en Markdown y, con ``--report``, en JSON. Se anota en quickstart.md §3.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Donde puede correr. Prod no está, y se rechaza con nombre propio.
ENVIRONMENTS = ("local", "staging")
REFUSED_ENV = "prod"

SOL = "openai/gpt-5.6-sol"
SCENARIOS = (
    "no_tools",
    "three_tools",
    "image",
    "switch_between_turns",
    "fallback_mid_turn",
    "cross_after_tools",
    "booking_brake_retry",
    "long_turn_to_close",
)
PROVIDER_FACTS = (
    "openai_cache_write_reported",
    "prompt_tokens_include_writes",
    "cache_marker_is_not_an_edit",
)
#: Lo que solo tiene sentido en una familia.
ONLY_FOR: dict[str, str] = {
    "cross_after_tools": "openai",
    "openai_cache_write_reported": "openai",
    "cache_marker_is_not_an_edit": "anthropic",
}


def _six() -> tuple[str, ...]:
    from nexus_api.core.respond_profiles import PROFILES

    return tuple(PROFILES)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="respond_compat.py",
        description="Batería de compatibilidad contra los proveedores reales (spec 065).",
    )
    parser.add_argument("--env", required=True, help="staging o local; nunca prod")
    parser.add_argument("--models", default="all", help="all o ids separados por comas")
    parser.add_argument(
        "--scenarios", default="all", help="all o escenarios y hechos separados por comas"
    )
    parser.add_argument("--report", type=Path, default=None, help="JSON con el resultado")
    args = parser.parse_args(argv)
    if args.env == REFUSED_ENV:
        parser.exit(
            2,
            "respond_compat.py: se niega a correr con --env prod. La batería real va en "
            "staging (T064); en prod solo el humo de T065, con el sí de Luis.\n",
        )
    if args.env not in ENVIRONMENTS:
        parser.error(f"--env {args.env!r}: usa uno de {', '.join(ENVIRONMENTS)}")
    six = _six()
    models = six if args.models == "all" else tuple(m.strip() for m in args.models.split(","))
    unknown = [m for m in models if m not in six]
    if unknown or not models:
        parser.error(f"--models: sin perfil de respuesta {unknown}; los seis son {list(six)}")
    known = (*SCENARIOS, *PROVIDER_FACTS)
    chosen = (
        known if args.scenarios == "all" else tuple(s.strip() for s in args.scenarios.split(","))
    )
    bad = [s for s in chosen if s not in known]
    if bad or not chosen:
        parser.error(f"--scenarios: desconocidos {bad}; existen {list(known)}")
    args.models = models
    args.scenarios = chosen
    return args


def family_of(model: str) -> str:
    return "anthropic" if model.startswith("anthropic/") else "openai"


def plan(models: Sequence[str], scenarios: Sequence[str]) -> list[tuple[str, str]]:
    """``(modelo, escenario)`` que se corren: cada escenario solo donde tiene sentido."""
    return [
        (model, scenario)
        for model in models
        for scenario in scenarios
        if ONLY_FOR.get(scenario, family_of(model)) == family_of(model)
    ]


def p95(values: Sequence[float]) -> float | None:
    """El percentil 95 por rango más cercano; ``None`` sin datos."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def spend_factor(costs: dict[str, float], model: str, baseline: str = SOL) -> float | None:
    """Lo que gastó ``model`` frente a Sol en los mismos escenarios (estimate_factor, §D14)."""
    base = costs.get(baseline)
    if not base or model not in costs:
        return None
    return round(costs[model] / base, 3)


# ── la pasada ──────────────────────────────────────────────────────────────


@dataclass
class Outcome:
    model: str
    scenario: str
    ok: bool
    detail: str = ""
    calls: list[dict[str, Any]] = field(default_factory=list)


#: Cada llamada que sale a LiteLLM: modelo, latencia, uso y coste.
CALLS: list[dict[str, Any]] = []
TOOLS = ("client.get_history", "booking.check_availability", "booking.create_appointment")
TENANT = uuid.UUID("00000000-0000-0000-0000-000000065c0a")
AGENT = uuid.UUID("00000000-0000-0000-0000-000000065a9e")
PIXEL = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _install_recorder() -> None:
    from nexus_api.core.litellm_map import litellm_module

    litellm = litellm_module()
    real = litellm.acompletion

    async def recorded(**kwargs: Any) -> Any:
        started = time.perf_counter()
        entry: dict[str, Any] = {
            "model": kwargs.get("model"),
            "tool_choice": kwargs.get("tool_choice"),
        }
        try:
            response = await real(**kwargs)
        except Exception as exc:
            entry.update(error=f"{type(exc).__name__}: {str(exc)[:300]}")
            raise
        finally:
            entry["elapsed_s"] = round(time.perf_counter() - started, 3)
            CALLS.append(entry)
        usage = getattr(response, "usage", None)
        entry["usage"] = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage or {})
        try:
            entry["cost_usd"] = float(litellm.completion_cost(completion_response=response))
        except Exception:
            entry["cost_usd"] = None
        return response

    litellm.acompletion = recorded


def _enable_the_six() -> None:
    """La pasada decide si se habilitan: aquí se comportan como habilitados."""
    from nexus_api.core import respond_catalog
    from nexus_api.core.respond_profiles import PROFILES

    rows = [
        {
            "model_id": m,
            "status": "active",
            "offer_label": m,
            "price_input_per_mtok": 1,
            "respond_enabled_at": "respond_compat",
        }
        for m in PROFILES
    ] + [
        {"model_id": m, "status": "active", "offer_label": None, "price_input_per_mtok": 1}
        for m in respond_catalog.BOOT_HOP_MODEL_IDS
        if m not in PROFILES
    ]
    respond_catalog.refresh_from_rows(rows)


def _simulate_the_world(*, nothing_free: bool, brake_first: bool) -> None:
    """El agente de prueba: herramientas simuladas, sin base, sin Composio, sin cobro."""
    from nexus_api.services.activations import ToolPolicy

    import nexus_worker.runtime.pipeline as pipeline
    from nexus_worker.runtime import booking_brake

    async def nothing(*_a: Any, **_k: Any) -> Any:
        return ""

    async def no_history(*_a: Any, **_k: Any) -> list[dict[str, str]]:
        return []

    async def no_knowledge(*_a: Any, **_k: Any) -> tuple[str, list[Any]]:
        return "", []

    async def no_gates(_tenant: Any) -> frozenset[str]:
        return frozenset()

    async def policy(*_a: Any, **_k: Any) -> Any:
        return ToolPolicy(closed=True)

    async def dispatch(_registry: Any, call: Any, _available: Any, intent: str, **_k: Any) -> Any:
        if call.name == "booking.check_availability":
            result: dict[str, Any] = (
                {"slots": [], "note": "Ese día no hay huecos; prueba otro."}
                if nothing_free
                else {"slots": ["martes 10:00", "martes 12:00"]}
            )
        elif call.name == "booking.create_appointment":
            result = {"appointment_id": "SIM-1", "status": "booked", "args": call.arguments}
        else:
            result = {"visits": 2, "last_service": "corte"}
        return {"tool": call.name, "intent": intent, "status": "ok", "result": result}

    brakes = [True] if brake_first else []

    async def claim(*_a: Any, **_k: Any) -> bool:
        return brakes.pop(0) if brakes else False

    async def record_brake(**_k: Any) -> None:
        return None

    pipeline._load_recent_history = no_history  # type: ignore[assignment]
    pipeline._load_kg_snapshot_text = nothing  # type: ignore[assignment]
    pipeline._load_knowledge = no_knowledge  # type: ignore[assignment]
    pipeline._load_gated_tools = no_gates  # type: ignore[assignment]
    pipeline._load_tool_policy = policy  # type: ignore[assignment]
    pipeline._dispatch_tool = dispatch  # type: ignore[assignment]
    booking_brake.unbacked_claim = claim  # type: ignore[assignment]
    booking_brake.record_brake = record_brake  # type: ignore[assignment]


class _Faulty:
    """``LiteLLMProvider`` que hace fallar las llamadas ``fail[model]`` (1, 2, … por intento)
    con un 503 simulado: la caída que la reserva tiene que cubrir."""

    def __init__(self, inner: Any, fail: dict[str, set[int]]) -> None:
        self.inner = inner
        self.fail = fail
        self.seen: dict[str, int] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    async def acomplete_with_tools(self, **kwargs: Any) -> Any:
        model = kwargs["model"]
        self.seen[model] = self.seen.get(model, 0) + 1
        if self.seen[model] in self.fail.get(model, set()):
            raise type("ServiceUnavailableError", (Exception,), {})(f"{model}: caída simulada")
        return await self.inner.acomplete_with_tools(**kwargs)


def _router(fail: dict[str, set[int]] | None = None) -> Any:
    from nexus_worker.runtime.llm import LiteLLMProvider, LLMRouter

    provider: Any = LiteLLMProvider()
    if fail:
        provider = _Faulty(provider, fail)
    return LLMRouter(
        provider=provider,
        classify_model="anthropic/claude-haiku-5-5",
        respond_model=SOL,
        fallback_model=SOL,
        # Modo estricto: una edición de lo enviado es un error visible (§D4.3, §D9.2).
        prefix_mismatch_behavior="error",
    )


class _Loader:
    def __init__(self, bundle: Any) -> None:
        self.bundle = bundle

    async def load(self, _tenant: Any, _agent: Any = None) -> Any:
        return self.bundle


def _registry() -> Any:
    from nexus_mcp import MCPRegistry

    class Registry(MCPRegistry):  # type: ignore[misc]
        def get_openai_tools(self, names: Any) -> list[dict[str, Any]]:
            described = {
                "client.get_history": "Historial de visitas del cliente.",
                "booking.check_availability": "Huecos libres de un día (YYYY-MM-DD o 'martes').",
                "booking.create_appointment": "Reserva una cita en un hueco libre.",
            }
            return [
                {
                    "type": "function",
                    "function": {
                        "name": n,
                        "description": described.get(n, n),
                        "parameters": {
                            "type": "object",
                            "properties": {"dia": {"type": "string"}, "hora": {"type": "string"}},
                        },
                    },
                }
                for n in names
            ]

        def is_side_effecting(self, name: str) -> bool:
            return False

        def names(self) -> tuple[str, ...]:
            return TOOLS

    return Registry()


async def _turn(
    model: str,
    message: Any,
    *,
    history: Sequence[dict[str, str]] = (),
    fail: dict[str, set[int]] | None = None,
    nothing_free: bool = False,
    brake_first: bool = False,
) -> dict[str, Any]:
    import nexus_worker.runtime.pipeline as pipeline
    from nexus_worker.runtime.agent_loader import AgentBundle

    _simulate_the_world(nothing_free=nothing_free, brake_first=brake_first)
    bundle = AgentBundle(
        tenant_id=TENANT,
        version=1,
        version_id=uuid.uuid4(),
        system_prompt=(
            "Eres la recepción de una peluquería de prueba. Usa tus herramientas para mirar "
            "el historial, los huecos y reservar. Contesta corto."
        ),
        tools=frozenset(TOOLS),
        policies={},
        agent_id=AGENT,
        respond_model=model,
        respond_model_set_by="operator",
    )
    state = {
        "tenant_id": str(TENANT),
        "agent_id": str(AGENT),
        "conversation_id": str(uuid.uuid4()),
        "inbound_message_id": str(uuid.uuid4()),
        "customer_id": str(uuid.uuid4()),
        "channel_type": "whatsapp",
        "user_message": message,
        "history": list(history),
        "intent": "book",
        "classification": {},
        "router_turn": {},
    }
    handler = pipeline.make_handler_node("book", _Loader(bundle), _router(fail), _registry())
    out: dict[str, Any] = await handler(state)  # type: ignore[arg-type]
    return out


def _answered(out: dict[str, Any]) -> str:
    if out.get("turn_failure"):
        return f"turn_failure={out['turn_failure']}"
    if not str(out.get("response") or "").strip():
        return "sin texto"
    return ""


def problem_of(out: dict[str, Any], model: str) -> str:
    """Lo que falla en un turno que tenía que responder ``model`` él mismo (T100).

    No basta con que el turno tenga respuesta: la primera pasada real dio en verde a los tres
    de Claude cuando todas sus llamadas con herramientas habían recibido un 400 y había
    respondido Terra, su reserva."""
    problem = _answered(out)
    if problem:
        return problem
    served = out.get("response_model")
    if served != model or out.get("response_fell_back"):
        return f"respondió {served}, no {model}"
    return ""


def fact_prompt() -> str:
    """Un prompt que nadie ha dejado en caché, por encima del mínimo de cualquiera de los seis
    (1.024 y 4.096 tokens). Lo distinto va al principio, porque la caché es por prefijo: con
    el mismo prompt, la segunda comprobación leía lo que había escrito la primera."""
    return (
        f"Pasada {uuid.uuid4().hex}. Eres la recepción de una peluquería de prueba. "
        + "Regla de la casa. " * 1500
    )


def _chosen_answered_once(model: str, since: int) -> bool:
    """¿El modelo elegido contestó alguna llamada del turno antes de caer?"""
    return any(c.get("model") == model and "error" not in c for c in CALLS[since:])


def _reserve_of(model: str) -> str:
    from nexus_api.core.respond_profiles import profile_for

    profile = profile_for(model)
    assert profile is not None
    return profile.reserve


async def _scenario(model: str, scenario: str) -> tuple[bool, str]:
    other = "anthropic/claude-sonnet-5-5" if family_of(model) == "openai" else SOL
    if scenario == "no_tools":
        out = await _turn(model, "Hola, ¿a qué hora abrís el sábado?")
        return not problem_of(out, model), problem_of(out, model)
    if scenario == "three_tools":
        out = await _turn(
            model,
            "Soy cliente de siempre: mira mi historial, busca hueco el martes y resérvame el "
            "primero.",
        )
        tools = len(out.get("tool_calls") or [])
        problem = problem_of(out, model) or ("" if tools >= 3 else f"{tools} herramientas")
        return not problem, problem
    if scenario == "image":
        message = [
            {"type": "text", "text": "¿Qué ves en esta imagen? Contesta en una frase."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + PIXEL}},
        ]
        out = await _turn(model, message)
        return not problem_of(out, model), problem_of(out, model)
    if scenario == "switch_between_turns":
        first = await _turn(other, "Hola, quiero una cita el martes.")
        history = [
            {"role": "user", "content": "Hola, quiero una cita el martes."},
            {"role": "assistant", "content": str(first.get("response") or "")},
        ]
        out = await _turn(model, "Mejor a las 12. ¿Puedes?", history=history)
        before = problem_of(first, other)
        problem = problem_of(out, model) or (f"turno anterior: {before}" if before else "")
        return not problem, problem
    if scenario in {"fallback_mid_turn", "cross_after_tools"}:
        mark = len(CALLS)
        out = await _turn(
            model,
            "Mira mi historial y busca hueco el martes, y resérvame el primero.",
            fail={model: {2, 3}},
        )
        served, expected = out.get("response_model"), _reserve_of(model)
        problem = _answered(out) or (
            "" if served == expected else f"respondió {served}, no {expected}"
        )
        if not problem and not _chosen_answered_once(model, mark):
            problem = f"{model} no contestó ninguna llamada antes de caer"
        if scenario == "cross_after_tools" and not out.get("tool_calls"):
            problem = problem or "GPT-5.6 no llegó a llamar a una herramienta antes de caer"
        return not problem, problem
    if scenario == "booking_brake_retry":
        out = await _turn(model, "Resérvame el martes a las 10.", brake_first=True)
        return not problem_of(out, model), problem_of(out, model)
    if scenario == "long_turn_to_close":
        out = await _turn(
            model,
            "Busca hueco el martes; si no hay, el miércoles, el jueves y el viernes.",
            nothing_free=True,
        )
        closed = any(c.get("tool_choice") == "none" for c in CALLS[-8:])
        problem = problem_of(out, model)
        return not problem, problem or ("" if closed else "(no llegó al cierre)")
    return await _provider_fact(model, scenario)


async def _provider_fact(model: str, fact: str) -> tuple[bool, str]:
    from nexus_worker.runtime.llm import LiteLLMProvider, respond_hop_extra

    provider = LiteLLMProvider()
    messages = [
        {"role": "system", "content": fact_prompt()},
        {"role": "user", "content": "Hola, ¿abrís el sábado?"},
    ]
    if fact == "cache_marker_is_not_an_edit":
        out = await _turn(model, "Mira mi historial y busca hueco el martes.")
        return not problem_of(out, model), problem_of(out, model)
    usages: list[dict[str, Any]] = []
    for _ in range(2):
        mark = len(CALLS)
        await provider.acomplete_with_tools(
            tenant_id=TENANT,
            role="respond",
            model=model,
            messages=messages,
            tools=[],
            extra=respond_hop_extra(model, None, tools=False, prefix_mismatch="error"),
        )
        usages.append(CALLS[mark]["usage"] if mark < len(CALLS) else {})
    first = usages[0]
    details = first.get("prompt_tokens_details") or {}
    written = int(
        first.get("cache_creation_input_tokens") or details.get("cache_write_tokens") or 0
    )
    if fact == "openai_cache_write_reported":
        ok = "cache_write_tokens" in details
        return ok, json.dumps(details)
    prompt = int(first.get("prompt_tokens") or 0)
    ok = written > 0 and prompt >= written
    return ok, f"prompt_tokens={prompt} escritos={written}"


async def run(args: argparse.Namespace) -> list[Outcome]:
    _install_recorder()
    _enable_the_six()
    outcomes: list[Outcome] = []
    for model, scenario in plan(args.models, args.scenarios):
        mark = len(CALLS)
        try:
            ok, detail = await _scenario(model, scenario)
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {str(exc)[:300]}"
        outcomes.append(Outcome(model, scenario, ok, detail, CALLS[mark:]))
        print(f"{'OK ' if ok else 'MAL'} {model:32} {scenario:30} {detail}", flush=True)
    return outcomes


def report(outcomes: Sequence[Outcome]) -> dict[str, Any]:
    models: dict[str, dict[str, Any]] = {}
    costs: dict[str, float] = {}
    for o in outcomes:
        entry = models.setdefault(o.model, {"scenarios": {}, "latencies": [], "cost_usd": 0.0})
        entry["scenarios"][o.scenario] = {"ok": o.ok, "detail": o.detail}
        for call in o.calls:
            if call.get("model") == o.model and "error" not in call:
                entry["latencies"].append(call["elapsed_s"])
            entry["cost_usd"] += float(call.get("cost_usd") or 0.0)
        costs[o.model] = entry["cost_usd"]
    for model, entry in models.items():
        entry["p95_s"] = p95(entry.pop("latencies"))
        entry["cost_usd"] = round(entry["cost_usd"], 5)
        entry["spend_vs_sol"] = spend_factor(costs, model)
        entry["green"] = all(s["ok"] for s in entry["scenarios"].values())
    return {"models": models, "green": all(e["green"] for e in models.values())}


def markdown(summary: dict[str, Any], render: Callable[[Any], str] = str) -> str:
    lines = [
        "| Modelo | Resultado | p95 (s) | Coste (US$) | Gasto frente a Sol |",
        "|---|---|---|---|---|",
    ]
    for model, entry in summary["models"].items():
        failed = [s for s, r in entry["scenarios"].items() if not r["ok"]]
        verdict = "verde" if entry["green"] else "rojo: " + ", ".join(failed)
        lines.append(
            f"| {model} | {verdict} | {render(entry['p95_s'])} | {render(entry['cost_usd'])} "
            f"| {render(entry['spend_vs_sol'])} |"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    import asyncio

    outcomes = asyncio.run(run(args))
    summary = report(outcomes)
    print(markdown(summary))
    if args.report is not None:
        args.report.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if summary["green"] else 1


if __name__ == "__main__":
    sys.exit(main())
