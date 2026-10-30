"""``reservation-outbox-cron`` — los avisos de Reservas al cliente final, cada
10 s (spec 043, R5.6 y R7.6; ``contracts/worker-y-avisos.md``).

Por cada fila pendiente que ya toca de ``reservation_outbox`` (bajo candado,
``SKIP LOCKED``, 50 por pasada):

1. ¿Sigue siendo verdad? Una pregunta a quien ya confirmó, o el recordatorio de
   una reserva cancelada, no sale (``skipped`` / ``stale``, sin evento: no es un
   fallo de aviso).
2. A quién: el contacto de la reserva o de la entrada de la lista. Sin teléfono,
   ``skipped`` / ``no_phone``. Con la baja pedida (en cualquiera de los números
   del negocio), ``opted_out``.
3. Desde qué número: el de la conversación del agente que reservó o, si no, la
   línea del agente (``channel_routing``, rol ``agent``: la persona responde SÍ
   o NO al agente). Sin número, ``no_channel``.
4. **Dentro de la ventana de 24 h, texto; fuera, la plantilla aprobada** del
   número para ese aviso. Sin plantilla aprobada, ``no_template``. En todos los
   ``skipped`` (menos ``stale``), el historial de la reserva lo dice
   (``notify_failed``): nunca se da por avisado a quien no lo fue. Y nada a
   medias: un aviso que no sale no crea contacto ni conversación.
5. Se escribe el ``Message`` pendiente (``actor_kind = system``), igual que
   ``cobranza_reminder_cron``; el despachador de salida lo entrega. La fila
   queda ``sent`` con su ``message_id`` y la reserva, con ``notified`` (o
   ``reminder_sent``).

Un error preparando un aviso se queda en esa fila (``SAVEPOINT``): reintento a
1 y 5 min y, al tercer intento, ``failed`` con ``notify_failed``. Nunca se
reintenta para siempre.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from datetime import datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.db.models import (
    Channel,
    Conversation,
    Customer,
    Message,
    MessageDirection,
    MessageStatus,
    ReservationOutbox,
)
from nexus_api.services import whatsapp_opt_outs, whatsapp_templates
from nexus_api.services.channel_routing import (
    CHANNEL_ROLE_AGENT,
    ChannelResolutionError,
    resolve_whatsapp_channel,
)
from nexus_api.services.reservations import automation
from nexus_api.services.reservations.core import Ctx, load_ctx
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_worker.persistence.messages import upsert_conversation_for_customer, upsert_customer
from nexus_worker.streams.reservations_cron import Roster, run_for_reservation_tenants

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 10.0
PURPOSE = "reservation_outbox"
#: Las plantillas que usa el módulo (las aprueba Meta en el número del cliente).
WANTED_TEMPLATES = frozenset(t for t in automation.TEMPLATES.values() if t is not None)


class TemplatesUnavailable(RuntimeError):
    """No se pudo preguntar a Meta por las plantillas: se reintenta."""


class _Sender:
    """Los avisos de una pasada en un cliente. Guarda lo que no cambia entre
    filas: el número por defecto y las plantillas aprobadas."""

    def __init__(self, session: AsyncSession, ctx: Ctx, now: datetime) -> None:
        self.session = session
        self.ctx = ctx
        self.now = now
        self._default_channel: Channel | None = None
        self._default_resolved = False
        self._approved: dict[str, str] | None = None
        self._approved_error: str | None = None

    async def send(self, row: ReservationOutbox) -> str:
        try:
            async with self.session.begin_nested():
                return await self._deliver(row)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # El SAVEPOINT deshizo lo de esta fila; se relee antes de anotar.
            await self.session.refresh(row)
            await automation.mark_error(self.session, row, exc, self.now)
            log.warning(
                "reservation_outbox.send_error",
                tenant_id=str(self.ctx.tenant_id),
                outbox_id=str(row.id),
                kind=row.kind,
                attempts=row.attempts,
                status=row.status,
                error=row.last_error,
            )
            return "error"

    async def _deliver(self, row: ReservationOutbox) -> str:
        s, now = self.session, self.now
        notice = await automation.compose(s, self.ctx, row, now)
        if notice.stale:
            return self._skip(row, automation.SKIP_STALE, notice)
        if notice.phone is None:
            return self._skip(row, automation.SKIP_NO_PHONE, notice)
        if await self._opted_out(notice.phone):
            return self._skip(row, automation.SKIP_OPTED_OUT, notice)
        channel = await self._channel(notice)
        if channel is None:
            return self._skip(row, automation.SKIP_NO_CHANNEL, notice)

        customer = await self._find_customer(notice.phone)
        conversation = (
            await self._find_conversation(channel.id, customer.id) if customer is not None else None
        )
        payload: dict[str, Any] | None
        if automation.window_open(conversation, now):
            payload, content, via = None, notice.text, "text"
        else:
            language = (
                await self._approved_language(notice.template)
                if notice.template is not None
                else None
            )
            if notice.template is None or language is None:
                return self._skip(row, automation.SKIP_NO_TEMPLATE, notice)
            payload = {
                "name": notice.template,
                "language": language,
                "params": {"body": notice.template_body()},
            }
            content, via = f"[template:{notice.template}] {notice.text}", "template"

        # Ahora sí sale: el contacto y su conversación en ese número.
        if customer is None:
            customer = await upsert_customer(s, identifier=notice.phone)
        conversation = await upsert_conversation_for_customer(
            s, channel_id=channel.id, customer_id=customer.id, reopened_by="system"
        )
        message = Message(
            id=uuid.uuid4(),
            tenant_id=self.ctx.tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            status=MessageStatus.PENDING,
            content=content,
            tool_calls=[],
            actor_kind="system",
            template_payload=payload,
        )
        s.add(message)
        conversation.last_message_at = now
        await s.flush()
        automation.mark_sent(s, row, notice, message_id=message.id, via=via)
        return via

    def _skip(self, row: ReservationOutbox, reason: str, notice: automation.Notice) -> str:
        automation.mark_skipped(self.session, row, reason, notice.reservation)
        log.info(
            "reservation_outbox.skipped",
            tenant_id=str(self.ctx.tenant_id),
            outbox_id=str(row.id),
            kind=row.kind,
            reason=reason,
        )
        return reason

    async def _opted_out(self, digits: str) -> bool:
        """Un recordatorio de cita no es publicidad: solo lo para una baja que
        puso el negocio, no el «STOP» del cliente (decisión del owner, QA
        2026-10-30, INC-18). Vale en cualquiera de los números del negocio
        (RLS acota al cliente), como en ``cobranza_reminder_cron``."""
        return await whatsapp_opt_outs.blocks(
            self.session, channel_id=None, phone=digits, marketing=False
        )

    async def _channel(self, notice: automation.Notice) -> Channel | None:
        if notice.conversation_id is not None:
            conv = await self.session.get(Conversation, notice.conversation_id)
            if conv is not None:
                try:
                    return await resolve_whatsapp_channel(
                        self.session, channel_id=conv.channel_id, provider="meta", purpose=PURPOSE
                    )
                except ChannelResolutionError:
                    pass  # ese número ya no está: la línea del agente
        if not self._default_resolved:
            self._default_resolved = True
            try:
                self._default_channel = await resolve_whatsapp_channel(
                    self.session, role=CHANNEL_ROLE_AGENT, provider="meta", purpose=PURPOSE
                )
            except ChannelResolutionError as exc:
                log.warning(
                    "reservation_outbox.no_channel",
                    tenant_id=str(self.ctx.tenant_id),
                    reason=exc.reason,
                )
                self._default_channel = None
        return self._default_channel

    async def _find_customer(self, digits: str) -> Customer | None:
        found: Customer | None = await self.session.scalar(
            sa.select(Customer)
            .where(Customer.identifier.in_((digits, f"+{digits}")))
            .order_by(Customer.created_at)
            .limit(1)
        )
        return found

    async def _find_conversation(
        self, channel_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Conversation | None:
        """La de ``upsert_conversation_for_customer`` sin crearla ni reabrirla."""
        found: Conversation | None = await self.session.scalar(
            sa.select(Conversation)
            .where(Conversation.channel_id == channel_id, Conversation.customer_id == customer_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(1)
        )
        return found

    async def _approved_language(self, template: str) -> str | None:
        """El idioma de la plantilla si Meta la da por aprobada; ``None`` si no.
        Una sola consulta a Meta por pasada; si falla, falla la fila (reintento)."""
        if self._approved is None and self._approved_error is None:
            try:
                templates, _waba = await whatsapp_templates.fetch_templates(self.session)
            except Exception as exc:
                self._approved_error = automation.error_text(exc)
            else:
                approved: dict[str, str] = {}
                for t in templates:
                    if (
                        t.name in WANTED_TEMPLATES
                        and (t.status or "").upper() == "APPROVED"
                        and (t.language or "").lower().startswith(automation.TEMPLATE_LANGUAGE)
                    ):
                        approved.setdefault(t.name, t.language)
                self._approved = approved
        if self._approved_error is not None:
            raise TemplatesUnavailable(self._approved_error)
        assert self._approved is not None
        return self._approved.get(template)


async def process_tenant(session: AsyncSession, tenant_id: uuid.UUID, now: datetime) -> int:
    """Manda lo pendiente que ya toca de un cliente. Devuelve cuántas filas miró."""
    ctx = await load_ctx(session, tenant_id)
    if ctx is None:
        return 0
    rows = await automation.due_outbox(session, now)
    if not rows:
        return 0
    sender = _Sender(session, ctx, now)
    outcomes: Counter[str] = Counter()
    for row in rows:
        outcomes[await sender.send(row)] += 1
    await session.flush()
    log.info("reservation_outbox.batch", tenant_id=str(tenant_id), **dict(outcomes))
    return len(rows)


async def run_reservation_outbox_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    await run_for_reservation_tenants(
        name="reservation_outbox_cron",
        stop=stop,
        tick_seconds=tick_seconds,
        process=process_tenant,
        roster=Roster(),
    )


__all__ = [
    "DEFAULT_TICK_SECONDS",
    "TemplatesUnavailable",
    "process_tenant",
    "run_reservation_outbox_cron",
]
