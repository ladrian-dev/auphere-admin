"""A client's lifecycle: the three-field alta (spec 047) and the hard-delete.

**Lifecycle is not preparation** (spec 047, requisito 4.7, research D2). A
client is ``active``, ``paused`` or ``archived``; whether it has agents that
serve anyone is its *preparation*, derived from its agents
(``agent_lifecycle.visible_state``) and never stored as a client status. A
client with no agents is ``active``: :func:`create_client` gives birth to
exactly that — the client, its empty business profile and its bag — and
**never** an agent, even when the partner has a default template (that
template is the starting point of «Nuevo agente»).

``provisioning`` stays for one road only: the public partner API
(``services/partner_clients.py``), whose contract (``docs/partner-integration.md``)
keeps a provisioned client silent until its WhatsApp is connected and it is
activated. Migration 0181 moves to ``active`` every ``provisioning`` client that
cannot answer anyone; :func:`lifecycle_of` reads the rest as ``active`` that is
still awaiting activation.

Hard-delete of a tenant — shared by the backoffice
(``DELETE /admin/tenants/{id}``) and the partner console
(``DELETE /console/clients/{ref}``).

Extracted verbatim from the admin handler (WP-29 / migration 0077) so
the two surfaces cannot drift on the three things a schema cannot decide:

1. **Archive first.** Delete is not reversible; archive is. The
   two-step is deliberate.
2. **What is NOT deleted**: an issued invoice — the tenant's own, or its
   partner's where the tenant is a line — has a legal retention duty
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

import re
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

import sqlalchemy as sa
import structlog
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session
from nexus_api.db.models import AuditLog, Job, Partner, PartnerTenant, Tenant, TenantStatus

if TYPE_CHECKING:
    from nexus_api.services.agent_lifecycle import VisibleState
    from nexus_api.services.business.links import DetectedLink
    from nexus_api.services.client_overview import AgentState

log = structlog.get_logger(__name__)

# ── lifecycle and preparation ────────────────────────────────────────────

Lifecycle = Literal["active", "paused", "archived"]
#: What a client is being prepared for: no agents yet, agents that serve
#: nobody, agents serving, or (only through the partner API) a client that
#: still awaits its activation.
Preparation = Literal["no_agents", "not_serving", "serving", "awaiting_activation"]

#: The status a client is born with in the console. Never ``provisioning``.
NEW_CLIENT_STATUS: Final = TenantStatus.ACTIVE


def lifecycle_of(status: TenantStatus) -> Lifecycle:
    """The client's lifecycle. ``provisioning`` is not a lifecycle: it is a
    partner-API client awaiting activation, which is still not paused nor
    archived."""
    if status is TenantStatus.PAUSED:
        return "paused"
    if status is TenantStatus.ARCHIVED:
        return "archived"
    return "active"


def preparation_of(status: TenantStatus, *, agents: int, serving: int) -> Preparation:
    """Whether its agents serve anyone — derived, never stored."""
    if status is TenantStatus.PROVISIONING:
        return "awaiting_activation"
    if agents <= 0:
        return "no_agents"
    return "serving" if serving > 0 else "not_serving"


# ── the three-field alta (spec 047, requisito 4) ───────────────────────────

#: An external reference is the partner's id for the client; the console
#: derives one from the name. Same alphabet the partner API accepts.
_REF_UNSAFE = re.compile(r"[^a-z0-9]+")
_REF_MAX = 60
#: Action and words already in ``console_audit_vocabulary`` (migration 0084).
CREATE_ACTION: Final = "console.client.create"


def slugify_ref(name: str) -> str:
    """``Barbería Cultor`` → ``barberia-cultor``. Never empty."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    slug = _REF_UNSAFE.sub("-", ascii_only).strip("-")[:_REF_MAX].strip("-")
    return slug or "cliente"


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return " ".join(
        "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().split()
    )


@dataclass(frozen=True)
class NewClient:
    """What the alta asks and what «Más ajustes» settled."""

    name: str
    niche: str
    info: str | None
    country: str | None
    timezone: str
    price_currency: str | None
    eu_only: bool
    #: The chips the person kept, normalised.
    links: Sequence[DetectedLink]


@dataclass(frozen=True)
class CreatedClient:
    tenant_id: uuid.UUID
    ref: str
    name: str
    duplicate_name: bool
    #: The background reading of its web and networks, when it has any.
    read_job: Job | None


async def _free_ref(session: AsyncSession, partner_id: uuid.UUID, base: str) -> str:
    taken = set(
        (
            await session.execute(
                sa.select(PartnerTenant.external_client_ref).where(
                    PartnerTenant.partner_id == partner_id,
                    PartnerTenant.external_client_ref.like(f"{base}%"),
                )
            )
        )
        .scalars()
        .all()
    )
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


async def _name_is_taken(session: AsyncSession, partner_id: uuid.UUID, name: str) -> bool:
    wanted = _fold(name)
    names = (
        await session.execute(
            sa.select(PartnerTenant.client_name).where(PartnerTenant.partner_id == partner_id)
        )
    ).scalars()
    return any(_fold(existing or "") == wanted for existing in names)


async def create_client(
    session: AsyncSession,
    *,
    partner: Partner,
    new: NewClient,
    person_id: str,
    audit_actor: str,
    ip: str | None = None,
) -> CreatedClient:
    """One transaction: the client (``active``), its mapping, its bag, its
    business profile and, if it has a web or networks, the reading job.

    Platform rows first (partner lock, quota guard, tenant, mapping, bag,
    partner audit); then the transaction switches to the client (RLS) for the
    profile, the audit row and the job. Nothing is half-created: a failure
    rolls everything back. The caller enqueues the job **after** this returns
    (the row must exist before the worker hears about it).

    Raises ``ProvisioningQuotaExceeded`` (the guard against loops and leaked
    keys, not a plan limit) before writing anything.
    """
    from nexus_api.metering.wallet import seed_default_allocation
    from nexus_api.repositories.partner import EmbedAuditRepository
    from nexus_api.services.business.profile import create_profile
    from nexus_api.services.business.sections import Actor
    from nexus_api.services.jobs import create_job
    from nexus_api.services.partner_clients import (
        ProvisioningQuotaExceeded,
        client_slug,
        count_quota_usage,
    )

    links = list(new.links)
    for attempt in range(2):
        try:
            async with session.begin():
                limit = await session.scalar(
                    sa.select(Partner.max_clients).where(Partner.id == partner.id).with_for_update()
                )
                used = await count_quota_usage(session, partner.id)
                if limit is not None and used >= int(limit):
                    raise ProvisioningQuotaExceeded(used=used, limit=int(limit))

                ref = await _free_ref(session, partner.id, slugify_ref(new.name))
                duplicate = await _name_is_taken(session, partner.id, new.name)
                tenant = Tenant(
                    id=uuid.uuid4(),
                    name=new.name,
                    slug=client_slug(partner.slug, ref),
                    status=NEW_CLIENT_STATUS,
                    timezone=new.timezone,
                    partner_id=partner.id,
                )
                session.add(tenant)
                await session.flush()
                session.add(
                    PartnerTenant(
                        partner_id=partner.id,
                        external_client_ref=ref,
                        tenant_id=tenant.id,
                        client_name=new.name,
                    )
                )
                await session.flush()
                granted = await seed_default_allocation(
                    session,
                    partner_id=partner.id,
                    tenant_id=tenant.id,
                    default_cap=get_settings().partner_default_client_allocation_tokens,
                )
                await EmbedAuditRepository(session).record(
                    event="client.provisioned",
                    partner_id=partner.id,
                    tenant_id=tenant.id,
                    payload={
                        "external_client_ref": ref,
                        "actor": audit_actor,
                        "allocation_tokens": granted,
                        "agents": 0,
                    },
                    ip=ip,
                )

                # From here on, the client's own rows: RLS on, as the app role.
                token = _current_tenant.set(tenant.id)
                try:
                    await apply_tenant_to_session(session, tenant.id)
                    await create_profile(
                        session,
                        niche=new.niche,
                        info=new.info,
                        country=new.country,
                        timezone=new.timezone,
                        price_currency=new.price_currency,
                        eu_only=new.eu_only,
                        links=links,
                        actor=Actor(kind="partner_member", id=person_id, origin="console"),
                    )
                    session.add(
                        AuditLog(
                            tenant_id=tenant.id,
                            actor=audit_actor,
                            action=CREATE_ACTION,
                            target=f"tenant:{tenant.id}",
                            before_json=None,
                            after_json={
                                "ref": ref,
                                "name": new.name,
                                "niche": new.niche,
                                "country": new.country,
                                "timezone": new.timezone,
                                "price_currency": new.price_currency,
                                "eu_only": new.eu_only,
                                "links": len(links),
                                "duplicate_name": duplicate,
                            },
                        )
                    )
                    job = (
                        await create_job(session, kind="client_read", created_by=person_id)
                        if links
                        else None
                    )
                finally:
                    _current_tenant.reset(token)
        except IntegrityError:
            # Lost a race for the same derived ref (the partner API takes any
            # ref it is given): the next free one, once.
            if attempt == 0:
                continue
            raise
        log.info(
            "console.client.created",
            partner_id=str(partner.id),
            tenant_id=str(tenant.id),
            external_client_ref=ref,
            links=len(links),
            duplicate_name=duplicate,
        )
        return CreatedClient(
            tenant_id=tenant.id, ref=ref, name=new.name, duplicate_name=duplicate, read_job=job
        )
    raise AssertionError("unreachable")  # pragma: no cover


# ── hard delete ──────────────────────────────────────────────────────────


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

    # Its own invoices AND its partner's: a partner invoice carries no
    # ``tenant_id`` and names the tenant as one of its lines — RESTRICT too.
    invoices = await session.scalar(
        sa.text(
            "SELECT count(*) FROM ("
            "  SELECT id FROM invoices WHERE tenant_id = :t"
            "  UNION SELECT invoice_id FROM invoice_lines WHERE tenant_id = :t"
            ") AS i"
        ),
        {"t": str(tenant_id)},
    )
    if invoices:
        raise TenantDeleteBlocked(
            409,
            f"el tenant aparece en {invoices} factura(s), propias o de su partner, "
            "y no se puede borrar: la conservación de facturación es una "
            "obligación legal (RGPD art. 17.3.b). Anula o traspasa las facturas "
            "antes de borrar.",
        )

    payments = await session.scalar(
        sa.text("SELECT count(*) FROM tenant_payments WHERE tenant_id = :t"),
        {"t": str(tenant_id)},
    )
    if payments:
        raise TenantDeleteBlocked(
            409,
            f"el tenant tiene {payments} pago(s) anotado(s) y no se puede borrar: "
            "son registros de cobro de Auphere y se conservan como las facturas.",
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


# ── archivar y restaurar (spec 047, requisitos 6.4, 6.5 y 6.8) ─────────────────

#: Acciones y frases que ya están en ``console_audit_vocabulary`` (migración 0084).
STATUS_ACTION: Final = "console.client.status"
UPDATE_ACTION: Final = "console.client.update"


class LifecycleError(Exception):
    """Un no con nombre: ``code`` cerrado y el HTTP que le toca."""

    def __init__(self, code: str, status: int, message: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.message = message


@dataclass(frozen=True)
class AgentChange:
    agent_id: uuid.UUID
    name: str
    before: VisibleState
    after: VisibleState


async def _agents_now(session: AsyncSession, tenant: Tenant) -> list[AgentState]:
    from nexus_api.services.client_overview import read_client

    return (await read_client(session, tenant.id, tenant.status)).agents


def _pair(before: list[AgentState], after: list[AgentState]) -> list[AgentChange]:
    old = {a.agent_id: a for a in before}
    return [
        AgentChange(
            agent_id=a.agent_id,
            name=a.name,
            before=old[a.agent_id].visible if a.agent_id in old else a.visible,
            after=a.visible,
        )
        for a in after
    ]


async def archive_client(
    session: AsyncSession, tenant: Tenant, *, actor: str
) -> tuple[Lifecycle, list[AgentChange]]:
    """Archiva el cliente: sus agentes quedan «Pausado · cliente archivado» (el
    turno no los corre: ``dispatcher._INACTIVE_STATUSES``), su consola lite y su
    app se cierran (``client_auth.open_client``) y lo que tenía cada agente queda
    en la auditoría para devolverlo al restaurar. Devuelve de qué venía y cómo
    quedó cada agente. Hasta el bloque E no hay pausa por agente: la pausa es la
    del cliente."""
    if tenant.status is TenantStatus.ARCHIVED:
        raise LifecycleError("already_archived", 409)
    before = await _agents_now(session, tenant)
    previous = tenant.status
    tenant.status = TenantStatus.ARCHIVED
    await session.flush()
    after = await _agents_now(session, tenant)
    remembered = {str(a.agent_id): a.visible.code for a in before}
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor=actor,
            action=STATUS_ACTION,
            target=f"tenant:{tenant.id}",
            before_json={"status": previous.value, "agents": remembered},
            after_json={
                "status": "archived",
                "agents": remembered,
                "pause_reason": "client_archived",
            },
        )
    )
    await session.flush()
    return lifecycle_of(previous), _pair(before, after)


async def _archived_from(session: AsyncSession, tenant_id: uuid.UUID) -> TenantStatus:
    """El estado que tenía el cliente cuando lo archivaron, de su auditoría."""
    before = await session.scalar(
        sa.select(AuditLog.before_json)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == STATUS_ACTION,
            AuditLog.after_json["status"].astext == "archived",
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )
    raw = (before or {}).get("status")
    try:
        status = TenantStatus(raw) if raw else TenantStatus.ACTIVE
    except ValueError:
        status = TenantStatus.ACTIVE
    return TenantStatus.ACTIVE if status is TenantStatus.ARCHIVED else status


async def restore_client(
    session: AsyncSession, tenant: Tenant, *, actor: str
) -> tuple[Lifecycle, list[AgentChange]]:
    """Restaura un cliente archivado al estado que tenía, y con él a cada agente."""
    if tenant.status is not TenantStatus.ARCHIVED:
        raise LifecycleError("not_archived", 409)
    before = await _agents_now(session, tenant)
    target = await _archived_from(session, tenant.id)
    tenant.status = target
    await session.flush()
    after = await _agents_now(session, tenant)
    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor=actor,
            action=STATUS_ACTION,
            target=f"tenant:{tenant.id}",
            before_json={"status": "archived"},
            after_json={
                "status": target.value,
                "agents": {str(a.agent_id): a.visible.code for a in after},
            },
        )
    )
    await session.flush()
    return lifecycle_of(target), _pair(before, after)


async def delete_client(
    session: AsyncSession, tenant: Tenant, *, confirm_name: str, actor: str
) -> DeleteReport:
    """El borrado RGPD de hoy (research D40) con los «no» con nombre de la
    consola nueva: ``archive_first``, ``name_mismatch`` y ``legal_retention``
    (una factura o un pago anotado: RGPD art. 17.3.b)."""
    if tenant.status is not TenantStatus.ARCHIVED:
        raise LifecycleError("archive_first", 409)
    if confirm_name.strip() != tenant.name.strip():
        raise LifecycleError("name_mismatch", 409)
    try:
        return await hard_delete_tenant(session, tenant, actor=actor)
    except TenantDeleteBlocked as exc:
        if exc.status_code == 409:
            raise LifecycleError("legal_retention", 409, exc.detail) from exc
        raise LifecycleError("delete_failed", exc.status_code) from exc
