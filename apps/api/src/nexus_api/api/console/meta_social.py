"""``/console/clients/{ref}/channels/{instagram|messenger}/connect`` — spec 049.

The console opens Facebook Login for Business with the channel's
configuration (``FB.login``, ``response_type=code``) and posts the single-use
``code`` here. :class:`MetaSocialConnector` does the rest under this
request's tenant-scoped transaction: a failure leaves no channel and no
credential behind.

- A partner without the channel enabled gets a 404: the route does not exist
  for it (requirement 5.5).
- If the business granted several accounts or Pages, the answer is
  ``choose`` with the list; ``/connect/complete`` connects the one picked.
- A connection that cannot work is a 409 ``{code, help}`` with the exact step
  to fix it (requirement 5.2). Nothing was created.

Spec 085: ``POST …/{instagram|messenger}/signup-link`` mints the link the
business owner opens to connect the channel themselves (``link_router``,
mounted after WhatsApp's so ``/whatsapp/signup-link`` keeps its own route).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.meta_social import MetaSocialConnectError
from nexus_channels.meta_social.connect import ConnectableAccount, ConnectOutcome
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.db.models import Channel
from nexus_api.services import meta_social_service

from .channels import _detail, channel_logos
from .deps import ClientScope, client_scope
from .schemas_channels import ChannelDetailOut

router = APIRouter(prefix="/clients/{ref}/channels")
#: Spec 085. Its own router: ``/{kind}/signup-link`` would also match
#: ``/whatsapp/signup-link``, so it is mounted after the WhatsApp routes.
link_router = APIRouter(prefix="/clients/{ref}/channels")

Kind = Literal["instagram", "messenger"]


class ConnectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=2048)


class CompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nonce: str = Field(min_length=8, max_length=64)
    account_id: str = Field(min_length=1, max_length=64)


class AccountOut(BaseModel):
    id: str
    name: str
    username: str | None = None
    picture_url: str | None = None


class ConnectOut(BaseModel):
    status: Literal["connected", "choose"]
    channel: ChannelDetailOut | None = None
    nonce: str | None = None
    accounts: list[AccountOut] = Field(default_factory=list)


def _require_enabled(scope: ClientScope, kind: Kind) -> None:
    if kind not in meta_social_service.enabled_kinds(scope.principal.partner):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def _refuse(exc: MetaSocialConnectError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": exc.reason, "help": meta_social_service.REASON_HELP.get(exc.reason)},
    )


async def _answer(scope: ClientScope, kind: Kind, outcome: ConnectOutcome) -> ConnectOut:
    if outcome.status == "choose":
        return ConnectOut(
            status="choose",
            nonce=outcome.nonce,
            accounts=[_account(a) for a in outcome.accounts],
        )
    assert outcome.channel_id is not None and outcome.account is not None
    channel = await scope.session.get(Channel, outcome.channel_id)
    assert channel is not None
    await meta_social_service.audit_connect(
        scope.session,
        actor=scope.principal.actor,
        kind=kind,
        channel_id=channel.id,
        account=outcome.account,
    )
    return ConnectOut(
        status="connected", channel=_detail(channel, await channel_logos(scope.session))
    )


def _account(a: ConnectableAccount) -> AccountOut:
    return AccountOut(id=a.id, name=a.name, username=a.username, picture_url=a.picture_url)


@router.post("/{kind}/connect", response_model=ConnectOut, status_code=status.HTTP_200_OK)
async def connect(
    kind: Kind,
    body: ConnectIn,
    scope: ClientScope = Depends(client_scope("channels:write")),
    redis: Redis = Depends(get_redis),
) -> ConnectOut:
    _require_enabled(scope, kind)
    try:
        outcome = await meta_social_service.connector(scope.session, redis).begin(
            kind=kind, code=body.code
        )
    except MetaSocialConnectError as exc:
        raise _refuse(exc) from None
    except MetaAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Meta did not answer"
        ) from exc
    return await _answer(scope, kind, outcome)


@router.post("/{kind}/connect/complete", response_model=ConnectOut)
async def complete(
    kind: Kind,
    body: CompleteIn,
    scope: ClientScope = Depends(client_scope("channels:write")),
    redis: Redis = Depends(get_redis),
) -> ConnectOut:
    _require_enabled(scope, kind)
    try:
        outcome = await meta_social_service.connector(scope.session, redis).complete(
            kind=kind, nonce=body.nonce, account_id=body.account_id
        )
    except MetaSocialConnectError as exc:
        raise _refuse(exc) from None
    except MetaAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Meta did not answer"
        ) from exc
    return await _answer(scope, kind, outcome)


class SignupLinkOut(BaseModel):
    """Spec 085: the URL is shown only here; Auphere keeps its fingerprint."""

    url: str
    channel: Kind
    expires_at: datetime


@link_router.post(
    "/{kind}/signup-link", response_model=SignupLinkOut, status_code=status.HTTP_201_CREATED
)
async def signup_link(
    kind: Kind,
    scope: ClientScope = Depends(client_scope("channels:write")),
) -> SignupLinkOut:
    """Spec 085 (1.1, 1.2, 1.3, 1.6): the link the business owner opens to connect
    Instagram or Messenger themselves. Nothing to choose: the owner picks how
    to sign in to Meta on their page. It replaces the client's earlier unused
    link of this channel, and only that one."""
    from nexus_api.services.channel_signup_links import mint_link

    _require_enabled(scope, kind)
    minted = await mint_link(
        scope.session, tenant_id=scope.tenant.id, channel=kind, actor=scope.principal.actor
    )
    return SignupLinkOut(url=minted.url, channel=kind, expires_at=minted.link.expires_at)
