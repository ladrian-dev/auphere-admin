"""El catálogo cerrado de correos de la plataforma — spec 051.

Cada correo es un :class:`EmailKind` con su ficha: la plantilla publicada en
Resend (una por idioma), el remitente, las variables que el código envía, cuáles
de ellas son enlaces de acción y a qué negocio pertenece. **El cuerpo vive en
Resend** (decisión D1 de la spec): aquí no hay HTML. El texto inicial de cada
plantilla está en ``specs/051-correos-con-oficio/contracts/catalogo.md``.

Las ayudas de abajo son puras y existen para que cada sitio que envía escriba
fechas, meses, enlaces y listas igual que los demás.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from html import escape
from types import MappingProxyType
from typing import Literal

from nexus_api.config import get_settings

#: Tope de Resend para una variable de tipo cadena.
MAX_VARIABLE_CHARS = 2000


class EmailKind(StrEnum):
    TEAM_INVITE = "team_invite"
    CLIENT_INVITE = "client_invite"
    SIGNUP_LINK = "signup_link"
    SIGNUP_EXISTING = "signup_existing"
    PASSWORD_RESET = "password_reset"
    PASSWORD_CHANGED = "password_changed"
    RECEIPT = "receipt"
    CHARGE_CONFIRM = "charge_confirm"
    CLIENT_OUT_OF_QUOTA = "client_out_of_quota"
    WALLET_LOW = "wallet_low"
    WALLET_EMPTY = "wallet_empty"
    USAGE_CAP_THRESHOLD = "usage_cap_threshold"
    USAGE_CAP_REACHED = "usage_cap_reached"
    INBOX_WAITING = "inbox_waiting"
    CLIENT_BALANCE_LOW = "client_balance_low"
    CLIENT_BALANCE_OUT = "client_balance_out"
    CONVERSATION_ESCALATED = "conversation_escalated"
    PARTNER_NOTICE = "partner_notice"
    CLIENT_NOTICE = "client_notice"
    INTERNAL_ALERT = "internal_alert"


@dataclass(frozen=True)
class EmailSpec:
    aliases: Mapping[str, str]
    sender: Literal["billing", "notifications"]
    variables: frozenset[str]
    #: Las únicas variables que el modo de registro escribe (R1.1).
    link_variables: frozenset[str]
    #: Qué negocio exige la prueba de barrido de aislamiento (garantía 6).
    owner: Literal["partner", "client", "none"]
    links_allowed: bool = True
    #: Correo de acceso: alguien lo necesita para seguir (alta, invitación,
    #: contraseña). Son los únicos que salen en modo ``access`` (staging).
    access: bool = False


class EmailLines(str):
    """Una variable de líneas **ya escapadas** y unidas con ``<br>``.

    Las plantillas de Resend no tienen bucles (spec 051, R8 de research): un
    recibo pasa sus conceptos así. Es la única forma de que un ``<`` llegue sin
    escapar a una plantilla, y solo la construye :func:`lines_variable`.
    """

    __slots__ = ()


def _spec(
    template: str,
    variables: Iterable[str],
    *,
    links: Iterable[str] = (),
    owner: Literal["partner", "client", "none"],
    sender: Literal["billing", "notifications"] = "notifications",
    english: bool = True,
    links_allowed: bool = True,
    access: bool = False,
) -> EmailSpec:
    aliases = {"es": f"auphere-{template}-es"}
    if english:
        aliases["en"] = f"auphere-{template}-en"
    return EmailSpec(
        aliases=MappingProxyType(aliases),
        sender=sender,
        variables=frozenset(variables),
        link_variables=frozenset(links),
        owner=owner,
        links_allowed=links_allowed,
        access=access,
    )


CATALOG: Mapping[EmailKind, EmailSpec] = MappingProxyType(
    {
        EmailKind.TEAM_INVITE: _spec(
            "team-invite",
            ["INVITER", "PARTNER_NAME", "ROLE_LABEL", "EXPIRES_ON", "ACCEPT_URL"],
            links=["ACCEPT_URL"],
            owner="partner",
            access=True,
        ),
        EmailKind.CLIENT_INVITE: _spec(
            "client-invite",
            ["CLIENT_NAME", "EXPIRES_ON", "ACCEPT_URL"],
            links=["ACCEPT_URL"],
            owner="client",
            access=True,
        ),
        EmailKind.SIGNUP_LINK: _spec(
            "signup-link",
            ["EXPIRES_IN", "SIGNUP_URL"],
            links=["SIGNUP_URL"],
            owner="none",
            access=True,
        ),
        EmailKind.SIGNUP_EXISTING: _spec(
            "signup-existing",
            ["LOGIN_URL", "FORGOT_URL"],
            links=["LOGIN_URL", "FORGOT_URL"],
            owner="none",
            access=True,
        ),
        EmailKind.PASSWORD_RESET: _spec(
            "password-reset",
            ["RESET_URL"],
            links=["RESET_URL"],
            owner="none",
            access=True,
        ),
        # Spec 011, R4.3: ni un enlace salvo el ``mailto:`` del contacto.
        EmailKind.PASSWORD_CHANGED: _spec(
            "password-changed",
            ["CHANGED_AT", "SECURITY_CONTACT"],
            owner="none",
            links_allowed=False,
            access=True,
        ),
        EmailKind.RECEIPT: _spec(
            "receipt",
            ["PARTNER_NAME", "PERIOD", "TOTAL", "DUE_ON", "LINES", "FX_NOTE", "BILLING_URL"],
            links=["BILLING_URL"],
            owner="partner",
            sender="billing",
        ),
        EmailKind.CHARGE_CONFIRM: _spec(
            "charge-confirm",
            ["PARTNER_NAME", "AMOUNT", "CONCEPT", "CONFIRM_URL"],
            links=["CONFIRM_URL"],
            owner="partner",
            sender="billing",
        ),
        EmailKind.CLIENT_OUT_OF_QUOTA: _spec(
            "client-out-of-quota",
            ["CLIENT_NAME", "USAGE_URL"],
            links=["USAGE_URL"],
            owner="partner",
        ),
        EmailKind.WALLET_LOW: _spec(
            "wallet-low",
            ["PARTNER_NAME", "PERCENT_USED", "PERIOD", "CLIENTS_OUT_NOTE", "BILLING_URL"],
            links=["BILLING_URL"],
            owner="partner",
        ),
        EmailKind.WALLET_EMPTY: _spec(
            "wallet-empty",
            ["PARTNER_NAME", "PERIOD", "BILLING_URL"],
            links=["BILLING_URL"],
            owner="partner",
        ),
        EmailKind.USAGE_CAP_THRESHOLD: _spec(
            "usage-cap-threshold",
            ["PARTNER_NAME", "PERCENT", "USED", "CAP", "PERIOD", "USAGE_URL"],
            links=["USAGE_URL"],
            owner="partner",
        ),
        EmailKind.USAGE_CAP_REACHED: _spec(
            "usage-cap-reached",
            ["PARTNER_NAME", "CAP", "PERIOD", "ALERTS_URL"],
            links=["ALERTS_URL"],
            owner="partner",
        ),
        EmailKind.INBOX_WAITING: _spec(
            "inbox-waiting",
            ["CONTACT", "CONVERSATION_URL"],
            links=["CONVERSATION_URL"],
            owner="client",
        ),
        EmailKind.CLIENT_BALANCE_LOW: _spec(
            "client-balance-low",
            ["CLIENT_NAME", "CONSOLE_URL"],
            links=["CONSOLE_URL"],
            owner="client",
        ),
        EmailKind.CLIENT_BALANCE_OUT: _spec(
            "client-balance-out",
            ["CLIENT_NAME", "CONSOLE_URL"],
            links=["CONSOLE_URL"],
            owner="client",
        ),
        EmailKind.CONVERSATION_ESCALATED: _spec(
            "conversation-escalated",
            ["CONTACT", "REASON_LINE", "INBOX_URL"],
            links=["INBOX_URL"],
            owner="client",
        ),
        EmailKind.PARTNER_NOTICE: _spec(
            "partner-notice",
            ["HEADING", "MESSAGE", "ACTION_LABEL", "ACTION_URL"],
            links=["ACTION_URL"],
            owner="partner",
        ),
        EmailKind.CLIENT_NOTICE: _spec(
            "client-notice",
            ["HEADING", "MESSAGE", "CONSOLE_URL"],
            links=["CONSOLE_URL"],
            owner="client",
        ),
        EmailKind.INTERNAL_ALERT: _spec(
            "internal-alert",
            ["HEADING", "DETAIL", "KIND"],
            owner="none",
            # Lo lee el equipo de Auphere: solo en español.
            english=False,
        ),
    }
)


# ── ayudas ────────────────────────────────────────────────────────────

_MONTHS_ES = (
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
)
_MONTHS_EN = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

#: Las etiquetas de rol de la consola (``apps/console/src/i18n``, ``role.*``):
#: el correo nombra el rol igual que la pantalla en la que se va a ver.
ROLE_LABELS: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "es": MappingProxyType(
            {
                "owner": "Propietario",
                "admin": "Administrador",
                "builder": "Constructor",
                "analyst": "Analista",
                "billing": "Facturación",
            }
        ),
        "en": MappingProxyType(
            {
                "owner": "Owner",
                "admin": "Admin",
                "builder": "Builder",
                "analyst": "Analyst",
                "billing": "Billing",
            }
        ),
    }
)


def email_locale(value: str | None) -> Literal["es", "en"]:
    """El idioma de un correo a partir del de una cuenta (``es``, ``en-US``…).

    Inglés solo si la cuenta lo pide; cualquier otra cosa, o nada, español.
    Es la regla que ya seguían los correos de la contraseña (spec 011); el alta
    hacía lo contrario —todo lo que no fuera ``es`` salía en inglés— y la spec
    051 la iguala.
    """
    return "en" if (value or "").lower().startswith("en") else "es"


def format_day_es(day: date) -> str:
    """«6 de noviembre de 2026»."""
    return f"{day.day} de {_MONTHS_ES[day.month]} de {day.year}"


def format_day_en(day: date) -> str:
    """«November 6, 2026»."""
    return f"{_MONTHS_EN[day.month]} {day.day}, {day.year}"


def format_month_es(year: int, month: int) -> str:
    """«octubre de 2026»."""
    return f"{_MONTHS_ES[month]} de {year}"


def format_month_en(year: int, month: int) -> str:
    """«October 2026»."""
    return f"{_MONTHS_EN[month]} {year}"


def format_day(day: date, locale: str) -> str:
    return format_day_en(day) if locale == "en" else format_day_es(day)


def format_month(year: int, month: int, locale: str) -> str:
    return format_month_en(year, month) if locale == "en" else format_month_es(year, month)


def format_usd(cents: int) -> str:
    """«US$1,234.56», como el resto de importes de los correos de cobro."""
    return f"US${cents / 100:,.2f}"


def console_link(path: str) -> str:
    """Un enlace **absoluto** a la consola del entorno (R2.6)."""
    base = get_settings().console_base_url.rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def lines_variable(
    lines: Iterable[str],
    *,
    more: Callable[[int], str] | None = None,
    limit: int = MAX_VARIABLE_CHARS,
) -> EmailLines:
    """Escapa cada línea y las une con ``<br>``, sin pasar de ``limit``.

    Si no caben todas, se añaden mientras quepan junto con la línea de
    ``more(n)``, que dice cuántas quedaron fuera.
    """
    escaped = [escape(line, quote=True) for line in lines]
    joined = "<br>".join(escaped)
    if len(joined) <= limit:
        return EmailLines(joined)
    shown: list[str] = []
    for i, line in enumerate(escaped):
        rest = len(escaped) - i
        tail = escape(more(rest), quote=True) if more else "…"
        candidate = "<br>".join([*shown, line])
        # La línea entra solo si, detrás, todavía cabe la de «y N más» que
        # contaría a las que quedan después de ella.
        after = escape(more(rest - 1), quote=True) if more else "…"
        if len(f"{candidate}<br>{after}") > limit:
            return EmailLines("<br>".join([*shown, tail]))
        shown.append(line)
    return EmailLines("<br>".join(shown))


__all__ = [
    "CATALOG",
    "MAX_VARIABLE_CHARS",
    "ROLE_LABELS",
    "EmailKind",
    "EmailLines",
    "EmailSpec",
    "console_link",
    "email_locale",
    "format_day",
    "format_day_en",
    "format_day_es",
    "format_month",
    "format_month_en",
    "format_month_es",
    "format_usd",
    "lines_variable",
]
