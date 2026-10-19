"""The operator behind a panel request (ADR-034).

The admin token says the request comes from the panel; ``X-Operator-Id`` says
which person in the panel made it. Every write that moves money or access
names that person in the audit (constitution §IV). Shared by client access
(spec 030), partner money (spec 033) and partner modules (spec 032).
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.db.models import OperatorAccount


async def require_operator(
    x_operator_id: str | None = Header(default=None, alias="X-Operator-Id"),
    session: AsyncSession = Depends(get_db_session),
) -> OperatorAccount:
    """El operador de la sesión del panel, nunca el token (ADR-034). Mismas
    respuestas que la suplantación: 400 si falta o no es un operador."""
    raw = (x_operator_id or "").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Operator-Id header"
        )
    try:
        operator_id = uuid.UUID(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be an operator principal id",
        ) from None
    async with session.begin():
        account = await session.get(OperatorAccount, operator_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be an operator principal id",
        )
    return account


def _actor(operator: OperatorAccount) -> str:
    return f"operator:{operator.email}"


def operator_actor(operator: OperatorAccount) -> str:
    """The audit actor for an operator: their e-mail, never the token."""
    return f"operator:{operator.email}"
