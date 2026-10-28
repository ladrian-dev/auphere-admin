"""Propuestas durables con su huella — spec 047, T078 (requisitos 15.2 y 15.3; research D5, D17).

El constructor, el copiloto, las sugerencias y las correcciones **proponen**;
una persona con permiso aplica (§IV). Cada propuesta guarda:

- su autor (``builder``, ``copilot``, ``suggestion`` o ``correction``) y quién la
  decidió;
- su estado (``open``, ``applied``, ``rejected``, ``expired``, ``stale``);
- la huella (``state_hash``) del estado sobre el que se hizo: el
  :func:`canonical_hash` del documento que cambia.

Aplicar compara la huella con la del estado de ahora: si cambió, la propuesta
queda ``stale`` y se rechaza (``proposal_stale``). Sin decidir, caduca a los 15
minutos (``proposal_expired``).

El ``id`` es un uuid5 del cliente, el agente, el tipo, el parche y la huella:
proponer dos veces lo mismo sobre el mismo estado es la misma fila.

``canonical_hash`` vive en ``core/canonical.py``: lo importan este módulo y el
Companion, y el constructor no depende del módulo ``companion``
(requisito 15.1).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.canonical import canonical_hash
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.agent_spec import Proposal

#: Una propuesta sin decidir deja de valer a los 15 minutos (§IV, como el Companion).
PROPOSAL_TTL: Final = timedelta(minutes=15)
_NAMESPACE: Final = uuid.UUID("0b8b7f30-4f5e-4a0a-9a47-047f0047fa01")


class ProposalError(Exception):
    code: str = "proposal_error"
    status: int = 409

    def __init__(self, proposal: Proposal | None = None) -> None:
        super().__init__(self.code)
        self.proposal = proposal


class ProposalStale(ProposalError):
    code = "proposal_stale"
    status = 409


class ProposalExpired(ProposalError):
    code = "proposal_expired"
    status = 410


class ProposalClosed(ProposalError):
    """Ya se aplicó o se rechazó."""

    code = "proposal_closed"
    status = 409


def proposal_id(
    *, tenant_id: uuid.UUID, agent_id: uuid.UUID | None, kind: str, diff: Any, state_hash: str
) -> uuid.UUID:
    key = canonical_hash(
        {
            "t": str(tenant_id),
            "a": str(agent_id) if agent_id else None,
            "k": kind,
            "d": diff,
            "s": state_hash,
        }
    )
    return uuid.uuid5(_NAMESPACE, key)


async def propose(
    session: AsyncSession,
    *,
    agent_id: uuid.UUID | None,
    kind: str,
    author: str,
    diff: dict[str, Any],
    state_hash: str,
    summary: str | None = None,
    job_id: uuid.UUID | None = None,
    created_by: str | None = None,
    now: datetime | None = None,
) -> Proposal:
    """Escribe la propuesta (o devuelve la que ya había, igual). Nunca aplica nada."""
    tenant_id = require_current_tenant()
    now = now or datetime.now(UTC)
    pid = proposal_id(
        tenant_id=tenant_id, agent_id=agent_id, kind=kind, diff=diff, state_hash=state_hash
    )
    await session.execute(
        insert(Proposal)
        .values(
            id=pid,
            tenant_id=tenant_id,
            agent_id=agent_id,
            kind=kind,
            author=author,
            summary=(summary or None) and summary[:300],
            diff=diff,
            state_hash=state_hash,
            status="open",
            job_id=job_id,
            created_by=created_by,
            expires_at=now + PROPOSAL_TTL,
        )
        .on_conflict_do_nothing(index_elements=[Proposal.id])
    )
    found = await session.get(Proposal, pid, populate_existing=True)
    assert found is not None
    return found


async def get_open(
    session: AsyncSession, proposal_id_: uuid.UUID, *, agent_id: uuid.UUID | None
) -> Proposal | None:
    """La propuesta del cliente del contexto **y de ese agente**; la de un
    hermano no existe (garantía 9)."""
    stmt = sa.select(Proposal).where(
        Proposal.tenant_id == require_current_tenant(), Proposal.id == proposal_id_
    )
    stmt = stmt.where(
        Proposal.agent_id == agent_id if agent_id is not None else Proposal.agent_id.is_(None)
    )
    return (await session.scalars(stmt.with_for_update())).first()


def _check(proposal: Proposal, *, current_state_hash: str, now: datetime) -> None:
    if proposal.status == "expired":
        raise ProposalExpired(proposal)
    if proposal.status == "stale":
        raise ProposalStale(proposal)
    if proposal.status != "open":
        raise ProposalClosed(proposal)
    if now >= proposal.expires_at:
        proposal.status = "expired"
        raise ProposalExpired(proposal)
    if proposal.state_hash != current_state_hash:
        proposal.status = "stale"
        raise ProposalStale(proposal)


def accept(
    proposal: Proposal, *, current_state_hash: str, actor: str, now: datetime | None = None
) -> None:
    """Marca la propuesta como aplicada si sigue valiendo; si no, la cierra con su
    motivo y lanza el error. Quien llama aplica el parche en la misma transacción."""
    now = now or datetime.now(UTC)
    _check(proposal, current_state_hash=current_state_hash, now=now)
    proposal.status = "applied"
    proposal.decided_by = actor
    proposal.decided_at = now


def reject(proposal: Proposal, *, actor: str, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    if proposal.status != "open":
        raise ProposalClosed(proposal)
    proposal.status = "rejected"
    proposal.decided_by = actor
    proposal.decided_at = now


async def expire_open(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Cierra las que pasaron su plazo (lectura perezosa: la consola las pide)."""
    now = now or datetime.now(UTC)
    result = await session.execute(
        sa.update(Proposal)
        .where(
            Proposal.tenant_id == require_current_tenant(),
            Proposal.status == "open",
            Proposal.expires_at <= now,
        )
        .values(status="expired")
    )
    return int(getattr(result, "rowcount", 0) or 0)


__all__ = [
    "PROPOSAL_TTL",
    "ProposalClosed",
    "ProposalError",
    "ProposalExpired",
    "ProposalStale",
    "accept",
    "canonical_hash",
    "expire_open",
    "get_open",
    "proposal_id",
    "propose",
    "reject",
]
