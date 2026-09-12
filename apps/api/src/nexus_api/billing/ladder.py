"""Spec 005 · the dunning ladder, and the exhaustive mapping behind it.

ADR-037 D6. Four states of ours, and the only thing any of them changes is
whether the weekly pool refills. **Nothing is archived, nothing is cancelled,
no pending confirmation is lost** (principle IV: "deleting does not exist").

``partners.status`` is NOT this. It only admits ``active``/``suspended`` and
means whether the partner is operational — an unpaid partner is still
operational for reading their own history.
"""

from __future__ import annotations

from nexus_api.db.models.membership import (
    STATE_CANCELED,
    STATE_CURRENT,
    STATE_PAYMENT_FAILED,
    STATE_UNPAID,
)


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
