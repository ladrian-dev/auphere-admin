"""Garantía 9 con Recepción — spec 047, T178 (requisitos 53.3 a 53.6).

``reception.handoff`` es la única herramienta que nombra un agente. Lo que impide
que por ahí un agente llegue a lo de otro:

1. **Solo a los de su lista y de su cliente.** El agente de otro cliente, un
   hermano que no está en la lista o un id inventado dan ``not_in_list`` sin
   decir a quién, y nada cambia.
2. **Ni en pausa ni archivado.**
3. **Al destino pasa el resumen, no lo de Recepción**: su conocimiento, su
   memoria y su prompt se quedan con ella.

Los mundos y los pasos son los de
``tests/integration/reception/test_reception_handoff.py``: aquí se fijan como
barrido, con un nombre que no se puede quitar sin poner esta suite en rojo.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.reception import test_reception_handoff as handoff

pytestmark = [pytest.mark.isolation]


async def test_reception_never_hands_off_outside_its_list_and_its_client(
    db_session: AsyncSession,
) -> None:
    await handoff.test_only_to_the_agents_of_its_list_and_of_its_client(db_session)


@pytest.mark.parametrize("lifecycle", ["paused", "archived"])
async def test_reception_never_hands_off_to_a_paused_or_archived_agent(
    db_session: AsyncSession, lifecycle: str
) -> None:
    await handoff.test_no_handoff_to_a_paused_or_archived_target(db_session, lifecycle)


async def test_the_target_gets_the_summary_and_never_receptions_knowledge(
    db_session: AsyncSession,
) -> None:
    await handoff.test_the_summary_passes_and_receptions_own_knowledge_does_not(db_session)
