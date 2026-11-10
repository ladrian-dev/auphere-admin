"""``POST /console/support/tickets`` — el escalado con expediente (CO-08, §4).

Este endpoint es la **aplicación** de una acción de soporte ya confirmada:
lo llama ``console.apply`` con el cuerpo que la propuesta guardó, después
de que una persona del partner haya dicho que sí. Un humano puede llamarlo
igual desde la consola; es el mismo trabajo.

F4 persiste en ``support_tickets`` + ``support_ticket_events`` (FORCE RLS
``app.partner_id``) **desde este mismo POST**. Siguen existiendo el acuse
en ``console_notifications``, la auditoría y el correo interno. No hay
un segundo POST ni un GET de consola.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.companion.tools.support import normalise_topic, sla_for
from nexus_api.config import get_settings
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.rate_limit import allow
from nexus_api.db.models import AuditLog
from nexus_api.db.models.console_notification import NotificationSeverity
from nexus_api.db.models.support_ticket import (
    EVENT_OPEN,
    STATUS_OPEN,
    SupportTicket,
    SupportTicketEvent,
)
from nexus_api.services import console_notifications
from nexus_api.services.email_catalog import EmailKind, lines_variable

from .deps import resolve_mapping
from .schemas_capabilities import SupportTicketIn, SupportTicketOut

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/support")

#: Prefijo del identificador. "AU" de Auphere, y corto porque se dicta en
#: voz alta.
TICKET_PREFIX = "AU"

TICKET_SEQUENCE = "console_support_ticket_seq"

#: ``category`` → (kind de notificación, acción de auditoría). Los dos
#: vocabularios se mantienen alineados a mano y a propósito: el de
#: notificaciones lo pinta la consola y el de auditoría está sembrado en la
#: migración 0092, así que un valor nuevo obliga a tocar los dos sitios.
_CATEGORY_ROUTING: dict[str, tuple[str, str]] = {
    "help": ("support.ticket_opened", "console.support.ticket_opened"),
    "capability": ("support.capability_requested", "console.support.capability_requested"),
}


async def _next_ticket_ref(session: AsyncSession) -> str:
    number = await session.scalar(sa.text(f"SELECT nextval('{TICKET_SEQUENCE}')"))
    return f"{TICKET_PREFIX}-{int(number or 0)}"


async def _alert_auphere(
    *,
    ticket_ref: str,
    body: SupportTicketIn,
    topic: str,
    sla: str,
    partner_id: uuid.UUID,
    partner_name: str,
    partner_slug: str,
    opened_by: str,
) -> None:
    """El aviso interno. Nunca rompe la petición.

    La línea de log va primero y va siempre: es la que alimenta la
    agregación del §25.2 (*"siete partners han pedido Shopify este
    trimestre"*) y la única que no depende de que haya un buzón
    configurado. El correo es el empujón, y es opcional.

    Spec 051 (catálogo §20): sale por ``internal_alert``, en español, con una
    línea por dato. Todo lo que escribió el partner se escapa en
    ``lines_variable``.
    """
    from nexus_api.services.email import send_template

    log.info(
        "console.support.ticket_opened",
        ticket_ref=ticket_ref,
        category=body.category,
        topic=topic,
        sla=sla,
        partner=partner_slug,
        client_ref=body.client_ref,
        bridge=body.bridge,
        checked_items=len(body.checked),
        opened_by=opened_by,
    )
    address = get_settings().support_alert_email.strip()
    if not address:
        return
    lines = [f"Partner: {partner_name} ({partner_slug})"]
    if body.client_ref:
        lines.append(f"Cliente: {body.client_ref}")
    lines.append(f"Qué necesita: {body.need}")
    if body.checked:
        lines.append("Ya comprobado:")
        lines.extend(f"· {item}" for item in body.checked)
    if body.alternative:
        bridge = " (puente)" if body.bridge else ""
        lines.append(f"Alternativa propuesta{bridge}: {body.alternative}")
    lines.append(f"SLA: {sla}")
    try:
        await send_template(
            EmailKind.INTERNAL_ALERT,
            to=[address],
            subject=f"[Auphere] Consulta {ticket_ref} · {body.category} · {topic}",
            variables={
                "HEADING": f"{partner_name} ha abierto la consulta {ticket_ref}",
                "DETAIL": lines_variable(lines, more=lambda n: f"y {n} líneas más"),
                "KIND": "support.ticket",
            },
            locale="es",
            # Garantía 6: el aviso lleva el negocio del caso.
            partner_id=partner_id,
        )
    except Exception:  # pragma: no cover - un aviso no puede tumbar la petición
        log.warning("console.support.alert_failed", ticket_ref=ticket_ref)


@router.post(
    "/tickets",
    response_model=SupportTicketOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "No such client reference for this partner."},
        429: {"description": "Too many support tickets in a short window."},
    },
)
async def open_support_ticket(
    body: SupportTicketIn,
    # ``partner:read`` a propósito: lo tienen los cinco roles. Abrir un
    # ticket no cambia nada de la configuración del partner, y denegarlo por
    # rol significaría que justo la persona que topa con la pared no puede
    # contarlo. La superficie de escritura del Companion sigue siendo
    # estrecha porque el ``kind`` está en la lista cerrada de ``APPLY_ROUTES``,
    # no porque este endpoint sea privilegiado.
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> SupportTicketOut:
    settings = get_settings()
    if not await allow(
        redis,
        key=f"console:support_ticket:{principal.user_id}",
        per_minute=settings.console_support_tickets_per_minute,
        surface="console",
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many support tickets in a row — give the first ones a moment.",
        )

    if body.client_ref is not None:
        # Un ref ajeno y uno inexistente dan el mismo 404 opaco: si no lo
        # dieran, este endpoint sería un oráculo para averiguar la cartera
        # de otro partner probando referencias.
        await resolve_mapping(session, principal, body.client_ref)

    topic = normalise_topic(body.topic)
    # El ``sla`` se RECALCULA aquí y no se acepta del cuerpo: es una
    # promesa de Auphere, no un dato del llamante. Que no exista como campo
    # de entrada es lo que lo hace imposible de forzar desde el modelo.
    sla = sla_for(body.category, topic)
    notification_kind, audit_action = _CATEGORY_ROUTING[body.category]
    opened_at = datetime.now(UTC)
    opened_by = principal.actor

    async with session.begin():
        ticket_ref = await _next_ticket_ref(session)
        # ``email=True`` explícito: la fila se queda en ``info`` —un ticket
        # que abriste tú no es una advertencia— y el acuse por correo a los
        # dueños del partner sale igual. Es justo para lo que existe el
        # parámetro.
        await console_notifications.emit(
            session,
            partner_id=principal.partner.id,
            kind=notification_kind,
            severity=NotificationSeverity.INFO,
            data={"ticket_ref": ticket_ref, "topic": topic, "category": body.category},
            external_client_ref=body.client_ref,
            dedupe_key=f"partner:{principal.partner.id}:support:{ticket_ref}",
            email=True,
        )
        session.add(
            AuditLog(
                # ``tenant_id=None`` aunque el ticket sea de un cliente: la
                # fila la escribe una transacción de plataforma, y
                # ``audit_log`` tiene FORCE ROW LEVEL SECURITY por tenant.
                # Escribirla con tenant desde aquí chocaría con la policy.
                # El cliente queda nombrado en ``after_json.client_ref``,
                # que es la referencia del partner y no un id interno.
                tenant_id=None,
                actor=opened_by,
                action=audit_action,
                target=f"partner:{principal.partner.id}",
                after_json={
                    "ticket_ref": ticket_ref,
                    "topic": topic,
                    "category": body.category,
                    "sla": sla,
                    "bridge": body.bridge,
                    "client_ref": body.client_ref,
                    "checked_items": len(body.checked),
                },
            )
        )
        session.add(
            AuditLog(
                tenant_id=None,
                actor=opened_by,
                action="ticket.open",
                target=f"ticket:{ticket_ref}",
                after_json={
                    "ticket_ref": ticket_ref,
                    "category": body.category,
                    "topic": topic,
                    "sla": sla,
                    "status": STATUS_OPEN,
                },
            )
        )
        # Flush como dueño (notificación + auditorías) ANTES de bajar a
        # ``nexus_app``: emit de plataforma no corre bajo el GUC.
        await session.flush()
        await apply_partner_to_session(session, principal.partner.id)
        ticket_id = uuid.uuid4()
        session.add(
            SupportTicket(
                id=ticket_id,
                partner_id=principal.partner.id,
                ticket_ref=ticket_ref,
                category=body.category,
                topic=topic,
                client_ref=body.client_ref,
                need=body.need,
                checked=list(body.checked),
                alternative=body.alternative,
                bridge=body.bridge,
                sla=sla,
                status=STATUS_OPEN,
                opened_by=opened_by,
                opened_at=opened_at,
            )
        )
        session.add(
            SupportTicketEvent(
                ticket_id=ticket_id,
                partner_id=principal.partner.id,
                kind=EVENT_OPEN,
                from_status=None,
                to_status=STATUS_OPEN,
                actor=opened_by,
            )
        )

    await _alert_auphere(
        ticket_ref=ticket_ref,
        body=body,
        topic=topic,
        sla=sla,
        partner_id=principal.partner.id,
        partner_name=principal.partner.name,
        partner_slug=principal.partner.slug,
        opened_by=opened_by,
    )
    return SupportTicketOut(
        ticket_ref=ticket_ref,
        category=body.category,
        topic=topic,
        sla=sla,
        opened_at=opened_at,
    )
