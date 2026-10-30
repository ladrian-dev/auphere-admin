"""El texto de los avisos de la consola que salen por correo — spec 051.

Los avisos al partner y a la persona del cliente salen por dos plantillas
genéricas de Resend (``partner_notice`` y ``client_notice``): la plantilla pone
la forma —logo, titular, «Hola,», mensaje, botón y firma— y el texto de cada
tipo de aviso vive aquí. Es la excepción a la regla de que el texto está en
Resend (R6 bis de ``research.md``): treinta tipos con la misma forma serían
treinta plantillas casi idénticas, y cada cambio de forma, treinta cambios.

El texto inicial es el de ``specs/051-correos-con-oficio/contracts/catalogo.md``
§18 y §19. ``tests/unit/test_email_notices.py`` comprueba que todo tipo que puede
salir por correo tiene fila, que cada titular cabe en un asunto y que ningún
texto usa una muletilla de ``contracts/redaccion.md``.

Las funciones son puras salvo por el registro: reciben la fila del aviso y
devuelven el asunto y las variables de la plantilla. Ningún valor se escapa
aquí; lo hace ``send_template``.

Marcadores
----------
``{client}`` el nombre del cliente o, si no lo tiene, su referencia ·
``{ref}`` la referencia, para las rutas · ``{model}`` · ``{days}`` ·
``{percent}`` · ``{date}`` · ``{template}`` · ``{ticket}``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any, Protocol
from urllib.parse import quote

import structlog

from nexus_api.services.email_catalog import console_link, email_locale, format_day

log = structlog.get_logger(__name__)


class NoticeRow(Protocol):
    """Lo que el texto lee de una fila de ``console_notifications``."""

    @property
    def kind(self) -> str: ...

    @property
    def payload(self) -> Mapping[str, Any]: ...

    @property
    def external_client_ref(self) -> str | None: ...


@dataclass(frozen=True)
class NoticeCopy:
    """El texto de un aviso en un idioma.

    ``action`` es la etiqueta del botón (verbo + objeto) y ``path`` la ruta de
    la consola a la que lleva. Los avisos al cliente no tienen ni una ni otra:
    su botón es siempre «Abrir la consola» y va a la raíz.
    """

    heading: str
    message: str
    action: str = ""
    path: str = "/"


#: Texto por idioma: ``{"es": …, "en": …}``.
NoticeText = Mapping[str, NoticeCopy]


def _partner(
    path: str,
    *,
    es: tuple[str, str, str],
    en: tuple[str, str, str],
) -> NoticeText:
    return MappingProxyType(
        {
            "es": NoticeCopy(heading=es[0], message=es[1], action=es[2], path=path),
            "en": NoticeCopy(heading=en[0], message=en[1], action=en[2], path=path),
        }
    )


def _client(*, es: tuple[str, str], en: tuple[str, str]) -> NoticeText:
    return MappingProxyType(
        {
            "es": NoticeCopy(heading=es[0], message=es[1]),
            "en": NoticeCopy(heading=en[0], message=en[1]),
        }
    )


_ACTIVATED_HEADING = (
    "{client} está activo, pero todavía no puede atender",
    "{client} is active but can't reply yet",
)

#: ``client.activated`` solo sale por correo cuando el cliente **no** puede
#: atender (``severity = warning``), y el texto dice qué le falta según
#: ``payload["missing"]``: ``quota``, ``whatsapp`` o los dos.
ACTIVATED_NOTICES: Mapping[str, NoticeText] = MappingProxyType(
    {
        "quota": _partner(
            "/usage",
            es=(
                _ACTIVATED_HEADING[0],
                "El agente ya está publicado, pero el cliente no tiene saldo asignado. "
                "Asígnale saldo para que empiece a responder.",
                "Asignar saldo",
            ),
            en=(
                _ACTIVATED_HEADING[1],
                "The agent is published, but the client has no balance assigned. "
                "Assign balance so it can start replying.",
                "Assign balance",
            ),
        ),
        "whatsapp": _partner(
            "/clients/{ref}/channels",
            es=(
                _ACTIVATED_HEADING[0],
                "El agente ya está publicado, pero falta conectar su número de WhatsApp.",
                "Conectar WhatsApp",
            ),
            en=(
                _ACTIVATED_HEADING[1],
                "The agent is published, but its WhatsApp number isn't connected yet.",
                "Connect WhatsApp",
            ),
        ),
        "both": _partner(
            "/clients/{ref}",
            es=(
                _ACTIVATED_HEADING[0],
                "El agente ya está publicado, pero faltan el número de WhatsApp y el saldo.",
                "Abrir el cliente",
            ),
            en=(
                _ACTIVATED_HEADING[1],
                "The agent is published, but it still needs a WhatsApp number and balance.",
                "Open client",
            ),
        ),
    }
)

_REVIEW_AGENTS = ("Revisar los agentes", "Review agents")
_ASSIGN_BALANCE = ("Asignar saldo", "Assign balance")
_REVIEW_LIMIT = ("Revisar el límite", "Review limit")
_VIEW_USAGE = ("Ver el consumo", "View usage")
_REVIEW_TEMPLATES = ("Revisar las plantillas", "Review templates")
_OPEN_CHANNEL = ("Abrir el canal", "Open channel")
_VIEW_NOTICES = ("Ver tus avisos", "View your notifications")

#: Catálogo §18: el aviso al partner, por tipo. Las rutas son de la consola del
#: partner.
PARTNER_NOTICES: Mapping[str, NoticeText] = MappingProxyType(
    {
        "support.ticket_opened": _partner(
            "/notifications",
            es=(
                "Hemos recibido tu consulta {ticket}",
                "Nuestro equipo de soporte ya la está revisando y te responderá lo antes posible.",
                _VIEW_NOTICES[0],
            ),
            en=(
                "We've received your request {ticket}",
                "Our support team is already looking into it and will get back to you as "
                "soon as possible.",
                _VIEW_NOTICES[1],
            ),
        ),
        "support.capability_requested": _partner(
            "/notifications",
            es=(
                "Hemos recibido tu solicitud {ticket}",
                "Nuestro equipo ya la está revisando y te responderá lo antes posible.",
                _VIEW_NOTICES[0],
            ),
            en=(
                "We've received your request {ticket}",
                "Our team is already looking into it and will get back to you as soon as possible.",
                _VIEW_NOTICES[1],
            ),
        ),
        # La variante la elige ``partner_notice_email``; ésta, la de los dos
        # que faltan, es también la que da ``_client_can_serve`` cuando no
        # puede leer qué falta.
        "client.activated": ACTIVATED_NOTICES["both"],
        "model.retirement": _partner(
            "/agentes",
            es=(
                "El modelo {model} dejará de estar disponible en {days} días",
                "Los agentes que lo usan tienen que pasar a otro modelo antes de esa fecha "
                "para seguir funcionando.",
                _REVIEW_AGENTS[0],
            ),
            en=(
                "The {model} model will be retired in {days} days",
                "Agents that use it need to switch to another model before then to keep working.",
                _REVIEW_AGENTS[1],
            ),
        ),
        "model.price_change": _partner(
            "/agentes",
            es=(
                "El precio del modelo {model} sube un {percent} %",
                "El cambio se aplica desde el {date} y afecta al consumo de los agentes que "
                "lo usan.",
                _REVIEW_AGENTS[0],
            ),
            en=(
                "The price of the {model} model is going up {percent}%",
                "The change applies from {date} and affects the usage of the agents that use it.",
                _REVIEW_AGENTS[1],
            ),
        ),
        "integration.reauth_required": _partner(
            "/clients/{ref}/integrations",
            es=(
                "Una conexión de {client} necesita permiso de nuevo",
                "Una de las herramientas conectadas de {client} ha perdido el permiso de "
                "acceso. Hasta que alguien lo vuelva a conceder, el agente no podrá usarla.",
                "Revisar las conexiones",
            ),
            en=(
                "A {client} connection needs permission again",
                "One of {client}'s connected tools has lost its access permission. Until "
                "someone grants it again, the agent won't be able to use it.",
                "Review connections",
            ),
        ),
        "agent.tests.failing": _partner(
            "/clients/{ref}/agents",
            es=(
                "Algunas pruebas de un agente de {client} han dejado de pasar",
                "Ha ocurrido después de un cambio en los datos del negocio. Revisa las "
                "pruebas para ver qué respuestas han cambiado.",
                "Ver las pruebas",
            ),
            en=(
                "Some tests for a {client} agent are failing",
                "This happened after a change to the business details. Check the tests to "
                "see which replies have changed.",
                "View tests",
            ),
        ),
        # Cuando el partner no tiene lista de alertas de consumo: con lista, el
        # mismo hecho le llega por ``client_out_of_quota`` (catálogo §9).
        "client.out_of_quota": _partner(
            "/usage",
            es=(
                "{client} se ha quedado sin saldo",
                "Su agente ha dejado de responder a los mensajes que recibe. Asígnale más "
                "saldo para que vuelva a atender.",
                _ASSIGN_BALANCE[0],
            ),
            en=(
                "{client} has run out of balance",
                "Its agent has stopped replying to incoming messages. Assign more balance "
                "to get it working again.",
                _ASSIGN_BALANCE[1],
            ),
        ),
        "client.wallet.refill_short": _partner(
            "/billing",
            es=(
                "No se ha podido recargar el saldo de {client}",
                "No había saldo suficiente en tu cuenta para la recarga de este mes.",
                "Comprar saldo",
            ),
            en=(
                "{client}'s balance couldn't be topped up",
                "There wasn't enough balance in your account for this month's top-up.",
                "Buy balance",
            ),
        ),
        "client.wallet.low": _partner(
            "/usage",
            es=(
                "A {client} le queda poco saldo",
                "Cuando se agote, sus agentes dejarán de responder.",
                _ASSIGN_BALANCE[0],
            ),
            en=(
                "{client} is running low on balance",
                "When it runs out, its agents will stop replying.",
                _ASSIGN_BALANCE[1],
            ),
        ),
        "client.wallet.not_enough": _partner(
            "/usage",
            es=(
                "El saldo de {client} no llegará a fin de mes",
                "Al ritmo de uso de este mes, se agotará antes de que termine.",
                _ASSIGN_BALANCE[0],
            ),
            en=(
                "{client}'s balance won't last the month",
                "At this month's rate, it will run out before the month ends.",
                _ASSIGN_BALANCE[1],
            ),
        ),
        "client.wallet.empty": _partner(
            "/usage",
            es=(
                "{client} se ha quedado sin saldo",
                "Sus agentes han dejado de responder. Asígnale más saldo para que vuelvan a "
                "atender.",
                _ASSIGN_BALANCE[0],
            ),
            en=(
                "{client} has run out of balance",
                "Its agents have stopped replying. Assign more balance to get them working again.",
                _ASSIGN_BALANCE[1],
            ),
        ),
        "agent.cap.warning": _partner(
            "/usage",
            es=(
                "Un agente de {client} ha usado el 80 % de su límite del mes",
                "Cuando llegue al límite, el agente se pausará hasta el mes que viene.",
                _REVIEW_LIMIT[0],
            ),
            en=(
                "A {client} agent has used 80% of its monthly limit",
                "When it reaches the limit, the agent will be paused until next month.",
                _REVIEW_LIMIT[1],
            ),
        ),
        "agent.cap.reached": _partner(
            "/usage",
            es=(
                "Un agente de {client} ha llegado a su límite del mes",
                "El agente está en pausa y no responderá hasta el mes que viene, salvo que "
                "amplíes su límite.",
                _REVIEW_LIMIT[0],
            ),
            en=(
                "A {client} agent has reached its monthly limit",
                "The agent is paused and won't reply until next month unless you raise its limit.",
                _REVIEW_LIMIT[1],
            ),
        ),
        "build.budget.warning": _partner(
            "/usage",
            es=(
                "Has usado el 80 % del límite de creación de agentes",
                "Cuando llegues al límite, no se podrán crear agentes nuevos hasta el mes "
                "que viene. Editar los que ya tienes seguirá funcionando.",
                _VIEW_USAGE[0],
            ),
            en=(
                "You've used 80% of your agent-building limit",
                "Once you reach it, you won't be able to create new agents until next month. "
                "Editing your existing agents will still work.",
                _VIEW_USAGE[1],
            ),
        ),
        "build.budget.exhausted": _partner(
            "/usage",
            es=(
                "Has alcanzado el límite de creación de agentes",
                "No se podrán crear agentes nuevos hasta el mes que viene. Puedes seguir "
                "editando los que ya tienes.",
                _VIEW_USAGE[0],
            ),
            en=(
                "You've reached your agent-building limit",
                "You won't be able to create new agents until next month. You can still edit "
                "your existing agents.",
                _VIEW_USAGE[1],
            ),
        ),
        "template.paused": _partner(
            "/clients/{ref}/channels",
            es=(
                "Meta ha pausado la plantilla {template} de {client}",
                "Meta la ha pausado por baja calidad y no se podrá enviar hasta que se reactive.",
                _REVIEW_TEMPLATES[0],
            ),
            en=(
                "Meta has paused {client}'s {template} template",
                "Meta paused it for low quality, and it can't be sent until it's reactivated.",
                _REVIEW_TEMPLATES[1],
            ),
        ),
        "template.disabled": _partner(
            "/clients/{ref}/channels",
            es=(
                "Meta ha desactivado la plantilla {template} de {client}",
                "Ya no se puede enviar. Si la necesitas, tendrás que crear una nueva.",
                _REVIEW_TEMPLATES[0],
            ),
            en=(
                "Meta has disabled {client}'s {template} template",
                "It can no longer be sent. If you need it, you'll have to create a new one.",
                _REVIEW_TEMPLATES[1],
            ),
        ),
        # Fuera del catálogo §18, que no lo listaba: ``whatsapp_account_events``
        # lo emite en ``warning`` cuando Meta rechaza una plantilla, así que sale
        # por correo. Texto con la forma de ``template.paused``/``disabled``.
        "template.rejected": _partner(
            "/clients/{ref}/channels",
            es=(
                "Meta ha rechazado la plantilla {template} de {client}",
                "No se podrá enviar hasta que Meta la apruebe. En la página del canal "
                "encontrarás el motivo.",
                _REVIEW_TEMPLATES[0],
            ),
            en=(
                "Meta has rejected {client}'s {template} template",
                "It can't be sent until Meta approves it. You'll find the reason on the "
                "channel page.",
                _REVIEW_TEMPLATES[1],
            ),
        ),
        "template.quality_dropped": _partner(
            "/clients/{ref}/channels",
            es=(
                "Ha bajado la calidad de la plantilla {template} de {client}",
                "Si sigue bajando, Meta podría pausarla. Te recomendamos revisar su texto y "
                "a quién se envía.",
                _REVIEW_TEMPLATES[0],
            ),
            en=(
                "The quality of {client}'s {template} template has dropped",
                "If it keeps dropping, Meta may pause it. We recommend reviewing its wording "
                "and who it's sent to.",
                _REVIEW_TEMPLATES[1],
            ),
        ),
        "channel.problem": _partner(
            "/clients/{ref}/channels",
            es=(
                "El WhatsApp de {client} no está respondiendo",
                "Hay un problema con uno de sus números y el agente no puede atender por él. "
                "En la página del canal encontrarás el detalle.",
                _OPEN_CHANNEL[0],
            ),
            en=(
                "{client}'s WhatsApp isn't replying",
                "There's a problem with one of its numbers and the agent can't reply through "
                "it. You'll find the details on the channel page.",
                _OPEN_CHANNEL[1],
            ),
        ),
        "channel.account_alert": _partner(
            "/clients/{ref}/channels",
            es=(
                "Meta ha enviado un aviso sobre el WhatsApp de {client}",
                "En la página del canal puedes ver el aviso y si hace falta hacer algo.",
                _OPEN_CHANNEL[0],
            ),
            en=(
                "Meta has sent an alert about {client}'s WhatsApp",
                "On the channel page you can see the alert and whether any action is needed.",
                _OPEN_CHANNEL[1],
            ),
        ),
        "channel.account_review": _partner(
            "/clients/{ref}/channels",
            es=(
                "Meta no ha aprobado la cuenta de WhatsApp de {client}",
                "En la página del canal encontrarás el motivo y los pasos para solicitar una "
                "nueva revisión.",
                _OPEN_CHANNEL[0],
            ),
            en=(
                "Meta hasn't approved {client}'s WhatsApp account",
                "On the channel page you'll find the reason and the steps to request a new review.",
                _OPEN_CHANNEL[1],
            ),
        ),
        "channel.name_rejected": _partner(
            "/clients/{ref}/channels",
            es=(
                "Meta ha rechazado el nombre del WhatsApp de {client}",
                "Puedes proponer otro nombre desde la página del canal.",
                _OPEN_CHANNEL[0],
            ),
            en=(
                "Meta has rejected the name for {client}'s WhatsApp",
                "You can suggest a different name from the channel page.",
                _OPEN_CHANNEL[1],
            ),
        ),
    }
)

#: La última fila del §18: un tipo sin texto propio.
PARTNER_FALLBACK: NoticeText = _partner(
    "/notifications",
    es=(
        "Tienes un aviso nuevo en la consola",
        "Entra en la consola para ver el detalle.",
        _VIEW_NOTICES[0],
    ),
    en=(
        "You have a new notification in the console",
        "Sign in to the console to see the details.",
        _VIEW_NOTICES[1],
    ),
)

#: Catálogo §19: el aviso a la persona del cliente, por tipo. Son los que
#: ``channel_config.announce`` le lleva (``CLIENT_PUSH_KIND``) y salen en
#: ``warning`` o ``critical``. ``inbox.waiting`` y ``client.balance_*`` tienen
#: plantilla propia.
CLIENT_NOTICES: Mapping[str, NoticeText] = MappingProxyType(
    {
        "client.wallet.low": _client(
            es=(
                "Te queda poco saldo",
                "Cuando se agote, tu agente dejará de responder. Puedes pedir más saldo "
                "desde la consola.",
            ),
            en=(
                "Your balance is running low",
                "When it runs out, your agent will stop replying. You can request more "
                "balance from the console.",
            ),
        ),
        "client.wallet.not_enough": _client(
            es=(
                "Tu saldo no llegará a fin de mes",
                "Al ritmo de uso de este mes, se agotará antes de que termine. Puedes pedir "
                "más saldo desde la consola.",
            ),
            en=(
                "Your balance won't last the month",
                "At this month's rate, it will run out before the month ends. You can "
                "request more balance from the console.",
            ),
        ),
        "client.wallet.empty": _client(
            es=(
                "Tu saldo se ha agotado",
                "Tu agente ha dejado de responder. Pide más saldo desde la consola para que "
                "vuelva a atender.",
            ),
            en=(
                "Your balance has run out",
                "Your agent has stopped replying. Request more balance from the console to "
                "get it working again.",
            ),
        ),
        "agent.cap.warning": _client(
            es=(
                "Tu agente ha usado el 80 % de su límite del mes",
                "Cuando llegue al límite, se pausará hasta el mes que viene.",
            ),
            en=(
                "Your agent has used 80% of its monthly limit",
                "When it reaches the limit, it will be paused until next month.",
            ),
        ),
        "agent.cap.reached": _client(
            es=(
                "Tu agente ha llegado a su límite del mes",
                "Está en pausa y no responderá hasta el mes que viene, salvo que se amplíe "
                "su límite.",
            ),
            en=(
                "Your agent has reached its monthly limit",
                "It's paused and won't reply until next month unless its limit is raised.",
            ),
        ),
        "channel.problem": _client(
            es=(
                "Tu WhatsApp no está respondiendo",
                "Hay un problema con tu número y el agente no puede atender por él. La "
                "persona que gestiona tu agente ya ha recibido el aviso.",
            ),
            en=(
                "Your WhatsApp isn't replying",
                "There's a problem with your number and the agent can't reply through it. "
                "The person who manages your agent has already been notified.",
            ),
        ),
    }
)

#: La última fila del §19.
CLIENT_FALLBACK: NoticeText = _client(
    es=("Tienes un aviso nuevo en la consola", "Entra en la consola para ver el detalle."),
    en=(
        "You have a new notification in the console",
        "Sign in to the console to see the details.",
    ),
)


# ── rellenar ──────────────────────────────────────────────────────────────


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _day(value: Any, locale: str) -> str:
    """Una fecha ISO del aviso (``2026-11-06`` o con hora) en el formato del correo."""
    raw = _text(value)
    try:
        return format_day(date.fromisoformat(raw[:10]), locale)
    except ValueError:
        return raw


def _fill(row: NoticeRow, locale: str, client_name: str | None) -> dict[str, str]:
    payload = row.payload or {}
    ref = row.external_client_ref or _text(payload.get("external_client_ref"))
    return {
        "client": (client_name or "").strip() or ref,
        # Una referencia la elige el partner: en una ruta va codificada.
        "ref": quote(ref, safe=""),
        "model": _text(payload.get("deployment")),
        "days": _text(payload.get("days_left")),
        "percent": _text(payload.get("increase_pct")),
        "date": _day(payload.get("valid_from"), locale),
        "template": _text(payload.get("template_name")),
        "ticket": _text(payload.get("ticket_ref")),
    }


def _activated_variant(payload: Mapping[str, Any]) -> str | None:
    raw = payload.get("missing")
    missing = {str(m) for m in raw} if isinstance(raw, list | tuple | set) else set()
    if {"quota", "whatsapp"} <= missing:
        return "both"
    if "quota" in missing:
        return "quota"
    if "whatsapp" in missing:
        return "whatsapp"
    return None


def _partner_text(row: NoticeRow, audience: str) -> NoticeText:
    if row.kind == "client.activated":
        variant = _activated_variant(row.payload or {})
        if variant is not None:
            return ACTIVATED_NOTICES[variant]
    elif row.kind in PARTNER_NOTICES:
        return PARTNER_NOTICES[row.kind]
    log.warning("email.notice_without_copy", notice_kind=row.kind, audience=audience)
    return PARTNER_FALLBACK


def partner_notice_email(
    row: NoticeRow, locale: str, client_name: str | None
) -> tuple[str, dict[str, str]]:
    """El asunto y las variables de ``partner_notice`` para ``row`` en ``locale``.

    El asunto es el titular, como dice el catálogo. ``client_name`` es el
    nombre del cliente si se conoce; sin él, ``{client}`` es su referencia.
    """
    lang = email_locale(locale)
    copy = _partner_text(row, "partner")[lang]
    values = _fill(row, lang, client_name)
    heading = copy.heading.format_map(values)
    return heading, {
        "HEADING": heading,
        "MESSAGE": copy.message.format_map(values),
        "ACTION_LABEL": copy.action,
        "ACTION_URL": console_link(copy.path.format_map(values)),
    }


def client_notice_email(
    row: NoticeRow, locale: str, client_name: str | None = None
) -> tuple[str, dict[str, str]]:
    """El asunto y las variables de ``client_notice`` para ``row`` en ``locale``.

    El botón de la plantilla es «Abrir la consola» y lleva a su raíz: la persona
    del cliente ve la consola lite, que no tiene las rutas del partner.
    """
    text = CLIENT_NOTICES.get(row.kind)
    if text is None:
        log.warning("email.notice_without_copy", notice_kind=row.kind, audience="client")
        text = CLIENT_FALLBACK
    lang = email_locale(locale)
    copy = text[lang]
    values = _fill(row, lang, client_name)
    heading = copy.heading.format_map(values)
    return heading, {
        "HEADING": heading,
        "MESSAGE": copy.message.format_map(values),
        "CONSOLE_URL": console_link("/"),
    }


__all__ = [
    "ACTIVATED_NOTICES",
    "CLIENT_FALLBACK",
    "CLIENT_NOTICES",
    "PARTNER_FALLBACK",
    "PARTNER_NOTICES",
    "NoticeCopy",
    "NoticeRow",
    "NoticeText",
    "client_notice_email",
    "partner_notice_email",
]
