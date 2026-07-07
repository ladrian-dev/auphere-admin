"""Owner outbox dispatcher (Meta Cloud API).

Mirrors :mod:`nexus_worker.streams.outbound` but drains
``owner_consultations WHERE status='pending'`` instead of customer-side
messages. For each row:

1. Resolve the recipient owner phone via ``owner_phone_index``.
2. Resolve the Auphere backchannel number for that owner
   (``resolve_channel_for_owner`` — pinned channel, else provider
   default). The channel row carries the Meta ``phone_number_id`` and
   the Fernet-encrypted access token.
3. Render the template with the row's stored params and send through
   :class:`MetaClient.send_template`. The sender is the Auphere
   multi-tenant number, NOT the tenant's business number — the owner
   sees Auphere talking to them.
4. On success: mark ``status='sent'``, persist ``provider_message_id``
   so an owner reply can be matched via quoted message.
5. On failure: increment a retry counter and either retry the next tick
   or mark ``cancelled`` after :data:`MAX_ATTEMPTS`.

Templates (``auphere_owner_consult`` / ``auphere_owner_action_request``)
use **named** variables — the components builder emits
``parameter_name`` entries per the Cloud API contract. The templates
must be approved on the Auphere WABA in Meta Business Manager.

Tenant isolation: each row carries ``tenant_id`` and the dispatcher
enters :func:`tenant_scoped_session` BEFORE reading any tenant-scoped
table. The ``Tenant`` table itself is global (no RLS) and is read inside
the scoped session for convenience.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import OwnerConsultation, OwnerPhoneIndex, Tenant
from nexus_api.repositories import resolve_channel_for_owner
from nexus_api.repositories.auphere_channels import ResolvedAuphereChannel
from nexus_channels.whatsapp_meta import MetaClient

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 1.0
DEFAULT_BATCH_SIZE = 25
MAX_ATTEMPTS = 5


async def run_owner_outbox_dispatcher(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    meta_client: MetaClient | None = None,
) -> None:
    """Background task. Returns when ``stop`` is set.

    Each consultation resolves its own outbound channel per-tenant via
    ``resolve_channel_for_owner`` — so a multi-country setup can serve
    CL owners from +56 and AR owners from +54 without any restart.
    ``meta_client`` is injectable for tests; production builds one from
    settings and closes it on exit.
    """
    log.info(
        "owner_outbox.dispatcher.start",
        tick_seconds=tick_seconds,
        batch=batch_size,
    )
    settings = get_settings()
    own_client = meta_client is None
    client = meta_client or MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
    )
    sm = get_sessionmaker()
    try:
        while not stop.is_set():
            try:
                tenant_ids = await _list_tenants_with_pending(sm)
                for tid in tenant_ids:
                    if stop.is_set():
                        break
                    await _drain_tenant(sm, tid, client, batch_size)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("owner_outbox.dispatcher.tick_failed", error=str(exc))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    finally:
        if own_client:
            with contextlib.suppress(Exception):
                await client.close()
    log.info("owner_outbox.dispatcher.stopped")


async def _list_tenants_with_pending(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
) -> list[uuid.UUID]:
    """Cheap discovery query — RLS is bypassed because we read with the
    migration role here (no ``SET LOCAL ROLE`` issued). Returning the
    distinct list lets us scope the actual drains by tenant."""
    async with sm() as session:
        rows = await session.execute(
            sa.select(OwnerConsultation.tenant_id)
            .where(OwnerConsultation.status == "pending")
            .distinct()
        )
        return [row[0] for row in rows]


async def _drain_tenant(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
    client: MetaClient,
    batch_size: int,
) -> None:
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        # Fetch the active owner row (full record, not just the phone)
        # so the resolver can read ``auphere_channel_id`` for outbound
        # routing. RLS-free table — read inside the scoped session for
        # convenience.
        owner_row_q = await session.execute(
            sa.select(OwnerPhoneIndex)
            .where(OwnerPhoneIndex.tenant_id == tenant_id)
            .where(OwnerPhoneIndex.active.is_(True))
            .order_by(OwnerPhoneIndex.added_at.asc())
            .limit(1)
        )
        owner = owner_row_q.scalar_one_or_none()

        tenant_row = await session.get(Tenant, tenant_id)
        if tenant_row is None:  # pragma: no cover
            return

        # Resolve the Auphere channel ONCE per tenant batch. Per-owner
        # resolution happens via ``owner.auphere_channel_id``, with
        # fallback to the provider default.
        channel: ResolvedAuphereChannel | None = None
        if owner is not None:
            channel = await resolve_channel_for_owner(session, owner=owner)

        rows = await session.execute(
            sa.select(OwnerConsultation)
            .where(OwnerConsultation.status == "pending")
            .order_by(OwnerConsultation.asked_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        pending = list(rows.scalars())
        if not pending:
            return
        log.info(
            "owner_outbox.dispatcher.batch",
            tenant_id=str(tenant_id),
            count=len(pending),
            has_owner_phone=owner is not None,
            from_channel=channel.display_name if channel else None,
        )
        for row in pending:
            await _send_one(
                row=row,
                client=client,
                channel=channel,
                recipient=owner.phone_e164 if owner else None,
                tenant_name=tenant_row.name,
            )


async def _send_one(
    *,
    row: OwnerConsultation,
    client: MetaClient,
    channel: ResolvedAuphereChannel | None,
    recipient: str | None,
    tenant_name: str,
) -> None:
    if recipient is None:
        row.status = "cancelled"
        row.cancelled_at = datetime.now(UTC)
        row.cancelled_reason = "no owner_phone_index for tenant"
        log.warning(
            "owner_outbox.cancelled.no_recipient",
            tenant_id=str(row.tenant_id),
            consultation_id=str(row.id),
        )
        return
    if channel is None or not channel.can_send:
        # No backchannel resolved (registry empty) OR the channel lacks
        # credentials. Hold the row so a later config change picks it up
        # (do NOT cancel — operator may be mid-setup in the panel).
        log.info(
            "owner_outbox.held.no_channel",
            tenant_id=str(row.tenant_id),
            consultation_id=str(row.id),
            has_channel=channel is not None,
        )
        return

    components = _template_components(row, tenant_name=tenant_name)
    try:
        assert channel.provider_phone_id is not None  # can_send guarantees
        assert channel.access_token is not None
        result = await client.send_template(
            phone_number_id=channel.provider_phone_id,
            access_token=channel.access_token,
            to=recipient.lstrip("+"),
            template_name=row.template_name,
            language="es",
            components=components,
        )
    except Exception as exc:
        row.reminded_count += 1
        if row.reminded_count >= MAX_ATTEMPTS:
            row.status = "cancelled"
            row.cancelled_at = datetime.now(UTC)
            row.cancelled_reason = (
                f"dispatcher: send failed {row.reminded_count}x: {type(exc).__name__}: {exc}"
            )[:500]
            log.warning(
                "owner_outbox.permanent_failure",
                tenant_id=str(row.tenant_id),
                consultation_id=str(row.id),
                error=row.cancelled_reason,
            )
        else:
            log.info(
                "owner_outbox.retry",
                tenant_id=str(row.tenant_id),
                consultation_id=str(row.id),
                attempts=row.reminded_count,
                error=str(exc)[:200],
            )
        return

    row.status = "sent"
    row.sent_at = datetime.now(UTC)
    row.provider_message_id = _extract_wamid(result)
    log.info(
        "owner_outbox.sent",
        tenant_id=str(row.tenant_id),
        consultation_id=str(row.id),
        provider_message_id=row.provider_message_id,
    )


def _extract_wamid(result: dict[str, Any]) -> str | None:
    messages = result.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            wamid = first.get("id")
            if isinstance(wamid, str):
                return wamid
    return None


def _template_components(row: OwnerConsultation, *, tenant_name: str) -> list[dict[str, Any]]:
    """Build Cloud API ``components`` with NAMED body parameters.

    Both Phase 1 templates (``auphere_owner_consult`` and
    ``auphere_owner_action_request``) declare **named** variables (not
    positional ``{{1}}…{{4}}``). The keys match the variable names
    registered in the template:

    - ``tenant_name`` — tenant business name
    - ``question`` — question / action description
    - ``urgency`` — urgency label (low / normal / high)
    - ``correlation_id`` — short ref the owner quotes when replying

    Keeping the key set identical across templates lets us add new
    template variants without touching this renderer.
    """
    params = row.template_params_json or {}
    named = {
        "tenant_name": str(params.get("tenant_name") or tenant_name),
        "question": str(params.get("question") or row.question_text),
        "urgency": str(params.get("urgency") or row.urgency),
        "correlation_id": row.correlation_id,
    }
    return [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "parameter_name": key, "text": value}
                for key, value in named.items()
            ],
        }
    ]
