"""Principal context — puerta RLS del Companion (CO-01).

Tercera dimensión de aislamiento, junto a ``app.tenant_id``
(``core/tenant_context.py``) y ``app.operator_id``
(``core/operator_context.py``). El sujeto del Companion es el
**principal de consola** — la persona del partner — y no un operador de
Auphere ni un tenant: dos miembros del mismo partner no ven los hilos del
otro, igual que dos operadores no ven sus hilos de QA.

Un request que olvide llamar a :func:`apply_principal_to_session` verá
**cero filas** de cualquier tabla ``companion.*``: las policies leen
``current_setting('app.principal_id', true)`` y tratan el valor ausente
como un no-encaje. Fail-closed, no fail-open.

``principal_id`` es TEXTO porque ``partner_memberships.user_id`` lo es. La
seguridad viene de la simetría USING/WITH CHECK de la policy y del Bearer
que resolvió el principal, no de la forma del identificador.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import IsolationViolation

_current_principal: ContextVar[str | None] = ContextVar("current_principal", default=None)


def get_current_principal() -> str | None:
    return _current_principal.get()


def require_current_principal() -> str:
    principal_id = _current_principal.get()
    if principal_id is None:
        raise IsolationViolation(
            "No principal_id in context — a companion.* table was reached "
            "outside a principal-scoped request."
        )
    return principal_id


@contextmanager
def principal_context(principal_id: str) -> Iterator[str]:
    token = _current_principal.set(principal_id)
    try:
        yield principal_id
    finally:
        _current_principal.reset(token)


async def apply_principal_to_session(session: AsyncSession, principal_id: str) -> None:
    """Fija ``app.principal_id`` y baja al rol ``nexus_app`` para esta
    transacción.

    Las dos cosas van en **una sola sentencia**, igual que
    ``apply_tenant_to_session``: ``SET LOCAL ROLE x`` es exactamente
    ``set_config('role', x, true)``, y dos ``execute`` son dos viajes de red
    en el camino crítico.

    Bajar de superusuario es lo que hace que la RLS **exista**: el usuario
    que conecta corre las migraciones y la saltaría en silencio. Un endpoint
    del Companion que fije el GUC sin cambiar de rol tendría aislamiento
    solo de mentira.

    ``is_local=true`` hace que el valor se descarte en el COMMIT/ROLLBACK y
    no pueda filtrarse entre peticiones que comparten conexión del pool.
    """
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :pid, true), "
            "       set_config('role', 'nexus_app', true)"
        ),
        {"pid": str(principal_id)},
    )


__all__ = [
    "apply_principal_to_session",
    "get_current_principal",
    "principal_context",
    "require_current_principal",
]
