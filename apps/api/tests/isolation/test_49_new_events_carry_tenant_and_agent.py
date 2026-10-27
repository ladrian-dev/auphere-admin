"""Garantía 6 — los eventos nuevos llevan cliente y agente, y ningún texto
(spec 047, T018 · requisitos 56.6 y 40.9).

El catálogo es ``contracts/events.md`` §5: cada evento con sus campos. Este test
**lee el catálogo del contrato** —no una lista copiada aquí— y **barre el código
de producto** con ``ast`` buscando dónde se emite cada evento. Por cada emisión:

1. lleva ``tenant_id`` como argumento explícito (no basta el contexto de
   structlog: los consumidores del worker emiten fuera de una petición);
2. los siete eventos de la 047 —``llm.route_decision``, ``builder.job``,
   ``suite.run``, ``gate.decision``, ``wallet.transfer``,
   ``channel.echo_takeover`` y ``reception.handoff``— llevan además ``agent_id``;
3. no lleva ningún campo que pueda llevar texto de mensajes, cuerpos de
   herramientas o teléfonos, ni ningún campo que el contrato no declare;
4. el nombre del evento aparece como literal en la llamada (o en una constante
   del módulo): una emisión que el barrido no puede leer es roja.

Hoy ninguno de esos eventos se emite todavía, así que el barrido no encuentra
emisiones; cada uno entra en el test el día que alguien lo escriba en el código.
El control de abajo comprueba que el escáner sí ve las emisiones reales de
otros eventos y que señala una emisión mala.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = [pytest.mark.isolation]

ROOT = Path(__file__).resolve().parents[4]
EVENTS_MD = ROOT / "specs" / "047-la-fabrica-de-agentes" / "contracts" / "events.md"
SOURCE_ROOTS = tuple(ROOT / "apps" / part / "src" for part in ("api", "worker", "mcp", "channels"))

#: Los siete de la tarea T018 (requisito 56.6): llevan cliente Y agente.
NEEDS_AGENT = frozenset(
    {
        "llm.route_decision",
        "builder.job",
        "suite.run",
        "gate.decision",
        "wallet.transfer",
        "channel.echo_takeover",
        "reception.handoff",
    }
)
#: Campos que pueden llevar texto de un mensaje, de una herramienta o un teléfono.
FORBIDDEN_FIELDS = frozenset(
    {
        "text",
        "body",
        "content",
        "message",
        "messages",
        "user_message",
        "response",
        "reply",
        "prompt",
        "transcript",
        "args",
        "arguments",
        "tool_args",
        "tool_result",
        "result",
        "payload",
        "phone",
        "customer_phone",
        "from_number",
        "to_number",
        "wa_id",
    }
)
_LOG_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "msg", "log"}
)


def catalog() -> dict[str, frozenset[str]]:
    """Evento → campos declarados, leídos de la tabla de ``events.md`` §5."""
    text = EVENTS_MD.read_text(encoding="utf-8")
    section = re.search(r"^## 5\..*?$(.*?)^## ", text, re.MULTILINE | re.DOTALL)
    assert section, "no encuentro la sección 5 de events.md"
    events: dict[str, frozenset[str]] = {}
    for row in re.finditer(r"^\|\s*`([a-z_]+\.[a-z_]+)`\s*\|(.*)\|\s*$", section.group(1), re.M):
        # Lo que va entre paréntesis son valores o formas, no campos.
        fields = re.sub(r"\([^)]*\)", "", row.group(2))
        events[row.group(1)] = frozenset(re.findall(r"`([a-z_]+)`", fields))
    return events


@dataclass(frozen=True)
class Emission:
    where: str
    event: str
    fields: frozenset[str]
    dynamic: bool  # ``**kwargs``: el barrido no puede saber qué lleva


def scan_source(source: str, where: str, events: set[str]) -> tuple[list[Emission], list[str]]:
    """Las emisiones de ``events`` en un módulo, y los usos del nombre que no son
    una emisión legible."""
    tree = ast.parse(source)
    # ``ROUTE = "llm.route_decision"`` al nivel del módulo: el literal cuenta
    # como emitido solo si alguna llamada de log usa ese nombre.
    constants: dict[str, tuple[str, ast.Constant]] = {
        t.id: (node.value.value, node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and node.value.value in events
        for t in node.targets
        if isinstance(t, ast.Name)
    }
    emissions: list[Emission] = []
    consumed: set[int] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LOG_METHODS
            and node.args
        ):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and first.value in events:
            event = first.value
            consumed.add(id(first))
        elif isinstance(first, ast.Name) and first.id in constants:
            event, literal = constants[first.id]
            consumed.add(id(literal))
        else:
            continue
        emissions.append(
            Emission(
                where=f"{where}:{node.lineno}",
                event=event,
                fields=frozenset(k.arg for k in node.keywords if k.arg),
                dynamic=any(k.arg is None for k in node.keywords),
            )
        )
    stray = [
        f"{where}:{node.lineno} «{node.value}»"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in events and id(node) not in consumed
    ]
    return emissions, stray


def sweep(events: set[str]) -> tuple[list[Emission], list[str]]:
    emissions: list[Emission] = []
    stray: list[str] = []
    for root in SOURCE_ROOTS:
        for path in root.rglob("*.py"):
            found, odd = scan_source(
                path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)), events
            )
            emissions += found
            stray += odd
    return emissions, stray


def violations(emissions: list[Emission], declared: dict[str, frozenset[str]]) -> list[str]:
    out: list[str] = []
    for e in emissions:
        if e.dynamic:
            out.append(f"{e.where} {e.event}: emite **kwargs; el contrato no se puede comprobar")
        if "tenant_id" not in e.fields:
            out.append(f"{e.where} {e.event}: sin tenant_id")
        if e.event in NEEDS_AGENT and "agent_id" not in e.fields:
            out.append(f"{e.where} {e.event}: sin agent_id")
        leaked = sorted(e.fields & FORBIDDEN_FIELDS)
        if leaked:
            out.append(f"{e.where} {e.event}: campos que llevan texto o teléfonos {leaked}")
        undeclared = sorted(e.fields - declared[e.event] - {"tenant_id", "agent_id"})
        if undeclared:
            out.append(f"{e.where} {e.event}: campos fuera de events.md §5 {undeclared}")
    return out


# ── los tests ───────────────────────────────────────────────────────────────


def test_the_catalog_is_read_from_the_contract() -> None:
    events = catalog()
    missing = sorted(NEEDS_AGENT - events.keys())
    assert not missing, f"eventos de la 047 que no están en events.md §5: {missing}"
    assert {"turn_id", "job_id", "chosen", "cost_micros"} <= events["llm.route_decision"]
    assert "open" not in events["inbound.persisted"], "se coló un valor como campo"


def test_every_emission_of_a_catalog_event_honours_the_contract() -> None:
    declared = catalog()
    emissions, stray = sweep(set(declared))
    assert not stray, f"el nombre de un evento aparece fuera de una emisión legible: {stray}"
    bad = violations(emissions, declared)
    assert not bad, "eventos de events.md §5 que rompen la garantía 6:\n" + "\n".join(
        f"  - {b}" for b in bad
    )


def test_the_route_decision_is_emitted_and_honours_the_contract() -> None:
    """T141: el router ya registra cada decisión (requisito 40.9). La emisión
    existe, lleva cliente y agente, y nada que no declare ``events.md`` §5."""
    declared = catalog()
    emissions, stray = sweep({"llm.route_decision"})
    assert emissions, "nadie emite llm.route_decision"
    assert not stray, stray
    assert not violations(emissions, declared)
    for e in emissions:
        assert {"tenant_id", "agent_id", "task", "chosen", "candidates_rejected"} <= e.fields, e


def test_the_route_decision_names_its_conversation() -> None:
    """C3 (T140): el grafo pasa la conversación a la decisión; ``events.md`` §5
    la pide y el transporte la emite."""
    emissions, _ = sweep({"llm.route_decision"})
    assert emissions
    assert all({"conversation_id", "agent_version", "decision_id"} <= e.fields for e in emissions)


#: Lo que el grafo registra del router (C3, T140). No están en §5 —son avisos
#: operativos, no el registro de la decisión—, pero tampoco llevan texto y
#: dicen de qué cliente son.
ROUTER_GRAPH_EVENTS = frozenset(
    {
        "router.anomaly",
        "router.anomaly_not_recorded",
        "router.escalation",
        "router.escalation_failed",
        "router.profile_missing",
        "classify.no_model",
        "classify.routed_failed",
    }
)


def test_the_router_events_of_the_graph_carry_the_client_and_no_text() -> None:
    path = ROOT / "apps" / "worker" / "src" / "nexus_worker" / "runtime" / "pipeline.py"
    emissions, _ = scan_source(
        path.read_text(encoding="utf-8"), "pipeline.py", set(ROUTER_GRAPH_EVENTS)
    )
    assert {e.event for e in emissions} == ROUTER_GRAPH_EVENTS, "el barrido no ve las emisiones"
    for e in emissions:
        assert not e.dynamic, e
        assert "tenant_id" in e.fields, f"{e.where} {e.event}: sin tenant_id"
        assert not e.fields & FORBIDDEN_FIELDS, (
            f"{e.where} {e.event}: {e.fields & FORBIDDEN_FIELDS}"
        )
    for e in emissions:
        if e.event in {"router.anomaly", "router.escalation"}:
            assert "agent_id" in e.fields, f"{e.where} {e.event}: sin agent_id"


def test_the_scanner_reads_real_emissions() -> None:
    """Control: con un evento que el código sí emite, el barrido lo encuentra con
    sus campos (``llm.call_complete``, en el transporte del worker)."""
    emissions, _ = sweep({"llm.call_complete"})
    assert emissions, "el escáner no ve una emisión que existe"
    assert any({"tenant_id", "model"} <= e.fields for e in emissions)


def test_the_rules_catch_a_bad_emission() -> None:
    """Control: el mismo ``violations`` señala cada defecto de una emisión mala."""
    source = (
        "ROUTE = 'llm.route_decision'\n"
        "log.info(ROUTE, tenant_id=t, chosen=d, text=user_message, model_notes=n)\n"
        "log.info('builder.job', job_id=j, **extra)\n"
        "span = tracer.start_span('suite.run')\n"
    )
    declared = catalog()
    emissions, stray = scan_source(source, "probe.py", set(declared))
    assert stray == ["probe.py:4 «suite.run»"]
    found = violations(emissions, declared)
    assert any("llm.route_decision: sin agent_id" in v for v in found)
    assert any("['text']" in v for v in found)
    assert any("['model_notes', 'text']" in v for v in found)
    assert any("builder.job: emite **kwargs" in v for v in found)
    assert any("builder.job: sin tenant_id" in v for v in found)
