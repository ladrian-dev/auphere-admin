"""Hard-delete of a tenant — shared by the backoffice
(``DELETE /admin/tenants/{id}``) and the partner console
(``DELETE /console/clients/{ref}``).

Extracted verbatim from the admin handler (WP-29 / migration 0077) so
the two surfaces cannot drift on the three things a schema cannot decide:

1. **Archive first.** Delete is not reversible; archive is. The
   two-step is deliberate.
2. **What is NOT deleted**: an issued invoice has a legal retention duty
   (GDPR art. 17.3.b excludes it from erasure), so its FK stays RESTRICT
   and this checks BEFORE, answering 409 with what to resolve instead of
   letting Postgres refuse with an unreadable 502.
3. **What is anonymised instead of deleted**: the audit trail survives
   without tenant and without payloads. Erasure removes personal data,
   not the record of who did what — and with the old CASCADE the row
   recording this very deletion was lost too.

LangGraph checkpoints are deleted explicitly: the library creates and
recreates those tables, so a FK of ours would be a race we lose on the
next ``setup()``.

Callers must be inside a tenant-scoped transaction for the tenant being
deleted (RLS + contextvar) — the same contract as the admin dependency.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AuditLog, Tenant, TenantStatus

log = structlog.get_logger(__name__)


class TenantDeleteBlocked(Exception):
    """The deletion cannot proceed. ``status_code`` is what the surface
    should answer (409 for a guard, 502 for a storage failure)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class DeleteReport:
    tenant_id: uuid.UUID
    audit_rows_anonymised: int
    checkpoint_rows_deleted: int


async def hard_delete_tenant(session: AsyncSession, tenant: Tenant, *, actor: str) -> DeleteReport:
    """See module docstring. Raises :class:`TenantDeleteBlocked`."""
    tenant_id = tenant.id
    if tenant.status is not TenantStatus.ARCHIVED:
        raise TenantDeleteBlocked(
            409, "tenant must be archived before delete; PATCH status='archived' first"
        )

    invoices = await session.scalar(
        sa.text("SELECT count(*) FROM invoices WHERE tenant_id = :t"),
        {"t": str(tenant_id)},
    )
    if invoices:
        raise TenantDeleteBlocked(
            409,
            f"el tenant tiene {invoices} factura(s) y no se puede borrar: la "
            "conservación de facturación es una obligación legal (RGPD art. "
            "17.3.b). Anula o traspasa las facturas antes de borrar.",
        )

    slug, name = tenant.slug, tenant.name
    log.warning("tenant.delete.cascade", tenant_id=str(tenant_id), slug=slug, actor=actor)

    # Anonymise the trail first (payloads are where personal data lives),
    # then add this deletion's row already without a tenant snapshot. The
    # ``tenant_id`` becomes NULL through the SET NULL FK of 0077.
    anonymised = await session.execute(
        sa.text(
            "UPDATE audit_log SET before_json = NULL, after_json = NULL "
            " WHERE tenant_id = :t AND (before_json IS NOT NULL OR after_json IS NOT NULL)"
        ),
        {"t": str(tenant_id)},
    )
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action="tenant.delete",
            target=f"tenant:{tenant_id}",
            # Only what identifies the action, never the tenant's content:
            # the row outlives the deletion and cannot carry what was
            # just erased.
            before_json={"slug": slug, "name": name},
            after_json=None,
        )
    )
    await session.flush()

    # LangGraph checkpoints — the COLUMN is checked, not only the table
    # (``setup()`` may have created a table without ``tenant_id`` until
    # ``harden_checkpoint_tables()`` runs on the worker).
    checkpoints = 0
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        has_column = await session.scalar(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                " WHERE table_schema = 'public' AND table_name = :t "
                "   AND column_name = 'tenant_id'"
            ),
            {"t": table},
        )
        if not has_column:
            continue
        result = await session.execute(
            sa.text(f"DELETE FROM {table} WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        )
        checkpoints += result.rowcount or 0  # type: ignore[attr-defined]

    try:
        await session.delete(tenant)
        await session.flush()
    except SQLAlchemyError as exc:
        log.exception(
            "tenant.delete.failed", tenant_id=str(tenant_id), error_type=type(exc).__name__
        )
        raise TenantDeleteBlocked(
            502, f"no se pudo eliminar el tenant: {type(exc).__name__} — {exc}"
        ) from exc

    report = DeleteReport(
        tenant_id=tenant_id,
        audit_rows_anonymised=int(anonymised.rowcount or 0),  # type: ignore[attr-defined]
        checkpoint_rows_deleted=checkpoints,
    )
    log.info(
        "tenant.delete.done",
        tenant_id=str(tenant_id),
        audit_rows_anonymised=report.audit_rows_anonymised,
        checkpoint_rows_deleted=report.checkpoint_rows_deleted,
    )
    return report
