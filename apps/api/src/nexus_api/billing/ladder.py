"""Spec 005 · the dunning ladder, and the exhaustive mapping behind it.

ADR-037 D6. Four states of ours, and the only thing any of them changes is
whether the weekly pool refills. **Nothing is archived, nothing is cancelled,
no pending confirmation is lost** (principle IV: "deleting does not exist").

``partners.status`` is NOT this. It only admits ``active``/``suspended`` and
means whether the partner is operational — an unpaid partner is still
operational for reading their own history.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import sqlalchemy as sa
import structlog

from nexus_api.db.models.membership import (
    STATE_CANCELED,
    STATE_CURRENT,
    STATE_PAYMENT_FAILED,
    STATE_UNPAID,
    MembershipTier,
    PartnerSubscription,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


class UnknownProviderState(ValueError):
    """A provider status we have never seen.

    Raised rather than defaulting to anything. Defaulting to ``current``
    would be access given away silently; defaulting to ``canceled`` would cut
    off a partner who paid. The handler fails, the previous state stays
    untouched, and someone looks.
    """


#: Verified 2026-09-12 against Stripe's subscription lifecycle documentation.
#: Exhaustive on purpose: a status missing from this table must raise, never
#: fall through.
_FROM_PROVIDER: dict[str, str] = {
    # Everything is normal.
    "trialing": STATE_CURRENT,
    "active": STATE_CURRENT,
    # A charge failed and is being retried. NOTHING changes yet — this is the
    # step that exists so a partner fixing a card loses nothing.
    "past_due": STATE_PAYMENT_FAILED,
    # Retries are exhausted. The pool stops refilling; purchased credit keeps
    # being spent, because it is money already paid.
    #
    # Stripe only ever sets this **if the account is configured to** (verified
    # 2026-09-12: "Stripe sets a subscription's status to unpaid only when
    # your Dashboard subscription settings select this outcome"). With the
    # factory defaults an unpaid partner jumps from past_due to canceled and
    # this step never happens. The mapping is built to survive that: skipping
    # a step costs a warning, not anyone's work.
    "unpaid": STATE_UNPAID,
    "paused": STATE_UNPAID,
    # The end. The pool goes to Free; purchased credit lives 12 more months.
    "canceled": STATE_CANCELED,
    "incomplete_expired": STATE_CANCELED,
    # No first payment yet, so there is no tier granted and nothing to
    # degrade. The customer has 23 hours to pay before it expires.
    "incomplete": STATE_CURRENT,
}


def state_from_provider(provider_status: str) -> str:
    """Map a provider subscription status onto ours, or refuse."""
    try:
        return _FROM_PROVIDER[provider_status]
    except KeyError:
        raise UnknownProviderState(
            f"estado de suscripción desconocido: {provider_status!r}. No se "
            "asume ninguno: un estado no previsto leído como «al corriente» es "
            "acceso regalado y silencioso, y leído como «cancelada» corta a "
            "alguien que pagó"
        ) from None


def known_provider_states() -> frozenset[str]:
    return frozenset(_FROM_PROVIDER)


def pool_refills_in(state: str) -> bool:
    """Whether the weekly included pool replenishes in this state.

    The single behavioural consequence of the whole ladder. Everything else a
    partner has — teammates, tasks, pending confirmations, history — is
    untouched at every step.
    """
    return state == STATE_CURRENT


# ── Applying a notice to our own book ────────────────────────────────────────
#
# Everything below runs in the WORKER, never in the webhook, and never on the
# turn path. It only ever adds: no path that starts at an external notice may
# subtract balance (ADR-037 D3), and a structural test enforces it.


async def grant_tier(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    tier_code: str,
    period_end: datetime | None = None,
    subscription_id: str | None = None,
    customer_id: str | None = None,
) -> None:
    """Money arrived: apply the tier and size the pool, in the same act.

    R2.3 says "in the same act" for a reason. Granting the tier and leaving
    the pool for a second step means a partner who just paid can be told they
    have no budget — which is the first thing they would do after paying.

    ``partners.weekly_pool_tokens`` is written rather than joined at read
    time: the turn path reads that column to replenish, and putting the
    catalogue in the hot path of spending would make a plans query part of
    answering a message.
    """
    tier = (
        await session.execute(sa.select(MembershipTier).where(MembershipTier.code == tier_code))
    ).scalar_one_or_none()
    if tier is None:
        raise UnknownProviderState(f"nivel desconocido: {tier_code!r}")

    existing = (
        await session.execute(
            sa.select(PartnerSubscription).where(PartnerSubscription.partner_id == partner_id)
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing is None:
        session.add(
            PartnerSubscription(
                partner_id=partner_id,
                tier_code=tier_code,
                state=STATE_CURRENT,
                current_period_end=period_end,
                stripe_subscription_id=subscription_id,
                stripe_customer_id=customer_id,
                state_changed_at=now,
            )
        )
    else:
        if existing.state != STATE_CURRENT:
            existing.state_changed_at = now
        existing.tier_code = tier_code
        existing.state = STATE_CURRENT
        existing.current_period_end = period_end
        # References are only ever filled in, never used to find anybody.
        existing.stripe_subscription_id = subscription_id or existing.stripe_subscription_id
        existing.stripe_customer_id = customer_id or existing.stripe_customer_id
        # A partner coming back within the window gets their purchased credit
        # back without anyone restoring anything by hand (R7.3).
        existing.pending_tier_code = None

    await session.execute(
        sa.text("UPDATE partners SET weekly_pool_tokens = :n WHERE id = :p"),
        {"n": tier.weekly_pool_tokens, "p": str(partner_id)},
    )
    await session.execute(
        sa.text("UPDATE partner_wallets SET purchased_expires_at = NULL WHERE partner_id = :p"),
        {"p": str(partner_id)},
    )
    log.info(
        "metering.tier_granted",
        partner_id=str(partner_id),
        tier=tier_code,
        pool=tier.weekly_pool_tokens,
    )


#: Un escalón → el aviso que le corresponde. ``current`` no avisa: volver a la
#: normalidad no es una noticia que interrumpa a nadie.
_STEP_NOTICE: dict[str, str] = {
    STATE_PAYMENT_FAILED: "billing.payment_failed",
    STATE_UNPAID: "billing.unpaid",
    STATE_CANCELED: "billing.canceled",
}


async def _notify_step(session: AsyncSession, *, partner_id: uuid.UUID, state: str) -> None:
    """Avisa del escalón, una sola vez.

    R5.6 pide avisar **antes** de que el servicio se degrade, y el diseño lo
    consigue con el primer escalón: «pago fallido» no degrada nada, existe
    para abrir una ventana entre el aviso y el efecto.

    La clave de deduplicación lleva el estado y no la fecha: Stripe reintenta
    varias veces y el partner tiene que recibir **un** aviso por escalón, no
    uno por reintento. Un escalón nuevo sí vuelve a avisar, porque entonces sí
    cambia algo para él.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from nexus_api.db.models import ConsoleNotification

    kind = _STEP_NOTICE.get(state)
    if kind is None:
        return

    await session.execute(
        pg_insert(ConsoleNotification)
        .values(
            partner_id=partner_id,
            kind=kind,
            severity="warning",
            payload={"state": state, "since": datetime.now(UTC).isoformat()},
            dedupe_key=f"billing:{partner_id}:{state}",
        )
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"], index_where=sa.text("dedupe_key IS NOT NULL")
        )
    )


async def move_to(
    session: AsyncSession, *, partner_id: uuid.UUID, state: str, notify: bool = False
) -> None:
    """Move a partner one step of the ladder. Nothing else changes.

    Not one teammate archived, not one task cancelled, not one pending
    confirmation invalidated (principle IV). The only consequence of any step
    is whether the weekly pool replenishes — and purchased credit keeps being
    spendable at every step, because it is money already paid.
    """
    row = (
        await session.execute(
            sa.select(PartnerSubscription).where(PartnerSubscription.partner_id == partner_id)
        )
    ).scalar_one_or_none()
    if row is None:
        log.info("metering.ladder_no_subscription", partner_id=str(partner_id), target=state)
        return
    if row.state == state:
        return
    row.state = state
    row.state_changed_at = datetime.now(UTC)
    if notify:
        await _notify_step(session, partner_id=partner_id, state=state)
    log.info("metering.ladder_moved", partner_id=str(partner_id), state=state)


async def flag_finalization_failure(
    session: AsyncSession, *, partner_id: uuid.UUID | None, reason: str
) -> None:
    """An invoice could not be finalized: tell an operator, degrade nobody.

    Verified 2026-09-12: "Subscriptions remain active if invoices can't be
    finalized, which means that users may still be able to access your
    product while you're not able to collect payments."

    Read slowly, that is coverage without revenue and **with no symptom**.
    The partner keeps working, our ladder does not move, and nothing charges.
    It is not their fault, so their state is deliberately untouched; what has
    to happen is that somebody finds out.
    """
    log.warning(
        "metering.billing_finalization_failed",
        partner_id=str(partner_id or ""),
        reason=reason,
    )


async def cancel_subscription(
    session: AsyncSession, *, partner_id: uuid.UUID, months: int = 12
) -> datetime | None:
    """Cancel a partner's plan. Returns when their credit expires.

    What cancelling does **not** do is the important half: not a teammate
    archived, not a task cancelled, not a pending confirmation invalidated,
    not a conversation deleted (principle IV). The account stays whole and
    readable. The only thing that stops is the weekly pool refilling.

    What it does do is put a clock on the purchased credit — twelve months
    (R7.2). Until now that column was ``NULL``, which is how the invariant
    "purchased credit does not expire while the account lives" is written so
    that it cannot be violated by accident: with no date there is nothing to
    compare. Cancelling is the one moment a date belongs there, and coming
    back clears it again.
    """
    row = (
        await session.execute(
            sa.select(PartnerSubscription).where(PartnerSubscription.partner_id == partner_id)
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is not None and row.state != STATE_CANCELED:
        row.state = STATE_CANCELED
        row.state_changed_at = now
        row.pending_tier_code = None

    expires_at = now + timedelta(days=365 * months // 12)
    await session.execute(
        sa.text("UPDATE partner_wallets SET purchased_expires_at = :d WHERE partner_id = :p"),
        {"d": expires_at, "p": str(partner_id)},
    )
    log.info(
        "metering.subscription_canceled",
        partner_id=str(partner_id),
        credit_expires_at=expires_at.isoformat(),
    )
    return expires_at
