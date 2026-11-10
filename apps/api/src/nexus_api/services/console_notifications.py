"""In-app notifications of the partner console + the activation metric
(PLAN-CONSOLE-V1 CP-29; table from migration 0086).

Two jobs, both platform-level (no tenant scope, no RLS):

1. :func:`emit` — write ONE ``console_notifications`` row for a partner
   (idempotent through ``dedupe_key``) and, for severity ≥ ``warning``,
   best-effort e-mail the partner's owners/admins. ``data`` is the small
   dict the console renders in the viewer's language; **never** customer
   message content (C8) and **never** internal tenant ids — a client is
   referenced by ``external_client_ref``, the id the partner already knows.
   Spec 051: the e-mail is a template of the catalogue (``partner_notice``
   for the partner; ``inbox_waiting``, ``client_balance_*`` or
   ``client_notice`` for the client's people), in each recipient's account
   language. The words of each notice live in ``services/email_notices.py``.

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

import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ClientMembership,
    ClientMemberStatus,
    ConsoleNotification,
    MembershipStatus,
    NotificationAudience,
    NotificationKind,
    NotificationSeverity,
    Partner,
    PartnerMembership,
    PartnerRole,
    PartnerTenant,
)
from nexus_api.services.email_catalog import EmailKind, console_link, email_locale
from nexus_api.services.email_notices import client_notice_email, partner_notice_email

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
    audience: NotificationAudience | str = NotificationAudience.PARTNER,
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
        # Spec 030: ``client`` lo ven (y lo reciben por correo) solo las
        # personas de ese cliente; nunca los miembros del partner.
        audience=audience.value if isinstance(audience, NotificationAudience) else str(audience),
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


#: Spec 051 (catálogo §14-16): los avisos del cliente con plantilla propia. El
#: asunto lo pone el código en el idioma del envío. Sin datos del contacto más
#: allá de su nombre, y nunca el texto de un mensaje (spec 030).
_INBOX_WAITING_SUBJECT = {
    "es": "{contact} está esperando una respuesta",
    "en": "{contact} is waiting for a reply",
}
#: ``CONTACT`` abre siempre la frase: sin nombre, esto.
_SOMEONE = {"es": "Un cliente", "en": "A customer"}
_BALANCE_LOW_SUBJECT = {
    "es": "Tu saldo no llegará a fin de mes",
    "en": "Your balance won't last until the end of the month",
}
_BALANCE_OUT_SUBJECT = {
    "es": "Tu saldo se ha agotado y tu agente ha dejado de responder",
    "en": "Your balance has run out and your agent has stopped replying",
}

Compose = Callable[[str], tuple[str, Mapping[str, str]]]


def _inbox_waiting(row: ConsoleNotification) -> Compose:
    contact = str(row.payload.get("contact") or "").strip()
    conversation = row.payload.get("conversation_id")
    url = console_link(f"/inbox?c={conversation}") if conversation else console_link("/")

    def _compose(locale: str) -> tuple[str, Mapping[str, str]]:
        lang = email_locale(locale)
        who = contact or _SOMEONE[lang]
        return _INBOX_WAITING_SUBJECT[lang].format(contact=who), {
            "CONTACT": who,
            "CONVERSATION_URL": url,
        }

    return _compose


def _balance(subjects: Mapping[str, str], client_name: str) -> Compose:
    def _compose(locale: str) -> tuple[str, Mapping[str, str]]:
        return subjects[email_locale(locale)], {
            "CLIENT_NAME": client_name,
            "CONSOLE_URL": console_link("/"),
        }

    return _compose


async def _email_client_best_effort(session: AsyncSession, row: ConsoleNotification) -> None:
    """Correo a las personas activas del cliente del aviso. Nunca lanza.

    Cada envío nombra su tipo del catálogo y el negocio (garantía 6: el
    partner, el cliente y su referencia), que es lo que barre
    ``tests/isolation/test_55_email_owner_tagging.py``.
    """
    from nexus_api.services.email import send_localized

    try:
        stmt = (
            sa.select(ClientMembership.email, PartnerTenant.tenant_id, PartnerTenant.client_name)
            .join(PartnerTenant, PartnerTenant.tenant_id == ClientMembership.tenant_id)
            .where(
                PartnerTenant.partner_id == row.partner_id,
                PartnerTenant.external_client_ref == row.external_client_ref,
                ClientMembership.partner_id == row.partner_id,
                ClientMembership.status == ClientMemberStatus.ACTIVE.value,
            )
        )
        if row.recipient_user_id:
            stmt = stmt.where(ClientMembership.user_id == row.recipient_user_id)
        found = (await session.execute(stmt)).all()
        recipients = sorted({str(r.email) for r in found})
        if not recipients:
            return
        tenant_id, ref = found[0].tenant_id, row.external_client_ref
        name = (found[0].client_name or "").strip() or str(ref)
        if row.kind == NotificationKind.INBOX_WAITING.value:
            await send_localized(
                EmailKind.INBOX_WAITING,
                to=recipients,
                compose=_inbox_waiting(row),
                partner_id=row.partner_id,
                tenant_id=tenant_id,
                client_ref=ref,
            )
        elif row.kind == NotificationKind.CLIENT_BALANCE_LOW.value:
            await send_localized(
                EmailKind.CLIENT_BALANCE_LOW,
                to=recipients,
                compose=_balance(_BALANCE_LOW_SUBJECT, name),
                partner_id=row.partner_id,
                tenant_id=tenant_id,
                client_ref=ref,
            )
        elif row.kind == NotificationKind.CLIENT_BALANCE_OUT.value:
            await send_localized(
                EmailKind.CLIENT_BALANCE_OUT,
                to=recipients,
                compose=_balance(_BALANCE_OUT_SUBJECT, name),
                partner_id=row.partner_id,
                tenant_id=tenant_id,
                client_ref=ref,
            )
        else:
            # Los de ``announce(..., to_client=True)``: texto en ``email_notices``.
            def _notice(locale: str) -> tuple[str, Mapping[str, str]]:
                return client_notice_email(row, locale, name)

            await send_localized(
                EmailKind.CLIENT_NOTICE,
                to=recipients,
                compose=_notice,
                partner_id=row.partner_id,
                tenant_id=tenant_id,
                client_ref=ref,
            )
    except Exception as exc:  # pragma: no cover - never let e-mail break the request
        log.warning("console_notifications.client_email_failed", error=str(exc))


async def _client_name(session: AsyncSession, row: ConsoleNotification) -> str | None:
    """El nombre del cliente del aviso, para ``{client}``; sin él, su referencia."""
    if not row.external_client_ref:
        return None
    name = await session.scalar(
        sa.select(PartnerTenant.client_name).where(
            PartnerTenant.partner_id == row.partner_id,
            PartnerTenant.external_client_ref == row.external_client_ref,
        )
    )
    return str(name) if name else None


async def _email_best_effort(session: AsyncSession, row: ConsoleNotification) -> None:
    if row.audience == NotificationAudience.CLIENT.value:
        await _email_client_best_effort(session, row)
        return
    from nexus_api.services.email import send_localized

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
        client_name = await _client_name(session, row)

        # El texto de cada tipo vive en ``email_notices`` (catálogo §18): ya no
        # se vuelcan las claves del aviso. ``client.out_of_quota`` también sale
        # por aquí cuando el partner no tiene lista de alertas de consumo.
        def _compose(locale: str) -> tuple[str, Mapping[str, str]]:
            return partner_notice_email(row, locale, client_name)

        await send_localized(
            EmailKind.PARTNER_NOTICE,
            to=recipients,
            compose=_compose,
            partner_id=row.partner_id,
            client_ref=row.external_client_ref,
        )
    except Exception as exc:  # pragma: no cover - never let e-mail break the request
        log.warning("console_notifications.email_failed", error=str(exc))


# ── activation metric ─────────────────────────────────────────────────


async def record_client_activation(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    external_client_ref: str,
    now: datetime | None = None,
    serving: tuple[bool, list[str]] | None = None,
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
    # ``serving`` lets a caller that KNOWS pass the answer: the WhatsApp
    # signup (spec 016, R1.2) activates inside its own transaction, and a
    # fresh session would not see the channel it just created.
    if serving is not None:
        can_serve, missing = serving
    else:
        can_serve, missing = await _client_can_serve(session, partner_id, external_client_ref)
    await emit(
        session,
        partner_id=partner_id,
        kind=NotificationKind.CLIENT_ACTIVATED,
        data={
            "external_client_ref": external_client_ref,
            "first": first,
            "can_serve": can_serve,
            # What stands between "activated" and "answering": ``quota``
            # (the wallet gate is closed) and/or ``whatsapp`` (no customer-
            # facing channel). The console names the missing piece.
            "missing": missing,
        },
        severity=(NotificationSeverity.INFO if can_serve else NotificationSeverity.WARNING),
        external_client_ref=external_client_ref,
        dedupe_key=f"partner:{partner_id}:client.activated:{external_client_ref}",
    )
    return first


async def _client_can_serve(
    session: AsyncSession, partner_id: uuid.UUID, external_client_ref: str
) -> tuple[bool, list[str]]:
    """¿Contestaría este cliente a un mensaje que llegase ahora? Y si no, ¿qué falta?

    Dos cosas pueden faltar: cuota (``allow_channel_turn`` es la misma
    puerta que abre o cierra el dispatcher) y un canal por el que llegue el
    mensaje (un canal de clientes activo; el del Playground no cuenta).

    No lanza: un fallo leyendo el libro no puede tumbar una activación. En
    la duda devuelve ``False`` y la notificación avisa de más, que es el
    lado seguro — el otro es el silencio del 31-ago.
    """
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models import Channel, ChannelStatus, PartnerTenant
    from nexus_api.metering.wallet import allow_channel_turn
    from nexus_api.services.console_traffic import customer_facing_channel

    missing: list[str] = []
    try:
        tenant_id = await session.scalar(
            sa.select(PartnerTenant.tenant_id).where(
                PartnerTenant.partner_id == partner_id,
                PartnerTenant.external_client_ref == external_client_ref,
            )
        )
        if tenant_id is None:
            return False, ["quota", "whatsapp"]
        if not await allow_channel_turn(tenant_id):
            missing.append("quota")
        factory = get_sessionmaker()
        async with factory() as scoped, tenant_scoped_session(scoped, tenant_id):
            has_channel = (
                await scoped.scalar(
                    sa.select(Channel.id)
                    .where(Channel.status == ChannelStatus.ACTIVE, customer_facing_channel())
                    .limit(1)
                )
            ) is not None
        if not has_channel:
            missing.append("whatsapp")
        return not missing, missing
    except Exception as exc:
        log.warning(
            "notifications.can_serve_unreadable",
            partner_id=str(partner_id),
            client=external_client_ref,
            error=str(exc),
        )
        return False, missing or ["quota", "whatsapp"]


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
