"""Dónde va cada cosa en el turno — spec 015, Requisito 1.

**El defecto, con su número.** La identidad del teammate se anteponía al bloque
de conocimiento, y el conocimiento se añade *después de ``history`` entera*. En
un hilo de cuarenta mensajes la identidad llegaba en la **posición 42**, mientras
«Eres el Companion de Auphere» seguía en la **1**. Es decir: cuanto más se
trabajaba con un teammate, más sonaba al agente genérico.

Ahora la identidad es un mensaje propio en la **posición 2**, fija, y el
conocimiento se queda donde estaba — que es su sitio: es material de consulta y
va cerca del turno, no al principio.
"""

from __future__ import annotations

import pytest
from nexus_worker.runtime.companion.prompt import SYSTEM_PROMPT, build_messages

pytestmark = pytest.mark.unit

IDENTIDAD = "Eres Sofía, teammate del partner, con el oficio «revisora»."


def _historia(n: int) -> list[dict[str, str]]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(n)]


def test_the_identity_is_the_second_message() -> None:
    msgs = build_messages(history=None, user_message="hola", page_context=None, identity=IDENTIDAD)

    assert msgs[0]["content"] == SYSTEM_PROMPT
    assert msgs[1]["role"] == "system"
    assert msgs[1]["content"] == IDENTIDAD


@pytest.mark.parametrize("largo", [0, 2, 40])
def test_the_identity_does_not_drift_with_the_thread(largo: int) -> None:
    """Es el requisito entero: la posición **no depende** de la conversación."""
    msgs = build_messages(
        history=_historia(largo), user_message="hola", page_context=None, identity=IDENTIDAD
    )

    assert msgs[1]["content"] == IDENTIDAD, (
        f"con {largo} mensajes de historia la identidad se movió de la posición 2"
    )


def test_knowledge_no_longer_carries_the_identity_glued_in_front() -> None:
    msgs = build_messages(
        history=None,
        user_message="hola",
        page_context=None,
        identity=IDENTIDAD,
        knowledge_context="lo que el partner escribió en su playbook",
    )
    conocimiento = [m for m in msgs if "playbook" in str(m.get("content", ""))]

    assert len(conocimiento) == 1
    assert IDENTIDAD not in conocimiento[0]["content"], (
        "la identidad volvió a viajar de polizón dentro del conocimiento"
    )


def test_without_a_teammate_the_turn_is_exactly_what_it_was() -> None:
    """R1.5. Quien habla con el Companion no paga nada de esta spec."""
    con_hueco = build_messages(
        history=_historia(4), user_message="hola", page_context=None, identity=None
    )
    como_antes = build_messages(history=_historia(4), user_message="hola", page_context=None)

    assert con_hueco == como_antes
    assert all(m["content"] != IDENTIDAD for m in con_hueco)
    assert len([m for m in con_hueco if m["role"] == "system"]) == 1
