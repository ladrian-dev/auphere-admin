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
- **Spec 016 (R1.2-R1.6)**: after the number is in, the client is
  activated when it can operate (``activate_tenant_if_ready``), the
  response carries ``client_status`` and ``health``, a number that already
  belongs to another client is a 409 ``number_in_use`` with no effects, and
  any failure leaves no channel and no credentials behind: the whole signup
  runs in the request's one transaction.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import SignupIngressPayload
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError

from nexus_api.api.deps import get_redis
from nexus_api.services.console_notifications import record_client_activation_detached
from nexus_api.services.meta_signup_service import complete_meta_signup
from nexus_api.services.partner_provisioning import activate_tenant_if_ready

from .channels import count_connected_channels
from .deps import ClientScope, client_health, client_scope, out_of_quota
from .schemas_channels import WhatsAppSignupIn, WhatsAppSignupOut

#: The UNIQUE that says «this number already belongs to a client».
_NUMBER_UNIQUE = "uq_channels_type_provider_id"

router = APIRouter(prefix="/clients/{ref}/channels/whatsapp")


@router.post(
    "/signup",
    response_model=WhatsAppSignupOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Meta rejected the code / register / subscribe."},
        409: {
            "description": "Channel quota of this client is full, or the number already "
            "belongs to another client (`number_in_use`). Nothing was created."
        },
        502: {"description": "Meta unreachable. Nothing was created."},
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
    try:
        bundle = await complete_meta_signup(
            session=scope.session,
            redis=redis,
            payload=payload,
            tenant_id=scope.tenant.id,
            actor=scope.principal.actor,
            audit_action="console.channel.connect",
        )
        # The orchestrator flushes as it goes, but the UNIQUE on the number
        # can also surface at the end of the transaction. Force it here, where
        # it can still be a 409 instead of a 500 at commit time.
        await scope.session.flush()
    except IntegrityError as exc:
        if _NUMBER_UNIQUE not in str(exc.orig or exc):
            raise
        # R1.4: the number is someone else's. Raising inside the scope rolls
        # the whole signup back — no channel, no credentials, no audit row.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "number_in_use"},
        ) from None
    result = bundle.result
    used_after = await count_connected_channels(scope.session)
    # R1.2: with the number in, the client may now operate. Same gates as the
    # embed signup (partner opted in, still provisioning, agent published).
    activated = await activate_tenant_if_ready(
        scope.session, partner=scope.principal.partner, tenant_id=scope.tenant.id
    )
    no_quota = await out_of_quota(scope.principal.partner.id, scope.tenant.id)
    if activated:
        # CP-29: the «activated» notice and the partner's first-activation
        # stamp. The channel is not committed yet, so the answer to «can it
        # serve?» is passed in: the number is in; only quota can be missing.
        await record_client_activation_detached(
            partner_id=scope.principal.partner.id,
            external_client_ref=scope.mapping.external_client_ref,
            serving=(not no_quota, ["quota"] if no_quota else []),
        )
    health = await client_health(scope.session, scope.tenant, out_of_quota=no_quota)
    return WhatsAppSignupOut(
        status="connected",
        channel_id=result.channel_id,
        display_phone_number=result.display_phone_number,
        mode=result.mode,
        used_channels=used_after,
        max_channels=limit,
        client_status=scope.tenant.status.value,
        health=health,
    )


__all__ = ["router"]
