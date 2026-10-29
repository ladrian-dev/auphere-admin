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
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.meta_social import MetaSocialConnectError
from nexus_channels.meta_social.connect import ConnectableAccount, ConnectOutcome
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.db.models import Channel
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services import meta_social_service

from .channels import _detail, channel_logos
from .deps import ClientScope, client_scope
from .schemas_channels import ChannelDetailOut

router = APIRouter(prefix="/clients/{ref}/channels")

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
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action=f"channel.{kind}.connect",
        target=f"channel:{channel.id}",
        before=None,
        after={
            "display_name": (
                f"@{outcome.account.username}" if outcome.account.username else outcome.account.name
            ),
            "account_id": outcome.account.id,
        },
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
