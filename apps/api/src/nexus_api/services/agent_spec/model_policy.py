"""La política de modelo la gestiona Auphere — spec 047, enmienda del 2026-10-29
(requisito 64; research D55).

Mientras no exista la gestión de modelos, precios y selección desde el panel de
operador, la consola no cambia la política de modelo de un agente: ni escribiendo
otra en el AgentSpec del borrador (``PATCH …/draft``) ni comprobando otra en
«Calidad» (``POST …/quality/check``). La API responde ``409 model_policy_managed``.
Los agentes siguen con la suya (D44 y D45), y el constructor, la plantilla y el
admin la ponen como hasta ahora: lo que se rechaza es el cambio pedido por una
persona desde la consola.

Cuando llegue la gestión de modelos (64.4), la spec que la construya retira esto y
los requisitos 39 y 41 vuelven a aplicarse a la consola.
"""

from __future__ import annotations

from typing import Any, Final

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.services.agent_spec.schema import AgentSpec, dump

CODE: Final = "model_policy_managed"


def refuse_model_policy_change() -> None:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": CODE})


async def _default_policy(session: AsyncSession) -> dict[str, Any]:
    from nexus_api.services.agent_spec.legacy import LEGACY_DEPLOYMENT
    from nexus_api.services.router_catalog import default_model_policy

    return dict(
        await default_model_policy(session) or {"kind": "pinned", "deployment": LEGACY_DEPLOYMENT}
    )


async def guard_model_policy(
    session: AsyncSession, before: AgentSpec | None, spec: AgentSpec
) -> None:
    """``409 model_policy_managed`` si ``spec`` trae otra política que la que tenía
    el agente (o, sin AgentSpec todavía, que la que le daría la plataforma)."""
    current = (
        dump(before).get("model_policy") if before is not None else await _default_policy(session)
    )
    if dump(spec).get("model_policy") != current:
        refuse_model_policy_change()


__all__ = ["CODE", "guard_model_policy", "refuse_model_policy_change"]
