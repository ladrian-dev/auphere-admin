"""El texto de los avisos por correo — spec 051, R2.5, R4.1 y R4.4 (T014).

Los avisos de la consola salen por dos plantillas genéricas (``partner_notice``
y ``client_notice``, R6 bis de ``research.md``): la plantilla pone la forma y el
texto de cada tipo vive en ``services/email_notices.py``. Lo que fija este
archivo:

- **barrido**: todo ``NotificationKind`` que puede salir por correo al partner o
  al cliente tiene fila; los que no salen nunca están en una lista explícita, con
  el motivo leído en el sitio que los emite;
- cada titular (que es también el asunto) cabe en 60 caracteres sin contar el
  nombre del cliente;
- ningún texto contiene una muletilla de ``contracts/redaccion.md``;
- ``client.activated`` elige su variante por lo que falta (``missing``);
- un tipo sin texto propio cae al genérico y deja ``email.notice_without_copy``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
import structlog

from nexus_api.api.console.support import _CATEGORY_ROUTING
from nexus_api.config import get_settings
from nexus_api.db.models import NotificationKind
from nexus_api.services.channel_config import CLIENT_PUSH_KIND
from nexus_api.services.email_catalog import CATALOG, EmailKind
from nexus_api.services.email_notices import (
    ACTIVATED_NOTICES,
    CLIENT_NOTICES,
    PARTNER_NOTICES,
    client_notice_email,
    partner_notice_email,
)

BASE = "https://consola.auphere.test"


@pytest.fixture(autouse=True)
def _console_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "console_base_url", BASE)


@dataclass
class Row:
    """Lo que el texto lee de una fila de ``console_notifications``."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    external_client_ref: str | None = None


# ── el barrido ────────────────────────────────────────────────────────────

#: Los tipos que **nunca** salen por correo, con el motivo leído en quien los
#: emite. ``emit`` manda correo con ``severity`` ≥ ``warning`` o ``email=True``;
#: una fila escrita sin pasar por ``emit`` no manda ninguno.
NEVER_EMAILED: dict[str, str] = {
    # Tienen su propio correo (``usage_cap_*`` y ``wallet_*``), que sale del
    # servicio que los evalúa; la fila de la campana se inserta directamente,
    # sin ``emit`` (``services/usage_alerts.py``, ``services/wallet_alerts.py``).
    "usage.threshold": "usage_alerts inserta la fila y envía usage_cap_threshold",
    "usage.cap_reached": "usage_alerts inserta la fila y envía usage_cap_reached",
    "wallet.low": "wallet_alerts inserta la fila y envía wallet_low",
    "wallet.empty": "wallet_alerts inserta la fila y envía wallet_empty",
    # Filas insertadas a mano, solo para la campana.
    "qa.cap_reached": "api/console/playground.py añade la fila sin emit",
    "billing.payment_failed": "billing/ladder.py inserta la fila sin emit",
    "billing.unpaid": "billing/ladder.py inserta la fila sin emit",
    "billing.canceled": "billing/ladder.py inserta la fila sin emit",
    # ``emit`` con ``email=False`` explícito.
    "client.read.done": "business/reader.py: email=False",
    "client.read.failed": "business/reader.py: email=False",
    "client.business_changed": "business/writes.py: email=False",
    # ``info`` (por defecto o explícito): campana, y push donde toca.
    "client.model_reset": "core/partner_allowlist.py: severity info",
    "member.joined": "api/console/invitations.py: severity info",
    "client.balance_request": "api/console/client_bags.py: severity info",
    "agent.paused": "lite/agents.py y agent_lifecycle_routes.py: severity info",
    "agent.resumed": "lite/agents.py y agent_lifecycle_routes.py: severity info",
    "channel.paused": "lite/agents.py y console/channel_config.py: severity info",
    "channel.resumed": "lite/agents.py y console/channel_config.py: severity info",
    "channel.connected": "services/channel_signup_links.py: severity info",
    "agent.suggestions.ready": "improvement/suggestions.py: severity info",
    "agent.correction.proposed": "improvement/corrections.py: severity info",
    "template.recategorized": "whatsapp_account_events.py: severity info",
    # Sin emisor: vocabulario que ya no se usa.
    "onboarding.step": "nadie lo emite",
    "channel.degraded": "nadie lo emite (lo sustituyó channel.problem)",
}

#: Solo para la persona del cliente (``audience = client``) y con plantilla
#: propia (catálogo §14-16): el partner nunca los recibe.
CLIENT_OWN_TEMPLATE = frozenset({"inbox.waiting", "client.balance_low", "client.balance_out"})

#: Lo que ``announce(..., to_client=True)`` lleva al cliente (``CLIENT_PUSH_KIND``)
#: pero siempre en ``info``: las pausas y reanudaciones que hace una persona.
CLIENT_INFO_ONLY = frozenset({"agent.paused", "agent.resumed", "channel.paused", "channel.resumed"})

#: Los avisos de soporte no son ``NotificationKind``: los nombra
#: ``api/console/support.py``, y salen siempre (``email=True``).
SUPPORT_KINDS = frozenset(kind for kind, _action in _CATEGORY_ROUTING.values())

ALL_KINDS = frozenset(k.value for k in NotificationKind) | SUPPORT_KINDS


def test_every_kind_a_partner_can_get_by_email_has_copy() -> None:
    emailed = ALL_KINDS - set(NEVER_EMAILED) - CLIENT_OWN_TEMPLATE
    missing = sorted(emailed - set(PARTNER_NOTICES))
    assert not missing, f"R2.5: tipos que salen por correo al partner sin texto: {missing}"


def test_every_kind_a_client_can_get_by_email_has_copy() -> None:
    emailed = set(CLIENT_PUSH_KIND) - CLIENT_INFO_ONLY
    missing = sorted(emailed - set(CLIENT_NOTICES))
    assert not missing, f"R2.5: tipos que salen por correo al cliente sin texto: {missing}"


def test_the_lists_name_real_kinds_and_do_not_contradict_each_other() -> None:
    assert set(NEVER_EMAILED) <= ALL_KINDS, "la lista nombra un tipo que ya no existe"
    assert set(PARTNER_NOTICES) <= ALL_KINDS, "una fila de partner con un tipo que no existe"
    assert set(CLIENT_NOTICES) <= ALL_KINDS, "una fila de cliente con un tipo que no existe"
    assert not set(NEVER_EMAILED) & set(PARTNER_NOTICES), "texto para un tipo que nunca sale"
    assert set(NEVER_EMAILED) >= CLIENT_INFO_ONLY


# ── la forma del texto ────────────────────────────────────────────────────


def _rows() -> Iterator[tuple[str, str, Any]]:
    """(tabla, tipo, textos por idioma) de cada fila, variantes incluidas."""
    for kind, by_locale in PARTNER_NOTICES.items():
        yield "partner", kind, by_locale
    for variant, by_locale in ACTIVATED_NOTICES.items():
        yield f"partner:{variant}", "client.activated", by_locale
    for kind, by_locale in CLIENT_NOTICES.items():
        yield "client", kind, by_locale


def _texts() -> Iterator[tuple[str, str, str, str]]:
    """(tabla, tipo, idioma, texto) de cada titular, mensaje y botón."""
    for table, kind, by_locale in _rows():
        assert set(by_locale) == {"es", "en"}, f"{table}/{kind}: falta un idioma"
        for locale, copy in by_locale.items():
            for text in (copy.heading, copy.message, copy.action):
                if text:
                    yield table, kind, locale, text


def test_every_heading_fits_in_sixty_characters_without_the_client_name() -> None:
    """R4.1: el titular es el asunto, y el asunto cabe en 60 sin el negocio."""
    long = [
        (table, kind, locale, copy.heading)
        for table, kind, by_locale in _rows()
        for locale, copy in by_locale.items()
        if len(copy.heading.replace("{client}", "")) > 60
    ]
    assert not long, long


def test_partner_rows_have_a_button_and_a_path_and_client_rows_do_not_need_one() -> None:
    for table, kind, by_locale in _rows():
        for locale, copy in by_locale.items():
            if table.startswith("partner"):
                assert copy.action, f"{table}/{kind}/{locale}: el botón (verbo + objeto)"
                assert copy.path.startswith("/"), f"{table}/{kind}: la ruta de la consola"


#: ``contracts/redaccion.md`` §«Lo que delata un texto hecho por una máquina».
BLACKLIST = (
    "esperamos que estés bien",
    "espero que este correo te encuentre bien",
    "¡hola!",
    "te escribimos para informarte",
    "te informamos que",
    "nos complace informarte",
    "no dudes en contactarnos",
    "no dudes en escribirnos",
    "estamos aquí para ayudarte",
    "estamos para lo que necesites",
    "gracias por confiar en nosotros",
    "gracias por elegirnos",
    "saludos cordiales",
    "atentamente",
    "un cordial saludo",
    "por favor, ten en cuenta que",
    "cabe destacar que",
    "es importante destacar",
    "recibes este correo porque",
    "recibes este aviso porque",
    "te recordamos que",
    "de manera rápida y sencilla",
    "en tan solo unos clics",
    "fácil y rápido",
    "increíble",
    "emocionante",
    "asombroso",
    "fantástico",
    "experiencia",
    "solución integral",
    "transformación digital",
    "revolucionario",
    "de vanguardia",
    "a propósito",
    "tope",
    "bolsa",
    "máquinas",
    "dar de baja",
    "haz clic aquí",
    "pulsa aquí",
    "ver más",
    "más información",
    "continuar",
    "click aquí",
    "i hope this email finds you well",
    "we are pleased to inform you",
    "please be advised",
    "don't hesitate to reach out",
    "feel free to reach out",
    "click here",
    "learn more",
    "seamless",
    "delightful",
    "unlock",
    "leverage",
)
_EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f2ff]")


def test_no_copy_uses_a_phrase_from_the_blacklist() -> None:
    hits = [
        (table, kind, locale, phrase)
        for table, kind, locale, text in _texts()
        for phrase in BLACKLIST
        if phrase in text.lower()
    ]
    assert not hits, hits


def test_no_copy_uses_emojis_dashes_or_exclamations() -> None:
    bad = [
        (table, kind, locale, text)
        for table, kind, locale, text in _texts()
        if _EMOJI.search(text) or "—" in text or "!" in text or "¡" in text
    ]
    assert not bad, bad


# ── el correo de cada aviso ───────────────────────────────────────────────


def test_a_partner_notice_fills_exactly_the_template_variables() -> None:
    row = Row("integration.reauth_required", {"integration": "gmail"}, "acme-01")
    subject, variables = partner_notice_email(row, "es", "Clínica Boreal")
    assert set(variables) == CATALOG[EmailKind.PARTNER_NOTICE].variables
    assert all(isinstance(v, str) for v in variables.values())
    assert (
        subject
        == variables["HEADING"]
        == "Una conexión de Clínica Boreal necesita permiso de nuevo"
    )
    assert variables["MESSAGE"].startswith("Una de las herramientas conectadas de Clínica Boreal")
    assert variables["ACTION_LABEL"] == "Revisar las conexiones"
    assert variables["ACTION_URL"] == f"{BASE}/clients/acme-01/integrations"


def test_without_a_name_the_client_is_its_reference() -> None:
    row = Row("client.out_of_quota", {"external_client_ref": "acme-01"}, "acme-01")
    subject, variables = partner_notice_email(row, "en", None)
    assert subject == "acme-01 has run out of balance"
    assert variables["ACTION_LABEL"] == "Assign balance"
    assert variables["ACTION_URL"] == f"{BASE}/usage"


def test_the_reference_in_a_link_is_escaped_for_the_path() -> None:
    row = Row("channel.problem", {"reason": "meta_error"}, "acme/01 sur")
    _subject, variables = partner_notice_email(row, "es", "Acme")
    assert variables["ACTION_URL"] == f"{BASE}/clients/acme%2F01%20sur/channels"


def test_the_payload_fills_model_days_percent_date_template_and_ticket() -> None:
    retirement = Row("model.retirement", {"deployment": "gpt-4o-mini", "days_left": 30})
    assert partner_notice_email(retirement, "es", None)[0] == (
        "El modelo gpt-4o-mini dejará de estar disponible en 30 días"
    )
    assert partner_notice_email(retirement, "en", None)[0] == (
        "The gpt-4o-mini model will be retired in 30 days"
    )

    price = Row(
        "model.price_change",
        {"deployment": "gpt-4o", "increase_pct": 25, "valid_from": "2026-11-06"},
    )
    subject, variables = partner_notice_email(price, "es", None)
    assert subject == "El precio del modelo gpt-4o sube un 25 %"
    assert "desde el 6 de noviembre de 2026" in variables["MESSAGE"]
    subject, variables = partner_notice_email(price, "en", None)
    assert subject == "The price of the gpt-4o model is going up 25%"
    assert "from November 6, 2026" in variables["MESSAGE"]

    paused = Row("template.paused", {"template_name": "recordatorio_cita"}, "acme-01")
    assert partner_notice_email(paused, "es", "Acme")[0] == (
        "Meta ha pausado la plantilla recordatorio_cita de Acme"
    )

    ticket = Row("support.ticket_opened", {"ticket_ref": "AU-42", "topic": "shopify"})
    subject, variables = partner_notice_email(ticket, "es", None)
    assert subject == "Hemos recibido tu consulta AU-42"
    assert variables["ACTION_URL"] == f"{BASE}/notifications"


@pytest.mark.parametrize(
    ("missing", "message_es", "label_es", "path"),
    [
        (["quota"], "no tiene saldo asignado", "Asignar saldo", "/usage"),
        (
            ["whatsapp"],
            "falta conectar su número de WhatsApp",
            "Conectar WhatsApp",
            "/clients/acme-01/channels",
        ),
        (
            ["quota", "whatsapp"],
            "faltan el número de WhatsApp y el saldo",
            "Abrir el cliente",
            "/clients/acme-01",
        ),
        (
            ["whatsapp", "quota"],
            "faltan el número de WhatsApp y el saldo",
            "Abrir el cliente",
            "/clients/acme-01",
        ),
    ],
)
def test_client_activated_says_what_is_missing(
    missing: list[str], message_es: str, label_es: str, path: str
) -> None:
    row = Row(
        "client.activated",
        {"external_client_ref": "acme-01", "can_serve": False, "missing": missing},
        "acme-01",
    )
    subject, variables = partner_notice_email(row, "es", "Acme")
    assert subject == "Acme está activo, pero todavía no puede atender"
    assert message_es in variables["MESSAGE"]
    assert variables["ACTION_LABEL"] == label_es
    assert variables["ACTION_URL"] == f"{BASE}{path}"


def test_a_kind_without_copy_falls_back_and_says_so() -> None:
    row = Row("something.new", {"x": 1}, "acme-01")
    with structlog.testing.capture_logs() as logs:
        subject, variables = partner_notice_email(row, "es", "Acme")
    assert subject == "Tienes un aviso nuevo en la consola"
    assert variables["MESSAGE"] == "Entra en la consola para ver el detalle."
    assert variables["ACTION_LABEL"] == "Ver tus avisos"
    assert variables["ACTION_URL"] == f"{BASE}/notifications"
    [event] = [e for e in logs if e["event"] == "email.notice_without_copy"]
    assert event["notice_kind"] == "something.new"
    assert event["log_level"] == "warning"


def test_client_activated_without_anything_missing_has_no_copy_of_its_own() -> None:
    row = Row("client.activated", {"can_serve": True, "missing": []}, "acme-01")
    with structlog.testing.capture_logs() as logs:
        subject, _variables = partner_notice_email(row, "en", "Acme")
    assert subject == "You have a new notification in the console"
    assert [e["notice_kind"] for e in logs if e["event"] == "email.notice_without_copy"] == [
        "client.activated"
    ]


def test_a_client_notice_fills_exactly_the_template_variables() -> None:
    row = Row("channel.problem", {"reason": "meta_error"}, "acme-01")
    subject, variables = client_notice_email(row, "es")
    assert set(variables) == CATALOG[EmailKind.CLIENT_NOTICE].variables
    assert subject == variables["HEADING"] == "Tu WhatsApp no está respondiendo"
    assert "La persona que gestiona tu agente ya ha recibido el aviso." in variables["MESSAGE"]
    assert variables["CONSOLE_URL"] == f"{BASE}/"

    subject, variables = client_notice_email(Row("client.wallet.empty", {}, "acme-01"), "en")
    assert subject == "Your balance has run out"
    assert variables["MESSAGE"].startswith("Your agent has stopped replying.")


def test_a_client_kind_without_copy_falls_back_and_says_so() -> None:
    with structlog.testing.capture_logs() as logs:
        subject, variables = client_notice_email(Row("agent.paused", {}, "acme-01"), "en")
    assert subject == "You have a new notification in the console"
    assert variables["MESSAGE"] == "Sign in to the console to see the details."
    assert [e["notice_kind"] for e in logs if e["event"] == "email.notice_without_copy"] == [
        "agent.paused"
    ]
