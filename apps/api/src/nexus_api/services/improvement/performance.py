"""El rendimiento de un agente y sus conversaciones, solo con metadatos — spec 047,
T174 (requisitos 51.1 y 51.2).

- :func:`agent_performance`: los últimos ``days`` días (30 en la consola), en
  total y por día UTC para la gráfica de bloques: conversaciones, cuántas pasaron
  a una persona, cuántas se resolvieron sin persona y el gasto.
- :func:`agent_conversations`: la lista, de la más reciente a la más antigua,
  con fecha, canal, duración, número de mensajes, resultado, motivo del traspaso
  y gasto.

**Nada sale de un texto.** Las consultas cuentan filas y suman importes; ninguna
proyecta ``messages.content`` ni un dato del cliente final (C1 y C8).

**Las mismas reglas que el Panel** (``client_overview.month_conversations``):

- una conversación es de un agente si Recepción se la derivó o, si no, si
  entró por su número; las de números sin agente son del agente principal;
- «pasada a una persona» es una escalada, una conversación que tomó una persona o
  una que espera con un motivo (salvo «fuera de la audiencia»);
- «resuelta sin persona» es todo lo demás;
- el Playground no es tráfico de clientes (``console_traffic``).

**El gasto es a precio, nunca a coste (C9)**: lo medido en la partida
Conversaciones (``usage_records.source = channel``) por 2,2, en cien milésimas de
US$, como el precio real de la pantalla Calidad.

Todo dentro de la transacción del cliente (RLS).
"""

from __future__ import annotations

import base64
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Channel,
    Conversation,
    ConversationStatus,
    Message,
    UsageRecord,
)
from nexus_api.services.agents import principal_agent_id
from nexus_api.services.console_traffic import customer_facing_channel
from nexus_api.services.wallet.usage_lines import PRICE_MULTIPLIER, UNITS

DEFAULT_DAYS: Final = 30
MAX_DAYS: Final = 90
#: La medición de las conversaciones (la partida que paga la bolsa del cliente).
CHANNEL_SOURCE: Final = "channel"


class CursorInvalid(ValueError):
    """El cursor de la lista no es uno que diera esta API."""


def handed_to_person() -> sa.ColumnElement[bool]:
    """«Pasada a una persona»: la misma regla que el mes del Panel."""
    return sa.or_(
        Conversation.status == ConversationStatus.ESCALATED,
        Conversation.assigned_user_id.is_not(None),
        sa.and_(
            Conversation.waiting_reason.is_not(None),
            Conversation.waiting_reason != "out_of_audience",
        ),
    )


def conversation_owner() -> sa.ColumnElement[Any]:
    """El agente de la conversación: al que la derivó Recepción o el de su número."""
    return sa.func.coalesce(Conversation.handled_by_agent_id, Channel.agent_id)


async def _is_principal(session: AsyncSession, agent_id: uuid.UUID) -> bool:
    return await principal_agent_id(session) == agent_id


def _mine(agent_id: uuid.UUID, *, principal: bool) -> sa.ColumnElement[bool]:
    owner = conversation_owner()
    return sa.or_(owner == agent_id, owner.is_(None)) if principal else owner == agent_id


def _spend_of(agent_id: uuid.UUID, *, principal: bool) -> sa.ColumnElement[bool]:
    mine = UsageRecord.agent_id == agent_id
    return sa.or_(mine, UsageRecord.agent_id.is_(None)) if principal else mine


def price_micros(cost_usd: Any) -> int:
    """Coste del modelo (US$) → precio en cien milésimas de US$."""
    return int((Decimal(str(cost_usd or 0)) * PRICE_MULTIPLIER * UNITS).to_integral_value())


def _utc_day(column: Any) -> sa.ColumnElement[date]:
    return sa.cast(sa.func.timezone("UTC", column), sa.Date)


# ── el rendimiento ─────────────────────────────────────────────────────────


@dataclass
class DayFigures:
    day: date
    conversations: int = 0
    handed_to_person: int = 0
    spent_micros: int = 0

    @property
    def resolved_without_person(self) -> int:
        return max(0, self.conversations - self.handed_to_person)


@dataclass
class Performance:
    days: int
    since: datetime
    until: datetime
    series: list[DayFigures] = field(default_factory=list)

    @property
    def conversations(self) -> int:
        return sum(d.conversations for d in self.series)

    @property
    def handed_to_person(self) -> int:
        return sum(d.handed_to_person for d in self.series)

    @property
    def resolved_without_person(self) -> int:
        return max(0, self.conversations - self.handed_to_person)

    @property
    def resolved_pct(self) -> float | None:
        total = self.conversations
        return round(self.resolved_without_person / total * 100, 1) if total else None

    @property
    def spent_micros(self) -> int:
        return sum(d.spent_micros for d in self.series)

    @property
    def spend_per_conversation_micros(self) -> int | None:
        total = self.conversations
        return round(self.spent_micros / total) if total else None


async def agent_performance(
    session: AsyncSession,
    agent_id: uuid.UUID,
    *,
    days: int = DEFAULT_DAYS,
    now: datetime | None = None,
) -> Performance:
    """Los últimos ``days`` días del agente, hoy incluido, día a día (UTC)."""
    now = now or datetime.now(UTC)
    days = max(1, min(days, MAX_DAYS))
    first = now.astimezone(UTC).date() - timedelta(days=days - 1)
    since = datetime(first.year, first.month, first.day, tzinfo=UTC)
    out = Performance(days=days, since=since, until=now)
    by_day = {first + timedelta(days=i): DayFigures(first + timedelta(days=i)) for i in range(days)}
    principal = await _is_principal(session, agent_id)

    day = _utc_day(Conversation.created_at)
    rows = (
        await session.execute(
            sa.select(day, sa.func.count(), sa.func.count().filter(handed_to_person()))
            .select_from(Conversation)
            .join(Channel, Channel.id == Conversation.channel_id)
            .where(
                customer_facing_channel(),
                _mine(agent_id, principal=principal),
                Conversation.created_at >= since,
                Conversation.created_at <= now,
            )
            .group_by(day)
        )
    ).all()
    for d, count, handed in rows:
        if d in by_day:
            by_day[d].conversations += int(count)
            by_day[d].handed_to_person += int(handed)

    spent_day = _utc_day(UsageRecord.occurred_at)
    for d, cost in (
        await session.execute(
            sa.select(spent_day, sa.func.sum(UsageRecord.cost_usd))
            .where(
                UsageRecord.source == CHANNEL_SOURCE,
                _spend_of(agent_id, principal=principal),
                UsageRecord.occurred_at >= since,
                UsageRecord.occurred_at <= now,
            )
            .group_by(spent_day)
        )
    ).all():
        if d in by_day:
            by_day[d].spent_micros += price_micros(cost)
    out.series = [by_day[d] for d in sorted(by_day)]
    return out


# ── la lista de conversaciones ─────────────────────────────────────────────


@dataclass(frozen=True)
class ConversationFacts:
    """Lo que se sabe de una conversación sin leerla."""

    id: uuid.UUID
    started_at: datetime
    last_activity_at: datetime
    channel_type: str | None
    messages_count: int
    duration_seconds: int | None
    handed_to_person: bool
    in_progress: bool
    handoff_reason: str | None
    spent_micros: int | None


def encode_cursor(at: datetime, conversation_id: uuid.UUID) -> str:
    raw = f"{at.isoformat()}|{conversation_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        at, cid = base64.urlsafe_b64decode(padded.encode()).decode().split("|", 1)
        return datetime.fromisoformat(at), uuid.UUID(cid)
    except Exception as exc:
        raise CursorInvalid(cursor) from exc


def _handoff_reason(conv: Conversation, handed: bool) -> str | None:
    """Un código, nunca un texto: la consola pone las palabras."""
    if not handed:
        return None
    if conv.waiting_reason and conv.waiting_reason != "out_of_audience":
        return conv.waiting_reason
    if conv.status == ConversationStatus.ESCALATED:
        return "escalated"
    return "taken_by_person"


async def agent_conversations(
    session: AsyncSession,
    agent_id: uuid.UUID,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[ConversationFacts], str | None]:
    """Una página de conversaciones del agente y el cursor de la siguiente."""
    principal = await _is_principal(session, agent_id)
    handed = handed_to_person().label("handed")
    stmt = (
        sa.select(Conversation, Channel.type.label("channel_type"), handed)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(customer_facing_channel(), _mine(agent_id, principal=principal))
    )
    if cursor:
        at, cid = decode_cursor(cursor)
        stmt = stmt.where(
            sa.tuple_(Conversation.created_at, Conversation.id)
            < sa.tuple_(sa.literal(at, sa.DateTime(timezone=True)), sa.literal(cid, sa.Uuid()))
        )
    rows = (
        await session.execute(
            stmt.order_by(Conversation.created_at.desc(), Conversation.id.desc()).limit(limit + 1)
        )
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    ids = [row[0].id for row in rows]

    stats: dict[uuid.UUID, tuple[int, datetime | None, datetime | None]] = {}
    spent: dict[uuid.UUID, int] = defaultdict(int)
    if ids:
        for cid, count, first_at, last_at in (
            await session.execute(
                sa.select(
                    Message.conversation_id,
                    sa.func.count(Message.id),
                    sa.func.min(Message.created_at),
                    sa.func.max(Message.created_at),
                )
                .where(Message.conversation_id.in_(ids))
                .group_by(Message.conversation_id)
            )
        ).all():
            stats[cid] = (int(count), first_at, last_at)
        for cid, cost in (
            await session.execute(
                sa.select(UsageRecord.conversation_id, sa.func.sum(UsageRecord.cost_usd))
                .where(
                    UsageRecord.source == CHANNEL_SOURCE,
                    UsageRecord.conversation_id.in_(ids),
                )
                .group_by(UsageRecord.conversation_id)
            )
        ).all():
            if cid is not None and cost is not None:
                spent[cid] += price_micros(cost)

    items: list[ConversationFacts] = []
    for row in rows:
        conv: Conversation = row[0]
        count, first_at, last_at = stats.get(conv.id, (0, None, None))
        was_handed = bool(row.handed)
        items.append(
            ConversationFacts(
                id=conv.id,
                started_at=conv.created_at,
                last_activity_at=last_at or conv.last_message_at or conv.updated_at,
                channel_type=row.channel_type.value if row.channel_type is not None else None,
                messages_count=count,
                duration_seconds=int((last_at - first_at).total_seconds())
                if first_at and last_at
                else None,
                handed_to_person=was_handed,
                in_progress=conv.status == ConversationStatus.OPEN,
                handoff_reason=_handoff_reason(conv, was_handed),
                spent_micros=spent.get(conv.id),
            )
        )
    next_cursor = encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if more and rows else None
    return items, next_cursor


__all__ = [
    "DEFAULT_DAYS",
    "MAX_DAYS",
    "ConversationFacts",
    "CursorInvalid",
    "DayFigures",
    "Performance",
    "agent_conversations",
    "agent_performance",
    "conversation_owner",
    "decode_cursor",
    "encode_cursor",
    "handed_to_person",
    "price_micros",
]
