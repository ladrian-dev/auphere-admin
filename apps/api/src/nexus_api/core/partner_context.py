"""Partner context — puerta RLS del libro Fase 3.

Cuarta dimensión de aislamiento, junto a ``app.tenant_id``,
``app.operator_id`` y ``app.principal_id``. El libro
(``partner_wallets``, ``partner_allocations``, ``usage_ledger``) se
filtra por ``partner_id``. Un request que olvide llamar a
:func:`apply_partner_to_session` ve **cero filas**: las policies leen
``current_setting('app.partner_id', true)`` y tratan el valor ausente
como un no-encaje. Fail-closed, no fail-open.

No es el principal de consola. Dos miembros del mismo partner leen el
mismo libro; un miembro de otro partner no ve ni que existe.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import IsolationViolation

_current_partner: ContextVar[str | None] = ContextVar("current_partner", default=None)


def get_current_partner() -> str | None:
    return _current_partner.get()


def require_current_partner() -> str:
    partner_id = _current_partner.get()
    if partner_id is None:
        raise IsolationViolation(
            "No partner_id in context — a partner-wallet table was reached "
            "outside a partner-scoped request."
        )
    return partner_id


@contextmanager
def partner_context(partner_id: str) -> Iterator[str]:
    token = _current_partner.set(partner_id)
    try:
        yield partner_id
    finally:
        _current_partner.reset(token)


async def apply_partner_to_session(session: AsyncSession, partner_id: object) -> None:
    """Fija ``app.partner_id`` y baja al rol ``nexus_app`` para esta transacción.

    Las dos cosas van en **una sola sentencia**, igual que
    ``apply_tenant_to_session`` / ``apply_principal_to_session``.
    ``is_local=true`` descarta el valor en el COMMIT/ROLLBACK.
    """
    await session.execute(
        text(
            "SELECT set_config('app.partner_id', :pid, true), "
            "       set_config('app.is_admin', '', true), "
            "       set_config('role', 'nexus_app', true)"
        ),
        {"pid": str(partner_id)},
    )


async def apply_admin_to_session(session: AsyncSession) -> None:
    """Fija ``app.is_admin`` para esta transacción. Sin BYPASSRLS.

    FORCE + policy ``app.is_admin``. No baja a ``nexus_app``: ese rol no
    tiene ``operator_auth`` ni escribe ``audit_log`` de plataforma
    (tenant_id NULL). El GUC basta para que FORCE deje ver las filas.
    ``app.partner_id`` se vacía: la cookie de overlay no es un GUC de partner.
    """
    await session.execute(
        text(
            "SELECT set_config('app.is_admin', 'true', true), "
            "       set_config('app.partner_id', '', true)"
        )
    )


__all__ = [
    "apply_admin_to_session",
    "apply_partner_to_session",
    "get_current_partner",
    "partner_context",
    "require_current_partner",
]
