"""Spec 023: the closed list of tools per Composio toolkit.

A Composio toolkit exposes hundreds of tools (Stripe 426, HubSpot 262,
Calendly 53 on 2026-09-30). Syncing all of them would put every one of
them in ``tool_catalog`` and in the agent's whitelist screen, almost all
blocked and named by their technical slug. The owner chose a **closed
list per toolkit, written by Auphere**: the 8 to 12 tools a business uses in
a conversation. What is not listed is not synced, does not reach the
agent and does not reach Capacidades.

Three rules, pinned by ``tests/unit/connectors/test_toolkit_allowlists.py``:

- Every slug starts with ``<TOOLKIT>_`` (the provider's slug prefix).
- A tool either reads (``read_only=True, destructive=False``) or writes
  (``read_only=False, destructive=True``). Writing is born blocked; there is
  no third state.
- Every slug has a business name in ``api/console/capability_names.py``
  in both languages. A slug without a name does not enter the list.

Toolkits **without** a list here (googlecalendar, notion, gmail, …) keep
the previous behaviour: every upstream tool is synced and annotated by
``service._derive_annotations``.

Where each list came from (spec 023, ``evidence/README.md``):

- Calendly: read complete from the Composio dashboard (53 tools,
  ``v20260929_00``, 2026-09-30).
- Stripe and HubSpot: read from Composio's public catalogue
  (``docs.composio.dev/toolkits/{stripe,hubspot}``, 2026-09-30), confirmed
  slug by slug in the dashboard when the first account is connected in
  staging. ``sync_tools_for`` logs ``connector.sync.allowlist_missing`` for
  any slug the provider does not return, so a wrong slug is visible on
  day one instead of silently absent.
"""

from __future__ import annotations

from typing import Final, TypedDict


class ToolHint(TypedDict):
    read_only: bool
    destructive: bool


_READ: Final[ToolHint] = {"read_only": True, "destructive": False}
_WRITE: Final[ToolHint] = {"read_only": False, "destructive": True}


TOOLKIT_ALLOWLISTS: Final[dict[str, dict[str, ToolHint]]] = {
    # ── Stripe — 12 (8 read · 4 write) ──────────────────────────────────
    "stripe": {
        "STRIPE_SEARCH_CUSTOMERS": _READ,
        "STRIPE_SEARCH_PAYMENT_INTENTS": _READ,
        "STRIPE_RETRIEVE_PAYMENT_INTENT": _READ,
        "STRIPE_LIST_INVOICES": _READ,
        "STRIPE_LIST_PAYMENT_LINKS": _READ,
        "STRIPE_LIST_PRODUCTS": _READ,
        "STRIPE_LIST_PRICES": _READ,
        "STRIPE_LIST_REFUNDS": _READ,
        "STRIPE_CREATE_CUSTOMER": _WRITE,
        "STRIPE_CREATE_PAYMENT_LINK": _WRITE,
        "STRIPE_CREATE_REFUND": _WRITE,
        "STRIPE_SEND_INVOICE": _WRITE,
    },
    # ── Calendly — 10 (7 read · 3 write) ────────────────────────────────
    # WHO_AM_I is in because Calendly's API needs the user URI to list
    # event types and scheduled events; without it the agent cannot start.
    "calendly": {
        "CALENDLY_WHO_AM_I": _READ,
        "CALENDLY_LIST_EVENT_TYPES": _READ,
        "CALENDLY_LIST_EVENT_TYPE_AVAILABLE_TIMES": _READ,
        "CALENDLY_LIST_SCHEDULED_EVENTS": _READ,
        "CALENDLY_GET_EVENT": _READ,
        "CALENDLY_LIST_EVENT_INVITEES": _READ,
        "CALENDLY_LIST_USER_BUSY_TIMES": _READ,
        "CALENDLY_POST_INVITEE": _WRITE,
        "CALENDLY_CREATE_SINGLE_USE_SCHEDULING_LINK": _WRITE,
        "CALENDLY_CANCEL_SCHEDULED_EVENT": _WRITE,
    },
    # ── HubSpot — 11 (6 read · 5 write) ─────────────────────────────────
    # Archiving and deleting stay out on purpose: a conversation never
    # needs them, and the constitution says deleting does not exist.
    "hubspot": {
        "HUBSPOT_SEARCH_CONTACTS": _READ,
        "HUBSPOT_LIST_CONTACT_NOTES": _READ,
        "HUBSPOT_SEARCH_DEALS": _READ,
        "HUBSPOT_GET_DEAL": _READ,
        "HUBSPOT_SEARCH_TICKETS": _READ,
        "HUBSPOT_GET_TICKET": _READ,
        "HUBSPOT_CREATE_CONTACT": _WRITE,
        "HUBSPOT_UPDATE_CONTACT": _WRITE,
        "HUBSPOT_CREATE_NOTE": _WRITE,
        "HUBSPOT_CREATE_DEAL": _WRITE,
        "HUBSPOT_CREATE_TICKET": _WRITE,
    },
}


def allowlist_for(toolkit: str) -> dict[str, ToolHint] | None:
    """The closed list for ``toolkit`` (case-insensitive), or ``None`` when
    the toolkit has no list and syncs everything as before."""
    return TOOLKIT_ALLOWLISTS.get(toolkit.lower())


def hint_for_slug(slug: str) -> ToolHint | None:
    """Auphere's word on whether ``slug`` reads or writes, if it belongs to
    a closed list. The toolkit is the slug's prefix (``STRIPE_…`` → stripe)."""
    toolkit, sep, _rest = slug.partition("_")
    if not sep:
        return None
    entries = TOOLKIT_ALLOWLISTS.get(toolkit.lower())
    if entries is None:
        return None
    return entries.get(slug)
