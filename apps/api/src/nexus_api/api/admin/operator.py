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
from nexus_api.services import operator_identity


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


async def require_enabled_operator(
    operator: OperatorAccount = Depends(require_operator),
) -> OperatorAccount:
    """Lo mismo, y además habilitado: una cuenta deshabilitada no es un operador
    válido (spec 052, R6.3). Misma respuesta que para quien no es operador.

    ``require_operator`` se queda como está: lo usan rutas de otras specs que
    tendrían que decidirlo con su propia prueba.
    """
    if not operator_identity.load_operator_view(operator).ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be an operator principal id",
        )
    return operator


def _actor(operator: OperatorAccount) -> str:
    return f"operator:{operator.email}"


def operator_actor(operator: OperatorAccount) -> str:
    """The audit actor for an operator: their e-mail, never the token."""
    return f"operator:{operator.email}"


async def operator_from_header(raw: str | None) -> OperatorAccount | None:
    """The operator an optional ``X-Operator-Id`` names, or ``None`` without it.

    For writes that predate ADR-034 and still accept the bare admin token:
    when the panel sends the header the audit names the person; a header that
    does not name an enabled operator is refused like everywhere else. Opens
    its own session so it can sit next to a tenant-scoped one.
    """
    if raw is None or not raw.strip():
        return None
    try:
        operator_id = uuid.UUID(raw.strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be an operator principal id",
        ) from None
    from nexus_api.db.base import get_sessionmaker

    async with get_sessionmaker()() as session, session.begin():
        account = await session.get(OperatorAccount, operator_id)
    if account is None or not operator_identity.load_operator_view(account).ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Operator-Id must be an operator principal id",
        )
    return account
