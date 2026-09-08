"""In-app notifications of the partner console + the activation metric
(PLAN-CONSOLE-V1 CP-29; table from migration 0086).

Two jobs, both platform-level (no tenant scope, no RLS):

1. :func:`emit` — write ONE ``console_notifications`` row for a partner
   (idempotent through ``dedupe_key``) and, for severity ≥ ``warning``,
   best-effort e-mail the partner's owners/admins. ``data`` is the small
   dict the console renders in the viewer's language; **never** customer
   message content (C8) and **never** internal tenant ids — a client is
   referenced by ``external_client_ref``, the id the partner already knows.

2. :func:`record_client_activation` — the first time a partner has an
   ACTIVE client with a published agent, stamp ``partners.activated_at``
   (time-to-first-active-client) and emit ``client.activated``.

Callers inside a **tenant-scoped** transaction (``SET LOCAL ROLE
nexus_app``) cannot write these platform tables; they use the
``*_detached`` variants, which open their own short session. Callers in a
plain platform transaction (invitation accept, scripts) pass their
session.
"""

from __future__ import annotations

import html
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ConsoleNotification,
    MembershipStatus,
    NotificationKind,
    NotificationSeverity,
    Partner,
    PartnerMembership,
    PartnerRole,
)
from nexus_api.services.email import send_email

log = structlog.get_logger(__name__)

#: Roles that receive the e-mail copy of a warning/critical notification.
_EMAIL_ROLES: frozenset[str] = frozenset({PartnerRole.OWNER.value, PartnerRole.ADMIN.value})


async def emit(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    kind: NotificationKind | str,
    data: dict[str, Any] | None = None,
    severity: NotificationSeverity | str = NotificationSeverity.INFO,
    recipient_user_id: str | None = None,
    external_client_ref: str | None = None,
    dedupe_key: str | None = None,
    email: bool | None = None,
) -> ConsoleNotification | None:
    """Insert one notification inside the caller's transaction.

    Returns the row, or ``None`` when ``dedupe_key`` already exists (the
    partial unique index makes the emitter idempotent; the failed INSERT
    is rolled back to a savepoint so the caller's transaction survives).
    E-mail (``email=None`` → automatic for severity ≥ warning) is sent
    after the row exists and never raises.
    """
    kind_value = kind.value if isinstance(kind, NotificationKind) else str(kind)
    sev_value = severity.value if isinstance(severity, NotificationSeverity) else str(severity)
    payload = dict(data or {})
    row = ConsoleNotification(
        id=uuid.uuid4(),
        partner_id=partner_id,
        recipient_user_id=recipient_user_id,
        external_client_ref=external_client_ref,
        kind=kind_value,
        severity=sev_value,
        payload=payload,
        dedupe_key=dedupe_key,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        log.info("console_notifications.deduped", partner_id=str(partner_id), kind=kind_value)
        return None

    want_email = email if email is not None else sev_value in {"warning", "critical"}
    if want_email:
        await _email_best_effort(session, row)
    return row


async def emit_detached(**kwargs: Any) -> ConsoleNotification | None:
    """:func:`emit` in its own short platform session — for callers that
    are inside a tenant-scoped (``nexus_app``) transaction."""
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        return await emit(session, **kwargs)


async def _email_best_effort(session: AsyncSession, row: ConsoleNotification) -> None:
    try:
        if row.recipient_user_id:
            stmt = sa.select(PartnerMembership.email).where(
                PartnerMembership.partner_id == row.partner_id,
                PartnerMembership.user_id == row.recipient_user_id,
                PartnerMembership.status == MembershipStatus.ACTIVE.value,
            )
        else:
            stmt = sa.select(PartnerMembership.email).where(
                PartnerMembership.partner_id == row.partner_id,
                PartnerMembership.status == MembershipStatus.ACTIVE.value,
                PartnerMembership.role.in_(sorted(_EMAIL_ROLES)),
            )
        recipients = [str(e) for e in (await session.scalars(stmt)).all()]
        if not recipients:
            return
        subject = f"[Auphere] {row.kind} ({row.severity})"
        pairs = "".join(
            f"<li><code>{html.escape(str(k))}</code>: {html.escape(str(v))}</li>"
            for k, v in sorted(row.payload.items())
        )
        body = (
            f"<p>Nueva notificación en tu consola de partner: <b>{html.escape(row.kind)}</b>.</p>"
            f"<ul>{pairs}</ul>"
            "<p>Ábrela en la consola → Notificaciones.</p>"
        )
        await send_email(to=recipients, subject=subject, html=body)
    except Exception as exc:  # pragma: no cover - never let e-mail break the request
        log.warning("console_notifications.email_failed", error=str(exc))


# ── activation metric ─────────────────────────────────────────────────


async def record_client_activation(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    external_client_ref: str,
    now: datetime | None = None,
) -> bool:
    """A client of ``partner_id`` is ACTIVE with a published agent.

    Stamps ``partners.activated_at`` the FIRST time only (the metric is
    time-to-first-active-client) and emits ``client.activated`` once per
    client (dedupe on the client ref). Returns True when this call was the
    partner's first activation. Platform transaction of the caller.
    """
    ts = now or datetime.now(UTC)
    result = await session.execute(
        sa.update(Partner)
        .where(Partner.id == partner_id, Partner.activated_at.is_(None))
        .values(activated_at=ts)
    )
    first = (getattr(result, "rowcount", 0) or 0) > 0

    # D8 — «activado» no puede significar «ya atiende» si no atiende.
    #
    # ``allow_channel_turn`` es la misma puerta que abre o cierra el
    # dispatcher, así que preguntarle aquí es preguntar por lo único que
    # importa: si llega un mensaje ahora, ¿contesta? Cuando la respuesta es
    # no, la notificación lo dice (``can_serve``) y sube a ``warning``, que
    # es lo que la hace visible en la consola en vez de pasar por un
    # «todo bien» más.
    can_serve = await _client_can_serve(session, partner_id, external_client_ref)
    await emit(
        session,
        partner_id=partner_id,
        kind=NotificationKind.CLIENT_ACTIVATED,
        data={
            "external_client_ref": external_client_ref,
            "first": first,
            "can_serve": can_serve,
        },
        severity=(NotificationSeverity.INFO if can_serve else NotificationSeverity.WARNING),
        external_client_ref=external_client_ref,
        dedupe_key=f"partner:{partner_id}:client.activated:{external_client_ref}",
    )
    return first


async def _client_can_serve(
    session: AsyncSession, partner_id: uuid.UUID, external_client_ref: str
) -> bool:
    """¿Contestaría este cliente a un mensaje que llegase ahora?

    No lanza: un fallo leyendo el libro no puede tumbar una activación. En
    la duda devuelve ``False`` y la notificación avisa de más, que es el
    lado seguro — el otro es el silencio del 31-ago.
    """
    from nexus_api.db.models import PartnerTenant
    from nexus_api.metering.wallet import allow_channel_turn

    try:
        tenant_id = await session.scalar(
            sa.select(PartnerTenant.tenant_id).where(
                PartnerTenant.partner_id == partner_id,
                PartnerTenant.external_client_ref == external_client_ref,
            )
        )
        if tenant_id is None:
            return False
        return await allow_channel_turn(tenant_id)
    except Exception as exc:
        log.warning(
            "notifications.can_serve_unreadable",
            partner_id=str(partner_id),
            client=external_client_ref,
            error=str(exc),
        )
        return False


async def record_client_activation_detached(**kwargs: Any) -> bool:
    factory = get_sessionmaker()
    async with factory() as session, session.begin():
        return await record_client_activation(session, **kwargs)


__all__ = [
    "emit",
    "emit_detached",
    "record_client_activation",
    "record_client_activation_detached",
]
