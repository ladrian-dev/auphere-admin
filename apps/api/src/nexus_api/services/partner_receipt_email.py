"""The monthly recibo as the ``receipt`` email — spec 051.

Pure: no I/O. It turns a :class:`ReceiptResult` into the subject and the
variables of the ``auphere-receipt-{es,en}`` template, in the language of
whoever receives it. The body lives in Resend (decision D1), so the email has
no HTML here; its copy is in ``specs/051-correos-con-oficio/contracts/catalogo.md``
§7. Callers hand :func:`receipt_email` to ``send_localized`` as its ``compose``.

The line descriptions come from the stored invoice lines and stay in Spanish
in both languages: ``partner_receipt`` persists them and reads the line model
back from their text, so they cannot be rewritten per reader.

The printable receipt the console lets you download is a different thing, a
document for the browser, and lives in ``partner_receipt_document``.
"""

from __future__ import annotations

from decimal import Decimal

from nexus_api.services.email_catalog import (
    console_link,
    format_day,
    format_month,
    format_usd,
    lines_variable,
)
from nexus_api.services.partner_receipt import ReceiptResult


def _more(locale: str) -> str:
    return "and {n} more items" if locale == "en" else "y {n} conceptos más"


def _rate(value: Decimal, locale: str) -> str:
    """The CLP-per-USD rate as the reader writes numbers: 932,84 / 932.84."""
    text = f"{value:,.2f}"
    if locale == "en":
        return text
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def _fx_note(rate: Decimal | None, locale: str) -> str:
    if not rate:
        return ""
    if locale == "en":
        return (
            "Amounts in Chilean pesos were converted to US dollars at the observed exchange "
            f"rate on the issue date ({_rate(rate, locale)} CLP per USD)."
        )
    return (
        "Los importes en pesos chilenos se han convertido a dólares al tipo de cambio "
        f"observado el día de emisión ({_rate(rate, locale)} CLP por USD)."
    )


def receipt_email(r: ReceiptResult, locale: str) -> tuple[str, dict[str, str]]:
    """Subject and variables of the ``receipt`` template in ``locale``."""
    period = format_month(r.period_year, r.period_month, locale)
    if locale == "en":
        subject = f"Your Auphere receipt for {period} ({r.partner_name})"
    else:
        subject = f"Tu recibo de {period} ({r.partner_name})"
    more = _more(locale)
    lines = lines_variable(
        (f"{line.description} · {format_usd(line.amount_cents)}" for line in r.lines),
        more=lambda n: more.format(n=n),
    )
    return subject, {
        "PARTNER_NAME": r.partner_name,
        "PERIOD": period,
        "TOTAL": format_usd(r.total_cents),
        "DUE_ON": format_day(r.due_date, locale),
        "LINES": lines,
        "FX_NOTE": _fx_note(r.clp_per_usd, locale),
        "BILLING_URL": console_link("/billing"),
    }


__all__ = ["receipt_email"]
