"""Spec 058, T003 — la audiencia se decide antes que cualquier pausa.

Requisitos 1.1, 1.2, 1.4 y 1.7. Hasta la 058, las puertas de estado (el cliente
en pausa, archivado o en alta; el canal en pausa o desconectado; el agente sin
publicar o en pausa) iban antes que la de audiencia. Así, un contacto al que el
número nunca responde abría «Espera a una persona» y avisaba a la gente del
cliente en cuanto algo estaba en pausa (Flor y Encanto, producción, 2026-11-10).
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from nexus_api.db.models import ChannelStatus, TenantStatus

from nexus_worker.runtime import dispatcher
from nexus_worker.runtime.dispatcher import Gate, TurnFacts, gate_for

OUT = Gate("not_admin", "out_of_audience")

ANSWERING = TurnFacts(
    tenant_status=TenantStatus.ACTIVE,
    channel_status=ChannelStatus.ACTIVE,
    send_only_channel=False,
    has_active_agent=True,
    ever_had_agent=True,
    agent_active=True,
    out_of_audience=False,
)

#: Cada puerta de estado, con la puerta que da hoy a un contacto de la audiencia.
STATE_GATES: list[tuple[str, TurnFacts, Gate]] = [
    (
        "cliente en pausa",
        replace(ANSWERING, tenant_status=TenantStatus.PAUSED),
        Gate("tenant_inactive", "paused_client"),
    ),
    (
        "cliente archivado",
        replace(ANSWERING, tenant_status=TenantStatus.ARCHIVED),
        Gate("tenant_inactive", "archived_client"),
    ),
    (
        "cliente en alta",
        replace(ANSWERING, tenant_status=TenantStatus.PROVISIONING),
        Gate("tenant_inactive", "agent_unpublished"),
    ),
    (
        "canal en pausa",
        replace(ANSWERING, channel_status=ChannelStatus.PAUSED),
        Gate("channel_paused", "paused_channel"),
    ),
    (
        "canal desconectado",
        replace(ANSWERING, channel_status=ChannelStatus.DISCONNECTED),
        Gate("channel_problem", "channel_problem"),
    ),
    (
        "agente sin publicar",
        replace(ANSWERING, has_active_agent=False),
        Gate("agent_unpublished", "agent_unpublished"),
    ),
    (
        "cliente sin agente",
        replace(ANSWERING, has_active_agent=False, ever_had_agent=False),
        Gate("no_agent", "agent_unpublished"),
    ),
    (
        "agente en pausa a mano",
        replace(ANSWERING, agent_pause_reason="manual"),
        Gate("agent_paused", "paused_agent"),
    ),
    (
        "agente en pausa sin saldo",
        replace(ANSWERING, agent_pause_reason="no_balance"),
        Gate("agent_paused", "no_balance"),
    ),
    (
        "agente en pausa por su tope",
        replace(ANSWERING, agent_pause_reason="agent_cap"),
        Gate("agent_paused", "agent_cap"),
    ),
    (
        "agente en pausa con el cliente",
        replace(ANSWERING, agent_pause_reason="client_paused"),
        Gate("agent_paused", "paused_client"),
    ),
    (
        "agente en pausa con el cliente archivado",
        replace(ANSWERING, agent_pause_reason="client_archived"),
        Gate("agent_paused", "archived_client"),
    ),
]


@pytest.mark.parametrize(
    ("facts", "_today"), [(f, g) for _, f, g in STATE_GATES], ids=[n for n, _, _ in STATE_GATES]
)
def test_out_of_audience_wins_over_every_state_gate(facts: TurnFacts, _today: Gate) -> None:
    """Requisitos 1.1 y 1.2: fuera de la audiencia es fuera de la audiencia,
    pase lo que pase con el cliente, el canal o el agente."""
    assert gate_for(replace(facts, out_of_audience=True)) == OUT


@pytest.mark.parametrize(
    ("facts", "today"), [(f, g) for _, f, g in STATE_GATES], ids=[n for n, _, _ in STATE_GATES]
)
def test_inside_the_audience_every_state_gate_stays_as_today(facts: TurnFacts, today: Gate) -> None:
    """Requisito 1.4: con el contacto en la audiencia nada cambia."""
    assert gate_for(facts) == today


def test_out_of_audience_on_an_answering_number_is_still_out_of_audience() -> None:
    assert gate_for(replace(ANSWERING, out_of_audience=True)) == OUT


def test_a_person_in_control_still_comes_after_the_audience() -> None:
    assert gate_for(replace(ANSWERING, agent_active=False)) == Gate(
        "human_takeover", "human_takeover"
    )
    assert gate_for(replace(ANSWERING, agent_active=False, out_of_audience=True)) == OUT


def test_a_send_only_number_is_left_exactly_as_today() -> None:
    """Requisito 1.7: el número solo de envío no lo toca esta spec. Con el
    cliente activo sigue dando ``send_only_channel`` (New Air en producción), y
    en pausa sigue dando la pausa —un hueco anotado en research D5—."""
    send_only = replace(ANSWERING, send_only_channel=True, out_of_audience=True)
    assert gate_for(send_only) == Gate("send_only_channel", None)
    assert gate_for(replace(send_only, tenant_status=TenantStatus.PAUSED)) == Gate(
        "tenant_inactive", "paused_client"
    )
    assert gate_for(replace(send_only, channel_status=ChannelStatus.PAUSED)) == Gate(
        "channel_paused", "paused_channel"
    )


def test_the_module_documents_the_new_order() -> None:
    """La tabla del docstring es la spec viva del orden: dice que la audiencia
    va primero (contrato ``turn-gates.md``)."""
    doc = dispatcher.__doc__ or ""
    assert "058" in doc
    assert doc.index("fuera de la audiencia") < doc.index("cliente en pausa")
