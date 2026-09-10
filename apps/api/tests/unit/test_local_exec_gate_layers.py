"""Requisito 10.2 — las tres capas y la regla que las une.

La lista blanca es del cliente y solo se toca desde la consola (001). Encima
hay dos capas que **solo pueden restringir**: el techo del partner y la
preferencia de la persona. Este fichero prueba la regla en sí, sin base de
datos: si `most_restrictive` se equivocara, todo lo demás daría igual.
"""

from __future__ import annotations

import pytest

from nexus_api.db.models.local_workstation import (
    EXEC_ALWAYS,
    EXEC_ASK,
    EXEC_MODES,
    EXEC_NEVER,
    most_restrictive,
)
from nexus_api.services.local_exec_policy import effective_mode


def test_the_three_modes_are_ordered_from_most_to_least_restrictive():
    assert EXEC_MODES == (EXEC_NEVER, EXEC_ASK, EXEC_ALWAYS)


@pytest.mark.parametrize(
    ("modes", "expected"),
    [
        ((EXEC_ALWAYS, EXEC_ALWAYS), EXEC_ALWAYS),
        ((EXEC_ALWAYS, EXEC_ASK), EXEC_ASK),
        ((EXEC_ASK, EXEC_ALWAYS), EXEC_ASK),
        ((EXEC_NEVER, EXEC_ALWAYS), EXEC_NEVER),
        ((EXEC_ALWAYS, EXEC_NEVER), EXEC_NEVER),
        ((EXEC_NEVER, EXEC_ASK), EXEC_NEVER),
    ],
)
def test_the_most_restrictive_always_wins(modes: tuple[str, str], expected: str):
    assert most_restrictive(*modes) == expected


def test_what_nobody_set_counts_as_ask():
    """Fail-closed: sin techo y sin preferencia se pregunta, no se permite."""
    assert most_restrictive() == EXEC_ASK
    assert most_restrictive(None, None) == EXEC_ASK
    assert most_restrictive(None, EXEC_ALWAYS) == EXEC_ALWAYS
    assert most_restrictive("cualquier-cosa") == EXEC_ASK


def test_the_preference_for_an_executable_beats_the_global_one():
    """Y el techo sigue mandando sobre las dos."""
    assert (
        effective_mode(ceiling=None, global_pref=EXEC_NEVER, executable_pref=EXEC_ALWAYS)
        == EXEC_ALWAYS
    )
    assert (
        effective_mode(ceiling=None, global_pref=EXEC_ALWAYS, executable_pref=EXEC_NEVER)
        == EXEC_NEVER
    )
    # Sin preferencia por ejecutable manda la global.
    assert (
        effective_mode(ceiling=None, global_pref=EXEC_ALWAYS, executable_pref=None) == EXEC_ALWAYS
    )
    # Con techo, la persona no puede subir.
    assert (
        effective_mode(ceiling=EXEC_ASK, global_pref=None, executable_pref=EXEC_ALWAYS) == EXEC_ASK
    )
    assert (
        effective_mode(ceiling=EXEC_NEVER, global_pref=EXEC_ALWAYS, executable_pref=EXEC_ALWAYS)
        == EXEC_NEVER
    )
    # Y un techo permisivo no baja lo que la persona restringió.
    assert (
        effective_mode(ceiling=EXEC_ALWAYS, global_pref=EXEC_NEVER, executable_pref=None)
        == EXEC_NEVER
    )


def test_an_absent_ceiling_does_not_restrict():
    """El techo es una restricción que alguien pone. Ausente no es «ask»: leerlo
    así convertiría la ausencia de una decisión en una decisión, y nadie podría
    elegir «permitir siempre» sin pasar por una pantalla de equipo. El defecto
    seguro lo pone la preferencia, que sí es ``ask``."""
    from nexus_api.services.local_exec_policy import resolve

    assert resolve(ceiling=None, global_pref=None, executable_pref=None).mode == EXEC_ASK
    assert resolve(ceiling=None, global_pref=EXEC_ALWAYS, executable_pref=None).mode == EXEC_ALWAYS
    assert resolve(ceiling=None, global_pref=EXEC_ALWAYS, executable_pref=None).capped is False


def test_capped_says_when_the_ceiling_lowered_what_the_person_asked_for():
    """La pantalla tiene que poder decir «el techo del partner manda» (R10.4)."""
    from nexus_api.services.local_exec_policy import resolve

    capped = resolve(ceiling=EXEC_ASK, global_pref=EXEC_ALWAYS, executable_pref=None)
    assert (capped.mode, capped.capped) == (EXEC_ASK, True)
    free = resolve(ceiling=EXEC_ALWAYS, global_pref=EXEC_ALWAYS, executable_pref=None)
    assert (free.mode, free.capped) == (EXEC_ALWAYS, False)
    # Restringirse a uno mismo no es que te capen.
    own = resolve(ceiling=EXEC_ALWAYS, global_pref=EXEC_NEVER, executable_pref=None)
    assert (own.mode, own.capped) == (EXEC_NEVER, False)
