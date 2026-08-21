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

import difflib
import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
    TenantCredentials,
)
from sqlalchemy import select, text

from nexus_mcp.base import ToolBase, ToolError
from nexus_mcp.servers.amigable_cobro.client import DEFAULT_BASE_URL, AmigableCobroClient
from nexus_mcp.servers.amigable_cobro.errors import AmigableCobroNotFound
from nexus_mcp.servers.amigable_cobro.schemas import (
    AddChargeInput,
    ApplyDiscountInput,
    CreateAccountInput,
    DebtRecord,
    FindClientInput,
    FindClientOutput,
    GetAccountInput,
    GetAccountOutput,
    GetDebtorByPhoneInput,
    GetDebtorByPhoneOutput,
    GetMyDebtInput,
    ListOverdueInput,
    ListOverdueOutput,
    PaymentEntry,
    RegisterPaymentInput,
    ReminderRecipient,
    SendRemindersInput,
    SendRemindersOutput,
    UpdateAccountInput,
    UpdateStatusInput,
    WriteResultOutput,
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


# ── concurrency: per-account advisory lock ───────────────────────────────
#
# The Amigable Cobro API is last-write-wins; when several admins text about
# the SAME account at once (add a charge, register a payment…), the agent
# would read-modify-write on stale data and clobber each other. We serialize
# writes to one account with a Postgres transaction-scoped advisory lock
# keyed by (tenant, account id). It auto-releases when the short lock
# transaction commits. Writes to different accounts never block each other.


def _lock_key(tenant_id: uuid.UUID, transaction_id: int) -> int:
    digest = hashlib.blake2b(f"{tenant_id}:{transaction_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


@asynccontextmanager
async def _account_lock(tenant_id: uuid.UUID, transaction_id: int) -> AsyncIterator[None]:
    """Serialize concurrent billing writes to one account across turns."""
    if _client_override is not None:  # unit tests bypass the DB
        yield
        return
    sm = get_sessionmaker()
    key = _lock_key(tenant_id, transaction_id)
    # ``tenant_scoped_session`` already opens the transaction; take the
    # xact-scoped advisory lock inside it (released when it commits on exit).
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
        yield


# ── dedup: find an existing client before creating a new account ──────────


def _norm_name(value: str | None) -> str:
    """Lowercase, strip accents + non-alphanumerics for fuzzy name compare."""
    if not value:
        return ""
    nfkd = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).strip()


def _token_matches(token: str, pool: set[str]) -> bool:
    """A name token matches a token in ``pool`` exactly or via a small typo."""
    return any(token == p or difflib.SequenceMatcher(None, token, p).ratio() >= 0.85 for p in pool)


def _name_matches(a: str | None, b: str | None) -> bool:
    """Match names tolerating partial names ("Leo" vs "Leo Morales Prueba") and
    typos ("jhonny" vs "johnny"). One name's tokens being a (fuzzy) subset of
    the other's counts as a match — the admin disambiguates."""
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    # Every token of the shorter name matches some token of the longer one.
    if all(_token_matches(t, longer) for t in shorter):
        return True
    # Whole-string fuzzy as a fallback (handles token order / minor edits).
    return difflib.SequenceMatcher(None, na, nb).ratio() >= 0.85


async def _find_existing_client(
    client: AmigableCobroClient,
    *,
    name: str | None,
    phone: str | None,
    document: str | None,
    max_pages: int,
) -> list[DebtRecord]:
    """Scan accounts and return those that likely belong to the same client,
    matching by phone (last digits), document (normalized) or fuzzy name."""
    doc = _norm_name(document)
    matches: list[DebtRecord] = []
    seen: set[int] = set()
    page = 1
    while page <= max_pages:
        raw, meta = await client.list_cuentas(page=page)
        for r in raw:
            rid = int(r.get("id") or 0)
            if rid in seen:
                continue
            hit = (
                (phone and _phone_matches(r.get("client_phone"), phone))
                or (doc and _norm_name(r.get("client_document")) == doc)
                or (name and _name_matches(r.get("client_name"), name))
            )
            if hit:
                seen.add(rid)
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


class GetAccount(_AmigableTool):
    name = "billing.get_account"
    description = (
        "Consulta UNA cuenta por cobrar por su ID, incluyendo el historial "
        "completo de abonos (payments). Úsala antes de registrar un pago o "
        "modificar una cuenta, para confirmar con el admin sobre datos reales."
    )
    input_model = GetAccountInput
    output_model = GetAccountOutput

    async def run(self, payload: GetAccountInput) -> GetAccountOutput:  # type: ignore[override]
        client = await self._client()
        try:
            raw = await client.get_cuenta(payload.transaction_id)
        except AmigableCobroNotFound:
            return GetAccountOutput(found=False, account=None, payments=[])
        payments = [
            PaymentEntry(
                id=p.get("id"),
                amount=float(p.get("amount") or 0),
                payment_date=p.get("payment_date"),
                payment_method=p.get("payment_method"),
                reference=p.get("reference"),
                notes=p.get("notes"),
            )
            for p in (raw.get("payments") or [])
            if isinstance(p, dict)
        ]
        return GetAccountOutput(found=True, account=_to_record(raw), payments=payments)


# ── write tools (admin-only agent) ───────────────────────────────────────
#
# These mutate real data in Amigable Cobro. They declare
# ``side_effects=("mutates_db",)`` so the QA Playground (dry_run)
# intercepts them — the operator sees WHAT would have been written
# without touching production data. The agent's system prompt requires
# an explicit admin confirmation before calling any of these.


class _AmigableWriteTool(_AmigableTool):
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    @staticmethod
    def _shape(raw: dict[str, Any], default_msg: str) -> WriteResultOutput:
        """Map the API's write response into WriteResultOutput.

        ``_unwrap`` returns either the refreshed account object or the
        flat ``{"success": ..., "message": ...}`` envelope.
        """
        account = _to_record(raw) if raw.get("id") and raw.get("total_amount") is not None else None
        message = str(raw.get("message") or default_msg)
        ok = bool(raw.get("success", True))
        return WriteResultOutput(ok=ok, message=message, account=account)


class RegisterPayment(_AmigableWriteTool):
    name = "billing.register_payment"
    description = (
        "Registra un abono (pago parcial o total) en una cuenta por cobrar de "
        "Amigable Cobro. La plataforma actualiza el monto pagado y marca PAID "
        "automáticamente si el saldo llega a cero. SOLO llamar después de que "
        "el administrador confirme explícitamente monto y cuenta."
    )
    input_model = RegisterPaymentInput
    output_model = WriteResultOutput

    async def run(self, payload: RegisterPaymentInput) -> WriteResultOutput:  # type: ignore[override]
        tenant_id = require_current_tenant()
        client = await self._client()
        async with _account_lock(tenant_id, payload.transaction_id):
            raw = await client.register_payment(
                payload.transaction_id,
                amount=payload.amount,
                payment_method=payload.payment_method,
                reference=payload.reference,
                notes=payload.notes,
            )
        return self._shape(raw, "Abono registrado")


class AddCharge(_AmigableWriteTool):
    name = "billing.add_charge"
    description = (
        "SUMA un cargo/anexo al monto total de una cuenta (aumenta la deuda) de "
        "forma segura: re-lee el total actual y le suma el monto, serializado por "
        "cuenta para no pisar cambios concurrentes de otros admins. USA ESTA para "
        "'agregar deuda / anexar un monto', NUNCA update_account para eso. SOLO "
        "tras confirmación explícita del admin (cuenta + monto a sumar)."
    )
    input_model = AddChargeInput
    output_model = WriteResultOutput

    async def run(self, payload: AddChargeInput) -> WriteResultOutput:  # type: ignore[override]
        tenant_id = require_current_tenant()
        client = await self._client()
        async with _account_lock(tenant_id, payload.transaction_id):
            try:
                current = await client.get_cuenta(payload.transaction_id)
            except AmigableCobroNotFound:
                return WriteResultOutput(
                    ok=False,
                    message=f"No existe la cuenta {payload.transaction_id}.",
                    account=None,
                )
            base_total = float(current.get("total_amount") or 0)
            new_total = round(base_total + payload.amount, 2)
            # Only send total_amount (the proven update shape). The lock +
            # fresh read is what prevents the lost-update corruption.
            raw = await client.update_cuenta(payload.transaction_id, {"total_amount": new_total})
        return self._shape(raw, f"Cargo de {payload.amount} agregado. Nuevo total: {new_total}")


class UpdateStatus(_AmigableWriteTool):
    name = "billing.update_status"
    description = (
        "Cambia manualmente el estado de una cuenta por cobrar: PENDING, PAID, "
        "OVERDUE o CANCELLED. Ej.: marcar PAID si se cobró en efectivo fuera del "
        "sistema, o CANCELLED para anularla. SOLO tras confirmación del admin."
    )
    input_model = UpdateStatusInput
    output_model = WriteResultOutput

    async def run(self, payload: UpdateStatusInput) -> WriteResultOutput:  # type: ignore[override]
        tenant_id = require_current_tenant()
        client = await self._client()
        async with _account_lock(tenant_id, payload.transaction_id):
            raw = await client.update_status(payload.transaction_id, status=payload.status)
        return self._shape(raw, f"Estado actualizado a {payload.status}")


class ApplyDiscount(_AmigableWriteTool):
    name = "billing.apply_discount"
    description = (
        "Aplica un descuento porcentual sobre el saldo pendiente de una o varias "
        "cuentas. Si el saldo queda en cero la cuenta pasa a PAID automáticamente. "
        "SOLO tras confirmación explícita del admin (cuentas + porcentaje)."
    )
    input_model = ApplyDiscountInput
    output_model = WriteResultOutput

    async def run(self, payload: ApplyDiscountInput) -> WriteResultOutput:  # type: ignore[override]
        client = await self._client()
        raw = await client.apply_discount(payload.transaction_ids, percentage=payload.percentage)
        return self._shape(raw, "Descuento aplicado")


class CreateAccount(_AmigableWriteTool):
    name = "billing.create_account"
    description = (
        "Crea una nueva cuenta por cobrar (deuda) en Amigable Cobro, con estado "
        "inicial PENDING y monto pagado en cero. SOLO tras confirmación del admin "
        "con nombre del deudor y monto."
    )
    input_model = CreateAccountInput
    output_model = WriteResultOutput

    async def run(self, payload: CreateAccountInput) -> WriteResultOutput:  # type: ignore[override]
        client = await self._client()
        # Anti-duplicate guard: unless the admin forced it, refuse to create a
        # client that already exists (same phone / document / fuzzy name) and
        # return the match so the agent can ask the admin.
        if not payload.force:
            dupes = await _find_existing_client(
                client,
                name=payload.client_name,
                phone=payload.client_phone,
                document=payload.client_document,
                max_pages=10,
            )
            if dupes:
                d = dupes[0]
                return WriteResultOutput(
                    ok=False,
                    message=(
                        f"Posible duplicado: ya existe '{d.client_name}' "
                        f"(cuenta ID {d.id}, saldo {d.balance}). ¿Usas esa cuenta o "
                        f"es otra persona? Para crear igual, confirma con force."
                    ),
                    account=d,
                )
        fields: dict[str, Any] = {
            "client_name": payload.client_name,
            "total_amount": payload.total_amount,
        }
        if payload.client_phone:
            fields["client_phone"] = payload.client_phone
        if payload.client_document:
            fields["client_document"] = payload.client_document
        fields["due_date"] = payload.due_date
        raw = await client.create_cuenta(fields)
        return self._shape(raw, "Cuenta creada")


class FindClient(_AmigableTool):
    name = "billing.find_client"
    description = (
        "Busca si un cliente YA existe en Amigable Cobro por nombre, teléfono o "
        "documento (tolera errores de tipeo en el nombre). Úsala ANTES de crear "
        "una cuenta nueva para no duplicar clientes."
    )
    input_model = FindClientInput
    output_model = FindClientOutput

    async def run(self, payload: FindClientInput) -> FindClientOutput:  # type: ignore[override]
        client = await self._client()
        matches = await _find_existing_client(
            client,
            name=payload.name,
            phone=payload.phone,
            document=payload.document,
            max_pages=payload.max_pages,
        )
        return FindClientOutput(found=bool(matches), matches=matches)


class UpdateAccount(_AmigableWriteTool):
    name = "billing.update_account"
    description = (
        "Actualiza los datos de una cuenta por cobrar existente (nombre, teléfono, "
        "documento, monto total, vencimiento o estado). SOLO tras confirmación del "
        "admin, y solo los campos que pidió cambiar."
    )
    input_model = UpdateAccountInput
    output_model = WriteResultOutput

    async def run(self, payload: UpdateAccountInput) -> WriteResultOutput:  # type: ignore[override]
        tenant_id = require_current_tenant()
        client = await self._client()
        fields = {
            k: v
            for k, v in {
                "client_name": payload.client_name,
                "client_phone": payload.client_phone,
                "client_document": payload.client_document,
                "total_amount": payload.total_amount,
                "due_date": payload.due_date,
                "status": payload.status,
            }.items()
            if v is not None
        }
        async with _account_lock(tenant_id, payload.transaction_id):
            raw = await client.update_cuenta(payload.transaction_id, fields)
        return self._shape(raw, "Cuenta actualizada")


_REMINDER_STATUS_MESSAGE: dict[str, str] = {
    "no_connector": "No pude enviar: este negocio no tiene el conector de Amigable Cobro conectado.",
    "no_channel": "No pude enviar: este negocio aún no tiene una línea de WhatsApp activa.",
    "templates_not_approved": (
        "No pude enviar: las plantillas de recordatorio todavía no están aprobadas por Meta."
    ),
    "no_due_accounts": "No hay cuentas con recordatorio pendiente para hoy — no se envió ninguno.",
    "not_confirmed": "No se enviaron recordatorios: falta la confirmación explícita del admin.",
    # The business has more than one active WhatsApp number and none is
    # marked as the notifications line. We refuse rather than pick one:
    # sending a debt reminder from the line the owner administers on is not
    # something a retry can undo.
    "channel_role_unassigned": (
        "No pude enviar: este negocio tiene más de una línea de WhatsApp activa y ninguna "
        "está marcada como línea de notificaciones. Hay que asignarla en el panel antes "
        "de enviar."
    ),
    "channel_not_available": (
        "No pude enviar: la línea de WhatsApp indicada no está activa para este negocio."
    ),
}


async def _tenant_name(tenant_id: uuid.UUID) -> str:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        tenant = await session.get(Tenant, tenant_id)
        return tenant.name if tenant else ""


class SendReminders(_AmigableTool):
    name = "billing.send_reminders"
    description = (
        "Envía AHORA los recordatorios de vencimiento a los DEUDORES del negocio "
        "(vence hoy, vence en 1-3 días, o lleva 7+ días vencida). El sistema ya hace "
        "este barrido solo una vez al día; esta herramienta es el adelanto manual, "
        "para cuando el admin no quiere esperar al barrido. Úsala SOLO si un admin te "
        "lo pide explícitamente, y con confirm=true únicamente después de que "
        "confirme. Es idempotente: un recordatorio ya enviado para esa cuenta, etapa "
        "y fecha de vencimiento no se reenvía, así que no duplica lo que ya mandó el "
        "barrido automático."
    )
    input_model = SendRemindersInput
    output_model = SendRemindersOutput
    # Encola mensajes salientes reales → efecto de lado (interceptado en QA dry_run).
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: SendRemindersInput) -> SendRemindersOutput:  # type: ignore[override]
        if not payload.confirm:
            return SendRemindersOutput(
                status="not_confirmed",
                queued=0,
                recipients=[],
                message=_REMINDER_STATUS_MESSAGE["not_confirmed"],
            )
        tenant_id = require_current_tenant()
        tenant_name = await _tenant_name(tenant_id)
        # Lazy import: the reminder engine lives in the worker package.
        from nexus_worker.streams.cobranza_reminder_cron import send_due_reminders_for_tenant

        result = await send_due_reminders_for_tenant(tenant_id, tenant_name)
        recipients = [ReminderRecipient(**r) for r in result.get("recipients", [])]
        queued = int(result.get("queued") or 0)
        deferred = int(result.get("deferred") or 0)
        status = str(result.get("status") or "ok")
        if status == "ok":
            message = f"Encolé {queued} recordatorio(s) de vencimiento."
        else:
            message = _REMINDER_STATUS_MESSAGE.get(status, "No se enviaron recordatorios.")
        if deferred:
            # Say it out loud. A cap that goes unmentioned reads to the admin
            # as "that was everybody".
            message += (
                f" Quedaron {deferred} fuera por el tope de este envío; "
                "salen en el barrido siguiente."
            )
        return SendRemindersOutput(
            status=status,
            queued=queued,
            deferred=deferred,
            recipients=recipients,
            message=message,
        )


AMIGABLE_COBRO_TOOLS: tuple[type[ToolBase], ...] = (
    # Debtor-facing (own debt only, no phone arg). Not whitelisted in the
    # admin-only cobranza_v1 vertical; kept for future debtor-facing use.
    GetMyDebt,
    # Admin reads.
    FindClient,
    GetAccount,
    GetDebtorByPhone,
    ListOverdue,
    # Admin writes (dry_run-intercepted in QA; prompt requires confirmation).
    AddCharge,
    ApplyDiscount,
    CreateAccount,
    RegisterPayment,
    UpdateAccount,
    UpdateStatus,
    # Admin on-demand action: send due-date reminders (requires confirm=true).
    SendReminders,
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
