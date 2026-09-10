"""CONTRACT-V3 — veinticuatro eventos, y los enums se comprueban al publicar.

La v2 fijó veinte con un test; la 003 lo enmienda por la puerta. Además de
contar, se comprueba lo que la v3 añade como regla: ``task.state`` solo acepta
estados del enum, y ``hitl.requested`` solo puede llevar ``expires_at`` nulo
cuando hay ``task_id`` (la aprobación espera a la tarea).
"""

from __future__ import annotations

import pytest

from nexus_api.api.companion_streaming import (
    COMPANION_EVENTS,
    InvalidCompanionEvent,
    sanitise_payload,
)


def test_the_catalogue_has_exactly_twenty_four_events():
    assert len(COMPANION_EVENTS) == 24
    for name in ("task.state", "exec.dispatched", "exec.completed", "inbox.changed"):
        assert name in COMPANION_EVENTS
    assert {"level", "task_id"} <= COMPANION_EVENTS["hitl.requested"]


def test_task_state_rejects_a_state_outside_the_enum():
    ok = sanitise_payload("task.state", {"task_id": "t", "state": "esperandote", "cause": "hitl"})
    assert ok == {"task_id": "t", "state": "esperandote", "cause": "hitl"}
    with pytest.raises(InvalidCompanionEvent):
        sanitise_payload("task.state", {"task_id": "t", "state": "bogus", "cause": "hitl"})
    with pytest.raises(InvalidCompanionEvent):
        sanitise_payload("task.state", {"task_id": "t", "state": "en_marcha", "cause": "porque"})


def test_hitl_requested_may_wait_forever_only_when_it_has_a_task():
    base = {"action_id": "a", "kind": "prompt", "title": "t", "level": "aviso"}
    assert (
        sanitise_payload("hitl.requested", {**base, "expires_at": None, "task_id": "task"})[
            "task_id"
        ]
        == "task"
    )
    with pytest.raises(InvalidCompanionEvent):
        sanitise_payload("hitl.requested", {**base, "expires_at": None})
    with pytest.raises(InvalidCompanionEvent):
        sanitise_payload(
            "hitl.requested", {**base, "expires_at": "2026-09-10T00:00:00Z", "level": "urgente"}
        )


def test_exec_completed_never_carries_output():
    assert "stdout_sample" not in COMPANION_EVENTS["exec.completed"]
    assert "output" not in COMPANION_EVENTS["exec.completed"]
