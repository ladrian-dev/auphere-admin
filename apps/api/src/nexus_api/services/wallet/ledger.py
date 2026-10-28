"""El cuadre diario del dinero — spec 047, T156 (requisito 43.9; research D25).

Por cada partner que cobra de las bolsas, en su moneda y al céntimo:

- **cada bolsa**: su saldo es la suma de sus asientos, y el último asiento dice ese
  mismo saldo;
- **la cuenta**: lo que el libro de la cuenta sacó para las bolsas (``bag_assign``
  menos ``bag_return``) es lo que dicen los traspasos (asignar y rellenar menos
  bajar).

Devuelve las diferencias; el cron las deja en el log y en las anomalías del admin.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import ClientWallet, ClientWalletEntry, UsageLedger, WalletTransfer
from nexus_api.db.models.partner_wallet import KIND_BAG_ASSIGN, KIND_BAG_RETURN


@dataclass
class Reconciliation:
    partner_id: uuid.UUID
    differences: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.differences


async def reconcile(session: AsyncSession, partner_id: uuid.UUID) -> Reconciliation:
    """Dentro de una sesión con el ``app.partner_id`` del partner; cada bolsa se lee
    con el ``app.tenant_id`` de su cliente."""
    from nexus_api.services.wallet.bags import as_client, partner_tenants

    out = Reconciliation(partner_id=partner_id)
    # La bolsa y sus asientos son del cliente: uno a uno, con su contexto puesto.
    for tenant_id in await partner_tenants(session, partner_id):
        await as_client(session, tenant_id)
        bag = await session.scalar(
            sa.select(ClientWallet).where(ClientWallet.tenant_id == tenant_id)
        )
        if bag is None:
            continue
        total = int(
            await session.scalar(
                sa.select(sa.func.coalesce(sa.func.sum(ClientWalletEntry.amount_micros), 0)).where(
                    ClientWalletEntry.tenant_id == tenant_id
                )
            )
            or 0
        )
        last = await session.scalar(
            sa.select(ClientWalletEntry.balance_after_micros)
            .where(ClientWalletEntry.tenant_id == tenant_id)
            .order_by(ClientWalletEntry.seq.desc())
            .limit(1)
        )
        if total != bag.balance_micros or (last is not None and int(last) != bag.balance_micros):
            out.differences.append(
                {
                    "kind": "bag",
                    "tenant_id": str(tenant_id),
                    "balance": bag.balance_micros,
                    "entries": total,
                    "last_entry": None if last is None else int(last),
                }
            )
    ledger: dict[str, Any] = dict(
        (  # type: ignore[arg-type]
            await session.execute(
                sa.select(UsageLedger.kind, sa.func.sum(UsageLedger.qty))
                .where(
                    UsageLedger.partner_id == partner_id,
                    UsageLedger.kind.in_([KIND_BAG_ASSIGN, KIND_BAG_RETURN]),
                )
                .group_by(UsageLedger.kind)
            )
        ).all()
    )
    transfers: dict[str, Any] = dict(
        (  # type: ignore[arg-type]
            await session.execute(
                sa.select(WalletTransfer.kind, sa.func.sum(WalletTransfer.partner_amount_micros))
                .where(WalletTransfer.partner_id == partner_id)
                .group_by(WalletTransfer.kind)
            )
        ).all()
    )
    out_of_account = int(ledger.get(KIND_BAG_ASSIGN) or 0) - int(ledger.get(KIND_BAG_RETURN) or 0)
    by_transfers = (
        int(transfers.get("assign") or 0)
        + int(transfers.get("refill") or 0)
        + int(transfers.get("migration") or 0)
        - int(transfers.get("lower") or 0)
    )
    if out_of_account != by_transfers:
        out.differences.append(
            {"kind": "account", "ledger": out_of_account, "transfers": by_transfers}
        )
    return out


__all__ = ["Reconciliation", "reconcile"]
