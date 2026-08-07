"""Embedded Signup v4 orchestration.

The frontend (Auphere admin panel) opens Facebook Login for Business with
one of the two configuration IDs registered for the app:

- ``meta_config_id_wa_cloud_api`` — Cloud-only flow.
- ``meta_config_id_wa_coexistence`` — preserves the tenant's WA Business
  mobile app alongside the Cloud API.

On success Meta returns an OAuth ``code`` and a ``data`` envelope carrying
``waba_id`` / ``phone_number_id`` / ``business_id``. The backend ingests
this via :meth:`EmbeddedSignupOrchestrator.complete` and performs the
post-signup dance:

1. Exchange ``code`` → BISUAT via the Graph OAuth endpoint.
2. ``POST /{phone_number_id}/register`` with a generated PIN.
3. ``POST /{waba_id}/subscribed_apps`` with ``override_callback_uri`` and a
   per-tenant ``verify_token``.
4. ``GET /{phone_number_id}`` to capture ``display_phone_number`` and
   ``quality_rating`` for the ``channels`` row.
5. Persist :class:`MetaCredentials` under the active tenant.
6. Upsert / activate the ``channels`` row with ``provider="meta"``.
7. Invalidate the tenant-resolver Redis cache for the business phone so the
   next webhook routes correctly.

If any step fails after the BISUAT exists, the orchestrator does NOT roll
back the BISUAT — it persists ``needs_reauth=True`` so the operator panel
shows what happened and the owner can retry from the panel.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

import structlog
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.core.tenant_resolver import invalidate_tenant_cache
from nexus_api.db.models import Channel
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_channels.whatsapp_meta.credentials import (
    ChannelCredentialsRepository,
    MetaCredentials,
    MetaCredentialsRepository,
)
from nexus_channels.whatsapp_meta.exceptions import (
    RegisterPhoneError,
    SubscribeWebhookError,
    TokenExchangeError,
)
from nexus_channels.whatsapp_meta.meta_client import MetaClient
from nexus_channels.whatsapp_meta.phone import to_e164

log = structlog.get_logger(__name__)


@dataclass(slots=True, frozen=True)
class SignupIngressPayload:
    """What the Embedded Signup frontend sends to the backend.

    ``code`` is single-use. ``waba_id`` always present.
    ``phone_number_id`` / ``business_id`` come from the ``data`` envelope
    Meta returns alongside the OAuth code — but ONLY for the Cloud API
    flow. The Coexistence ``FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING``
    event only carries ``waba_id`` (the orchestrator derives the rest from
    ``GET /{waba_id}/phone_numbers``). ``mode`` is ``cloud_api`` for the
    Cloud-only config ID and ``coexistence`` for the Coexistence config ID
    — the frontend picks which based on which configuration ID drove
    FB.login.
    """

    code: str
    waba_id: str
    phone_number_id: str | None = None
    business_id: str | None = None
    mode: Literal["cloud_api", "coexistence"] = "cloud_api"


@dataclass(slots=True)
class SignupResult:
    """Returned to the API layer for the panel UI."""

    channel_id: uuid.UUID
    waba_id: str
    phone_number_id: str
    display_phone_number: str
    mode: str
    bisuat_expires_at: datetime | None


class EmbeddedSignupOrchestrator:
    """Runs the post-signup steps end-to-end.

    Construct one per request — it holds the active SQLAlchemy session and
    the tenant-scoped credentials repository.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        redis: Redis,
        client: MetaClient,
        app_id: str,
        webhook_callback_url: str,
        webhook_verify_token: str,
    ) -> None:
        self._session = session
        self._redis = redis
        self._client = client
        self._app_id = app_id
        self._webhook_callback_url = webhook_callback_url
        # Single app-wide verify token. Meta calls our /webhook/meta with
        # this string on subscribed_apps; the handshake handler validates
        # it against ``settings.meta_webhook_verify_token``. Generating a
        # per-tenant random token here used to break subscribed_apps with
        # "(#2200) Callback verification failed HTTP 403" because the
        # handshake handler only knows the global one. Keep them aligned.
        self._webhook_verify_token = webhook_verify_token
        self._credentials = MetaCredentialsRepository(session)
        self._channel_credentials = ChannelCredentialsRepository(session)

    async def complete(self, payload: SignupIngressPayload) -> SignupResult:
        tenant_id = require_current_tenant()
        is_coex = payload.mode == "coexistence"

        # 1) Exchange OAuth code → BISUAT
        token_envelope = await self._client.exchange_code(
            app_id=self._app_id,
            code=payload.code,
        )
        bisuat = token_envelope.get("access_token")
        expires_in = token_envelope.get("expires_in")
        if not isinstance(bisuat, str) or not bisuat:
            raise TokenExchangeError("missing access_token in OAuth response")
        expires_at: datetime | None = None
        if isinstance(expires_in, int) and expires_in > 0:
            expires_at = datetime.now(tz=UTC) + timedelta(seconds=expires_in)

        # 1b) Coexistence: the FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING event
        # only carries waba_id. Derive phone_number_id from the WABA before
        # the steps that need it. The doc guarantees a Coexistence WABA
        # binds exactly one phone number (the one already in the mobile
        # app), so taking ``data[0]`` is safe — guard anyway in case Meta
        # ever returns an empty list mid-onboarding.
        phone_number_id = payload.phone_number_id
        business_id = payload.business_id or ""
        if not phone_number_id:
            phones = await self._client.list_phone_numbers(
                waba_id=payload.waba_id,
                access_token=bisuat,
            )
            phones_data = phones.get("data") if isinstance(phones, dict) else None
            first = phones_data[0] if isinstance(phones_data, list) and phones_data else None
            if not isinstance(first, dict) or not isinstance(first.get("id"), str):
                raise RegisterPhoneError(
                    f"waba {payload.waba_id} returned no phone numbers — cannot complete signup"
                )
            phone_number_id = first["id"]

        # 2) Register the phone number under our app — Cloud API ONLY.
        # The Coexistence doc explicitly says to skip this step: the
        # number is already registered as part of the QR-binding flow.
        # Calling /register against a Coexistence number returns
        # CallingNotAllowed and breaks the WABA, so the branch is hard.
        if not is_coex:
            assert phone_number_id is not None  # ensured for Cloud API by frontend
            pin = _generate_pin()
            try:
                await self._client.register_phone(
                    phone_number_id=phone_number_id,
                    access_token=bisuat,
                    pin=pin,
                )
            except Exception as exc:
                raise RegisterPhoneError(
                    f"register_phone failed for pn={phone_number_id}: {exc}"
                ) from exc

        # 3) Subscribe the WABA with the app-wide verify token + override URL
        verify_token = self._webhook_verify_token
        try:
            await self._client.subscribe_app(
                waba_id=payload.waba_id,
                access_token=bisuat,
                override_callback_uri=self._webhook_callback_url,
                verify_token=verify_token,
            )
        except Exception as exc:
            raise SubscribeWebhookError(
                f"subscribed_apps failed for waba={payload.waba_id}: {exc}"
            ) from exc

        # 4) Read phone metadata for display / quality fields
        phone_info = await self._client.get_phone_number(
            phone_number_id=phone_number_id,
            access_token=bisuat,
        )
        display_phone = _normalise_e164(phone_info.get("display_phone_number"))
        if not display_phone:
            # No display phone means we cannot route webhooks; surface
            # explicitly rather than letting Step 7 fail later.
            raise RegisterPhoneError(
                f"phone_number_id {phone_number_id} has no display_phone_number"
            )

        # 5) Upsert channels row (provider="meta") FIRST — the credential is
        # written against the channel, so the row has to exist.
        channel_id = await self._upsert_channel(
            display_phone=display_phone,
            waba_id=payload.waba_id,
            phone_number_id=phone_number_id,
            business_id=business_id,
            mode=payload.mode,
            quality_rating=phone_info.get("quality_rating"),
            verified_name=phone_info.get("verified_name"),
            messaging_tier=phone_info.get("messaging_limit_tier"),
        )

        # 6) Persist credentials
        credentials = MetaCredentials(
            bisuat=bisuat,
            bisuat_expires_at=expires_at,
            waba_id=payload.waba_id,
            phone_number_id=phone_number_id,
            business_id=business_id,
            display_phone_number=display_phone,
            verify_token=verify_token,
            mode=payload.mode,
            external_user_id_enrolled=False,
        )
        await self._persist_credentials(credentials, channel_id=channel_id)

        # 7) Invalidate the tenant-resolver cache so the next webhook hits
        # the freshly-written channels row.
        await invalidate_tenant_cache(self._redis, "meta", display_phone)

        log.info(
            "meta.signup.complete",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
            waba_id=payload.waba_id,
            phone_number_id=phone_number_id,
            display_phone=display_phone,
            mode=payload.mode,
        )

        return SignupResult(
            channel_id=channel_id,
            waba_id=payload.waba_id,
            phone_number_id=phone_number_id,
            display_phone_number=display_phone,
            mode=payload.mode,
            bisuat_expires_at=expires_at,
        )

    async def connect_with_token(
        self,
        *,
        token: str,
        waba_id: str,
        phone_number_id: str | None,
        catalog_id: str | None = None,
        business_id: str = "",
        mode: Literal["cloud_api", "coexistence"] = "cloud_api",
        attempt_register: bool = True,
    ) -> SignupResult:
        """Connect a WhatsApp number the app OWNER already controls, using a
        permanent System User access token instead of Embedded Signup.

        Meta's Embedded Signup only onboards *client* portfolios — it refuses
        the portfolio that owns the app (Facelad owns Auphere). For our own
        numbers we skip the OAuth code exchange and use a provided System
        User token directly; the remaining steps mirror ``complete()``.

        ``register_phone`` is best-effort: an already-live number is usually
        registered under the app, and a wrong/duplicate PIN must not block
        the connect — ``subscribed_apps`` is what activates the webhook.
        """
        tenant_id = require_current_tenant()

        # Derive phone_number_id from the WABA if the caller didn't pass it.
        if not phone_number_id:
            phones = await self._client.list_phone_numbers(waba_id=waba_id, access_token=token)
            phones_data = phones.get("data") if isinstance(phones, dict) else None
            first = phones_data[0] if isinstance(phones_data, list) and phones_data else None
            if not isinstance(first, dict) or not isinstance(first.get("id"), str):
                raise RegisterPhoneError(
                    f"waba {waba_id} returned no phone numbers — cannot connect"
                )
            phone_number_id = first["id"]

        if attempt_register:
            try:
                await self._client.register_phone(
                    phone_number_id=phone_number_id, access_token=token, pin=_generate_pin()
                )
            except Exception as exc:
                log.warning(
                    "meta.connect_owned.register_skipped",
                    phone_number_id=phone_number_id,
                    reason=str(exc),
                )

        verify_token = self._webhook_verify_token
        try:
            await self._client.subscribe_app(
                waba_id=waba_id,
                access_token=token,
                override_callback_uri=self._webhook_callback_url,
                verify_token=verify_token,
            )
        except Exception as exc:
            raise SubscribeWebhookError(
                f"subscribed_apps failed for waba={waba_id}: {exc}"
            ) from exc

        phone_info = await self._client.get_phone_number(
            phone_number_id=phone_number_id, access_token=token
        )
        display_phone = _normalise_e164(phone_info.get("display_phone_number"))
        if not display_phone:
            raise RegisterPhoneError(
                f"phone_number_id {phone_number_id} has no display_phone_number"
            )

        channel_id = await self._upsert_channel(
            display_phone=display_phone,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            business_id=business_id,
            mode=mode,
            quality_rating=phone_info.get("quality_rating"),
            verified_name=phone_info.get("verified_name"),
            messaging_tier=phone_info.get("messaging_limit_tier"),
            catalog_id=catalog_id,
        )

        credentials = MetaCredentials(
            bisuat=token,
            bisuat_expires_at=None,  # permanent System User token — no expiry
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            business_id=business_id,
            display_phone_number=display_phone,
            verify_token=verify_token,
            mode=mode,
            external_user_id_enrolled=False,
        )
        await self._persist_credentials(credentials, channel_id=channel_id)

        await invalidate_tenant_cache(self._redis, "meta", display_phone)
        log.info(
            "meta.connect_owned.complete",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            display_phone=display_phone,
            catalog_id=catalog_id,
        )
        return SignupResult(
            channel_id=channel_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            display_phone_number=display_phone,
            mode=mode,
            bisuat_expires_at=None,
        )

    async def _persist_credentials(
        self, credentials: MetaCredentials, *, channel_id: uuid.UUID
    ) -> None:
        """Store the credential on the channel, and on the tenant only if safe.

        The channel row always gets it: that is what makes a number
        self-describing and lets two numbers coexist.

        The tenant row is the subtle part. ``tenant_credentials`` holds ONE
        Meta credential per tenant, including a single ``phone_number_id``.
        Before this, connecting a second number overwrote it, and from that
        moment every outbound of the tenant — the agent's replies on the first
        line included — went out through the newly connected number. So we
        refresh it only when it is not somebody else's:

        - no tenant credential yet → write it (first connect, unchanged);
        - it already points at THIS number → refresh it (re-connect and token
          rotation, unchanged);
        - it points at a DIFFERENT number → leave it alone. The other line
          keeps resolving through it, this one resolves through its own row.

        Every tenant in production has exactly one number, so they all take
        one of the first two branches and see no change at all.
        """
        await self._channel_credentials.upsert(channel_id, credentials)

        existing = await self._credentials.get()
        if existing is not None and existing.phone_number_id != credentials.phone_number_id:
            log.info(
                "meta.credentials.tenant_row_preserved",
                channel_id=str(channel_id),
                tenant_phone_number_id=existing.phone_number_id,
                connected_phone_number_id=credentials.phone_number_id,
                reason="additional_number_connected",
            )
            return
        await self._credentials.upsert(credentials)

    async def _upsert_channel(
        self,
        *,
        display_phone: str,
        waba_id: str,
        phone_number_id: str,
        business_id: str,
        mode: str,
        quality_rating: Any,
        verified_name: Any,
        messaging_tier: Any,
        catalog_id: str | None = None,
    ) -> uuid.UUID:
        """Insert/update the ``channels`` row for this WABA.

        ``provider_identifier`` is the E.164 business phone — same shape as
        previous providers. ``config`` JSONB holds the Meta-specific IDs so the
        webhook layer can read them without a join.
        """
        tenant_id = require_current_tenant()
        from nexus_api.db.models import ChannelStatus, ChannelType

        existing = await self._session.execute(
            select(Channel).where(
                Channel.provider == "meta",
                Channel.provider_identifier == display_phone,
            )
        )
        row = existing.scalar_one_or_none()
        config: dict[str, Any] = {
            "waba_id": waba_id,
            "phone_number_id": phone_number_id,
            "business_id": business_id,
            "mode": mode,
            "verified_name": verified_name if isinstance(verified_name, str) else None,
            "quality_rating": (quality_rating if isinstance(quality_rating, str) else None),
            "messaging_tier": (messaging_tier if isinstance(messaging_tier, str) else None),
        }
        # Meta Commerce catalog linked to this WABA (WhatsApp native product
        # messages). Set only when provided (owned-number connect); the
        # Embedded Signup path leaves it absent.
        if catalog_id:
            config["catalog_id"] = catalog_id
        now = datetime.now(tz=UTC)
        if row is None:
            row = Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=display_phone,
                config=config,
                status=ChannelStatus.ACTIVE,
                last_provider_synced_at=now,
            )
            self._session.add(row)
            await self._session.flush()
        else:
            row.config = config
            row.status = ChannelStatus.ACTIVE
            row.last_provider_synced_at = now
            await self._session.flush()
        # ``row.id`` is typed as ``Mapped[UUID]`` — cast for mypy strict.
        return cast(uuid.UUID, row.id)


# ── helpers ────────────────────────────────────────────────────────────────


def _generate_pin() -> str:
    """6-digit PIN used to re-register a phone number under our app.

    The PIN is stored implicitly inside Meta — it isn't echoed back to us.
    If the same number is re-registered later (operator-driven), the same
    PIN must be supplied; we therefore persist it inside
    :class:`MetaCredentials` as part of the encrypted payload.

    Generating cryptographically random PINs (not zero-padded predictable
    sequences) makes a re-register from a different actor impossible
    without our DB row.
    """
    return f"{secrets.randbelow(1_000_000):06d}"


def _normalise_e164(phone: Any) -> str | None:
    # Canonical E.164 (``+`` + digits) via the shared normaliser, so the
    # channel we store here resolves against the same value the webhook
    # derives from ``metadata.display_phone_number``. The Graph API hands a
    # spaced number ("+34 672 13 83 67") — must collapse to "+34672138367".
    return to_e164(phone)
