"""Spec 005 · the only module in this codebase that imports ``stripe``.

Everything the provider knows how to do enters through here. The boundary is
not tidiness: the Stripe account belongs to a partner of Auphere while the
company's fiscal registration is completed and **it will be migrated**
(research D5). With the SDK imported in eight modules that migration is an
excavation; behind one module it is a contained job.

``tests/unit/test_billing_boundary.py`` fails the build if ``import stripe``
appears anywhere else.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog

from nexus_api.config import get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    import stripe

log = structlog.get_logger(__name__)

#: Stripe truncates idempotency keys at 255 characters.
_MAX_KEY = 255


class BillingUnavailable(RuntimeError):
    """The billing package is closed because its keys are absent.

    Raised instead of returning a half-built client: a client that fails on
    its first call surfaces the error far from its cause. The console turns
    this into ``503 billing_unavailable``, which tells the partner to try in a
    moment rather than that "something went wrong" (principle V).
    """


def idempotency_key(domain: str, partner_id: uuid.UUID, *parts: str) -> str:
    """Build the key for a call that creates or modifies something upstream.

    Two rules, both from ADR-022 §15 and research D5.1:

    * **Our identifier, never theirs.** A key built on ``cus_…`` stops being
      valid the day the account changes; one built on our ``partner_id``
      survives it.
    * **A discriminant per attempt.** Without it, upgrade → downgrade →
      upgrade-again reuses the first key, and Stripe replays the stored
      response instead of acting: a plan change the partner asked for that
      silently does not happen.
    """
    key = ":".join(("billing", domain, str(partner_id), *parts))
    return key[:_MAX_KEY]


def get_client(*, api_key: str | None = None) -> stripe.StripeClient:
    """The provider client, or ``BillingUnavailable``.

    The import lives inside the function on purpose: the module is imported by
    the console router at startup, and a missing SDK should not stop the app
    from booting without billing — running without billing is an honest state.
    """
    key = api_key if api_key is not None else get_settings().billing_api_key
    if not key.strip():
        raise BillingUnavailable(
            "billing is closed: NEXUS_BILLING_API_KEY is not set. The app runs "
            "fine without it; what does not run is charging anyone."
        )
    import stripe

    return stripe.StripeClient(api_key=key)


def verify_signature(*, payload: bytes, signature: str, secret: str) -> dict[str, Any]:
    """Verify a webhook notice and return its parsed event.

    Takes the body as **raw bytes**. The signature is computed over the exact
    bytes Stripe sent; if a framework parses and re-serialises, a single space
    invalidates it and the failure looks like an attack instead of a bug.
    """
    import stripe

    event = stripe.Webhook.construct_event(payload, signature, secret)
    # ``.to_dict()`` and not ``dict(event)``: the SDK's Event refuses the
    # plain-mapping conversion, and the TypeError it raises would surface here
    # as "invalid signature" — a verification bug that reads as an attack.
    return event.to_dict()


async def check_account_configuration(client: stripe.StripeClient) -> list[str]:
    """Report configuration the ladder depends on and that has no default.

    Verified 2026-09-12: Stripe only moves a subscription to ``unpaid`` **when
    the Dashboard subscription settings select that outcome**. With the
    factory defaults an unpaid partner goes from ``past_due` straight to
    ``canceled`` and **the intermediate step of ADR-037 D6 never happens** —
    the whole point of which is not to hurt anyone while a card is fixed.

    A product decision living in a checkbox is a product decision that gets
    lost, especially when the account changes hands. This returns the warnings
    rather than raising: a misconfigured account must not stop the app from
    booting, it must be loud.
    """
    warnings: list[str] = []
    try:
        # The setting is not exposed by the API; what we can assert is that
        # the account answers and that someone looked. The real check is the
        # runbook's, and this leaves a dated trace that it was due.
        client.accounts.retrieve()  # type: ignore[attr-defined]
    except Exception as exc:
        warnings.append(f"no se pudo leer la cuenta del proveedor: {exc}")
        return warnings

    warnings.append(
        "comprueba a mano en el panel del proveedor que, al agotar los "
        "reintentos, la suscripción pasa a «unpaid» y no a «canceled»: sin esa "
        "casilla el escalón intermedio de la escalera de impago no existe "
        "(research D10)"
    )
    return warnings
