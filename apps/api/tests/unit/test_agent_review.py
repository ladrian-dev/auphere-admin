"""Spec 047, T084 — la revisión automática (requisito 22).

Cada hallazgo del requisito 22.1 sale de una comprobación real, con su gravedad y
su arreglo (22.2), y sin «✓» fijos (22.3): la lista de comprobaciones dice cuáles
corrieron y si encontraron algo.
"""

from __future__ import annotations

import copy
from typing import Any

from nexus_api.services.agent_spec.review import (
    CHECKS,
    ChannelFact,
    ReviewInput,
    ServiceFact,
    review,
)
from nexus_api.services.agent_spec.schema import AgentSpec
from nexus_api.services.agent_spec.validator import Context, ToolInfo
from nexus_api.services.business.compilation import Facts
from tests.unit.test_agent_spec_contract import STRUCTURED

FACTS = Facts(
    name="Barbería Cultor",
    hours="De lunes a viernes de 10:00 a 20:00.",
    locations=("Cultor Centro · Calle Mayor 1",),
    services=("Corte de pelo · 30 min · 15,00 € · se reserva",),
)
CTX = Context(
    tools={
        "reservas.find_slots": ToolInfo("reservas.find_slots"),
        "reservas.create": ToolInfo("reservas.create"),
        "hubspot.create_contact": ToolInfo(
            "hubspot.create_contact", integration="hubspot", connected=False
        ),
        "calendly.book": ToolInfo("calendly.book", integration="calendly", connected=True),
    }
)
GOOD_SERVICES = (ServiceFact("s1", "Corte de pelo", True, 30, True),)
GOOD_CHANNELS = (ChannelFact("c1", "+34600123456", 2),)


def _input(**changes: Any) -> ReviewInput:
    doc = copy.deepcopy(STRUCTURED)
    doc["skills"] = [{"key": "booking", "enabled": True}]
    doc.update(changes.pop("doc", {}))
    base = {
        "spec": AgentSpec.model_validate(doc),
        "facts": FACTS,
        "ctx": CTX,
        "services": GOOD_SERVICES,
        "channels": GOOD_CHANNELS,
        "has_hours": True,
        "eu_client": False,
    }
    base.update(changes)
    return ReviewInput(**base)


def _codes(data: ReviewInput) -> dict[str, str]:
    return {f.code: f.severity for f in review(data).findings}


def test_a_good_draft_has_no_findings_and_every_check_ran() -> None:
    result = review(_input())
    assert result.findings == ()
    assert [c["check"] for c in result.checks] == list(CHECKS)
    assert all(c["ok"] is True and c["findings"] == 0 for c in result.checks)


def test_a_skill_without_its_integration_blocks_without_fallback_and_warns_with_one() -> None:
    skills = [{"key": "crm", "enabled": True, "integration": "hubspot"}]
    assert _codes(_input(doc={"skills": skills})) == {"skill_without_integration": "block"}
    skills[0]["fallback"] = "Apunta el contacto y pasa al equipo."
    finding = review(_input(doc={"skills": skills})).findings[0]
    assert finding.severity == "warn"
    assert finding.fix == {"kind": "link", "target": "integrations", "integration": "hubspot"}
    # Conectada, no hay hallazgo.
    assert (
        _codes(
            _input(doc={"skills": [{"key": "agenda", "enabled": True, "integration": "calendly"}]})
        )
        == {}
    )


def test_services_without_price_or_bookable_without_duration() -> None:
    services = (
        ServiceFact("s1", "Corte", True, None, True),
        ServiceFact("s2", "Cera", False, None, False),
    )
    codes = review(_input(services=services)).findings
    assert [(f.code, f.severity) for f in codes] == [
        ("bookable_without_duration", "block"),
        ("service_without_price", "warn"),
    ]


def test_no_hours_warns_whether_the_agent_books_or_informs() -> None:
    """Spec 057, 4.1 (decisión de Luis del 2026-11-09): un agente que reserva sin
    horario se publica con aviso; mientras, pasa las citas a una persona. Antes
    bloqueaba."""
    assert _codes(_input(has_hours=False)) == {"no_hours": "warn"}
    informer = {"tools": [], "procedures": []}
    assert _codes(_input(has_hours=False, doc=informer)) == {"no_hours": "warn"}


def test_contradictions_promises_and_unknown_tools() -> None:
    doc = copy.deepcopy(STRUCTURED)
    doc["skills"] = [{"key": "booking", "enabled": True}]
    doc["instructions"]["sections"].append(
        {"title": "Datos", "body": "Abrimos de 9 a 22. Cobra la señal con un enlace de pago."}
    )
    doc["procedures"][0]["tools"] = ["reservas.find_slots", "reservas.reschedule"]
    result = review(_input(doc={k: doc[k] for k in ("instructions", "procedures")}))
    codes = {(f.code, f.severity) for f in result.findings}
    assert ("contradicts_business", "warn") in codes
    # Spec 047, enmienda del 2026-10-30 (65.5): en un agente estructurado, bloquea.
    assert ("promises_without_tool", "block") in codes
    assert ("unknown_tool", "block") in codes
    unknown = next(f for f in result.findings if f.code == "unknown_tool")
    assert unknown.fix is not None and unknown.fix["kind"] == "proposal"
    assert {c["check"] for c in result.checks if not c["ok"]} == {
        "contradictions",
        "promises",
        "tools_exist",
    }


def test_a_channel_without_recipients() -> None:
    channels = (ChannelFact("c1", "+34600123456", 0),)
    assert _codes(_input(channels=channels)) == {"channel_without_recipients": "warn"}


def test_the_ai_disclosure_undecided_blocks_and_on_ask_warns_in_the_eu() -> None:
    assert _codes(_input(doc={"ai_disclosure": {"decided": False}})) == {
        "ai_disclosure_undecided": "block"
    }
    on_ask = {"ai_disclosure": {"decided": True, "mode": "on_ask"}}
    assert _codes(_input(doc=on_ask, eu_client=True)) == {"ai_disclosure_on_ask_eu": "warn"}
    assert _codes(_input(doc=on_ask, eu_client=False)) == {}


def test_blocking_findings_are_what_the_gate_reads() -> None:
    result = review(_input(has_hours=False, doc={"ai_disclosure": {"decided": False}}))
    # Spec 057 (4.1): sin horario avisa; no es de lo que lee la puerta.
    assert {f.code for f in result.blocking} == {"ai_disclosure_undecided"}


def test_the_booking_promise_is_kept_by_reservas_and_booking_and_not_by_agendapro() -> None:
    """Spec 048 (requisitos 1.9 y 2.4): AgendaPro no longer keeps a promise to
    book; ``booking.*`` still does, for the versions that book with it until
    they pass to Reservas, and ``reservas.*`` does."""
    from nexus_api.api.console.capability_names import TOOL_ACTIONS
    from nexus_api.services.agent_spec.compiler import incoherences

    # Spec 047, enmienda del 2026-10-30 (65.5): lo que hace cada herramienta, no
    # su prefijo.
    keepers = {name for name, actions in TOOL_ACTIONS.items() if "book" in actions}
    assert not [t for t in keepers if t.startswith("agendapro")]
    assert {"reservas.create", "booking.create_appointment"} <= keepers

    def promises_unkept(tool: str) -> bool:
        doc = copy.deepcopy(STRUCTURED)
        doc["tools"] = [tool]
        doc["procedures"] = []
        doc["instructions"]["sections"] = [
            {"title": "Citas", "body": "Reserva citas a quien lo pida."}
        ]
        found = incoherences(AgentSpec.model_validate(doc), None, [tool])
        return any(
            i.code == "promises_without_tool" and i.detail == "reservar citas" for i in found
        )

    assert promises_unkept("agendapro.create_appointment")
    assert not promises_unkept("booking.create_appointment")
    assert not promises_unkept("reservas.create")


# ── Spec 057: la agenda (3.8, 4.1 y 4.5) ───────────────────────────────────


def test_a_text_that_forbids_the_agenda_warns_with_its_pointer_and_asks_for_the_proposal() -> None:
    from tests.unit.test_agent_spec_compiler import AGENDA, SPA_JEMMA_POINTERS, _spa_jemma

    ctx = Context(tools={name: ToolInfo(name) for name in AGENDA})
    data = _input(ctx=ctx)
    data = ReviewInput(**{**data.__dict__, "spec": _spa_jemma()})
    found = [f for f in review(data).findings if f.code == "forbids_agenda"]
    assert {f.pointer for f in found} == SPA_JEMMA_POINTERS
    assert {f.severity for f in found} == {"warn"}
    assert all(f.fix == {"kind": "agenda_proposal"} for f in found)
    assert "forbids_agenda" not in {f.code for f in review(data).blocking}
    # Sin la agenda, el mismo texto no dice nada de ella.
    data = ReviewInput(**{**data.__dict__, "spec": _spa_jemma(["reservas.services"])})
    assert "forbids_agenda" not in {f.code for f in review(data).findings}


def test_an_agenda_that_is_not_ready_warns_with_its_reasons_and_the_link() -> None:
    result = review(_input(agenda_reasons=("no_staff", "no_services")))
    found = [f for f in result.findings if f.code == "agenda_not_ready"]
    assert len(found) == 1
    finding = found[0]
    assert finding.severity == "warn"
    assert finding.reasons == ("no_staff", "no_services")
    assert finding.fix == {"kind": "link", "target": "reservas"}
    out = finding.to_json()
    assert out["reasons"] == ["no_staff", "no_services"]
    assert result.blocking == []
    # Con la agenda lista, nada; y sin agenda, los motivos no son suyos.
    assert "agenda_not_ready" not in _codes(_input(agenda_reasons=()))
    informer = {"tools": [], "procedures": []}
    assert "agenda_not_ready" not in _codes(_input(agenda_reasons=("no_staff",), doc=informer))


def test_a_bookable_service_without_duration_still_blocks_an_agent_with_the_agenda() -> None:
    """Spec 057, 4.5: es un servicio mal dado de alta (043, requisito 14), no Reservas
    sin terminar."""
    services = (ServiceFact("s1", "Corte", True, None, True),)
    result = review(_input(services=services, has_hours=False, agenda_reasons=("no_staff",)))
    assert {f.code for f in result.blocking} == {"bookable_without_duration"}
