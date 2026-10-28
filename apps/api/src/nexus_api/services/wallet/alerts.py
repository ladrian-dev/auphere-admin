"""Los avisos de la bolsa y el tope de cada agente — spec 047, T157 (requisitos
44.1 a 44.8; research D27; ``contracts/events.md`` §3).

**La bolsa** (``client.wallet.*``, al partner y al cliente):

- «Queda poco» (``low``): el saldo baja del 20 % de la base del mes (saldo al
  empezar el mes más lo asignado en el mes). Una vez al mes; se puede apagar.
- «No llega a fin de mes» (``not_enough``): al ritmo de los últimos 7 días no
  llega. Una vez al mes. Con menos de 3 días de consumo no se estima.
- «Agotada» (``empty``): saldo cero. Una vez al día.
- Se **rearman** al subir el saldo (asignar, rellenar, mover hacia ella).

**El tope del agente** (``agent.cap.*``, mensual UTC, en la moneda de la bolsa):
al 80 % avisa una vez al mes; al 100 % el agente se pausa con su motivo
(``agent_cap``) y los demás siguen. Un tope por encima de la bolsa se permite.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Agent, AgentMonthlySpend, ClientWallet, ClientWalletEntry
from nexus_api.services.wallet.bags import month_of

LOW_SHARE: Final = 0.20
CAP_WARN_SHARE: Final = 0.80
PACE_DAYS: Final = 7
MIN_PACE_DAYS: Final = 3


@dataclass(frozen=True)
class Alert:
    kind: str
    severity: str
    tenant_id: uuid.UUID
    data: dict[str, object]


def rearm(bag: ClientWallet) -> None:
    """Subió el saldo: los avisos vuelven a poder salir."""
    bag.low_alerted_month = None
    bag.not_enough_alerted_month = None
    bag.empty_alerted_on = None


async def pace_per_day(session: AsyncSession, bag: ClientWallet, today: date) -> float | None:
    """El gasto medio por día de los últimos 7 días completos, o None con menos de
    3 días de consumo («Aún no hay datos para estimarlo»)."""
    start = datetime.combine(today - timedelta(days=PACE_DAYS), datetime.min.time(), UTC)
    end = datetime.combine(today, datetime.min.time(), UTC)
    # Una sola expresión para el SELECT y el GROUP BY: dos llamadas a
    # ``date_trunc`` serían dos parámetros distintos y Postgres no las iguala.
    day = sa.cast(sa.func.timezone("UTC", ClientWalletEntry.created_at), sa.Date)
    rows = (
        await session.execute(
            sa.select(day, sa.func.sum(-ClientWalletEntry.amount_micros))
            .where(
                ClientWalletEntry.tenant_id == bag.tenant_id,
                ClientWalletEntry.kind == "debit_turn",
                ClientWalletEntry.created_at >= start,
                ClientWalletEntry.created_at < end,
            )
            .group_by(day)
        )
    ).all()
    if len(rows) < MIN_PACE_DAYS:
        return None
    return sum(int(total or 0) for _day, total in rows) / PACE_DAYS


def days_left(balance: int, pace: float | None) -> int | None:
    if pace is None or pace <= 0:
        return None
    return int(balance // pace)


async def bag_state(session: AsyncSession, bag: ClientWallet, today: date | None = None) -> str:
    """``ok``, ``low``, ``not_enough`` o ``empty`` (``events.md`` §1.4)."""
    today = today or datetime.now(UTC).date()
    if bag.balance_micros <= 0:
        return "empty"
    if bag.month_base_micros > 0 and bag.balance_micros < LOW_SHARE * bag.month_base_micros:
        return "low"
    left = days_left(bag.balance_micros, await pace_per_day(session, bag, today))
    month_end = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    if left is not None and left < (month_end - today).days:
        return "not_enough"
    return "ok"


async def evaluate_bag(
    session: AsyncSession, bag: ClientWallet, today: date | None = None
) -> list[Alert]:
    """Los avisos que tocan ahora a esta bolsa, ya marcados como enviados."""
    today = today or datetime.now(UTC).date()
    month = month_of(datetime.combine(today, datetime.min.time(), UTC))
    out: list[Alert] = []
    state = await bag_state(session, bag, today)
    base = {"balance_micros": bag.balance_micros, "currency": bag.currency}
    if state == "empty" and bag.empty_alerted_on != today:
        bag.empty_alerted_on = today
        out.append(Alert("client.wallet.empty", "critical", bag.tenant_id, base))
    elif state == "low" and bag.alert_low_enabled and bag.low_alerted_month != month:
        bag.low_alerted_month = month
        out.append(
            Alert(
                "client.wallet.low",
                "warning",
                bag.tenant_id,
                {**base, "base_micros": bag.month_base_micros},
            )
        )
    elif state == "not_enough" and bag.not_enough_alerted_month != month:
        bag.not_enough_alerted_month = month
        out.append(Alert("client.wallet.not_enough", "warning", bag.tenant_id, base))
    return out


async def record_agent_spend(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    spent: int,
    currency: str,
    now: datetime | None = None,
) -> list[Alert]:
    """Suma el gasto del mes del agente y aplica su tope. Dentro de la sesión del
    cliente (``agent_monthly_spend`` tiene RLS por cliente)."""
    from nexus_api.services import agent_states

    now = now or datetime.now(UTC)
    month = month_of(now)
    await session.execute(
        insert(AgentMonthlySpend)
        .values(tenant_id=tenant_id, agent_id=agent_id, month=month, spent_micros=spent)
        .on_conflict_do_update(
            index_elements=["tenant_id", "agent_id", "month"],
            set_={"spent_micros": AgentMonthlySpend.spent_micros + spent},
        )
    )
    row = await session.get(AgentMonthlySpend, (tenant_id, agent_id, month), populate_existing=True)
    agent = await session.get(Agent, agent_id)
    if row is None or agent is None or agent.monthly_cap_micros is None:
        return []
    cap = int(agent.monthly_cap_micros)
    out: list[Alert] = []
    data: dict[str, object] = {
        "agent_id": str(agent_id),
        "spent_micros": row.spent_micros,
        "cap_micros": cap,
        "currency": currency,
    }
    if row.spent_micros >= cap and row.reached_at is None:
        row.reached_at = now
        await agent_states.pause(
            session,
            agent,
            reason="agent_cap",
            by_kind="system",
            by_id=None,
            origin="system",
            actor="system",
        )
        out.append(Alert("agent.cap.reached", "critical", tenant_id, data))
    elif row.spent_micros >= CAP_WARN_SHARE * cap and row.warned_at is None:
        row.warned_at = now
        out.append(Alert("agent.cap.warning", "warning", tenant_id, data))
    await session.flush()
    return out


async def announce(alerts: list[Alert]) -> None:
    """Los avisos, al partner y (los de la bolsa) también al cliente."""
    from nexus_api.services.channel_config import announce as tell

    for alert in alerts:
        dedupe = f"{alert.kind}:{alert.tenant_id}:{datetime.now(UTC).date().isoformat()}"
        # La bolsa y el tope del agente: al partner y a las personas del cliente
        # (events.md §3, campana, correo y push).
        await tell(
            tenant_id=alert.tenant_id,
            kind=alert.kind,
            severity=alert.severity,
            data=dict(alert.data),
            dedupe_key=dedupe,
            to_client=True,
        )


__all__ = [
    "CAP_WARN_SHARE",
    "LOW_SHARE",
    "Alert",
    "announce",
    "bag_state",
    "days_left",
    "evaluate_bag",
    "pace_per_day",
    "rearm",
    "record_agent_spend",
]
