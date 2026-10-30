"""Spec 047, enmienda del 2026-10-30, fase 28 — solo lo que tenemos (requisito 65).

Lo que se comprueba sin base de datos:

- **65.3 y 65.4** (T221): una integración que no es un conector ofrecido no llega
  al AgentSpec ni a «Conectar {X}»: sale como capacidad que falta. El validador la
  rechaza con ``integration_unknown``. Reservas (un módulo) y el catálogo de Meta
  (se enlaza en Canales) tampoco se «conectan».
- **65.5** (T222): la promesa se compara con lo que hace cada herramienta según
  ``capability_names``, no con su prefijo, y en un agente estructurado bloquea.
- **65.6** (T223): el prompt compilado lleva la sección fija de límites con la
  alternativa de cada habilidad.
- **65.7**: las guías y los patrones no nombran acciones sin herramienta en el
  catálogo; las sugerencias que necesitan algo que falta no salen.
- **65.8** (T224): una prueba del sector que necesita una acción que el agente no
  tiene queda «No aplica», con su razón.
- **65.11** (T225): sin la política de herramientas, ninguna de conector. El
  barrido del catálogo está en ``tests/isolation/test_44_agent_within_client.py``.
- **65.12** (T225): un modelo sin instrucciones es un fallo del constructor.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from nexus_api.services.agent_spec.schema import AgentSpec
from nexus_api.services.agent_spec.validator import Context, ToolInfo, validate_spec
from nexus_api.services.builder.agent_draft import (
    BuilderUnavailable,
    DraftRequest,
    offline_output,
    sanitize,
)
from nexus_api.services.business.compilation import Facts
from tests.unit.test_agent_spec_contract import INSTRUCTIONS, STRUCTURED

PENDING = "tienda_test.list_items"


def _ctx(*, reservas_on: bool) -> Context:
    """Un cliente con la agenda (encendida o apagada), un conector ofrecido sin
    conectar, el catálogo de Meta sin enlazar y herramientas de la casa."""
    agenda = {
        name: ToolInfo(
            name,
            integration="reservas",
            connected=reservas_on,
            activatable=False,
        )
        for name in (
            "reservas.services",
            "reservas.find_slots",
            "reservas.create",
            "reservas.reschedule",
        )
    }
    return Context(
        tools={
            **agenda,
            "escalate.escalate_to_human": ToolInfo("escalate.escalate_to_human"),
            "payments.request_review": ToolInfo("payments.request_review"),
            "notification.send_text": ToolInfo("notification.send_text"),
            PENDING: ToolInfo(PENDING, integration="tienda_test", connected=False),
            "catalog.search_products": ToolInfo(
                "catalog.search_products",
                integration="channel_catalog",
                connected=False,
                activatable=False,
            ),
            # Composio: un conector del catálogo cuyos nombres el AgentSpec no admite.
            "STRIPE_CREATE_PAYMENT_LINK": ToolInfo(
                "STRIPE_CREATE_PAYMENT_LINK", integration="stripe", connected=False
            ),
        }
    )


FACTS = Facts(name="Barbería Cultor")


def _request(description: str = "Atiende a los clientes de la barbería por WhatsApp.") -> Any:
    return DraftRequest.clean("Recepción", description)


def _raw(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "instructions": [{"title": "Cómo atiendes", "body": "Responde con la ficha."}],
        "tools": ["escalate.escalate_to_human"],
    }
    raw.update(changes)
    return raw


def _missing(draft: Any) -> set[tuple[str, str, str]]:
    return {(m["kind"], m["key"], m["reason"]) for m in draft.missing}


# ── 65.3 y 65.4: lo que no es un conector ofrecido ─────────────────────────


def test_an_integration_we_do_not_offer_is_a_missing_capability_not_a_connect() -> None:
    draft = sanitize(
        _raw(
            tools=[
                "escalate.escalate_to_human",
                PENDING,
                "reservas.create",
                "facturas.emitir",
                "catalog.search_products",
            ],
            skills=[
                {"key": "facturar", "enabled": True, "integration": "quickbooks"},
                {"key": "pedidos", "enabled": True, "integration": "tienda_test"},
                {"key": "agenda", "enabled": True, "integration": "reservas"},
                {"key": "cobros", "enabled": True, "integration": "stripe"},
            ],
            connection_requests=[
                {"integration": "quickbooks", "reason": "Para facturar"},
                {"integration": "reservas", "reason": "Para la agenda"},
                {"integration": "tienda_test", "reason": "Para los pedidos"},
            ],
        ),
        _request(),
        _ctx(reservas_on=False),
        FACTS,
        model_policy=None,
    )
    spec = draft.spec
    assert [r.integration for r in spec.connection_requests or []] == ["tienda_test"]
    assert {c["integration"] for c in draft.connect} == {"tienda_test"}, "ningún «Conectar X» más"
    skills = {s.key: s.integration for s in spec.skills or []}
    assert skills == {"pedidos": "tienda_test"}
    assert {
        ("integration", "quickbooks", "integration_unknown"),
        # Composio: sus herramientas no caben en un AgentSpec (65.13).
        ("integration", "stripe", "integration_unknown"),
        ("module", "reservas", "module_off"),
        ("tool", "facturas.emitir", "tool_unknown"),
        ("integration", "channel_catalog", "not_linked"),
    } <= _missing(draft)
    for item in draft.missing:
        assert item["label"], item
        assert set(item) == {"kind", "key", "label", "reason", "source", "pointer"}
    # Validará igual al guardarse: nada que el validador rechace.
    _spec, problems = validate_spec(spec, _ctx(reservas_on=False), author="builder")
    assert problems == []


def test_with_reservas_on_the_agenda_is_ours_and_needs_no_connect() -> None:
    draft = sanitize(
        _raw(
            tools=["reservas.find_slots", "reservas.create", "escalate.escalate_to_human"],
            skills=[{"key": "agenda", "enabled": True, "integration": "reservas"}],
            connection_requests=[{"integration": "reservas", "reason": "Para la agenda"}],
        ),
        _request("Atiende las citas de la barbería: busca hueco y reserva."),
        _ctx(reservas_on=True),
        FACTS,
        model_policy=None,
    )
    assert {"reservas.find_slots", "reservas.create"} <= set(draft.spec.tools or [])
    assert not draft.spec.connection_requests, "un módulo no se conecta"
    assert draft.connect == []
    assert not [m for m in draft.missing if m["key"] == "reservas"]


def test_the_validator_refuses_an_integration_that_is_not_an_offered_connector() -> None:
    def codes(doc: dict[str, Any], ctx: Context) -> set[tuple[str, str]]:
        _spec, problems = validate_spec(doc, ctx)
        return {(p.pointer, p.code) for p in problems if p.code == "integration_unknown"}

    doc = copy.deepcopy(STRUCTURED)
    doc["tools"] = ["reservas.find_slots"]
    doc["procedures"] = []
    doc["skills"] = [
        {"key": "facturar", "enabled": True, "integration": "quickbooks"},
        {"key": "agenda", "enabled": True, "integration": "reservas"},
        {"key": "pedidos", "enabled": True, "integration": "tienda_test"},
    ]
    doc["connection_requests"] = [
        {"integration": "tienda_test", "reason": "Para los pedidos"},
        {"integration": "reservas", "reason": "Para la agenda"},
        {"integration": "stripe", "reason": "Para cobrar"},
    ]
    off = codes(doc, _ctx(reservas_on=False))
    assert off == {
        ("/skills/0/integration", "integration_unknown"),
        ("/skills/1/integration", "integration_unknown"),
        ("/connection_requests/1/integration", "integration_unknown"),
        ("/connection_requests/2/integration", "integration_unknown"),
    }
    on = codes(doc, _ctx(reservas_on=True))
    # Encendido, una habilidad puede apoyarse en la agenda; pedir «conectarla», nunca.
    assert ("/skills/1/integration", "integration_unknown") not in on
    assert ("/connection_requests/1/integration", "integration_unknown") in on


# ── 65.12: sin instrucciones no hay borrador genérico ──────────────────────


def test_a_model_without_instructions_is_a_builder_failure() -> None:
    with pytest.raises(BuilderUnavailable):
        sanitize(
            _raw(instructions=[]),
            _request(),
            _ctx(reservas_on=True),
            FACTS,
            model_policy=None,
        )
    with pytest.raises(BuilderUnavailable):
        sanitize(
            _raw(instructions=[{"title": "", "body": ""}]),
            _request(),
            _ctx(reservas_on=True),
            FACTS,
            model_policy=None,
        )


# ── 65.5: la promesa contra lo que hace cada herramienta ───────────────────


def _spec(text: str, tools: list[str]) -> AgentSpec:
    doc = copy.deepcopy(STRUCTURED)
    doc["tools"] = tools
    doc["procedures"] = []
    doc["rules"] = []
    doc["identity"]["description"] = "Atiende a los clientes del negocio por WhatsApp."
    doc["identity"].pop("goal", None)
    doc["instructions"]["sections"] = [{"title": "Qué haces", "body": text}]
    return AgentSpec.model_validate(doc)


def _promised(text: str, tools: list[str]) -> set[str]:
    from nexus_api.services.agent_spec.compiler import incoherences

    return {
        i.action or ""
        for i in incoherences(_spec(text, tools), None, tools)
        if i.code == "promises_without_tool"
    }


@pytest.mark.parametrize(
    ("text", "tools", "action"),
    [
        ("Emite la factura al terminar cada visita.", ["payments.request_review"], "invoice"),
        ("Cobra con tarjeta la señal de la cita.", ["payments.request_review"], "charge"),
        ("Reserva una cita a quien la pida.", ["reservas.services"], "book"),
        ("Envía el PDF con la carta de servicios.", ["notification.send_text"], "send_media"),
        ("Cambia la cita a otro día si te lo piden.", ["reservas.create"], "modify_booking"),
        ("Toma los pedidos por WhatsApp.", ["woocommerce.list_products"], "order"),
    ],
)
def test_a_promise_is_checked_against_what_each_tool_does(
    text: str, tools: list[str], action: str
) -> None:
    """T222: ``payments.request_review`` revisa un comprobante, no cobra ni factura;
    ``reservas.services`` lista servicios, no reserva. El prefijo no cuenta."""
    assert action in _promised(text, tools)


@pytest.mark.parametrize(
    ("text", "tools"),
    [
        ("Reserva una cita a quien la pida.", ["reservas.services", "reservas.create"]),
        ("Envía el PDF con la carta de servicios.", ["notification.send_document"]),
        ("Cambia la cita a otro día si te lo piden.", ["reservas.reschedule"]),
        ("Cobra con tarjeta o con un enlace de pago.", ["woocommerce.build_checkout_link"]),
        ("Cobra las cuotas atrasadas con amabilidad.", ["billing.send_reminders"]),
    ],
)
def test_a_tool_that_does_it_keeps_the_promise(text: str, tools: list[str]) -> None:
    assert _promised(text, tools) == set()


@pytest.mark.parametrize(
    "text",
    [
        "No emitimos facturas: si te la piden, pasa la conversación al equipo.",
        "Nunca cobres por WhatsApp.",
        "Si quieren reservar, pasa la conversación al equipo.",
        "Cuando alguien pida cambiar la cita, toma nota y pásalo al equipo.",
        "Consulta su reserva y dile a qué hora es.",
        "Para reservar, pasa la conversación al equipo.",
    ],
)
def test_a_negation_a_condition_or_a_noun_is_not_a_promise(text: str) -> None:
    assert _promised(text, ["escalate.escalate_to_human"]) == set()


def test_every_tool_that_keeps_a_promise_is_in_capability_names() -> None:
    from nexus_api.api.console.capability_names import (
        ACTION_LABELS,
        CAPABILITY_NAMES,
        TOOL_ACTIONS,
    )

    tools = {key for kind, key in CAPABILITY_NAMES if kind == "tool"}
    assert set(TOOL_ACTIONS) <= tools, sorted(set(TOOL_ACTIONS) - tools)
    for name, actions in TOOL_ACTIONS.items():
        assert actions and actions <= set(ACTION_LABELS), name
    assert "payments.request_review" not in TOOL_ACTIONS
    assert "reservas.services" not in TOOL_ACTIONS


def test_the_review_blocks_a_promise_in_a_structured_agent_and_warns_in_an_old_one() -> None:
    from nexus_api.services.agent_spec.review import ReviewInput, review

    structured = _spec("Emite la factura al terminar.", ["payments.request_review"])
    found = [
        f
        for f in review(
            ReviewInput(spec=structured, facts=FACTS, ctx=_ctx(reservas_on=True))
        ).findings
        if f.code == "promises_without_tool"
    ]
    assert [(f.severity, f.pointer) for f in found] == [("block", "/instructions/sections/0/body")]
    assert found[0].fix == {"kind": "edit", "pointer": "/instructions/sections/0/body"}

    legacy = copy.deepcopy(INSTRUCTIONS)
    legacy["instructions"]["legacy_text"] = "Emite la factura al terminar."
    old = review(
        ReviewInput(spec=AgentSpec.model_validate(legacy), facts=FACTS, ctx=_ctx(reservas_on=True))
    )
    assert [f.severity for f in old.findings if f.code == "promises_without_tool"] == ["warn"]


def test_the_missing_actions_of_a_spec_are_listed_for_the_console() -> None:
    from nexus_api.services.agent_spec.missing import from_promises

    missing = from_promises(_spec("Emite la factura al terminar.", ["payments.request_review"]))
    assert [m.to_json() for m in missing] == [
        {
            "kind": "action",
            "key": "invoice",
            "label": "emitir facturas",
            "reason": "no_tool",
            "source": "text",
            "pointer": "/instructions/sections/0/body",
        }
    ]


def test_a_procedure_that_promises_without_a_tool_leaves_and_the_alternative_stays() -> None:
    """65.4: el borrador no se queda con la promesa. Un procedimiento que promete
    algo que ninguna de sus herramientas hace se quita y se anota."""
    draft = sanitize(
        _raw(
            tools=["escalate.escalate_to_human", "reservas.find_slots", "reservas.create"],
            procedures=[
                {
                    "id": "reservar",
                    "title": "Reservar",
                    "when": "Cuando piden cita",
                    "steps": "Busca hueco y reserva.",
                    "tools": ["reservas.find_slots", "reservas.create"],
                },
                {
                    "id": "queja",
                    "title": "Una queja",
                    "when": "Alguien está molesto",
                    "steps": "Se disculpa y pasa la queja al equipo.",
                },
            ],
            rules=["Emite siempre la factura.", "No ofrezcas descuentos."],
        ),
        _request(),
        _ctx(reservas_on=False),
        FACTS,
        model_policy=None,
    )
    assert [p.id for p in draft.spec.procedures or []] == ["queja"]
    assert draft.spec.rules == ["No ofrezcas descuentos."]
    assert {("action", "book", "no_tool"), ("action", "invoice", "no_tool")} <= _missing(draft)


def test_offline_never_invents_an_integration_nor_promises_the_agenda_without_it() -> None:
    ctx = _ctx(reservas_on=False)
    request = _request("Da citas por WhatsApp y cobra la señal de cada cita.")
    raw = offline_output(request, FACTS, ctx)
    assert not raw.get("connection_requests"), "ni «Conectar stripe» ni ninguna otra"
    draft = sanitize(raw, request, ctx, FACTS, model_policy=None)
    assert not [t for t in draft.spec.tools or [] if t.startswith("reservas.")]
    assert not [p for p in draft.spec.procedures or [] if "reserv" in p.steps.lower()]
    tests = [t["name"] for t in raw["tests"]]
    assert "Pide cita para mañana" not in tests, "una prueba que no puede pasar"


# ── 65.6: la sección fija de límites ───────────────────────────────────────


def test_the_compiled_prompt_has_the_limits_and_each_skills_alternative() -> None:
    from nexus_api.services.agent_spec.compiler import LIMITS_TITLE, compile_spec

    doc = copy.deepcopy(STRUCTURED)
    doc["skills"] = [
        {"key": "booking", "enabled": True, "fallback": "Toma los datos y pásalo al equipo."},
        {"key": "pedidos", "enabled": True, "integration": "tienda_test"},
        {"key": "apagada", "enabled": False, "fallback": "No sale."},
    ]
    text = compile_spec(AgentSpec.model_validate(doc), FACTS)
    assert f"## {LIMITS_TITLE}" in text
    limits = text.split(f"## {LIMITS_TITLE}", 1)[1].split("\n## ", 1)[0]
    assert "Solo haces acciones con tus herramientas" in limits
    assert "pasa la conversación a una persona" in limits
    assert "Toma los datos y pásalo al equipo." in limits
    assert "«pedidos»" in limits, "una habilidad sin alternativa lleva la de por defecto"
    assert "No sale." not in limits, "una habilidad apagada no cuenta"
    at = [text.index(p) for p in ("## Reglas", f"## {LIMITS_TITLE}", "## Cuándo pasar")]
    assert at == sorted(at)
    tagged = compile_spec(AgentSpec.model_validate(doc), FACTS, family="anthropic")
    assert f'<parte nombre="{LIMITS_TITLE}">' in tagged

    legacy = compile_spec(AgentSpec.model_validate(INSTRUCTIONS), FACTS)
    assert LIMITS_TITLE not in legacy, "un agente de antes no cambia (CE-009)"


# ── 65.7: guías, patrones y sugerencias ────────────────────────────────────


def test_patterns_and_guides_name_no_action_without_a_tool_in_the_catalog() -> None:
    from nexus_api.api.console.capability_names import TOOL_ACTIONS
    from nexus_api.services.agent_spec.compiler import promises_in
    from nexus_api.services.builder.guides.catalog import generic_guide, template_guides
    from nexus_api.services.builder.guides.roles import PATTERNS
    from nexus_api.services.builder.guides.schema import render

    doable = set().union(*TOOL_ACTIONS.values())
    texts = dict(PATTERNS)
    for key, guide in {**template_guides(), "generic": generic_guide()}.items():
        texts[f"guide:{key}"] = render(guide.guide)
    for where, text in texts.items():
        for promise in promises_in(text):
            assert promise.needs & doable, (where, promise.label)


def test_a_suggested_agent_that_needs_what_is_missing_is_not_suggested() -> None:
    from nexus_api.services.builder.client_profile import feasible_agents, offline_output

    agents = offline_output("barberia_peluqueria")["agents"]
    assert agents[0]["name"] == "Recepción"
    without = feasible_agents(agents, available=["escalate.escalate_to_human"])
    assert [a["name"] for a in without] == ["Atención"], "uno que atiende y pasa al equipo"
    with_agenda = feasible_agents(
        agents, available=["reservas.find_slots", "reservas.create", "escalate.escalate_to_human"]
    )
    assert [a["name"] for a in with_agenda] == ["Recepción"]
    free = feasible_agents(
        [
            {
                "name": "Seguimiento",
                "description": "Pregunta qué tal fue la visita y anota la respuesta.",
            }
        ],
        available=[],
    )
    assert [a["name"] for a in free] == ["Seguimiento"], "cualquier propósito, sin papel"


def test_a_suggestion_takes_any_role_or_none() -> None:
    from nexus_api.services.builder.suggested_agents import clean

    for role in (None, "logistica", "sales"):
        item = clean(
            {"name": "Seguimiento", "description": "Pregunta qué tal fue la visita.", "role": role}
        )
        assert item is not None, role
        assert item["role"] == ("sales" if role == "sales" else None)
    assert clean({"name": "Seguimiento", "description": "Pregunta qué tal fue la visita."})


# ── 65.8: pruebas del sector que no aplican ────────────────────────────────


def test_a_sector_test_that_needs_the_agenda_does_not_apply_without_it() -> None:
    from nexus_api.services.testing.sector_catalog import needs_of, not_applicable_reason

    book = {
        "key": "book",
        "name": "Pide cita para mañana",
        "first_message": "¿Tienes hueco mañana?",
        "expected_state": {},
        "criteria": [{"key": "ok", "text": "Crea la cita."}],
        "needs": ["book"],
    }
    inferred = {**book, "needs": None, "expected_state": {"booking": {"created": True}}}
    inferred.pop("needs")
    hours = {**book, "key": "hours", "needs": []}
    assert needs_of(book) == {"book"} and needs_of(inferred) == {"book"}
    assert needs_of(hours) == set()
    reason = not_applicable_reason(book, ["escalate.escalate_to_human", "reservas.services"])
    assert reason == "Este agente no tiene herramienta para reservar citas."
    # Sin «No aplica:» delante: lo pone la consola.
    assert not_applicable_reason(inferred, ["escalate.escalate_to_human"]) is not None
    assert not_applicable_reason(book, ["reservas.create"]) is None
    assert not_applicable_reason(hours, []) is None


def test_the_sector_catalog_declares_what_each_test_needs() -> None:
    import json
    from pathlib import Path

    from nexus_api.services.testing.sector_catalog import validate_tests

    data = Path(__file__).resolve().parents[2] / "alembic" / "data" / "0188_sector_tests_v1.json"
    catalog = json.loads(data.read_text(encoding="utf-8"))
    needs = {
        f"{sector}#{t['key']}": t.get("needs")
        for sector, tests in catalog.items()
        for t in validate_tests(tests)
        for t in [t.model_dump()]
    }
    assert needs["barberia_peluqueria#book"] == ["book"]
    assert needs["barberia_peluqueria#closed_day"] == ["book"]
    assert needs["clinica#book"] == ["book"]
    assert needs["restaurante#book_table"] == ["book"]
    assert needs["barberia_peluqueria#hours"] == []


# ── 65.11: sin política, ninguna herramienta de conector ───────────────────


def test_a_closed_policy_keeps_only_tools_that_need_no_connector() -> None:
    from nexus_api.services.activations import ToolPolicy, allowed_names

    names = (
        "reservas.create",
        "escalate.escalate_to_human",
        "payments.request_review",
        "notification.send_text",
        "woocommerce.list_products",
        "billing.get_my_debt",
        "inventory.check_stock",
        "list_products",
        "GMAIL_SEND_EMAIL",
        "tienda_test.list_items",
    )
    kept = allowed_names(names, ToolPolicy(closed=True))
    assert kept == (
        "reservas.create",
        "escalate.escalate_to_human",
        "payments.request_review",
        "notification.send_text",
    )
    assert allowed_names(names, ToolPolicy()) == names
    assert allowed_names(names, ToolPolicy(blocked=frozenset({"list_products"}))) == tuple(
        n for n in names if n != "list_products"
    )


# ── la revisión no manda a Conectores lo que no es un conector ─────────────


def test_a_skill_on_reservas_is_never_fixed_in_connectors() -> None:
    """Reservas es un módulo que enciende Auphere: el hallazgo lo dice y no lleva
    a Conectores. Un conector de verdad sí."""
    from nexus_api.services.agent_spec.review import ReviewInput, review

    doc = copy.deepcopy(STRUCTURED)
    doc["connection_requests"] = []
    doc["skills"] = [
        {"key": "agenda", "enabled": True, "integration": "reservas"},
        {"key": "pedidos", "enabled": True, "integration": "tienda_test"},
    ]
    found = {
        f.pointer: f
        for f in review(
            ReviewInput(
                spec=AgentSpec.model_validate(doc), facts=FACTS, ctx=_ctx(reservas_on=False)
            )
        ).findings
        if f.code == "skill_without_integration"
    }
    agenda = found["/skills/0"]
    assert agenda.fix is None and "Auphere" in agenda.message
    assert found["/skills/1"].fix == {
        "kind": "link",
        "target": "integrations",
        "integration": "tienda_test",
    }


def test_a_stored_spec_loses_what_we_lack_without_being_refused() -> None:
    """D72: un borrador de antes de la enmienda con una integración que no
    tenemos se lee sin ella y la anota; nada se rechaza por ella."""
    from nexus_api.services.agent_spec.missing import strip_spec

    doc = copy.deepcopy(STRUCTURED)
    doc["tools"] = ["reservas.find_slots"]
    doc["procedures"] = []
    doc["skills"] = [{"key": "facturar", "enabled": True, "integration": "quickbooks"}]
    doc["connection_requests"] = [{"integration": "quickbooks", "reason": "Para facturar"}]
    ctx = _ctx(reservas_on=True)
    before, problems = validate_spec(doc, ctx)
    assert before is not None
    assert "integration_unknown" in {p.code for p in problems}
    after, lacking = strip_spec(before, ctx)
    assert not after.skills and not after.connection_requests
    assert [(m.kind, m.key, m.reason) for m in lacking] == [
        ("integration", "quickbooks", "integration_unknown")
    ]
    _spec, again = validate_spec(after, ctx)
    assert "integration_unknown" not in {p.code for p in again}
