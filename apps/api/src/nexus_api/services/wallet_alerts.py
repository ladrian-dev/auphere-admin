"""Avisos de saldo del partner (D7).

Hermano de ``usage_alerts`` y **no lo mismo**. Aquel vigila el tope
comercial de mensajes y, en palabras de su propio módulo, «avisa, no
corta». Este vigila el saldo de tokens, y el saldo **sí corta**:
``allow_channel_turn`` cierra la puerta en cuanto el wallet queda vacío o
la asignación del cliente llega a 0, y el cliente deja de contestar sin un
solo error. Ese silencio es lo que costó el corte del 31-ago.

Por eso los umbrales aquí significan otra cosa y el correo lo dice: al
100 % no es que «se haya superado un tope», es que **los agentes se han
callado**.

Dos niveles, porque el saldo tiene dos techos:

- **El wallet del partner** — included del mes más purchased. Se repone el
  día 1 (``wallet_renewal_cron``); si se agota antes, callan todos sus
  clientes a la vez.
- **La asignación de cada cliente** — su ``cap`` dentro de ese wallet. Se
  agota sola y calla **solo a ese cliente**, con el partner lleno de saldo,
  que es el caso más difícil de diagnosticar desde fuera.

Idempotente por construcción: una fila por umbral, partner y mes, con el
mismo índice único de dedupe que usa CP-24, así que un tick repetido o un
reinicio no vuelven a avisar.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ConsoleNotification,
    NotificationKind,
    NotificationSeverity,
    Partner,
)
from nexus_api.metering.wallet import read_wallet
from nexus_api.services.console_reporting import month_bounds
from nexus_api.services.email import send_email

log = structlog.get_logger(__name__)

#: 80 % avisa con margen; 100 % es que ya no se atiende.
THRESHOLDS: tuple[int, ...] = (80, 100)


@dataclass
class WalletAlertEvaluation:
    available: int
    cap: int | None
    percent_used: float | None
    created: list[int] = field(default_factory=list)
    clients_out: list[str] = field(default_factory=list)
    emailed: bool = False


def wallet_dedupe_key(partner_id: uuid.UUID, threshold: int, since: datetime) -> str:
    """Distinto namespace que CP-24 (``:usage:``) — son dos libros."""
    return f"partner:{partner_id}:wallet:{threshold}:{since:%Y-%m}"


def client_out_of_quota_dedupe_key(partner_id: uuid.UUID, ref: str, now: datetime) -> str:
    """Uno por cliente y día (spec 016, R2.3)."""
    return f"partner:{partner_id}:client.out_of_quota:{ref}:{now:%Y-%m-%d}"


def _alert_recipients(partner: Partner) -> list[str]:
    return [r for r in (partner.usage_alert_recipients or []) if isinstance(r, str) and r]


async def _emit_client_out_of_quota(
    session: AsyncSession, partner: Partner, ref: str, *, now: datetime | None = None
) -> ConsoleNotification | None:
    """Aviso «{cliente} se ha quedado sin cupo» en la campana y por correo.

    Spec 016 (R2.2-R2.3). Dentro de la transacción del llamador. Si el
    partner tiene ``usage_alert_recipients`` el correo va a ellos con un
    texto que dice qué hacer; si no, ``emit`` avisa a owners y admins como
    con cualquier ``warning``. Un segundo aviso el mismo día no se crea.
    """
    from nexus_api.services.console_notifications import emit

    ts = now or datetime.now(UTC)
    recipients = _alert_recipients(partner)
    row = await emit(
        session,
        partner_id=partner.id,
        kind=NotificationKind.CLIENT_OUT_OF_QUOTA,
        data={"external_client_ref": ref, "remaining": 0},
        severity=NotificationSeverity.WARNING,
        external_client_ref=ref,
        dedupe_key=client_out_of_quota_dedupe_key(partner.id, ref, ts),
        email=not recipients,
    )
    if row is not None and recipients:
        await _email_client_out_of_quota(partner, ref, recipients)
    return row


async def _email_client_out_of_quota(partner: Partner, ref: str, recipients: list[str]) -> bool:
    subject = f"[Auphere] {partner.name}: {ref} se ha quedado sin saldo"
    html = (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:560px;margin:0 auto;color:#111">'
        f"<p style='font-size:16px;margin:0 0 8px'><strong>El cliente {ref} ha agotado su "
        "saldo y sus mensajes no se están atendiendo.</strong></p>"
        "<p style='margin:0'>Habla con tu cliente y súbele el tope en la sección "
        "Consumo de la consola. En cuanto tenga saldo, el agente vuelve a contestar solo.</p>"
        "</div>"
    )
    try:
        await send_email(to=recipients, subject=subject, html=html)
        return True
    except Exception as exc:  # pragma: no cover - best effort
        log.warning("wallet_alerts.client_email_failed", partner_id=str(partner.id), error=str(exc))
        return False


async def notify_client_out_of_quota_detached(tenant_id: uuid.UUID) -> ConsoleNotification | None:
    """El despachador saltó un turno por falta de cupo: que el partner lo vea.

    Sesión propia (el llamador está en una transacción de tenant, o en
    ninguna). Resuelve partner y ref por ``partner_tenants``; un tenant sin
    partner no tiene a quién avisar. **Recomprueba** ``allow_channel_turn``
    (R2.5): si entre el salto y el aviso alguien ya asignó cupo, no avisa.
    """
    from nexus_api.db.models import PartnerTenant
    from nexus_api.metering.wallet import allow_channel_turn

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        mapping = (
            await session.execute(
                sa.select(PartnerTenant.partner_id, PartnerTenant.external_client_ref).where(
                    PartnerTenant.tenant_id == tenant_id
                )
            )
        ).first()
        if mapping is None:
            return None
        partner_id, ref = mapping
        if await allow_channel_turn(tenant_id):
            return None
        partner = await session.get(Partner, partner_id)
        if partner is None:
            return None
        row = await _emit_client_out_of_quota(session, partner, ref)
        # Spec 030 (R15.3): si el cliente tiene consola, su gente también se
        # entera — en su campana y por correo, nunca en la del partner.
        if await _lite_enabled(session, tenant_id):
            await _emit_client_balance(session, partner_id, tenant_id, ref, "balance_out")
        return row


# ── Spec 030: los avisos de saldo del propio cliente ──────────────────


def client_balance_dedupe_key(tenant_id: uuid.UUID, kind: str, now: datetime) -> str:
    """Agotado: uno por cliente y día (como el del partner). «No llega a fin
    de mes»: uno por cliente y mes — repetirlo cada día sería ruido."""
    period = f"{now:%Y-%m-%d}" if kind == "balance_out" else f"{now:%Y-%m}"
    return f"client:{tenant_id}:{kind}:{period}"


async def _lite_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    from nexus_api.db.models import ClientAccess

    access = await session.get(ClientAccess, tenant_id)
    return bool(access and access.enabled)


async def _emit_client_balance(
    session: AsyncSession,
    partner_id: uuid.UUID,
    tenant_id: uuid.UUID,
    ref: str,
    kind: str,
    *,
    days_left: float | None = None,
    now: datetime | None = None,
) -> ConsoleNotification | None:
    """``client.balance_out`` / ``client.balance_low`` con ``audience =
    client``: la campana del cliente y el correo a sus personas activas
    (``console_notifications._email_client_best_effort``)."""
    from nexus_api.db.models import NotificationAudience
    from nexus_api.services.console_notifications import emit

    ts = now or datetime.now(UTC)
    data: dict[str, object] = {}
    if days_left is not None:
        data["days_left"] = max(round(days_left), 0)
    return await emit(
        session,
        partner_id=partner_id,
        kind=(
            NotificationKind.CLIENT_BALANCE_OUT
            if kind == "balance_out"
            else NotificationKind.CLIENT_BALANCE_LOW
        ),
        data=data,
        severity=NotificationSeverity.WARNING,
        external_client_ref=ref,
        dedupe_key=client_balance_dedupe_key(tenant_id, kind, ts),
        audience=NotificationAudience.CLIENT,
    )


async def evaluate_client_balance_alerts(
    session: AsyncSession, partner_id: uuid.UUID, *, now: datetime | None = None
) -> list[str]:
    """Spec 030 (R15.3): avisa a cada cliente con consola de su saldo, con la
    misma regla que su Panel (``lite_home.balance_notice``). Devuelve los
    ``external_client_ref`` a los que se avisó.

    Como ``evaluate_partner_wallet_alerts``: espera una ``session`` sin
    transacción abierta y gestiona las suyas, cortas.
    """
    from nexus_api.db.models import ClientAccess, PartnerTenant
    from nexus_api.metering.wallet import allocations_for, credit_burn
    from nexus_api.services.console_home import REVIEW_WINDOW
    from nexus_api.services.console_home_blocks import days_until
    from nexus_api.services.lite_home import balance_notice, balance_of

    ts = now or datetime.now(UTC)
    _since, until, _elapsed, _days = month_bounds(ts)
    async with session.begin():
        rows = (
            await session.execute(
                sa.select(PartnerTenant.tenant_id, PartnerTenant.external_client_ref)
                .join(ClientAccess, ClientAccess.tenant_id == PartnerTenant.tenant_id)
                .where(
                    PartnerTenant.partner_id == partner_id,
                    ClientAccess.partner_id == partner_id,
                    ClientAccess.enabled.is_(True),
                )
            )
        ).all()
    if not rows:
        return []
    refs = {tenant_id: str(ref) for tenant_id, ref in rows}
    tenant_ids = list(refs)
    allocations = await allocations_for(partner_id, tenant_ids)
    burn = await credit_burn(partner_id, tenant_ids, ts - REVIEW_WINDOW)
    to_month_end = days_until(until, ts)

    told: list[str] = []
    for tenant_id in tenant_ids:
        balance = balance_of(allocations.get(tenant_id), burn.get(tenant_id, 0))
        notice = balance_notice(balance, to_month_end)
        if notice is None:
            continue
        async with session.begin():
            row = await _emit_client_balance(
                session,
                partner_id,
                tenant_id,
                refs[tenant_id],
                notice,
                days_left=balance.days_left,
                now=ts,
            )
        if row is not None:
            told.append(refs[tenant_id])
    return told


def _percent_used(available: int, cap: int) -> float:
    if cap <= 0:
        return 0.0
    used = max(0, cap - max(0, available))
    return min(100.0, round(100.0 * used / cap, 2))


async def clients_without_quota(session: AsyncSession, partner_id: uuid.UUID) -> list[str]:
    """Clientes del partner que ya no contestan por falta de cupo, como refs.

    Misma definición que la puerta del canal (``quota_state``): sin fila, con
    ``remaining <= 0`` o con la cartera vacía. Antes excluía ``cap = 0`` como
    «apagado a propósito»; la spec 016 (R2.1) pide que la ficha, el aviso y
    la puerta digan lo mismo, y la puerta no distingue. Devuelve
    ``external_client_ref`` porque ``console_notifications`` nunca guarda
    ``tenant_id``.
    """
    from nexus_api.db.models import PartnerTenant
    from nexus_api.metering.wallet import quota_state

    mappings = (
        await session.execute(
            sa.select(PartnerTenant.tenant_id, PartnerTenant.external_client_ref).where(
                PartnerTenant.partner_id == partner_id
            )
        )
    ).all()
    if not mappings:
        return []
    states = await quota_state(partner_id, [tid for tid, _ in mappings])
    return sorted(ref for tid, ref in mappings if states.get(tid, True))


async def evaluate_partner_wallet_alerts(
    session: AsyncSession,
    partner: Partner,
    *,
    now: datetime | None = None,
) -> WalletAlertEvaluation:
    """Evalúa el saldo del partner y avisa una vez por umbral y mes.

    **Espera una ``session`` sin transacción abierta** y gestiona sus propias
    transacciones cortas, igual que ``usage_alerts``. El sessionmaker va con
    ``expire_on_commit=False``, así que leer atributos del ``partner`` tras un
    commit previo del llamador no dispara refresh y la sesión sigue limpia —
    que es como la deja ``usage_alerts_cron``.

    Si llega con una transacción ya abierta, SQLAlchemy lo dirá en voz alta
    («A transaction is already begun»). Se dejó así a propósito: la variante
    tolerante que se probó el 2026-09-08 no comiteaba cuando la transacción
    era del llamador, y las notificaciones se perdían en el rollback **sin un
    solo error**. Un fallo que se ve es mejor que un aviso que no sale.

    Un fallo de correo nunca tumba la evaluación: la notificación en la
    consola es el registro durable.
    """
    since, _until, _elapsed, _days = month_bounds(now)
    cap = int(partner.companion_monthly_token_cap or 0)
    snap = await read_wallet(partner.id)
    available = snap.available if snap is not None else 0

    result = WalletAlertEvaluation(
        available=available,
        cap=cap or None,
        percent_used=_percent_used(available, cap) if cap > 0 else None,
    )
    if snap is None or cap <= 0 or result.percent_used is None:
        return result

    async with session.begin():
        result.clients_out = await clients_without_quota(session, partner.id)
    # Spec 016 (R2.2): red de seguridad. El aviso por cliente lo dispara el
    # turno saltado; si el despachador no llegó a avisar, lo hace el cron.
    for ref in result.clients_out:
        async with session.begin():
            await _emit_client_out_of_quota(session, partner, ref, now=now)

    for threshold in THRESHOLDS:
        if result.percent_used < threshold:
            continue
        kind = NotificationKind.WALLET_EMPTY if threshold >= 100 else NotificationKind.WALLET_LOW
        severity = (
            NotificationSeverity.CRITICAL if threshold >= 100 else NotificationSeverity.WARNING
        )
        stmt = (
            pg_insert(ConsoleNotification)
            .values(
                partner_id=partner.id,
                kind=kind.value,
                severity=severity.value,
                payload={
                    "percent": threshold,
                    "cap": cap,
                    "available": available,
                    "period": f"{since:%Y-%m}",
                    "clients_out": len(result.clients_out),
                },
                dedupe_key=wallet_dedupe_key(partner.id, threshold, since),
            )
            .on_conflict_do_nothing(
                index_elements=["dedupe_key"], index_where=sa.text("dedupe_key IS NOT NULL")
            )
        )
        async with session.begin():
            inserted = await session.execute(stmt.returning(ConsoleNotification.id))
            if inserted.scalar_one_or_none() is not None:
                result.created.append(threshold)

    if result.created:
        result.emailed = await _notify_by_email(partner, result, since)
    return result


async def _notify_by_email(partner: Partner, ev: WalletAlertEvaluation, since: datetime) -> bool:
    recipients = [r for r in (partner.usage_alert_recipients or []) if isinstance(r, str) and r]
    if not recipients:
        return False
    top = max(ev.created)
    period = f"{since:%Y-%m}"
    if top >= 100:
        subject = f"[Auphere] {partner.name}: saldo agotado — los agentes han dejado de responder"
        headline = "Se ha agotado el saldo del mes y vuestros agentes ya no están contestando."
        note = (
            "Esto no es un aviso preventivo: los mensajes que lleguen ahora no reciben "
            "respuesta. Escribidnos y recargamos el saldo."
        )
    else:
        subject = f"[Auphere] {partner.name}: queda el {100 - top} % del saldo ({period})"
        headline = f"Habéis consumido el {top} % del saldo del mes."
        note = (
            "Cuando se agote, los agentes dejarán de responder a vuestros clientes. "
            "Avisadnos antes de llegar ahí y lo ampliamos."
        )
    extra = ""
    if ev.clients_out:
        extra = (
            f"<p style='margin:12px 0 0'>Además, <strong>{len(ev.clients_out)}</strong> "
            "cliente(s) ya han agotado su tope y no están respondiendo, "
            "aunque quede saldo general.</p>"
        )
    html = (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'max-width:560px;margin:0 auto;color:#111">'
        f"<p style='font-size:16px;margin:0 0 8px'><strong>{headline}</strong></p>"
        f"<p style='margin:0'>{note}</p>{extra}"
        f"<p style='color:#666;font-size:13px;margin:20px 0 0'>Periodo {period}.</p></div>"
    )
    try:
        await send_email(to=recipients, subject=subject, html=html)
        return True
    except Exception as exc:  # pragma: no cover - best effort
        log.warning("wallet_alerts.email_failed", partner_id=str(partner.id), error=str(exc))
        return False


__all__ = [
    "THRESHOLDS",
    "WalletAlertEvaluation",
    "client_out_of_quota_dedupe_key",
    "clients_without_quota",
    "evaluate_client_balance_alerts",
    "evaluate_partner_wallet_alerts",
    "notify_client_out_of_quota_detached",
    "wallet_dedupe_key",
]
