"""``POST /console/clients/{ref}/channels/whatsapp/signup`` — CP-17.

The console runs Meta's Embedded Signup in the browser (Facebook JS SDK,
``FB.login`` with the Auphere configuration id) and posts the resulting
single-use OAuth ``code`` + ids here. The post-signup dance (code →
BISUAT, register phone, subscribe webhook, encrypt credentials, upsert
``channels``) is the SAME helper the admin panel and the partner API use:
``services/meta_signup_service.complete_meta_signup``. This module only
adds what is console-specific:

- **Quota** (``partners.max_channels_per_client``, migration 0081): checked
  BEFORE any call to Meta. Channels that are not ``disconnected`` count.
  A full quota is a 409 with the numbers in the message and NO side
  effects — the OAuth code is left unconsumed so the partner can retry
  after freeing a slot.
- **Actor** is the console member (``scope.principal.actor``), audit action
  ``console.channel.connect``.
- ``connect-owned`` (permanent System User token) is NOT exposed: that
  token is a permanent secret and never crosses a partner surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import SignupIngressPayload
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.services.meta_signup_service import complete_meta_signup

from .channels import count_connected_channels
from .deps import ClientScope, client_scope
from .schemas_channels import WhatsAppSignupIn, WhatsAppSignupOut

router = APIRouter(prefix="/clients/{ref}/channels/whatsapp")


@router.post(
    "/signup",
    response_model=WhatsAppSignupOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Meta rejected the code / register / subscribe."},
        409: {"description": "Channel quota of this client is full. Nothing was created."},
        502: {"description": "Meta unreachable."},
    },
)
async def whatsapp_signup(
    body: WhatsAppSignupIn,
    scope: ClientScope = Depends(client_scope("channels:write")),
    redis: Redis = Depends(get_redis),
) -> WhatsAppSignupOut:
    limit = scope.principal.partner.max_channels_per_client
    used = await count_connected_channels(scope.session)
    if used >= limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Channel quota reached: {used} of {limit} channels connected for this "
                "client. Disconnect one or ask Auphere to raise max_channels_per_client."
            ),
        )
    payload = SignupIngressPayload(
        code=body.code,
        waba_id=body.waba_id,
        phone_number_id=body.phone_number_id,
        business_id=body.business_id,
        mode=body.mode,
    )
    bundle = await complete_meta_signup(
        session=scope.session,
        redis=redis,
        payload=payload,
        tenant_id=scope.tenant.id,
        actor=scope.principal.actor,
        audit_action="console.channel.connect",
    )
    result = bundle.result
    used_after = await count_connected_channels(scope.session)
    return WhatsAppSignupOut(
        status="connected",
        channel_id=result.channel_id,
        display_phone_number=result.display_phone_number,
        mode=result.mode,
        used_channels=used_after,
        max_channels=limit,
    )


__all__ = ["router"]
