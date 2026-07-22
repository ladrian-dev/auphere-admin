"""Render a :class:`ReceiptResult` into the monthly recibo email.

Pure string building — no I/O — so it is unit-testable and the cron can hand
the output straight to ``send_email``.
"""

from __future__ import annotations

from html import escape

from nexus_api.services.partner_receipt import ReceiptResult

_MONTHS_ES = [
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def _usd(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def receipt_subject(r: ReceiptResult) -> str:
    return f"Recibo {_MONTHS_ES[r.period_month].capitalize()} {r.period_year} — {r.partner_name}"


def render_receipt_html(r: ReceiptResult) -> str:
    """Build the recibo email body (self-contained inline-styled HTML)."""
    period = f"{_MONTHS_ES[r.period_month]} {r.period_year}"
    due = r.due_date.strftime("%d/%m/%Y")
    rows = "\n".join(
        f"""<tr>
              <td style="padding:8px 12px;border-bottom:1px solid #eee">{escape(line.description)}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap">{_usd(line.amount_cents)}</td>
            </tr>"""
        for line in r.lines
    )
    fx_note = (
        f'<p style="color:#666;font-size:12px;margin:4px 0 0">'
        f"Conversión CLP→USD al dólar observado del día de emisión: {r.clp_per_usd}.</p>"
        if r.clp_per_usd
        else ""
    )
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;color:#111">
  <h2 style="margin:0 0 4px">Recibo mensual</h2>
  <p style="margin:0 0 16px;color:#555">{escape(r.partner_name)} · {period}</p>
  <table style="width:100%;border-collapse:collapse;font-size:14px">
    <thead>
      <tr>
        <th style="text-align:left;padding:8px 12px;border-bottom:2px solid #111">Concepto</th>
        <th style="text-align:right;padding:8px 12px;border-bottom:2px solid #111">Monto (USD)</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
    <tfoot>
      <tr>
        <td style="padding:12px;text-align:right;font-weight:600">Total a pagar</td>
        <td style="padding:12px;text-align:right;font-weight:700;font-size:16px">{_usd(r.total_cents)}</td>
      </tr>
    </tfoot>
  </table>
  <p style="margin:16px 0 0;font-size:14px"><strong>Vence:</strong> {due}</p>
  {fx_note}
  <p style="color:#999;font-size:12px;margin:24px 0 0">Auphere · recibo generado automáticamente. Ante cualquier duda responde a este correo.</p>
</div>"""
