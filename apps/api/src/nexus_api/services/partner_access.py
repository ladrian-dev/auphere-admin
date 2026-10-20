"""What a partner's console has — spec 032.

The operator panel chooses, per partner, whether the console is on and which
modules it has: the views of the sidebar and the Companion. Three rules live
here and nowhere else:

* **The catalog** is ``PartnerModule`` (``db/models/partner.py``); anything
  else is refused, and the stored order is always the canonical one.
* **A console that is on has at least one view.** Turning it on with only the
  Companion — or nothing — would leave the person on an empty shell.
* **The Companion's switch follows the module.** ``companion_enabled`` is the
  column every Companion gate already reads; it is written here, in the same
  transaction, so the two never disagree.

Every change writes a platform audit row naming the operator (§IV). No
function commits: the caller owns the transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    PARTNER_MODULES,
    PARTNER_NAV_MODULES,
    AuditLog,
    Partner,
    PartnerModule,
)


class PartnerAccessError(Exception):
    """A named no. ``code`` is closed vocabulary; ``status`` is the HTTP one."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class PartnerAccessView:
    console_enabled: bool
    modules: list[str]


def _ordered(modules: list[str]) -> list[str]:
    have = set(modules)
    return [m for m in PARTNER_MODULES if m in have]


async def _partner(session: AsyncSession, partner_id: uuid.UUID, *, lock: bool) -> Partner:
    stmt = sa.select(Partner).where(Partner.id == partner_id)
    if lock:
        stmt = stmt.with_for_update()
    partner = await session.scalar(stmt)
    if partner is None:
        raise PartnerAccessError("unknown_partner", 404)
    return partner


async def read_access(session: AsyncSession, partner_id: uuid.UUID) -> PartnerAccessView:
    partner = await _partner(session, partner_id, lock=False)
    return PartnerAccessView(
        console_enabled=bool(partner.console_enabled),
        modules=partner.ordered_console_modules(),
    )


async def set_access(
    session: AsyncSession,
    partner_id: uuid.UUID,
    *,
    console_enabled: bool,
    modules: list[str],
    actor: str,
) -> PartnerAccessView:
    unknown = sorted(set(modules) - set(PARTNER_MODULES))
    if unknown:
        raise PartnerAccessError("unknown_module", 422)
    ordered = _ordered(modules)
    if console_enabled and not any(m in PARTNER_NAV_MODULES for m in ordered):
        raise PartnerAccessError("no_modules", 422)

    partner = await _partner(session, partner_id, lock=True)
    before = {
        "console_enabled": bool(partner.console_enabled),
        "modules": partner.ordered_console_modules(),
    }
    partner.console_enabled = console_enabled
    partner.console_modules = ordered
    partner.companion_enabled = PartnerModule.COMPANION.value in ordered
    after = {"console_enabled": console_enabled, "modules": ordered}
    if before != after:
        session.add(
            AuditLog(
                tenant_id=None,
                actor=actor,
                action="partner_access.updated",
                target=f"partner:{partner_id}",
                before_json=before,
                after_json=after,
            )
        )
    await session.flush()
    return PartnerAccessView(console_enabled=console_enabled, modules=ordered)
