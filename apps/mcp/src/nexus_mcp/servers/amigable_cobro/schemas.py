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
    balance: float = Field(description="Saldo pendiente (total_amount - paid_amount).")
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
    items: list[DebtRecord] = Field(description="Cuentas por cobrar de esta página.")
    total: int = Field(description="Total de cuentas reportadas por el negocio.")
    current_page: int = Field(description="Página actual.")
    last_page: int = Field(description="Última página disponible.")
    has_more: bool = Field(description="True si hay más páginas por consultar.")


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


__all__ = [
    "DebtRecord",
    "GetDebtorByPhoneInput",
    "GetDebtorByPhoneOutput",
    "GetMyDebtInput",
    "ListOverdueInput",
    "ListOverdueOutput",
]
