"""Pydantic input/output models for the Amigable Cobro (billing.*) tools.

Input models validate the LLM's arguments; output models are the strict
shape the tool must return (the LLM sees ``model_json_schema()``).
"""

from __future__ import annotations

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class DebtRecord(OutputModel):
    """One accounts-receivable record from Amigable Cobro."""

    id: int = Field(description="ID interno de la cuenta por cobrar en Amigable Cobro.")
    client_name: str | None = Field(default=None, description="Nombre del deudor.")
    client_phone: str | None = Field(default=None, description="Teléfono del deudor (E.164).")
    client_document: str | None = Field(default=None, description="Cédula o RIF del deudor.")
    total_amount: float = Field(description="Monto total de la deuda.")
    paid_amount: float = Field(description="Monto pagado hasta ahora.")
    balance: float = Field(
        description=(
            "Saldo (total_amount - paid_amount). POSITIVO = el cliente debe ese "
            "monto; NEGATIVO = saldo a FAVOR del cliente (el negocio le debe); "
            "0 = al día."
        )
    )
    status: str | None = Field(default=None, description="Estado de la cuenta (ej. PENDING).")
    due_date: str | None = Field(
        default=None, description="Fecha de vencimiento (ISO 8601) o null."
    )
    created_at: str | None = Field(default=None, description="Fecha de creación (ISO 8601).")


class ListOverdueInput(InputModel):
    page: int = Field(default=1, ge=1, description="Página a consultar (empieza en 1).")
    only_with_balance: bool = Field(
        default=True,
        description="Si true, devuelve solo cuentas con saldo pendiente (>0).",
    )
    status: str | None = Field(
        default=None,
        description="Filtro opcional por estado exacto (ej. 'PENDING'). Case-insensitive.",
    )


class ListOverdueOutput(OutputModel):
    # Scalars FIRST. The worker truncates tool JSON at 8_000 chars
    # (``_TOOL_RESULT_CHAR_CAP``); if ``items`` lead, ``total`` never
    # reaches the model on a fat page.
    total: int = Field(
        description=(
            "Cuentas que reporta el negocio en total (todas las páginas, "
            "sin filtrar por saldo). No es dinero."
        )
    )
    page_count: int = Field(description="Cuentas en ESTA página después de aplicar filtros.")
    page_balance: float = Field(
        description=(
            "Suma de saldos de ESTA página (dinero). Positivo = se debe; "
            "negativo = a favor del cliente."
        )
    )
    current_page: int = Field(description="Página actual.")
    last_page: int = Field(description="Última página disponible.")
    has_more: bool = Field(description="True si hay más páginas por consultar.")
    items: list[DebtRecord] = Field(description="Cuentas por cobrar de esta página.")


class GetDebtorByPhoneInput(InputModel):
    phone: str = Field(
        min_length=4,
        max_length=32,
        description="Teléfono del deudor a buscar. Se compara por los últimos dígitos, "
        "tolerando prefijos/formatos (+58, 0, espacios, guiones).",
    )
    max_pages: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Tope de páginas a escanear al buscar (la API no filtra por teléfono).",
    )


class GetMyDebtInput(InputModel):
    # No phone field by design: the tool resolves the CURRENT customer's
    # identity from the turn context, so a debtor can never query someone
    # else's debt.
    max_pages: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Tope de páginas a escanear (la API no filtra por teléfono).",
    )


class GetDebtorByPhoneOutput(OutputModel):
    found: bool = Field(description="True si se encontró al menos una cuenta para ese teléfono.")
    debts: list[DebtRecord] = Field(description="Cuentas del deudor (puede haber varias).")
    total_balance: float = Field(description="Suma del saldo pendiente de todas sus cuentas.")


# ── detail read (with payments history) ─────────────────────────────────


class PaymentEntry(OutputModel):
    """One recorded payment (abono) on an account."""

    id: int | None = Field(default=None, description="ID del pago.")
    amount: float = Field(description="Monto del abono.")
    payment_date: str | None = Field(default=None, description="Fecha del pago (ISO 8601).")
    payment_method: str | None = Field(default=None, description="Método de pago usado.")
    reference: str | None = Field(default=None, description="Referencia del pago.")
    notes: str | None = Field(default=None, description="Notas del pago.")


class GetAccountInput(InputModel):
    transaction_id: int = Field(ge=1, description="ID de la cuenta por cobrar a consultar.")


class GetAccountOutput(OutputModel):
    found: bool = Field(description="True si la cuenta existe.")
    account: DebtRecord | None = Field(default=None, description="La cuenta consultada.")
    payments: list[PaymentEntry] = Field(
        default_factory=list, description="Historial de abonos registrados."
    )


# ── writes (admin-only agent; ejecutar SOLO tras confirmación del admin) ─


class WriteResultOutput(OutputModel):
    ok: bool = Field(description="True si la operación se aplicó en Amigable Cobro.")
    message: str = Field(description="Mensaje de resultado de la plataforma.")
    account: DebtRecord | None = Field(
        default=None, description="La cuenta después del cambio, si la API la devuelve."
    )


class RegisterPaymentInput(InputModel):
    transaction_id: int = Field(ge=1, description="ID de la cuenta a la que se abona.")
    amount: float = Field(
        gt=0, description="Monto del abono que indica el admin (parcial o total)."
    )
    payment_method: str | None = Field(
        default=None,
        max_length=40,
        description="Método de pago (ej. pago_movil, transferencia, binance, efectivo).",
    )
    reference: str | None = Field(
        default=None, max_length=120, description="Número de referencia del pago, si existe."
    )
    notes: str | None = Field(default=None, max_length=500, description="Nota opcional.")


class UpdateStatusInput(InputModel):
    transaction_id: int = Field(ge=1, description="ID de la cuenta.")
    status: str = Field(
        description="Nuevo estado: PENDING, PAID, OVERDUE o CANCELLED.",
        pattern="^(PENDING|PAID|OVERDUE|CANCELLED)$",
    )


class ApplyDiscountInput(InputModel):
    transaction_ids: list[int] = Field(
        min_length=1, max_length=50, description="IDs de las cuentas a descontar."
    )
    percentage: float = Field(
        gt=0, le=100, description="Porcentaje de descuento sobre el saldo pendiente."
    )


class AddChargeInput(InputModel):
    transaction_id: int = Field(ge=1, description="ID de la cuenta a la que se agrega el cargo.")
    amount: float = Field(gt=0, description="Monto a SUMAR al total de la deuda (anexo/cargo).")
    concept: str | None = Field(
        default=None, max_length=200, description="Concepto del cargo, opcional (ej. 'anexo')."
    )


class CreateAccountInput(InputModel):
    client_name: str = Field(min_length=1, max_length=160, description="Nombre del deudor.")
    total_amount: float = Field(gt=0, description="Monto total de la nueva deuda.")
    client_phone: str | None = Field(
        default=None, max_length=32, description="Teléfono del deudor (E.164, ej. +58424...)."
    )
    client_document: str | None = Field(
        default=None, max_length=40, description="Cédula o RIF del deudor."
    )
    # Required, and not because the model should be nagged into it: the
    # Amigable Cobro API rejects a create without it
    # (``{'due_date': ['The due date field is required.']}``). Declaring it
    # optional meant the tool fired, failed, and the agent then improvised a
    # date to retry with — which on 2026-08-19 produced a real account dated
    # a year in the past.
    due_date: str = Field(
        min_length=8,
        max_length=32,
        description=(
            "Fecha de vencimiento en ISO 8601 (AAAA-MM-DD). OBLIGATORIA: la "
            "plataforma rechaza la cuenta sin ella. Pídesela al admin y "
            "confírmala; nunca la deduzcas."
        ),
    )
    force: bool = Field(
        default=False,
        description=(
            "Si es false (default) y ya existe un cliente parecido (por teléfono, "
            "documento o nombre), NO crea y devuelve el posible duplicado para que "
            "el admin decida. Pon true SOLO si el admin confirmó que es otra persona."
        ),
    )


class FindClientInput(InputModel):
    name: str | None = Field(default=None, max_length=160, description="Nombre a buscar.")
    phone: str | None = Field(default=None, max_length=32, description="Teléfono a buscar.")
    document: str | None = Field(default=None, max_length=40, description="Documento a buscar.")
    max_pages: int = Field(default=10, ge=1, le=50, description="Páginas a escanear.")


class FindClientOutput(OutputModel):
    found: bool
    matches: list[DebtRecord]


class UpdateAccountInput(InputModel):
    transaction_id: int = Field(ge=1, description="ID de la cuenta a actualizar.")
    client_name: str | None = Field(default=None, max_length=160)
    client_phone: str | None = Field(default=None, max_length=32)
    client_document: str | None = Field(default=None, max_length=40)
    total_amount: float | None = Field(default=None, gt=0)
    due_date: str | None = Field(default=None)
    status: str | None = Field(default=None, pattern="^(PENDING|PAID|OVERDUE|CANCELLED)$")


class SendRemindersInput(InputModel):
    confirm: bool = Field(
        default=False,
        description=(
            "DEBE ser true para enviar. Ponlo en true SOLO después de que el "
            "admin te pida explícitamente enviar los recordatorios y confirme. "
            "El agente nunca envía recordatorios por iniciativa propia."
        ),
    )


class ReminderRecipient(OutputModel):
    cliente: str = Field(description="Nombre del deudor al que se le encoló el recordatorio.")
    stage: str = Field(
        description="Etapa: T-3 (faltan 3 días), T0 (vence hoy) o T+7 (7 días vencido)."
    )
    monto: str = Field(description="Saldo pendiente formateado (ej. $1.668,50).")
    fecha: str = Field(description="Fecha de vencimiento (dd/mm/aaaa).")


class SendRemindersOutput(OutputModel):
    status: str = Field(
        description=(
            "ok | no_connector | no_channel | templates_not_approved | "
            "no_due_accounts | not_confirmed."
        )
    )
    queued: int = Field(description="Cantidad de recordatorios encolados en este envío.")
    deferred: int = Field(
        default=0,
        description=(
            "Recordatorios que correspondían hoy pero quedaron fuera por el tope "
            "por envío; saldrán en el barrido siguiente."
        ),
    )
    recipients: list[ReminderRecipient] = Field(
        default_factory=list, description="Detalle de los recordatorios encolados."
    )
    message: str = Field(description="Resumen legible para reportarle al admin.")


__all__ = [
    "AddChargeInput",
    "ApplyDiscountInput",
    "CreateAccountInput",
    "DebtRecord",
    "FindClientInput",
    "FindClientOutput",
    "GetAccountInput",
    "GetAccountOutput",
    "GetDebtorByPhoneInput",
    "GetDebtorByPhoneOutput",
    "GetMyDebtInput",
    "ListOverdueInput",
    "ListOverdueOutput",
    "PaymentEntry",
    "RegisterPaymentInput",
    "ReminderRecipient",
    "SendRemindersInput",
    "SendRemindersOutput",
    "UpdateAccountInput",
    "UpdateStatusInput",
    "WriteResultOutput",
]
