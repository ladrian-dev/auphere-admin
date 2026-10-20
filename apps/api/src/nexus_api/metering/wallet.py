"""Libro Fase 3 — saldo, asignación y débito.

Unidad: ``quota_tokens()`` (C3). Este módulo no cambia esa política;
solo mueve enteros de cuota entre cubos.

Fail-closed: si el libro no se puede leer, el saldo es 0 y no hay LLM.
Se gasta ``included`` (si no ha caducado) y después ``purchased``.
El débito es idempotente por ``idempotency_key``.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.partner import Partner
from nexus_api.db.models.partner_wallet import (
    BUCKET_INCLUDED,
    BUCKET_PURCHASED,
    CREDIT_KINDS,
    KIND_ABSORBED,
    KIND_CREDIT_REVERSAL,
    KIND_DEBIT,
    KIND_EXPIRY,
    KIND_OPENING_CREDIT,
    KIND_OPENING_DEBIT,
    PartnerAllocation,
    PartnerWallet,
    UsageLedger,
)
from nexus_api.db.models.tenant import Tenant

log = structlog.get_logger(__name__)

_PARTNER_OF_TENANT = sa.text("SELECT partner_id FROM partner_tenants WHERE tenant_id = :t LIMIT 1")


class OverAllocation(Exception):
    """La suma de caps superaría el wallet (included efectivo + purchased)."""


@dataclass(frozen=True)
class WalletSnapshot:
    partner_id: uuid.UUID
    included_remaining: int
    #: What is left of what was bought; never negative (a debt is ``owed``).
    purchased_remaining: int
    included_expires_at: datetime | None
    available: int
    #: Spec 041: the postpaid credit line Auphere granted (credits); 0 = prepaid.
    credit_limit: int = 0
    #: Spec 041: what a postpaid partner consumed beyond its balance (credits).
    owed: int = 0

    @property
    def spendable_purchased(self) -> int:
        """What a turn may still draw from the purchased pocket: the balance,
        or the unused part of the credit line once the balance is negative."""
        return max(0, self.purchased_remaining - self.owed + self.credit_limit)

    @property
    def empty(self) -> bool:
        return self.available <= 0


@dataclass(frozen=True)
class DebitResult:
    spent: int
    from_included: int
    from_purchased: int
    duplicate: bool


def _now() -> datetime:
    return datetime.now(UTC)


def effective_included(
    remaining: int, expires_at: datetime | None, *, now: datetime | None = None
) -> int:
    """Included que todavía se puede gastar. Caducado = 0."""
    if remaining <= 0:
        return 0
    if expires_at is None:
        return 0
    stamp = now or _now()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= stamp:
        return 0
    return remaining


def split_spend(qty: int, included: int, purchased: int) -> tuple[int, int]:
    """Parte ``qty``: included primero, luego purchased. Nunca negativo."""
    if qty <= 0:
        return 0, 0
    take = min(qty, max(0, included) + max(0, purchased))
    from_included = min(take, max(0, included))
    from_purchased = take - from_included
    return from_included, from_purchased


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


async def partner_id_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID | None:
    """Partner dueño del tenant, o None. No lanza."""
    found = await session.scalar(_PARTNER_OF_TENANT, {"t": str(tenant_id)})
    if found is not None:
        return uuid.UUID(str(found))
    row = await session.scalar(sa.select(Tenant.partner_id).where(Tenant.id == tenant_id))
    if row is None:
        return None
    return uuid.UUID(str(row))


def _snapshot(row: PartnerWallet, *, now: datetime | None = None) -> WalletSnapshot:
    included = effective_included(row.included_remaining, row.included_expires_at, now=now)
    raw = _as_int(row.purchased_remaining)
    purchased = max(0, raw)
    return WalletSnapshot(
        partner_id=row.partner_id,
        included_remaining=included,
        purchased_remaining=purchased,
        included_expires_at=row.included_expires_at,
        available=included + purchased,
        credit_limit=_as_int(getattr(row, "credit_limit", 0) or 0),
        owed=max(0, -raw),
    )


async def _load_wallet_for_update(
    session: AsyncSession, partner_id: uuid.UUID
) -> PartnerWallet | None:
    row = await session.scalar(
        sa.select(PartnerWallet).where(PartnerWallet.partner_id == partner_id).with_for_update()
    )
    return row if isinstance(row, PartnerWallet) else None


def _expire_included(row: PartnerWallet, *, now: datetime | None = None) -> None:
    stamp = now or _now()
    expired = effective_included(row.included_remaining, row.included_expires_at, now=stamp) == 0
    if (
        expired
        and row.included_remaining
        and (row.included_expires_at is None or row.included_expires_at <= stamp)
    ):
        row.included_remaining = 0
        row.updated_at = stamp


#: Duración del período del pool incluido. Spec 004, R2.1.
POOL_PERIOD = timedelta(days=7)


def next_period_end(*, anchor: datetime, now: datetime | None = None) -> datetime:
    """El siguiente límite semanal contado desde ``anchor``.

    Spec 004, R2.1/R2.2. El ``anchor`` es ``partners.created_at``: ya existe, no
    se mueve nunca, y por tanto **no hace falta una columna de ancla** — un
    segundo estado que mantener sincronizado con el primero es el modo de fallo
    que esta spec elimina en otro sitio.

    Anclado al partner y **no a un lunes global** a propósito: un lunes global
    concentra la renovación de toda la plataforma en un tick, y le da una
    primera «semana» de dos días a quien se dé de alta un viernes. Anthropic
    ancla por cuenta («un horario fijo asignado a tu cuenta») por lo mismo.

    Siempre devuelve un instante **estrictamente futuro**: un límite igual al
    reloj caduca en el momento de escribirse y haría que el cron renovara dos
    veces seguidas.
    """
    stamp = now or _now()
    if anchor.tzinfo is None:
        # Algunos drivers devuelven ``created_at`` naive. Reventar aquí tumbaría
        # la renovación de todos los partners a la vez.
        anchor = anchor.replace(tzinfo=UTC)
    elapsed = stamp - anchor
    periods = elapsed // POOL_PERIOD + 1
    return anchor + POOL_PERIOD * periods


async def renew_included_if_expired(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    pool_size: int | None = None,
    now: datetime | None = None,
) -> bool:
    """Repone el included del mes si ya caducó (D3). ``True`` si renovó.

    Hasta esto, ``included_expires_at`` nacía a fin de mes y **nada lo
    renovaba**: el día 1 el saldo efectivo pasaba a 0 y con él se cerraba
    ``allow_channel_turn`` para todos los clientes del partner, sin error y
    sin aviso. En staging y en producción caducó el 2026-09-01.

    Se dispara por **caducidad, no por calendario**: si el scheduler estuvo
    caído el día 1, renueva en cuanto vuelve, en vez de esperar un mes. Y es
    idempotente — con el included vigente no toca nada, así que el tick
    horario solo hace trabajo una vez.

    **El período es SEMANAL desde la spec 004** y va anclado a la fecha de alta
    del partner; el tamaño sale de ``partners.weekly_pool_tokens``. Ya no se
    pasa un cap desde fuera salvo en pruebas: el que había —
    ``companion_monthly_token_cap``— dimensionaba a la vez esto y una suma
    sobre ``companion.runs``, y ésa era la deuda **D5**.

    **Lo no gastado NO se acumula** (R2.3): se repone al tamaño completo, no se
    suma encima. Acumular convierte un peor caso semanal acotado en un pico
    mensual de cuatro veces, que es justo lo que la ventana semanal evita.
    """
    stamp = now or _now()
    # Spec 005 (R5.2): el pool se repone **si la suscripción está al corriente**.
    #
    # Es el ÚNICO efecto de la escalera de impago, y vive aquí en vez de en el
    # paquete de cobro a propósito: quien decide si hay saldo es el libro, no
    # el proveedor. Una caída de Stripe no puede cambiar esta respuesta.
    #
    # Ni un teammate se archiva, ni una tarea se cancela, ni una confirmación
    # pendiente se invalida por un impago. Sólo deja de reponerse esto — y el
    # saldo comprado, que es dinero ya pagado, se sigue gastando igual.
    if not await _pool_refills_for(session, partner_id):
        return False
    anchor, size = await _pool_anchor_and_size(session, partner_id)
    if pool_size is not None:
        size = pool_size
    row = await _load_wallet_for_update(session, partner_id)
    if row is None:
        return False
    if effective_included(row.included_remaining, row.included_expires_at, now=stamp) > 0:
        return False
    row.included_remaining = max(0, size)
    row.included_expires_at = next_period_end(anchor=anchor, now=stamp)
    row.updated_at = stamp
    await session.flush()
    log.info(
        "wallet.included_renewed",
        partner_id=str(partner_id),
        granted=row.included_remaining,
        expires_at=row.included_expires_at.isoformat(),
    )
    return True


def top_up_amount(*, remaining: int, old_size: int, new_size: int) -> int:
    """Cuánto pool añadir al subir de nivel a mitad de semana (R6.2).

    **La diferencia de tamaño**, que es exactamente lo que el partner no tenía
    y acaba de pagar. Ni el tamaño nuevo entero —eso regalaría lo ya
    consumido— ni nada —eso le cobraría el nivel nuevo sin dárselo, que es
    peor porque pagó y no notó nada.

    Que el resultado no dependa de ``remaining`` es la propiedad, no un
    descuido: lo gastado ya se gastó, y lo que cambia al subir es el techo.
    Por eso también funciona cuando el ciclo se repone en el mismo instante —
    reponer pone ``remaining`` al tamaño viejo y esto añade la diferencia, así
    que el resultado es el tamaño nuevo, ni duplicado ni a cero (R6.5).

    Nunca devuelve un número negativo: esta función solo suma. Bajar de nivel
    se aplica a fin de período y no toca el pool en curso.
    """
    del remaining  # parte de la firma para que el contrato se lea entero
    return max(0, _as_int(new_size) - _as_int(old_size))


async def apply_tier_change(session: AsyncSession, *, partner_id: uuid.UUID, new_tier: str) -> str:
    """Aplica un cambio de nivel al LIBRO. Devuelve ``"upgraded"`` o ``"scheduled"``.

    El reparto con el proveedor: **el dinero lo prorratea él** —esta función no
    calcula días ni importes— y **el pool lo completamos nosotros**, porque es
    nuestro libro y el proveedor no sabe qué es.

    Subir es inmediato: quien sube lo hace justo cuando se ha quedado sin pool,
    y hacerle esperar al siguiente ciclo es cobrarle por algo que todavía no
    puede usar.

    Bajar **se anota como pendiente** y no toca nada del ciclo en curso: el
    partner pagó esta semana entera. Se aplica cuando el proveedor confirme el
    período nuevo.
    """
    current = (
        await session.execute(
            sa.text("SELECT tier_code FROM partner_subscriptions WHERE partner_id = :p"),
            {"p": str(partner_id)},
        )
    ).scalar_one_or_none()

    rows = (
        await session.execute(
            sa.text(
                "SELECT code, weekly_pool_tokens FROM membership_tiers WHERE code = ANY(:codes)"
            ),
            {"codes": [c for c in (current, new_tier) if c]},
        )
    ).all()
    sizes: dict[str, int] = {str(row[0]): int(row[1]) for row in rows}
    old_size = sizes.get(current or "", 0)
    new_size = sizes.get(new_tier, 0)

    if new_size <= old_size:
        # Bajar: pendiente, y reemplaza cualquier bajada anterior. Cambiar de
        # opinión antes de que se aplique no puede dejar dos programadas.
        await session.execute(
            sa.text(
                "UPDATE partner_subscriptions SET pending_tier_code = :t WHERE partner_id = :p"
            ),
            {"t": new_tier, "p": str(partner_id)},
        )
        log.info("wallet.tier_downgrade_scheduled", partner_id=str(partner_id), tier=new_tier)
        return "scheduled"

    added = top_up_amount(remaining=0, old_size=old_size, new_size=new_size)
    await session.execute(
        sa.text(
            "UPDATE partner_wallets SET included_remaining = included_remaining + :n, "
            "updated_at = now() WHERE partner_id = :p"
        ),
        {"n": added, "p": str(partner_id)},
    )
    await session.execute(
        sa.text(
            "UPDATE partner_subscriptions SET tier_code = :t, pending_tier_code = NULL "
            "WHERE partner_id = :p"
        ),
        {"t": new_tier, "p": str(partner_id)},
    )
    await session.execute(
        sa.text("UPDATE partners SET weekly_pool_tokens = :n WHERE id = :p"),
        {"n": new_size, "p": str(partner_id)},
    )
    log.info(
        "wallet.tier_upgraded",
        partner_id=str(partner_id),
        tier=new_tier,
        topped_up=added,
    )
    return "upgraded"


async def _pool_refills_for(session: AsyncSession, partner_id: uuid.UUID) -> bool:
    """Si la suscripción del partner permite reponer el pool incluido.

    **Un partner sin fila repone.** La ausencia de suscripción es el nivel
    gratuito, que también tiene pool; exigir una fila haría que todo partner
    nuevo naciera sin reposición hasta que alguien la sembrara, y eso es el
    modo de fallo del 31 de agosto — cuentas que nacen mudas.

    Se consulta con SQL y no por el modelo para no arrastrar el paquete de
    cobro al camino del turno: esta función se llama al servir, y CE-004 dice
    que con el proveedor caído el trabajo continúa.
    """
    # Spec 034: with memberships off the console is free and the pool refills
    # whatever a (leftover) subscription row says.
    from nexus_api.config import get_settings

    if not get_settings().membership_enabled:
        return True
    state = await session.scalar(
        sa.text("SELECT state FROM partner_subscriptions WHERE partner_id = :p"),
        {"p": str(partner_id)},
    )
    return state is None or state == "current"


async def _pool_anchor_and_size(
    session: AsyncSession, partner_id: uuid.UUID
) -> tuple[datetime, int]:
    """Fecha de alta del partner y tamaño de su pool semanal.

    Una sola lectura: el ancla y el tamaño viven los dos en ``partners`` y se
    usan siempre juntos.
    """
    row = (
        await session.execute(
            sa.select(Partner.created_at, Partner.weekly_pool_tokens).where(
                Partner.id == partner_id
            )
        )
    ).first()
    if row is None:
        return _now(), 0
    created_at, size = row
    return (created_at or _now()), int(size or 0)


def month_start(now: datetime | None = None) -> date:
    """First day of the calendar month (UTC) ``now`` falls in."""
    stamp = now or _now()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).date().replace(day=1)


async def replenish_allocations(
    session: AsyncSession, *, partner_id: uuid.UUID, now: datetime | None = None
) -> int:
    """Refill the partner's client caps **once per calendar month** (UTC).

    Spec 033 (R6.1, owner 2026-10-18): the cap is a monthly spending limit
    and the client reads "spent this month" next to it. Until then it
    refilled with the weekly pool, so cap minus remaining never matched the
    month's spend and a client got four limits a month.

    A row refills when its ``period_month`` is before the current month:
    ``remaining`` goes back to ``cap`` and ``period_month`` moves to this
    month, so a second tick in the same month touches nothing. Only up,
    never down: what the partner sets as cap is the partner's decision.
    Returns the rows refilled.
    """
    current = month_start(now)
    result = await session.execute(
        sa.update(PartnerAllocation)
        .where(
            PartnerAllocation.partner_id == partner_id,
            PartnerAllocation.period_month < current,
        )
        .values(remaining=PartnerAllocation.cap, period_month=current, updated_at=_now())
    )
    # ``getattr`` y no ``result.rowcount``: el tipo estático de ``execute``
    # es ``Result``, que no declara ``rowcount``.
    touched = int(getattr(result, "rowcount", 0) or 0)
    if touched:
        log.info("wallet.allocations_replenished", partner_id=str(partner_id), rows=touched)
    return touched


async def read_wallet(partner_id: uuid.UUID) -> WalletSnapshot | None:
    """Saldo bajo RLS. None si no hay fila. None (y log) si el libro no se lee."""
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            row = await session.get(PartnerWallet, partner_id)
            if row is None:
                return None
            return _snapshot(row)
    except Exception as exc:
        log.warning("wallet.unreadable", partner_id=str(partner_id), error=str(exc))
        return None


async def companion_wallet_remaining(partner_id: uuid.UUID) -> int:
    """Saldo del cubo reserva (wallet) que gasta el Companion."""
    snap = await read_wallet(partner_id)
    if snap is None:
        return 0
    return snap.available


async def companion_allocation_remaining(partner_id: uuid.UUID, tenant_id: uuid.UUID | None) -> int:
    """``remaining`` de la asignación del cliente del hilo.

    Sin tenant, sin fila, remaining 0 o libro ilegible → 0 (fail-closed).
    No mira ``partner_wallets``: ese cubo es reserva / no asignado.
    """
    if tenant_id is None:
        return 0
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            remaining = await session.scalar(
                sa.select(PartnerAllocation.remaining).where(
                    PartnerAllocation.partner_id == partner_id,
                    PartnerAllocation.tenant_id == tenant_id,
                )
            )
            return max(0, _as_int(remaining))
    except Exception as exc:
        log.warning(
            "wallet.allocation_unreadable",
            partner_id=str(partner_id),
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        return 0


async def _is_unlimited(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    found = await session.scalar(
        sa.select(Tenant.unlimited_consumption).where(Tenant.id == tenant_id)
    )
    return bool(found)


async def unlimited_among(session: AsyncSession, tenant_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """The clients among ``tenant_ids`` whose consumption Auphere covers
    (owner, 2026-10-20). ``tenants`` is platform data: readable from any
    session, before or after the partner's GUC."""
    if not tenant_ids:
        return set()
    rows = await session.scalars(
        sa.select(Tenant.id).where(
            Tenant.id.in_(tenant_ids), Tenant.unlimited_consumption.is_(True)
        )
    )
    return set(rows.all())


async def is_unlimited(tenant_id: uuid.UUID) -> bool:
    """Whether Auphere covers this client's consumption. Raises when it
    cannot be read: the caller (the worker's debit) retries rather than
    guess who pays."""
    sm = get_sessionmaker()
    async with sm() as session:
        return await _is_unlimited(session, tenant_id)


async def allow_channel_turn(tenant_id: uuid.UUID) -> bool:
    """¿Puede el canal abrir el pipeline?

    Sin partner (tenant directo / tests legacy) → sí, el libro no aplica.
    Con partner: saldo recargado 0, sin asignación, asignación 0 o libro
    ilegible → no. Un cliente con consumo ilimitado (owner, 2026-10-20) → sí,
    sin mirar saldo ni tope: su consumo lo asume Auphere.

    Spec 033 (R5.1): la puerta mira el **saldo recargado**, el mismo bolsillo
    que paga el turno (``debit_wallet(..., allow_included=False)``). Mirando
    incluido + recargado, un partner con solo pool semanal abría turnos que
    después no se cobraban (seguimiento abierto de ``doble-cobro-del-tope``).
    """
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            partner_id = await partner_id_for_tenant(session, tenant_id)
            if partner_id is None:
                return True
            if await _is_unlimited(session, tenant_id):
                return True
            await apply_partner_to_session(session, partner_id)
            row = await session.get(PartnerWallet, partner_id)
            if row is None:
                return False
            # Spec 041: a postpaid partner keeps serving inside its credit line.
            if _snapshot(row).spendable_purchased <= 0:
                return False
            alloc = await session.scalar(
                sa.select(PartnerAllocation).where(
                    PartnerAllocation.partner_id == partner_id,
                    PartnerAllocation.tenant_id == tenant_id,
                )
            )
            return not (alloc is None or _as_int(alloc.remaining) <= 0)
    except Exception as exc:
        log.warning("wallet.channel_unreadable", tenant_id=str(tenant_id), error=str(exc))
        return False


async def quota_state(partner_id: uuid.UUID, tenant_ids: list[uuid.UUID]) -> dict[uuid.UUID, bool]:
    """``tenant_id → out_of_quota`` for a batch of a partner's clients.

    The ONE definition of "this client cannot take a turn for lack of
    quota", with the same reading as ``allow_channel_turn``: no wallet, an
    empty wallet, no allocation row, or ``remaining <= 0`` → ``True``; a
    client with unlimited consumption → ``False``, always. The
    console's health, list, home and the out-of-quota notice all read this
    so the screen and the gate never disagree (spec 016, R2.1/R2.5).

    Opens its own partner-scoped session: ``partner_allocations`` is FORCE
    RLS by ``app.partner_id`` and is invisible from a tenant-scoped one.
    Fails closed — an unreadable ledger reads as out of quota, which is
    what the gate does too. A tenant that is not the partner's is simply
    absent from the result.
    """
    if not tenant_ids:
        return {}
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            unlimited = await unlimited_among(session, tenant_ids)
            await apply_partner_to_session(session, partner_id)
            row = await session.get(PartnerWallet, partner_id)
            # Same pocket as the gate (spec 033, R5.1): the recharged balance.
            wallet_empty = row is None or _snapshot(row).spendable_purchased <= 0
            rows = await session.execute(
                sa.select(PartnerAllocation.tenant_id, PartnerAllocation.remaining).where(
                    PartnerAllocation.partner_id == partner_id,
                    PartnerAllocation.tenant_id.in_(tenant_ids),
                )
            )
            remaining = {tid: _as_int(rem) for tid, rem in rows.all()}
        return {
            tid: tid not in unlimited
            and (wallet_empty or tid not in remaining or remaining[tid] <= 0)
            for tid in tenant_ids
        }
    except Exception as exc:
        log.warning("wallet.quota_state_unreadable", partner_id=str(partner_id), error=str(exc))
        return dict.fromkeys(tenant_ids, True)


async def allocations_for(
    partner_id: uuid.UUID, tenant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """``tenant_id → (cap, remaining)`` for a batch of a partner's clients
    (spec 017, R1.2/R9.1). A tenant without an allocation row is absent —
    «sin cupo asignado». Same partner-scoped session as ``quota_state``;
    fails closed to «nothing readable»."""
    if not tenant_ids:
        return {}
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            rows = await session.execute(
                sa.select(
                    PartnerAllocation.tenant_id, PartnerAllocation.cap, PartnerAllocation.remaining
                ).where(
                    PartnerAllocation.partner_id == partner_id,
                    PartnerAllocation.tenant_id.in_(tenant_ids),
                )
            )
            return {tid: (_as_int(cap), _as_int(rem)) for tid, cap, rem in rows.all()}
    except Exception as exc:
        log.warning("wallet.allocations_unreadable", partner_id=str(partner_id), error=str(exc))
        return {}


#: Ledger entries the double cap debit wrote (bug ``doble-cobro-del-tope``,
#: 2026-09-02 → 2026-10-10): a second, wrong decrement of a client's cap, not
#: money spent. Since spec 033 they carry ``kind='allocation_legacy'``.
ALLOCATION_KEY_SUFFIX = ":allocation"


def _spend_only() -> sa.ColumnElement[bool]:
    """Spec 033 (R2.3): spend is a debit and nothing else.

    Until then spend was «every entry not ending in ``:allocation``», so an
    admin top-up and a credit expiry — both written with ``tenant_id`` NULL —
    showed up as spend outside clients on the partner's home and usage.
    """
    return UsageLedger.kind == KIND_DEBIT


@dataclass(frozen=True)
class AgentFilter:
    """Spec 030: the spend of one agent. The principal also owns what was
    spent before agents existed (``usage_ledger.agent_id IS NULL``)."""

    agent_id: uuid.UUID
    is_principal: bool

    def clause(self) -> sa.ColumnElement[bool]:
        mine = UsageLedger.agent_id == self.agent_id
        return sa.or_(mine, UsageLedger.agent_id.is_(None)) if self.is_principal else mine


async def credit_burn(
    partner_id: uuid.UUID,
    tenant_ids: list[uuid.UUID],
    since: datetime,
    until: datetime | None = None,
    *,
    agent: AgentFilter | None = None,
) -> dict[uuid.UUID | None, int]:
    """Spec 026: credit spent since ``since``, per client of the partner.

    ``None`` keys what was spent outside a client (the Companion). Read from
    ``usage_ledger`` in the same partner-scoped session as the allocations;
    an unreadable ledger reads as «nothing known» (``{}``), never as zero
    spend, so the home page shows no autonomy rather than a wrong one.
    """
    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            rows = await session.execute(
                sa.select(UsageLedger.tenant_id, sa.func.sum(UsageLedger.qty))
                .where(
                    UsageLedger.partner_id == partner_id,
                    UsageLedger.created_at >= since,
                    UsageLedger.created_at < until if until is not None else sa.true(),
                    sa.or_(UsageLedger.tenant_id.is_(None), UsageLedger.tenant_id.in_(tenant_ids)),
                    agent.clause() if agent is not None else sa.true(),
                    _spend_only(),
                )
                .group_by(UsageLedger.tenant_id)
            )
            return {tid: _as_int(total) for tid, total in rows.all()}
    except Exception as exc:
        log.warning("wallet.burn_unreadable", partner_id=str(partner_id), error=str(exc))
        return {}


async def credit_burn_by_agent(
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    since: datetime,
    until: datetime | None = None,
) -> dict[uuid.UUID | None, int]:
    """Spec 030: what one client spent since ``since``, per agent.

    The same rows as :func:`credit_burn` for that client, grouped by
    ``usage_ledger.agent_id``; ``None`` keys what was spent before agents
    existed (it was the principal's). Raises when unreadable — the caller
    shows no breakdown rather than a wrong one.
    """
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        rows = await session.execute(
            sa.select(UsageLedger.agent_id, sa.func.sum(UsageLedger.qty))
            .where(
                UsageLedger.partner_id == partner_id,
                UsageLedger.tenant_id == tenant_id,
                UsageLedger.created_at >= since,
                UsageLedger.created_at < until if until is not None else sa.true(),
                _spend_only(),
            )
            .group_by(UsageLedger.agent_id)
        )
        return {aid: _as_int(total) for aid, total in rows.all()}


async def credit_burn_by_day(
    partner_id: uuid.UUID,
    tenant_ids: list[uuid.UUID],
    since: datetime,
    *,
    include_outside: bool = True,
    agent: AgentFilter | None = None,
) -> dict[tuple[uuid.UUID | None, date], int]:
    """Spec 028: credit spent per client and UTC day since ``since``.

    ``None`` keys the spend outside any client (the Companion), only when
    ``include_outside``. Same partner-scoped read as :func:`credit_burn`;
    an unreadable ledger raises, so the screen says it failed instead of
    drawing a flat zero.
    """
    day = sa.cast(sa.func.timezone("UTC", UsageLedger.created_at), sa.Date)
    who: sa.ColumnElement[bool] = UsageLedger.tenant_id.in_(tenant_ids)
    if include_outside:
        who = sa.or_(UsageLedger.tenant_id.is_(None), who)
    if agent is not None:
        who = sa.and_(who, agent.clause())
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        rows = await session.execute(
            sa.select(UsageLedger.tenant_id, day, sa.func.sum(UsageLedger.qty))
            .where(
                UsageLedger.partner_id == partner_id,
                UsageLedger.created_at >= since,
                who,
                _spend_only(),
            )
            .group_by(UsageLedger.tenant_id, day)
        )
        return {(tid, d): _as_int(total) for tid, d, total in rows.all()}


@dataclass(frozen=True)
class CreditResult:
    """What a top-up did. ``duplicate``: the key was already in the book and
    nothing was credited this time — the snapshot is the balance as it is."""

    snapshot: WalletSnapshot
    duplicate: bool
    before_available: int


#: Called inside the top-up's transaction, after the balance moved: the audit
#: row lands in the same commit as the money or not at all (spec 033, R3.3).
AuditHook = Callable[[AsyncSession, WalletSnapshot, WalletSnapshot], Awaitable[None]]


async def add_purchased(
    partner_id: uuid.UUID,
    qty: int,
    *,
    kind: str,
    idempotency_key: str,
    audit: AuditHook | None = None,
) -> CreditResult:
    """Credit purchased balance — **one transaction, one entry, at most once**.

    Spec 033 (R2.2, R3): balance, ledger entry and (optional) audit commit
    together. The entry's ``idempotency_key`` is the caller's: the admin
    sends the key its form generated, Stripe uses the Checkout Session id.
    The same key twice credits once and returns ``duplicate=True``.

    The wallet row is locked first (``FOR UPDATE``), so two calls with the same
    key serialise and the second one sees the first one's entry.
    """
    if qty <= 0:
        raise ValueError("top-up qty must be > 0")
    if kind not in CREDIT_KINDS:
        raise ValueError(f"not a credit kind: {kind!r}")
    sm = get_sessionmaker()
    for attempt in range(2):
        try:
            async with sm() as session, session.begin():
                await apply_partner_to_session(session, partner_id)
                row = await _load_wallet_for_update(session, partner_id)
                if row is None:
                    row = PartnerWallet(
                        partner_id=partner_id,
                        included_remaining=0,
                        purchased_remaining=0,
                    )
                    session.add(row)
                    await session.flush()
                before = _snapshot(row)
                seen = await session.scalar(
                    sa.select(UsageLedger.id).where(UsageLedger.idempotency_key == idempotency_key)
                )
                if seen is not None:
                    return CreditResult(
                        snapshot=before, duplicate=True, before_available=before.available
                    )
                session.add(
                    UsageLedger(
                        partner_id=partner_id,
                        tenant_id=None,
                        qty=qty,
                        bucket=BUCKET_PURCHASED,
                        kind=kind,
                        idempotency_key=idempotency_key,
                        fx=None,
                    )
                )
                row.purchased_remaining = _as_int(row.purchased_remaining) + qty
                row.updated_at = _now()
                await session.flush()
                after = _snapshot(row)
                if audit is not None:
                    await audit(session, before, after)
                return CreditResult(
                    snapshot=after, duplicate=False, before_available=before.available
                )
        except IntegrityError:
            # Two first top-ups racing to create the wallet row: the loser
            # retries once and then sees the row (and maybe the entry).
            if attempt == 1:
                raise
    raise AssertionError("unreachable")  # pragma: no cover


class NotEnoughBalance(Exception):
    """Taking a credit back would leave the purchased balance below zero."""

    def __init__(self, available: int, qty: int) -> None:
        super().__init__(f"available {available} < qty {qty}")
        self.available = available
        self.qty = qty


async def reverse_purchased(
    partner_id: uuid.UUID,
    qty: int,
    *,
    idempotency_key: str,
    audit: AuditHook | None = None,
) -> CreditResult:
    """Take back a credit — the mirror of :func:`add_purchased`.

    Owner, 2026-10-20: voiding a payment recorded by mistake takes its credit
    back. One transaction, one ``credit_reversal`` entry, at most once by key.
    Refused with :class:`NotEnoughBalance` when the partner already spent it:
    the balance never goes below zero for a correction (the credit line is for
    postpaid spend, not for this).
    """
    if qty <= 0:
        raise ValueError("reversal qty must be > 0")
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        row = await _load_wallet_for_update(session, partner_id)
        if row is None:
            raise NotEnoughBalance(0, qty)
        before = _snapshot(row)
        seen = await session.scalar(
            sa.select(UsageLedger.id).where(UsageLedger.idempotency_key == idempotency_key)
        )
        if seen is not None:
            return CreditResult(snapshot=before, duplicate=True, before_available=before.available)
        available = _as_int(row.purchased_remaining)
        if available < qty:
            raise NotEnoughBalance(available, qty)
        session.add(
            UsageLedger(
                partner_id=partner_id,
                tenant_id=None,
                qty=qty,
                bucket=BUCKET_PURCHASED,
                kind=KIND_CREDIT_REVERSAL,
                idempotency_key=idempotency_key,
                fx=None,
            )
        )
        row.purchased_remaining = available - qty
        row.updated_at = _now()
        await session.flush()
        after = _snapshot(row)
        if audit is not None:
            await audit(session, before, after)
        return CreditResult(snapshot=after, duplicate=False, before_available=before.available)


async def purchased_spent_since(partner_id: uuid.UUID, since: datetime) -> int:
    """Recharged balance spent since ``since`` — debits of the purchased
    bucket, every client and the Companion. Raises when unreadable."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        total = await session.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(UsageLedger.qty), 0)).where(
                UsageLedger.partner_id == partner_id,
                UsageLedger.kind == KIND_DEBIT,
                UsageLedger.bucket == BUCKET_PURCHASED,
                UsageLedger.created_at >= since,
            )
        )
        return _as_int(total)


@dataclass(frozen=True)
class Reconciliation:
    """Spec 033 (R2.4): the purchased balance as stored and as the book says.

    Only the purchased bucket is money; the included pool is a weekly
    allowance that refills whole and is not reconciled.
    """

    stored: int
    credits: int
    debits: int
    expiries: int

    @property
    def expected(self) -> int:
        return self.credits - self.debits - self.expiries

    @property
    def difference(self) -> int:
        return self.stored - self.expected

    @property
    def balanced(self) -> bool:
        return self.difference == 0


async def reconcile_purchased(partner_id: uuid.UUID) -> Reconciliation | None:
    """Stored purchased balance against sum(credits) - sum(purchased debits) - sum(
    expiries), under the partner's GUC. ``None`` if the partner has no wallet.
    Raises when the ledger cannot be read: a reconciliation that guesses is
    worse than none."""
    plus = (*CREDIT_KINDS, KIND_OPENING_CREDIT)
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        stored = await session.scalar(
            sa.select(PartnerWallet.purchased_remaining).where(
                PartnerWallet.partner_id == partner_id
            )
        )
        if stored is None:
            return None
        row = (
            await session.execute(
                sa.select(
                    sa.func.coalesce(
                        sa.func.sum(UsageLedger.qty).filter(UsageLedger.kind.in_(plus)), 0
                    ),
                    sa.func.coalesce(
                        sa.func.sum(UsageLedger.qty).filter(
                            UsageLedger.kind == KIND_DEBIT,
                            UsageLedger.bucket == BUCKET_PURCHASED,
                        ),
                        0,
                    ),
                    sa.func.coalesce(
                        sa.func.sum(UsageLedger.qty).filter(
                            UsageLedger.kind.in_(
                                (KIND_EXPIRY, KIND_OPENING_DEBIT, KIND_CREDIT_REVERSAL)
                            )
                        ),
                        0,
                    ),
                ).where(UsageLedger.partner_id == partner_id)
            )
        ).one()
        return Reconciliation(
            stored=_as_int(stored),
            credits=_as_int(row[0]),
            debits=_as_int(row[1]),
            expiries=_as_int(row[2]),
        )


async def allocatable_for(
    session: AsyncSession, partner_id: uuid.UUID, tenant_id: uuid.UUID
) -> int:
    """Saldo **comprado** aún no comprometido en otros clientes. Informativo.

    Spec 004, R6.1: desde que los clientes finales gastan solo comprado (R5.2),
    el cubo relevante es ése y no el disponible entero.

    **Ya no es un límite.** El tope por cliente dejó de ser una reserva sobre un
    saldo y pasó a ser lo que su nombre dice: un límite de gasto mensual que el
    partner fija para que un cliente no se lo lleve todo. Acotarlo por el saldo
    del momento hacía que un partner sin créditos no pudiera dar cuota a nadie
    —y sus clientes **nacían mudos**, que es el modo de fallo que costó el corte
    del 31-ago—. Quien decide si un turno pasa es ``allow_channel_turn``, que
    mira el saldo real en cada turno; ésta es una cifra para la pantalla.
    """
    wallet = await session.get(PartnerWallet, partner_id)
    if wallet is None:
        return 0
    others = _as_int(
        await session.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(PartnerAllocation.cap), 0)).where(
                PartnerAllocation.partner_id == partner_id,
                PartnerAllocation.tenant_id != tenant_id,
            )
        )
    )
    return max(0, _as_int(wallet.purchased_remaining) - others)


async def seed_default_allocation(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    default_cap: int,
) -> int:
    """Siembra la cuota inicial de un cliente recién creado (D1).

    Corre **en la sesión de quien crea el tenant**, no en una propia: la
    cuota y el cliente nacen en la misma transacción o no nace ninguno. Ese
    era el agujero — el wizard, ``provision_partner_client`` y la migración
    0094 creaban clientes y ninguno escribía en ``partner_allocations``, así
    que ``allow_channel_turn`` los dejaba mudos sin error ni aviso.

    Nunca falla la creación del cliente:

    - si ya hay fila, no la toca (idempotente, como el resto del provisioning);
    - si el partner no tiene disponible para el defecto, siembra lo que quede,
      que puede ser 0. Una fila con cap 0 es visible en Consumo y explicable;
      la ausencia de fila es el silencio que costó el corte del 31-ago.

    Devuelve el cap sembrado.
    """
    if default_cap < 0:
        raise ValueError("default cap must be >= 0")
    existing = await session.scalar(
        sa.select(PartnerAllocation).where(
            PartnerAllocation.partner_id == partner_id,
            PartnerAllocation.tenant_id == tenant_id,
        )
    )
    if existing is not None:
        return _as_int(existing.cap)
    # Se siembra el defecto ENTERO. Recortarlo por el saldo del momento es lo
    # que hacía nacer mudo al cliente de un partner sin créditos: el tope es un
    # límite de gasto, no una reserva, y el saldo lo comprueba cada turno.
    cap = default_cap
    session.add(
        PartnerAllocation(
            partner_id=partner_id,
            tenant_id=tenant_id,
            cap=cap,
            remaining=cap,
        )
    )
    await session.flush()
    return cap


async def set_allocation(
    partner_id: uuid.UUID, tenant_id: uuid.UUID, cap: int
) -> PartnerAllocation:
    """Crea o actualiza el **límite de gasto mensual** de un tenant.

    Spec 004, R6: esto ya no es una porción reservada del libro. Es el techo que
    el partner le pone a un cliente para que no se lleve todo el saldo, y por
    eso **no se comprueba contra el saldo del momento**: hacerlo dejaba a los
    clientes de un partner sin créditos con cuota cero —naciendo mudos, el modo
    de fallo del corte del 31-ago— y no protegía de nada que
    ``allow_channel_turn`` no proteja ya en cada turno.

    ``OverAllocation`` se conserva para el caso en que no hay libro en absoluto:
    un tope sobre un partner que no tiene wallet no significa nada.
    """
    if cap < 0:
        raise ValueError("cap must be >= 0")
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        wallet = await _load_wallet_for_update(session, partner_id)
        if wallet is None:
            raise OverAllocation("no wallet")
        row = await session.scalar(
            sa.select(PartnerAllocation)
            .where(
                PartnerAllocation.partner_id == partner_id,
                PartnerAllocation.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if row is None:
            row = PartnerAllocation(
                partner_id=partner_id,
                tenant_id=tenant_id,
                cap=cap,
                remaining=cap,
            )
            session.add(row)
        else:
            delta = cap - _as_int(row.cap)
            row.cap = cap
            if delta < 0:
                row.remaining = min(_as_int(row.remaining), cap)
            else:
                row.remaining = _as_int(row.remaining) + delta
            row.updated_at = _now()
        await session.flush()
        await session.refresh(row)
        return row


class SameClient(Exception):
    """Origen y destino del movimiento son el mismo cliente."""


class InsufficientCap(Exception):
    """El origen no tiene tope suficiente para ceder ``qty``."""

    def __init__(self, cap: int, qty: int) -> None:
        super().__init__(f"cap {cap} < qty {qty}")
        self.cap = cap
        self.qty = qty


def _credit_allocation(row: PartnerAllocation, qty: int) -> None:
    """Sube el tope del destino.

    Función aparte a propósito: el test de atomicidad (spec 016, CE-003) la
    hace fallar después de que el origen ya ha bajado y comprueba que la
    transacción lo deshace. Si se pliega dentro de ``move_allocation`` el
    test deja de poder inyectar el fallo en el punto que importa.
    """
    row.cap = _as_int(row.cap) + qty
    row.remaining = _as_int(row.remaining) + qty
    row.updated_at = _now()


async def move_allocation(
    partner_id: uuid.UUID, from_tenant: uuid.UUID, to_tenant: uuid.UUID, qty: int
) -> tuple[PartnerAllocation, PartnerAllocation]:
    """Mueve ``qty`` de tope de un cliente a otro **en una transacción**.

    Spec 016 (R3.1): antes eran dos ``PUT`` seguidos, y si el segundo fallaba
    el partner perdía el tope que acababa de quitar al primero. Aquí las dos
    filas se bloquean en orden de ``tenant_id`` (dos movimientos cruzados no
    se interbloquean) y o cambian las dos o no cambia ninguna.

    Origen: ``cap -= qty`` y ``remaining`` recortado al tope nuevo, como en
    ``set_allocation``. Destino: ``cap += qty`` y ``remaining += qty``; si no
    tenía fila, nace con ``qty``. ``SameClient`` e ``InsufficientCap(cap,
    qty)`` son los dos errores de negocio; ``OverAllocation`` sigue
    significando «este partner no tiene libro».
    """
    if qty <= 0:
        raise ValueError("qty must be > 0")
    if from_tenant == to_tenant:
        raise SameClient("from and to are the same tenant")
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        wallet = await _load_wallet_for_update(session, partner_id)
        if wallet is None:
            raise OverAllocation("no wallet")
        rows = (
            (
                await session.execute(
                    sa.select(PartnerAllocation)
                    .where(
                        PartnerAllocation.partner_id == partner_id,
                        PartnerAllocation.tenant_id.in_([from_tenant, to_tenant]),
                    )
                    .order_by(PartnerAllocation.tenant_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        by_tenant = {row.tenant_id: row for row in rows}
        source = by_tenant.get(from_tenant)
        source_cap = _as_int(source.cap) if source is not None else 0
        if source is None or source_cap < qty:
            raise InsufficientCap(source_cap, qty)
        target = by_tenant.get(to_tenant)
        if target is None:
            target = PartnerAllocation(
                partner_id=partner_id, tenant_id=to_tenant, cap=0, remaining=0
            )
            session.add(target)
        source.cap = source_cap - qty
        source.remaining = min(_as_int(source.remaining), source.cap)
        source.updated_at = _now()
        _credit_allocation(target, qty)
        await session.flush()
        await session.refresh(source)
        await session.refresh(target)
        return source, target


async def debit_wallet(
    *,
    partner_id: uuid.UUID,
    qty: int,
    idempotency_key: str,
    tenant_id: uuid.UUID | None = None,
    usage_record_id: uuid.UUID | None = None,
    # Spec 030: the client's agent the debit belongs to (spend per agent).
    agent_id: uuid.UUID | None = None,
    companion_run_id: uuid.UUID | None = None,
    allow_included: bool = True,
) -> DebitResult:
    """Debita ``qty`` (unidad C3). Included primero. Misma clave = no dobla.

    Si no queda nada, ``spent=0`` y no escribe asiento (no se gasta sin cuota).
    Un débito partido en dos cubos usa ``{key}:included`` y ``{key}:purchased``.

    ``allow_included=False`` **cierra el cubo incluido para este llamante** y
    lo deja gastando solo comprado (spec 004, R5.2). Lo usa el consumidor de
    canal: el pool es de la aplicación —teammates y Companion— y el consumo de
    los clientes finales sale de los créditos que el partner compró. Sin esto,
    un cliente con un día movido deja al partner sin poder usar la aplicación
    que paga.

    El valor por defecto es ``True`` a propósito: los dos carriles que sí
    pueden gastar incluido no cambian ni una línea. El que cambia es el que
    tiene que cambiar.
    """
    if qty <= 0:
        return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=False)
    try:
        return await _debit_locked(
            partner_id=partner_id,
            qty=qty,
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
            usage_record_id=usage_record_id,
            agent_id=agent_id,
            companion_run_id=companion_run_id,
            allow_included=allow_included,
        )
    except Exception as exc:
        # Spec 033 (R4.2): only the ledger's unique key means «already
        # charged». Any other integrity error — a CHECK on a balance, a
        # foreign key — is a failure and must not be read as a duplicate.
        if isinstance(exc, IntegrityError) and "uq_usage_ledger_idempotency" in str(exc.orig):
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=True)
        log.warning(
            "wallet.debit_failed",
            partner_id=str(partner_id),
            key=idempotency_key,
            error=str(exc),
        )
        raise


async def _debit_locked(
    *,
    partner_id: uuid.UUID,
    qty: int,
    idempotency_key: str,
    tenant_id: uuid.UUID | None,
    usage_record_id: uuid.UUID | None,
    agent_id: uuid.UUID | None = None,
    companion_run_id: uuid.UUID | None,
    allow_included: bool = True,
) -> DebitResult:
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        already = await session.scalar(
            sa.select(sa.func.count())
            .select_from(UsageLedger)
            .where(
                UsageLedger.idempotency_key.in_(
                    (
                        f"{idempotency_key}:included",
                        f"{idempotency_key}:purchased",
                        # The same turn, written as covered by Auphere.
                        f"{idempotency_key}:absorbed",
                    )
                )
            )
        )
        if _as_int(already) > 0:
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=True)

        wallet = await _load_wallet_for_update(session, partner_id)
        if wallet is None:
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=False)
        _expire_included(wallet)
        snap = _snapshot(wallet)
        # R5.2: con el cubo incluido cerrado para este llamante, el reparto
        # se hace como si estuviera vacío. No se toca ``split_spend``: la
        # política de quién puede gastar qué es de aquí, no de la aritmética.
        spendable_included = snap.included_remaining if allow_included else 0
        # Spec 041: inside a postpaid credit line the purchased pocket may go
        # below zero, down to ``-credit_limit`` (the database CHECK).
        from_included, from_purchased = split_spend(
            qty, spendable_included, snap.spendable_purchased
        )
        spent = from_included + from_purchased
        if spent <= 0:
            return DebitResult(spent=0, from_included=0, from_purchased=0, duplicate=False)

        if from_included:
            wallet.included_remaining = snap.included_remaining - from_included
        if from_purchased:
            # From the stored value, never the snapshot: the snapshot shows a
            # debt as 0, and writing ``0 - x`` would forgive what is owed.
            wallet.purchased_remaining = _as_int(wallet.purchased_remaining) - from_purchased
        wallet.updated_at = _now()

        if tenant_id is not None:
            alloc = await session.scalar(
                sa.select(PartnerAllocation)
                .where(
                    PartnerAllocation.partner_id == partner_id,
                    PartnerAllocation.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            if alloc is not None:
                alloc.remaining = max(0, _as_int(alloc.remaining) - spent)
                alloc.updated_at = _now()

        if from_included:
            session.add(
                UsageLedger(
                    partner_id=partner_id,
                    tenant_id=tenant_id,
                    qty=from_included,
                    bucket=BUCKET_INCLUDED,
                    kind=KIND_DEBIT,
                    usage_record_id=usage_record_id,
                    agent_id=agent_id,
                    companion_run_id=companion_run_id,
                    idempotency_key=f"{idempotency_key}:included",
                    fx=None,
                )
            )
        if from_purchased:
            session.add(
                UsageLedger(
                    partner_id=partner_id,
                    tenant_id=tenant_id,
                    qty=from_purchased,
                    bucket=BUCKET_PURCHASED,
                    kind=KIND_DEBIT,
                    usage_record_id=usage_record_id,
                    agent_id=agent_id,
                    companion_run_id=companion_run_id,
                    idempotency_key=f"{idempotency_key}:purchased",
                    fx=None,
                )
            )
        await session.flush()
        return DebitResult(
            spent=spent,
            from_included=from_included,
            from_purchased=from_purchased,
            duplicate=False,
        )


async def record_absorbed(
    *,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    qty: int,
    idempotency_key: str,
    agent_id: uuid.UUID | None = None,
) -> bool:
    """Write a turn of a client with unlimited consumption (owner, 2026-10-20).

    One ``absorbed`` entry under ``{key}:absorbed``: measured like a debit,
    but the partner's balance and the client's cap do not move — Auphere
    covers it. ``False`` when the turn is already in the book, as absorbed or
    as a debit (the switch changed between two deliveries of the same turn).
    Any other failure raises, like the debit: the worker retries.
    """
    if qty <= 0:
        return False
    keys = (
        f"{idempotency_key}:absorbed",
        f"{idempotency_key}:included",
        f"{idempotency_key}:purchased",
    )
    sm = get_sessionmaker()
    try:
        async with sm() as session, session.begin():
            await apply_partner_to_session(session, partner_id)
            already = await session.scalar(
                sa.select(sa.func.count())
                .select_from(UsageLedger)
                .where(UsageLedger.idempotency_key.in_(keys))
            )
            if _as_int(already) > 0:
                return False
            session.add(
                UsageLedger(
                    partner_id=partner_id,
                    tenant_id=tenant_id,
                    qty=qty,
                    bucket=BUCKET_PURCHASED,
                    kind=KIND_ABSORBED,
                    agent_id=agent_id,
                    idempotency_key=keys[0],
                    fx=None,
                )
            )
            await session.flush()
        return True
    except IntegrityError as exc:
        if "uq_usage_ledger_idempotency" in str(exc.orig):
            return False
        raise


async def absorbed_since(
    partner_id: uuid.UUID, tenant_ids: list[uuid.UUID], since: datetime
) -> dict[uuid.UUID, int]:
    """What Auphere covered since ``since``, per client (``absorbed``
    entries). Raises when unreadable."""
    if not tenant_ids:
        return {}
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        rows = await session.execute(
            sa.select(UsageLedger.tenant_id, sa.func.sum(UsageLedger.qty))
            .where(
                UsageLedger.partner_id == partner_id,
                UsageLedger.tenant_id.in_(tenant_ids),
                UsageLedger.kind == KIND_ABSORBED,
                UsageLedger.created_at >= since,
            )
            .group_by(UsageLedger.tenant_id)
        )
        return {tid: _as_int(total) for tid, total in rows.all() if tid is not None}
