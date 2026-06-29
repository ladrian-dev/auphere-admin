"""LLM-facing Amigable Cobro tools (``billing.*``).

Read-only access to a tenant's accounts-receivable so the cobranza agent
can look up a debtor's real balance and list overdue accounts.

Credential resolution mirrors the WooCommerce server: read
``tenant_connectors.credentials_ref`` (slug ``amigable_cobro``), fetch the
``tenant_credentials`` row, decrypt the Fernet payload to
``{"entity_id", "token"}``, take ``business_uuid`` (+ optional
``base_url``) from ``endpoint_meta``, and return a ready client.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, ClassVar

import structlog
from nexus_api.core.tenant_context import (
    get_current_customer,
    require_current_tenant,
    tenant_scoped_session,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Connector,
    Customer,
    TenantConnector,
    TenantConnectorStatus,
    TenantCredentials,
)
from sqlalchemy import select

from nexus_mcp.base import ToolBase, ToolError
from nexus_mcp.servers.amigable_cobro.client import DEFAULT_BASE_URL, AmigableCobroClient
from nexus_mcp.servers.amigable_cobro.schemas import (
    DebtRecord,
    GetDebtorByPhoneInput,
    GetDebtorByPhoneOutput,
    GetMyDebtInput,
    ListOverdueInput,
    ListOverdueOutput,
)

log = structlog.get_logger(__name__)

_AMIGABLE_SLUG = "amigable_cobro"


# ── credential resolution ────────────────────────────────────────────────


class AmigableCobroNotConfigured(ToolError):
    """No active ``tenant_connectors`` row for Amigable Cobro. Surfaced as
    a clean "connector not connected" message, not a stack trace."""


async def _load_amigable_client(tenant_id: uuid.UUID) -> AmigableCobroClient:
    """Resolve the active Amigable Cobro connector for ``tenant_id``."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = (
            await session.execute(
                select(TenantConnector, Connector)
                .join(Connector, Connector.id == TenantConnector.connector_id)
                .where(
                    TenantConnector.tenant_id == tenant_id,
                    Connector.slug == _AMIGABLE_SLUG,
                    TenantConnector.status.in_(
                        [
                            TenantConnectorStatus.CONNECTED.value,
                            TenantConnectorStatus.PARTIAL.value,
                        ]
                    ),
                )
            )
        ).first()
        if row is None:
            raise AmigableCobroNotConfigured(
                "Amigable Cobro connector is not connected for this tenant"
            )
        tc: TenantConnector = row[0]
        cred_ref: dict[str, Any] = tc.credentials_ref or {}
        tenant_credentials_id_raw = cred_ref.get("tenant_credentials_id")
        endpoint_meta = cred_ref.get("endpoint_meta") or {}
        business_uuid = endpoint_meta.get("business_uuid")
        base_url = endpoint_meta.get("base_url") or DEFAULT_BASE_URL
        if not (tenant_credentials_id_raw and business_uuid):
            raise AmigableCobroNotConfigured(
                "Amigable Cobro credentials_ref missing tenant_credentials_id or "
                "endpoint_meta.business_uuid"
            )
        try:
            tenant_credentials_id = uuid.UUID(str(tenant_credentials_id_raw))
        except ValueError as exc:
            raise AmigableCobroNotConfigured(
                "Amigable Cobro credentials_ref.tenant_credentials_id is not a UUID: "
                f"{tenant_credentials_id_raw!r}"
            ) from exc

        creds_row = await session.get(TenantCredentials, tenant_credentials_id)
        if creds_row is None:
            raise AmigableCobroNotConfigured(
                f"tenant_credentials row {tenant_credentials_id} not found"
            )
        try:
            payload = json.loads(bytes(creds_row.encrypted_payload).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise AmigableCobroNotConfigured(
                f"Amigable Cobro credentials payload is not valid JSON: {exc}"
            ) from exc

    entity_id = payload.get("entity_id")
    token = payload.get("token")
    if not (isinstance(entity_id, str) and isinstance(token, str)):
        raise AmigableCobroNotConfigured(
            "Amigable Cobro credentials payload missing entity_id / token"
        )
    return AmigableCobroClient(
        entity_id=entity_id,
        token=token,
        business_uuid=str(business_uuid),
        base_url=str(base_url),
    )


# ── test hook ────────────────────────────────────────────────────────────


_client_override: AmigableCobroClient | None = None


def set_test_client(client: AmigableCobroClient | None) -> None:
    """Bypass credential resolution. Test-only."""
    global _client_override
    _client_override = client


async def _resolve_client(tenant_id: uuid.UUID) -> AmigableCobroClient:
    if _client_override is not None:
        return _client_override
    return await _load_amigable_client(tenant_id)


# ── shaping ──────────────────────────────────────────────────────────────


def _to_record(raw: dict[str, Any]) -> DebtRecord:
    total = float(raw.get("total_amount") or 0)
    paid = float(raw.get("paid_amount") or 0)
    return DebtRecord(
        id=int(raw.get("id") or 0),
        client_name=raw.get("client_name"),
        client_phone=raw.get("client_phone"),
        client_document=raw.get("client_document"),
        total_amount=total,
        paid_amount=paid,
        balance=round(total - paid, 2),
        status=raw.get("status"),
        due_date=raw.get("due_date"),
        created_at=raw.get("created_at"),
    )


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _phone_matches(a: str | None, b: str | None) -> bool:
    """Compare phones by their last 7+ digits, ignoring prefixes/format."""
    da, db = _digits(a), _digits(b)
    if len(da) < 7 or len(db) < 7:
        return False
    n = min(len(da), len(db), 10)
    return da[-n:] == db[-n:]


async def _scan_for_phone(
    client: AmigableCobroClient, phone: str, max_pages: int
) -> list[DebtRecord]:
    """Scan up to ``max_pages`` of accounts and return those matching ``phone``.

    The Amigable Cobro API has no phone filter, so we page through and match
    client-side. Shared by the admin lookup and the debtor's own-debt tool.
    """
    matches: list[DebtRecord] = []
    page = 1
    while page <= max_pages:
        raw, meta = await client.list_cuentas(page=page)
        for r in raw:
            if _phone_matches(r.get("client_phone"), phone):
                matches.append(_to_record(r))
        last = int(meta.get("last_page") or page)
        if page >= last:
            break
        page += 1
    return matches


# ── tools ────────────────────────────────────────────────────────────────


class _AmigableTool(ToolBase):
    """Shared client resolution for every billing.* tool."""

    # Read-only lookups: no side effect to block, so the QA Playground
    # (dry_run) executes them for real. Reading a debtor's balance is
    # idempotent and is exactly what the operator needs to preview.
    side_effects: ClassVar[tuple[str, ...]] = ()

    async def _client(self) -> AmigableCobroClient:
        return await _resolve_client(require_current_tenant())


class ListOverdue(_AmigableTool):
    name = "billing.list_overdue"
    description = (
        "List the tenant's accounts-receivable (debts) from Amigable Cobro, one "
        "page at a time. Use to drive a collections campaign or review who owes "
        "money. By default returns only accounts with a pending balance. Inspect "
        "has_more / last_page to decide whether to request another page."
    )
    input_model = ListOverdueInput
    output_model = ListOverdueOutput

    async def run(self, payload: ListOverdueInput) -> ListOverdueOutput:  # type: ignore[override]
        client = await self._client()
        raw, meta = await client.list_cuentas(page=payload.page)
        records = [_to_record(r) for r in raw]
        if payload.only_with_balance:
            records = [r for r in records if r.balance > 0]
        if payload.status:
            want = payload.status.strip().lower()
            records = [r for r in records if (r.status or "").lower() == want]
        current = int(meta.get("current_page") or payload.page)
        last = int(meta.get("last_page") or current)
        return ListOverdueOutput(
            items=records,
            total=int(meta.get("total") or len(records)),
            current_page=current,
            last_page=last,
            has_more=current < last,
        )


class GetDebtorByPhone(_AmigableTool):
    name = "billing.get_debtor_by_phone"
    description = (
        "Look up a debtor's accounts-receivable by phone number. Use when a "
        "customer replies to a reminder so you can confirm their real pending "
        "balance, status and due date before answering. The Amigable Cobro API "
        "has no phone filter, so this scans pages and matches by the last digits "
        "of the number (tolerating +58 / leading 0 / formatting)."
    )
    input_model = GetDebtorByPhoneInput
    output_model = GetDebtorByPhoneOutput

    async def run(self, payload: GetDebtorByPhoneInput) -> GetDebtorByPhoneOutput:  # type: ignore[override]
        client = await self._client()
        matches = await _scan_for_phone(client, payload.phone, payload.max_pages)
        total_balance = round(sum(d.balance for d in matches), 2)
        return GetDebtorByPhoneOutput(
            found=bool(matches), debts=matches, total_balance=total_balance
        )


class GetMyDebt(_AmigableTool):
    name = "billing.get_my_debt"
    description = (
        "Consulta el saldo del DEUDOR ACTUAL — el cliente de ESTA conversación. "
        "No recibe teléfono: usa la identidad del chat, así nunca puede consultar "
        "la deuda de otra persona. Úsala cuando el cliente pregunta cuánto debe o "
        "antes de hablar de montos con él."
    )
    input_model = GetMyDebtInput
    output_model = GetDebtorByPhoneOutput

    async def run(self, payload: GetMyDebtInput) -> GetDebtorByPhoneOutput:  # type: ignore[override]
        customer_id = get_current_customer()
        if customer_id is None:
            return GetDebtorByPhoneOutput(found=False, debts=[], total_balance=0.0)
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, require_current_tenant()):
            customer = await session.get(Customer, customer_id)
            phone = customer.identifier if customer else None
        if not phone:
            return GetDebtorByPhoneOutput(found=False, debts=[], total_balance=0.0)
        client = await self._client()
        matches = await _scan_for_phone(client, phone, payload.max_pages)
        total_balance = round(sum(d.balance for d in matches), 2)
        return GetDebtorByPhoneOutput(
            found=bool(matches), debts=matches, total_balance=total_balance
        )


AMIGABLE_COBRO_TOOLS: tuple[type[ToolBase], ...] = (
    # Debtor-facing (own debt only, no phone arg).
    GetMyDebt,
    # Admin-facing (arbitrary lookups / bulk list). NOT for the debtor agent.
    GetDebtorByPhone,
    ListOverdue,
)


def build_amigable_cobro_tools() -> list[ToolBase]:
    """Materialise tool instances. Called once at process startup from
    ``build_default_registry``."""
    return [cls() for cls in AMIGABLE_COBRO_TOOLS]


__all__ = [
    "AMIGABLE_COBRO_TOOLS",
    "AmigableCobroNotConfigured",
    "build_amigable_cobro_tools",
    "set_test_client",
]
