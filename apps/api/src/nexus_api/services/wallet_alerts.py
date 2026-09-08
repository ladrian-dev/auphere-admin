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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    ConsoleNotification,
    NotificationKind,
    NotificationSeverity,
    Partner,
    PartnerAllocation,
)
from nexus_api.metering.wallet import read_wallet
from nexus_api.services.console_reporting import month_bounds
from nexus_api.services.email import send_email

log = structlog.get_logger(__name__)

#: 80 % avisa con margen; 100 % es que ya no se atiende.
THRESHOLDS: tuple[int, ...] = (80, 100)


@asynccontextmanager
async def _tx(session: AsyncSession) -> AsyncIterator[None]:
    """Transacción propia, o la del llamador si ya tiene una abierta.

    Sin esto la función solo funciona con una sesión recién abierta: basta
    un ``execute`` previo del llamador —o leer un atributo de un objeto ORM
    expirado tras commit, que dispara un refresh— para que SQLAlchemy tenga
    ya una transacción implícita y ``session.begin()`` estalle con «A
    transaction is already begun». Es un contrato implícito y frágil; esto
    lo quita de en medio.
    """
    if session.in_transaction():
        yield
    else:
        async with session.begin():
            yield


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


def _percent_used(available: int, cap: int) -> float:
    if cap <= 0:
        return 0.0
    used = max(0, cap - max(0, available))
    return min(100.0, round(100.0 * used / cap, 2))


async def clients_without_quota(session: AsyncSession, partner_id: uuid.UUID) -> list[str]:
    """Clientes del partner cuya asignación está agotada.

    Son los que ya no contestan aunque el partner tenga saldo. La consulta
    va por ``remaining <= 0`` y no por ``cap``: un cap de 0 es una decisión
    del partner (cliente apagado a propósito) y no una incidencia.
    """
    rows = await session.execute(
        sa.select(PartnerAllocation.tenant_id).where(
            PartnerAllocation.partner_id == partner_id,
            PartnerAllocation.cap > 0,
            PartnerAllocation.remaining <= 0,
        )
    )
    return [str(r[0]) for r in rows.all()]


async def evaluate_partner_wallet_alerts(
    session: AsyncSession,
    partner: Partner,
    *,
    now: datetime | None = None,
) -> WalletAlertEvaluation:
    """Evalúa el saldo del partner y avisa una vez por umbral y mes.

    Gestiona sus propias transacciones cortas. Un fallo de correo nunca
    tumba la evaluación: la notificación en la consola es el registro
    durable.
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

    async with _tx(session):
        result.clients_out = await clients_without_quota(session, partner.id)

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
        async with _tx(session):
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
            "cliente(s) ya han agotado su cuota individual y no están respondiendo, "
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
    "clients_without_quota",
    "evaluate_partner_wallet_alerts",
    "wallet_dedupe_key",
]
