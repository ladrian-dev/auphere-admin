"""``/console/audit`` — the partner's audit trail (CP-28 backend).

Rows from ``audit_log`` that belong to the partner: every row of any of
its clients (``tenant_id IN partner_tenants``) plus the platform-level
rows the console itself writes about the partner (team, keys — written
with ``tenant_id NULL`` and ``target = partner:<id>``). Nothing else can
match: the filter is built from the principal, not from input.

Each row is rendered into a one-line human summary ("maría@facelad.com
publicó la versión 7 del agente de Clínica X") — the console shows that
line; the raw payloads (``before``/``after``) stay inside.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import AuditLog, PartnerTenant

from .schemas import AuditEntryOut, AuditPageOut

router = APIRouter(prefix="/audit")

# action → human template. ``{actor}`` ``{client}`` ``{v}`` are filled from
# the row. Unknown actions fall back to "<actor> · <action> · <target>".
_TEMPLATES: dict[str, str] = {
    "agent_config.promote": "{actor} published agent version {v} for {client}",
    "agent_config.rollback": "{actor} rolled {client}'s agent back to version {v}",
    "agent_config.stage": "{actor} saved a draft (version {v}) for {client}",
    "console.client.create": "{actor} created client {client}",
    "console.client.update": "{actor} updated client {client}",
    "console.client.status": "{actor} changed {client} to {status}",
    "tenant.update": "{actor} updated {client}",
    "tenant.delete": "{actor} deleted client {client}",
    "console.member.invite": "{actor} invited {email} as {role}",
    "console.member.role": "{actor} changed {email}'s role to {role}",
    "console.member.status": "{actor} set {email} to {status}",
    "console.member.remove": "{actor} removed {email} from the team",
    "console.invitation.revoke": "{actor} revoked the invitation for {email}",
    "console.invitation.accept": "{email} joined as {role}",
    "console.key.create": "{actor} created API key {key}",
    "console.key.rotate": "{actor} rotated API key {key}",
    "console.key.revoke": "{actor} revoked API key {key}",
}


def _encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{row_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, rid = raw.split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(rid)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor"
        ) from None


def _human_actor(actor: str) -> str:
    # ``console:maria@x.com`` → ``maria@x.com``; ``admin:1a2b3c4d`` → ``Auphere``.
    if actor.startswith("console:"):
        return actor.removeprefix("console:")
    if actor.startswith("admin:"):
        return "Auphere"
    if actor.startswith("partner:"):
        return "API key"
    return actor


def summarise(row: AuditLog, client_name: str | None) -> str:
    after = row.after_json or {}
    before = row.before_json or {}
    values = {
        "actor": _human_actor(row.actor),
        "client": client_name or "a client",
        "v": after.get("version", before.get("version", "?")),
        "status": after.get("status", "?"),
        "email": after.get("email", before.get("email", "?")),
        "role": after.get("role", "?"),
        "key": after.get("prefix_snippet", before.get("prefix_snippet", "?")),
    }
    template = _TEMPLATES.get(row.action)
    if template is None:
        return f"{values['actor']} · {row.action} · {row.target}"
    return template.format(**values)


@router.get("", response_model=AuditPageOut)
async def list_audit(
    principal: ConsolePrincipal = Depends(require_console_principal("audit:read")),
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    actor: str | None = Query(default=None, max_length=255, description="Substring match"),
    action: str | None = Query(default=None, max_length=80, description="Prefix match"),
    client: str | None = Query(default=None, max_length=255, description="external_client_ref"),
    after: datetime | None = Query(default=None),
    before: datetime | None = Query(default=None),
) -> AuditPageOut:
    partner_id = principal.partner.id
    async with session.begin():
        mappings = (
            (
                await session.execute(
                    sa.select(PartnerTenant).where(PartnerTenant.partner_id == partner_id)
                )
            )
            .scalars()
            .all()
        )
        by_tenant = {m.tenant_id: m for m in mappings}
        tenant_ids = list(by_tenant)
        if client is not None:
            tenant_ids = [m.tenant_id for m in mappings if m.external_client_ref == client]
            scope_filter: sa.ColumnElement[bool] = AuditLog.tenant_id.in_(tenant_ids)
        else:
            scope_filter = sa.or_(
                AuditLog.tenant_id.in_(tenant_ids),
                sa.and_(AuditLog.tenant_id.is_(None), AuditLog.target == f"partner:{partner_id}"),
            )
        stmt = sa.select(AuditLog).where(scope_filter)
        if actor:
            stmt = stmt.where(AuditLog.actor.ilike(f"%{actor}%"))
        if action:
            stmt = stmt.where(AuditLog.action.like(f"{action}%"))
        if after is not None:
            stmt = stmt.where(AuditLog.created_at >= after)
        if before is not None:
            stmt = stmt.where(AuditLog.created_at < before)
        if cursor:
            c_ts, c_id = _decode_cursor(cursor)
            stmt = stmt.where(
                sa.or_(
                    AuditLog.created_at < c_ts,
                    sa.and_(AuditLog.created_at == c_ts, AuditLog.id < c_id),
                )
            )
        rows = (
            (
                await session.execute(
                    stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)
                )
            )
            .scalars()
            .all()
        )

    has_more = len(rows) > limit
    rows = rows[:limit]
    items: list[AuditEntryOut] = []
    for row in rows:
        mapping = by_tenant.get(row.tenant_id) if row.tenant_id else None
        client_name = mapping.client_name if mapping else None
        items.append(
            AuditEntryOut(
                id=row.id,
                at=row.created_at,
                actor=_human_actor(row.actor),
                action=row.action,
                target=row.target,
                external_client_ref=mapping.external_client_ref if mapping else None,
                client_name=client_name,
                summary=summarise(row, client_name),
            )
        )
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return AuditPageOut(items=items, next_cursor=next_cursor)
