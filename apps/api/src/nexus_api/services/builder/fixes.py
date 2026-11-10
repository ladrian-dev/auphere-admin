"""«Arreglar» un dato desde una prueba fallida — spec 047, T099 (requisito 19.4).

El copiloto pregunta el alcance; esto aplica **cuando la persona confirma**:

- **en el negocio**: una pregunta frecuente de la ficha con la pregunta de la
  prueba y la respuesta correcta, escrita por esa persona (procedencia
  «person»): la saben todos los agentes;
- **solo este agente**: una pregunta frecuente propia del agente en su borrador
  (capa del agente, garantía 9).

En los dos casos la prueba queda desactualizada y vuelve a pasar.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.agent_spec import AgentTest
from nexus_api.services.business.sections import Actor

Scope = Literal["business", "agent"]


class FixError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def business_fix(
    session: AsyncSession, *, test: AgentTest, value: str, actor: Actor
) -> dict[str, Any]:
    from nexus_api.services.business import faqs

    faq_id, _written = await faqs.create_faq(
        session, q=test.first_message[:300], a=value, actor=actor
    )
    test.stale = True
    return {"scope": "business", "faq_id": str(faq_id)}


def agent_fix_ops(test: AgentTest, value: str) -> list[dict[str, Any]]:
    return [
        {
            "op": "add",
            "path": "/services/faqs/-",
            "value": {"q": test.first_message[:300], "a": value[:2000]},
        }
    ]


__all__ = ["FixError", "Scope", "agent_fix_ops", "business_fix"]
