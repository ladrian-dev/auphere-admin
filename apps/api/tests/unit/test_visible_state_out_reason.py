"""`GET /console/clients` devolvía 500 con un número sin configurar.

`VisibleState.reason` lleva dos cosas distintas: el motivo de una pausa
(`manual`, `no_balance`…) y, desde la spec 063 (2.6), el `unconfigured` de un
agente listo cuyo número no está configurado. Eso no es una pausa, pero el
serializador lo metía igual en `pause_reason`, cuyo `Literal` no lo admite: la
lista entera de clientes se caía con un 500 por un agente en ese estado, que es
el que deja la semilla de desarrollo.

Quien lo lee solo lo usa cuando el estado es `paused`
(`client-v2-model.ts::agentStateText`), así que el motivo viaja solo entonces y
no se pierde nada.
"""

from __future__ import annotations

import pytest

from nexus_api.api.console.tenants import _visible_out
from nexus_api.services.agent_lifecycle import VisibleState


def test_a_pause_carries_its_reason() -> None:
    out = _visible_out(VisibleState("paused", "warn", "no_balance"))
    assert (out.code, out.pause_reason) == ("paused", "no_balance")


def test_an_unconfigured_number_does_not_blow_up_the_list() -> None:
    """El caso que caía: listo, sin canal y con el número sin configurar."""
    out = _visible_out(VisibleState("ready_no_channel", "info", "unconfigured"))
    assert out.code == "ready_no_channel"
    assert out.pause_reason is None


@pytest.mark.parametrize("code", ["serving", "testing", "draft", "ready_no_channel"])
def test_only_a_pause_has_a_pause_reason(code: str) -> None:
    out = _visible_out(VisibleState(code, "info", "unconfigured"))
    assert out.pause_reason is None
