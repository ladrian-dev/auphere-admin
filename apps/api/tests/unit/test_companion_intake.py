"""El expediente del §7.1 y la garantía E1 (CO-06).

Lo que se prueba es el **motor**: que un `create_client` sin
`forbidden_behaviour` no llega a `plan` pase lo que pase, que el expediente
sobrevive al turno y no repregunta lo ya contestado, y que la puerta no se
convierte en un atasco donde el dato no tiene por dónde entrar.

Sobre `work_kind`: **el catálogo de eventos no es de este agente** (§8 del
contrato v2). En este árbol `COMPANION_EVENTS["intake.missing"]` todavía no
declara `work_kind`, así que aquí se comprueba **lo que el nodo produce**, no
lo que el publicador deja pasar. La comprobación de extremo a extremo la hace
el orquestador en la Fase 2.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from nexus_worker.runtime.companion import build_companion_graph
from nexus_worker.runtime.companion.intake import (
    SLOT_CATALOG,
    WORK_KINDS,
    blocking_slots,
    is_enforceable,
    ledger_note,
    missing_slots,
    record_answers,
    record_asked,
)
from nexus_worker.runtime.llm import InMemoryProvider, ToolCall

pytestmark = pytest.mark.unit

MODEL = "anthropic/claude-sonnet-4-6"

#: Los parámetros reales de ``console.propose_client`` (catálogo de CO-02).
#: Se copian aquí porque el doble tiene que publicar el mismo catálogo que
#: publica la herramienta de verdad: la puerta se mide contra él.
CLIENT_PARAMS = (
    "client_ref",
    "name",
    "timezone",
    "language",
    "vertical",
    "forbidden_behaviour",
)

FULL_CLIENT_ARGS = {
    "client_ref": "boreal",
    "name": "Clínica Boreal",
    "vertical": "Clínica estética",
    "timezone": "America/Caracas",
    "language": "es",
    "forbidden_behaviour": "No dar precios por WhatsApp",
}


def _spec(name: str, params: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "…",
            "parameters": {
                "type": "object",
                "properties": {p: {"type": "string"} for p in params},
            },
        },
    }


@dataclass
class FakeProposal:
    kind: str = "client"
    title: str = "Dar de alta Clínica Boreal"
    client_ref: str | None = "boreal"


@dataclass
class IntakeBelt:
    """Doble con camino de escritura y catálogo publicado.

    ``propose_when_called`` imita a la herramienta de verdad: deja la
    propuesta pendiente aunque le falten datos. Es a propósito — así el test
    mide que **el grafo** es quien para, no la herramienta.
    """

    specs_list: list[dict[str, Any]] = field(
        default_factory=lambda: [_spec("console.propose_client", CLIENT_PARAMS)]
    )
    proposals: list[FakeProposal] = field(default_factory=list)
    reported_missing: list[dict[str, Any]] = field(default_factory=list)
    staged: int = 0
    calls_made: int = 0

    @property
    def calls_left(self) -> int:
        return 25 - self.calls_made

    @property
    def reads_done(self) -> int:
        return 1

    def specs(self) -> list[dict[str, Any]]:
        return self.specs_list

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls_made += 1

        @dataclass
        class Result:
            name: str
            label: str
            ok: bool
            content: str
            latency_ms: int = 1
            error_code: str | None = None
            citation: Any = None

        return Result(name, name, True, "{}")

    # ── ActionPort ─────────────────────────────────────────────────────
    @property
    def pending(self) -> list[FakeProposal]:
        return self.proposals

    @property
    def missing_slots(self) -> list[dict[str, Any]]:
        return self.reported_missing

    def plan_steps(self) -> list[dict[str, Any]]:
        return [
            {
                "index": 1,
                "kind": p.kind,
                "tool": f"console.propose_{p.kind}",
                "title": p.title,
                "client_ref": p.client_ref,
                "reversible": False,
            }
            for p in self.proposals
        ]

    def plan_risk(self) -> str:
        return "high"

    async def stage(self, step_index: int) -> dict[str, Any] | None:
        if not self.proposals:
            return None
        self.staged += 1
        return {
            "action_id": "11111111-1111-4111-8111-111111111111",
            "kind": self.proposals[0].kind,
            "title": self.proposals[0].title,
            "preview": {"client_ref": "boreal"},
            "diff": None,
            "impact": [],
            "expires_at": "2026-08-18T14:33:00+00:00",
        }

    async def apply_confirmed(self, action_id: Any) -> Any:  # pragma: no cover
        raise AssertionError("no se aplica nada en estos tests")

    async def verify(self, action_id: Any) -> dict[str, Any] | None:  # pragma: no cover
        return None


def _graph(belt: Any) -> Any:
    return build_companion_graph(
        provider=_provider_calling(belt), model=MODEL, checkpointer=MemorySaver(), toolbelt=belt
    )


def _provider_calling(_belt: Any) -> InMemoryProvider:  # pragma: no cover - reemplazado
    return InMemoryProvider(responder=lambda _c: "ok")


def _base(**extra: Any) -> dict[str, Any]:
    return {
        "thread_id": str(uuid.uuid4()),
        "principal": {"role": "owner", "partner": "p", "permissions": []},
        "page_context": None,
        "history": [],
        "user_message": "da de alta a Clínica Boreal",
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        **extra,
    }


async def _run(
    belt: IntakeBelt,
    *,
    args: dict[str, Any],
    config: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    saver: MemorySaver | None = None,
) -> tuple[list[tuple[str, dict[str, Any]]], InMemoryProvider]:
    """Un turno donde el modelo llama a ``console.propose_client`` con ``args``.

    ``saver`` se pasa desde fuera cuando el test encadena dos turnos del
    mismo hilo: **el expediente vive en el checkpoint**, así que un
    ``MemorySaver`` nuevo por turno mediría un hilo distinto y el test
    "no repregunta" pasaría o fallaría por el banco de pruebas.
    """
    called = {"n": 0}

    def tool_caller(_call: Any) -> list[ToolCall]:
        if called["n"]:
            return []
        called["n"] += 1
        return [ToolCall(id="t1", name="console.propose_client", arguments=args)]

    provider = InMemoryProvider(responder=lambda _c: "voy a ello", tool_caller=tool_caller)
    graph = build_companion_graph(
        provider=provider, model=MODEL, checkpointer=saver or MemorySaver(), toolbelt=belt
    )
    config = config or {"configurable": {"thread_id": str(uuid.uuid4())}}
    events: list[tuple[str, dict[str, Any]]] = []
    async for ev in graph.astream_events(state or _base(), config=config, version="v2"):
        if ev.get("event") == "on_custom_event":
            events.append((str(ev.get("name")), dict(ev.get("data") or {})))
    return events, provider


# ── E1 · el campo que causa los incidentes ─────────────────────────────


async def test_a_client_without_forbidden_behaviour_never_reaches_plan() -> None:
    """**Garantía E1.** Falla en el MOTOR: la herramienta deja la propuesta
    pendiente igual, y aun así no se persiste nada ni se pide confirmar."""
    belt = IntakeBelt(proposals=[FakeProposal()])
    args = {k: v for k, v in FULL_CLIENT_ARGS.items() if k != "forbidden_behaviour"}

    events, _ = await _run(belt, args=args)
    names = [n for n, _ in events]

    assert "plan.proposed" not in names
    assert "hitl.requested" not in names
    assert belt.staged == 0, "se persistió una acción con el expediente incompleto"

    missing = next(d for n, d in events if n == "intake.missing")
    assert missing["work_kind"] == "create_client"
    assert [s["key"] for s in missing["slots"]] == ["forbidden_behaviour"]


async def test_a_complete_client_does_reach_plan() -> None:
    """La otra mitad: la puerta deja pasar lo que está completo. Sin esto,
    E1 se cumpliría bloqueándolo todo."""
    belt = IntakeBelt(proposals=[FakeProposal()])

    events, _ = await _run(belt, args=FULL_CLIENT_ARGS)
    names = [n for n, _ in events]

    assert "plan.proposed" in names and "hitl.requested" in names
    assert "intake.missing" not in names
    assert belt.staged == 1


@pytest.mark.parametrize("key", ["name", "vertical", "timezone", "language"])
async def test_every_required_field_blocks_on_its_own(key: str) -> None:
    """El §3.3 es un catálogo cerrado, no una lista de sugerencias."""
    belt = IntakeBelt(proposals=[FakeProposal()])
    args = {k: v for k, v in FULL_CLIENT_ARGS.items() if k != key}

    events, _ = await _run(belt, args=args)

    assert belt.staged == 0
    missing = next(d for n, d in events if n == "intake.missing")
    assert [s["key"] for s in missing["slots"]] == [key]


# ── el expediente es del hilo ──────────────────────────────────────────


async def test_an_answered_slot_is_never_asked_again() -> None:
    """§3.4: un slot respondido no se vuelve a preguntar. El expediente vive
    en el checkpoint, que está indexado por hilo — así que un turno servido
    por otro proceso ve lo mismo."""
    belt = IntakeBelt(proposals=[FakeProposal()])
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    saver = MemorySaver()

    # Turno 1: llega todo menos "qué NO debe hacer".
    first, _ = await _run(
        belt,
        args={k: v for k, v in FULL_CLIENT_ARGS.items() if k != "forbidden_behaviour"},
        config=config,
        saver=saver,
    )
    asked_first = next(d for n, d in first if n == "intake.missing")
    assert [s["key"] for s in asked_first["slots"]] == ["forbidden_behaviour"]

    # Turno 2 en el MISMO hilo: el modelo solo manda el dato nuevo, como
    # haría cualquiera que acabe de leer una respuesta de una línea.
    second, _ = await _run(
        belt,
        args={"client_ref": "boreal", "forbidden_behaviour": "No dar precios"},
        config=config,
        state=_base(user_message="no dé precios por WhatsApp"),
        saver=saver,
    )
    names = [n for n, _ in second]

    assert "intake.missing" not in names, "volvió a pedir lo que ya le habían dado"
    assert "hitl.requested" in names
    assert belt.staged == 1


async def test_the_ledger_is_handed_back_to_the_model() -> None:
    """La nota de expediente evita que la persona tenga que repetirse: sin
    ella, la herramienta ve los otros huecos vacíos en el turno siguiente."""
    note = ledger_note(
        {"answers": {"create_client": {"name": "Clínica Boreal"}}, "asked": {}, "facts": {}}
    )
    assert note is not None
    assert note["role"] == "system"
    assert "Clínica Boreal" in note["content"]
    assert ledger_note({"answers": {}, "asked": {}, "facts": {}}) is None


async def test_the_intake_note_never_touches_the_cached_prefix() -> None:
    """El caché es un encaje de prefijo: la nota se AÑADE al final."""
    from nexus_worker.runtime.companion.prompt import SYSTEM_PROMPT

    belt = IntakeBelt(proposals=[FakeProposal()])
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    saver = MemorySaver()
    await _run(belt, args=FULL_CLIENT_ARGS, config=config, saver=saver)

    _events, provider = await _run(
        belt, args=FULL_CLIENT_ARGS, config=config, saver=saver, state=_base()
    )

    notes = [
        m
        for call in provider.calls
        for m in call.messages
        if m["role"] == "system" and "YA te dio" in str(m["content"])
    ]
    assert notes, "el expediente no llegó al modelo"
    for call in provider.calls:
        assert call.messages[0]["content"] == SYSTEM_PROMPT


# ── la puerta no puede convertirse en un atasco ────────────────────────


def test_a_work_kind_whose_fields_have_nowhere_to_enter_is_not_enforced() -> None:
    """Hoy ``console.propose_prompt`` no acepta ``failing_behaviour`` ni
    ``real_example``. Exigirlos bloquearía **para siempre** todo cambio de
    prompt: el modelo no tendría por dónde entregarlos."""
    specs = [
        _spec("console.propose_prompt", ("client_ref", "system_prompt")),
        _spec("console.propose_client", CLIENT_PARAMS),
    ]
    assert is_enforceable("create_client", specs) is True
    assert is_enforceable("change_prompt", specs) is False

    _work, blocked = blocking_slots({"answers": {}}, "prompt", specs)
    assert blocked == []


def test_the_gate_turns_itself_on_when_the_parameters_exist() -> None:
    """Y el día que existan, se enciende sola: la satisfacibilidad se lee
    del catálogo publicado, no de una lista escrita a mano."""
    specs = [
        _spec("console.propose_prompt", ("client_ref", "failing_behaviour", "real_example")),
    ]
    assert is_enforceable("change_prompt", specs) is True

    _work, blocked = blocking_slots({"answers": {}}, "prompt", specs)
    assert [s["key"] for s in blocked] == ["failing_behaviour", "real_example"]


def test_an_unknown_action_kind_never_blocks() -> None:
    """§3.2: un tipo de trabajo que no esté en el enum no emite
    ``intake.missing``; pasa directo a planificar."""
    specs = [_spec("console.propose_client", CLIENT_PARAMS)]
    assert blocking_slots({}, "usage_alerts", specs) == (None, [])
    assert blocking_slots({}, "invite", specs) == (None, [])
    assert blocking_slots({}, None, specs) == (None, [])


# ── el catálogo cerrado del §3.3 ───────────────────────────────────────


def test_the_catalogue_is_the_one_the_contract_closes() -> None:
    expected = {
        "create_client": ["name", "vertical", "timezone", "language", "forbidden_behaviour"],
        "connect_whatsapp": ["phone_number", "number_owner", "channel_role"],
        "change_prompt": ["failing_behaviour", "real_example"],
        "enable_connector": ["connector_consent"],
        "publish": ["ai_disclosure_decision"],
    }
    assert set(WORK_KINDS) == set(expected)
    for work_kind, keys in expected.items():
        assert [s["key"] for s in SLOT_CATALOG[work_kind]] == keys


def test_every_slot_has_the_literal_shape_of_the_contract() -> None:
    """``examples`` es siempre lista, posiblemente vacía, nunca ``None``."""
    for slots in SLOT_CATALOG.values():
        for slot in slots:
            assert set(slot) >= {"key", "label", "why", "examples", "required"}
            assert isinstance(slot["examples"], list)
            assert slot["required"] is True
            assert slot["label"] and slot["why"]


def test_a_conditional_slot_is_not_asked_without_its_condition() -> None:
    """``channel_role`` solo es obligatorio si el cliente ya tiene otro canal
    activo. Preguntarlo sin la condición sería preguntar un deducible, y el
    §3.3 lo prohíbe."""
    keys = [s["key"] for s in missing_slots({"answers": {}, "facts": {}}, "connect_whatsapp")]
    assert keys == ["phone_number", "number_owner"]

    with_channel = missing_slots(
        {"answers": {}, "facts": {"other_channel_active": True}}, "connect_whatsapp"
    )
    assert [s["key"] for s in with_channel] == ["phone_number", "number_owner", "channel_role"]


def test_required_when_never_leaves_the_engine() -> None:
    """Es una condición del motor, no una clave del evento."""
    for slot in missing_slots(
        {"answers": {}, "facts": {"other_channel_active": True}}, "connect_whatsapp"
    ):
        assert "required_when" not in slot


# ── el expediente, como estructura ─────────────────────────────────────


def test_only_catalogue_keys_enter_the_ledger() -> None:
    """El expediente no es un búfer de la conversación: un ``system_prompt``
    entero dentro sería contexto pagado dos veces."""
    ledger = record_answers(None, "create_client", {**FULL_CLIENT_ARGS, "system_prompt": "x" * 90})
    stored = ledger["answers"]["create_client"]
    assert "system_prompt" not in stored
    assert "client_ref" not in stored
    assert stored["forbidden_behaviour"] == "No dar precios por WhatsApp"


def test_an_empty_value_does_not_count_as_answered() -> None:
    ledger = record_answers(None, "create_client", {"name": "  ", "vertical": "Barbería"})
    assert [s["key"] for s in missing_slots(ledger, "create_client")] == [
        "name",
        "timezone",
        "language",
        "forbidden_behaviour",
    ]


def test_recording_never_mutates_the_ledger_it_was_given() -> None:
    """El estado se serializa en cada frontera de nodo; mutar el que ya está
    dentro es la forma barata de que un checkpoint no coincida con lo que se
    emitió."""
    original = record_answers(None, "create_client", {"name": "Boreal"})
    snapshot = {"create_client": dict(original["answers"]["create_client"])}

    record_answers(original, "create_client", {"vertical": "Barbería"})
    record_asked(original, "create_client", ["timezone"])

    assert original["answers"] == snapshot
    assert original["asked"] == {}
