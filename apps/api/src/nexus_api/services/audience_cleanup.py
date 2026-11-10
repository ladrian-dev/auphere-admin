"""Spec 058 (requisito 3) — limpiar las esperas que dejó la pausa delante de la audiencia.

Hasta la 058, un contacto fuera de la audiencia de un número que escribía a un
cliente en pausa (o con el canal o el agente en pausa) abría «Espera a una
persona» y avisaba a la gente del cliente. El turno ya no lo hace, y la próxima
vez que ese contacto escriba su espera se cerrará sola
(``inbox_lifecycle.leave_gate_wait``). Esto cierra las que ya existen, sin
esperar a que escriba.

**Herramienta de operador.** La lanza una persona de Auphere con
``scripts/release_out_of_audience_waits.py``. Va en seco si no se pide otra
cosa: cuenta y no toca. Ningún despliegue la lanza (requisito 3.6, y la misma
decisión del 2026-11-10 que sacó de ``release.sh`` el paso a Reservas).

Qué saca (requisitos 3.1 y 3.3): las conversaciones en ``escalated`` por un
motivo de puerta (``GATE_REASONS``), sin asignar, cuyo contacto está fuera de la
audiencia **actual** de su número. Solo en los números que deciden su propia
audiencia (``strict``). En los demás, la audiencia depende del agente que lleve
la conversación, que puede ser el destino de una derivación de Recepción, y eso
no se sabe fuera de un turno sin efectos. Esos se cuentan en
``skipped_not_strict`` y los cierra el turno.

Cada cliente va en su propia transacción y bajo su RLS (garantía 1). Uno que
falla se revierte solo y no para a los demás. No envía avisos ni mensajes, y sus
logs no llevan datos del contacto (requisito 3.4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus_api.core.admin_gate import audience_suppresses
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Conversation, ConversationStatus, Customer, Tenant
from nexus_api.services import inbox_lifecycle
from nexus_api.services.channel_config import gate_audience

log = structlog.get_logger(__name__)


@dataclass
class TenantReport:
    """Un cliente. ``released`` son las que sacó, o las que sacaría en seco."""

    released: int = 0
    skipped_not_strict: int = 0
    conversation_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class Summary:
    apply: bool
    tenants: int = 0
    released: int = 0
    skipped_not_strict: int = 0
    failed: int = 0

    def add(self, report: TenantReport) -> None:
        self.tenants += 1
        self.released += report.released
        self.skipped_not_strict += report.skipped_not_strict

    def as_log(self) -> dict[str, Any]:
        counted = "released" if self.apply else "would_release"
        return {
            "apply": self.apply,
            "tenants": self.tenants,
            counted: self.released,
            "skipped_not_strict": self.skipped_not_strict,
            "failed": self.failed,
        }


async def release_tenant(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, *, apply: bool
) -> TenantReport:
    """Un cliente, en su transacción y bajo su RLS. En seco solo cuenta: no
    escribe nada. Si algo falla, no se queda nada y el error sube."""
    report = TenantReport()
    async with factory() as session, tenant_scoped_session(session, tenant_id):
        candidates = (
            (
                await session.execute(
                    sa.select(Conversation)
                    .where(
                        Conversation.tenant_id == tenant_id,
                        Conversation.status == ConversationStatus.ESCALATED,
                        Conversation.waiting_reason.in_(sorted(inbox_lifecycle.GATE_REASONS)),
                        Conversation.assigned_user_id.is_(None),
                    )
                    .order_by(Conversation.created_at, Conversation.id)
                )
            )
            .scalars()
            .all()
        )
        audiences: dict[uuid.UUID, dict[str, Any] | None] = {}
        for conversation in candidates:
            if conversation.channel_id not in audiences:
                audiences[conversation.channel_id] = await gate_audience(
                    session, conversation.channel_id
                )
            audience = audiences[conversation.channel_id]
            if not (audience or {}).get("strict"):
                report.skipped_not_strict += 1
                continue
            customer = await session.get(Customer, conversation.customer_id)
            sender = customer.identifier if customer is not None else ""
            # ``strict``: decide el número; la política del agente no cuenta.
            if not audience_suppresses(audience, None, sender):
                continue
            if apply and not await inbox_lifecycle.leave_gate_wait(session, conversation):
                continue  # pragma: no cover - el filtro de arriba ya lo garantiza
            report.released += 1
            report.conversation_ids.append(conversation.id)
    if apply and report.conversation_ids:
        # Tras el commit, como en el turno: su aviso pasa a atendido.
        await inbox_lifecycle.mark_waiting_handled(tenant_id, report.conversation_ids)
    return report


async def run(factory: async_sessionmaker[AsyncSession], *, apply: bool = False) -> Summary:
    """Todos los clientes, de uno en uno. Nunca lanza por culpa de un cliente."""
    async with factory() as session, session.begin():
        tenant_ids = list(
            (
                await session.execute(sa.select(Tenant.id).order_by(Tenant.created_at, Tenant.id))
            ).scalars()
        )
    summary = Summary(apply=apply)
    for tenant_id in tenant_ids:
        try:
            report = await release_tenant(factory, tenant_id, apply=apply)
        except Exception as exc:
            summary.failed += 1
            log.error(
                "inbox.audience_cleanup.tenant_failed",
                tenant_id=str(tenant_id),
                error=type(exc).__name__,
            )
            continue
        summary.add(report)
        if report.released or report.skipped_not_strict:
            log.info(
                "inbox.audience_cleanup.tenant",
                tenant_id=str(tenant_id),
                apply=apply,
                **{("released" if apply else "would_release"): report.released},
                skipped_not_strict=report.skipped_not_strict,
            )
    log.info("inbox.audience_cleanup.done", **summary.as_log())
    return summary


__all__ = ["Summary", "TenantReport", "release_tenant", "run"]
