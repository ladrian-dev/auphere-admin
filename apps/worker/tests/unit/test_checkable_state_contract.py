"""Lo que una prueba puede esperar es lo que el mundo simulado dice al final.

Si ``World.final_state`` cambia y ``CHECKABLE_STATE`` no, las pruebas fallarían siempre o
dejarían de comprobar algo sin avisar (bug ``las-pruebas-esperan-lo-que-no-se-mide``).
"""

from __future__ import annotations

from nexus_api.services.testing.judge import CHECKABLE_STATE

from nexus_worker.simulation.world import World


def test_everything_a_test_can_expect_is_said_by_the_simulated_world() -> None:
    world = World(timezone="Europe/Madrid", now="2026-11-05T09:00:00+00:00", week=None)
    world.escalated = True
    state = world.final_state()
    for key, inner in CHECKABLE_STATE.items():
        assert key in state, key
        if inner is not None:
            assert inner <= set(state[key]), key
