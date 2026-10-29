"""Instagram and Messenger for the consoles and the panel — spec 049.

Who may see the channels (requirement 5.5): until Meta approves the
permissions, only the partners Auphere switched on in
``partners.beta_channels`` (the review partner, internal test partners).
After approval, ``meta_social_general_availability`` opens them to all.
A partner without them does not see the channels at all (constitution §V).
"""

from __future__ import annotations

from typing import Any, Literal

from nexus_channels.meta_social import MetaSocialClient
from nexus_channels.meta_social.connect import MetaSocialConnector
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.db.models import Partner

Kind = Literal["instagram", "messenger"]
KINDS: tuple[Kind, ...] = ("instagram", "messenger")

_client: MetaSocialClient | None = None


def enabled_kinds(partner: Partner | None) -> list[Kind]:
    settings = get_settings()
    if settings.meta_social_general_availability:
        return list(KINDS)
    have = set((partner.beta_channels if partner is not None else None) or ())
    return [k for k in KINDS if k in have]


def config_id(kind: Kind) -> str:
    settings = get_settings()
    return (
        settings.meta_config_id_instagram
        if kind == "instagram"
        else settings.meta_config_id_messenger
    )


def offer(partner: Partner | None) -> dict[str, Any]:
    """What the console needs to draw the connect buttons: one entry per
    channel the partner has, with the Facebook Login for Business
    configuration the browser opens."""
    settings = get_settings()
    kinds = enabled_kinds(partner)
    return {
        "app_id": settings.meta_app_id,
        "graph_version": settings.meta_social_graph_api_version,
        "channels": [{"kind": k, "config_id": config_id(k)} for k in kinds],
    }


def client() -> MetaSocialClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = MetaSocialClient(
            settings.meta_app_secret,
            version=settings.meta_social_graph_api_version,
            require_appsecret_proof=settings.meta_require_appsecret_proof,
        )
    return _client


def connector(session: AsyncSession, redis: Redis) -> MetaSocialConnector:
    return MetaSocialConnector(
        session=session, redis=redis, client=client(), app_id=get_settings().meta_app_id
    )


#: ``channels.problem_reason`` (spec 047, closed list) for each reason an
#: Instagram / Messenger channel needs attention, so the new console shows
#: the same «problem» state it shows for a WhatsApp number.
PROBLEM_REASON_OF: dict[str, str] = {
    "token_revoked": "auth_expired",
    "permission_lost": "auth_expired",
    "no_credentials": "auth_expired",
    "messages_disabled": "meta_error",
    "subscribe_failed": "meta_error",
}


#: The step the business takes for each reason the connection stops.
REASON_HELP: dict[str, str] = {
    "code_exchange_failed": "Meta did not accept the login. Try connecting again.",
    "no_business_portfolio": (
        "The account has to belong to a Meta business portfolio. Create one in "
        "business.facebook.com and connect again."
    ),
    "no_instagram_account": (
        "No professional Instagram account was shared. Connect again and select the account."
    ),
    "no_page": "No Facebook Page was shared. Connect again and select the Page.",
    "messages_disabled": (
        "Turn on Instagram → Settings → Messages and story replies → Connected tools → "
        "Allow access to messages, then connect again."
    ),
    "missing_permission": "A permission was not granted. Connect again and accept every step.",
    "page_messaging_task_missing": (
        "The person who logged in cannot manage messages on that Page. Ask a Page admin to connect it."
    ),
    "already_connected_elsewhere": "That account is already connected to another client.",
    "subscribe_failed": "Meta did not let us receive the account's messages. Try again in a minute.",
    "pending_expired": "The selection expired. Connect again.",
}
