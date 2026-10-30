"""El único sitio que envía correo — spec 051.

Todo correo es un :class:`~nexus_api.services.email_catalog.EmailKind` que se
envía con :func:`send_template` por una plantilla publicada en Resend. Aquí no
hay HTML: el cuerpo vive en Resend; el asunto y las variables los pone quien
llama. **Nunca lanza**: un correo que no sale no puede deshacer el trabajo que
lo produjo (el recibo sigue generado, la contraseña sigue cambiada). Devuelve
si salió, y lo que no salió queda en el registro con el tipo y la plantilla.

El modo por entorno (``settings.email_mode``)
---------------------------------------------
- ``resend``: sale todo. Producción, o staging cuando se pide a propósito.
- ``access``: staging. Salen solo los correos de acceso (alta, invitaciones,
  contraseña), los que alguien necesita para seguir; lo automático (recibos,
  alertas, avisos) se retiene.
- ``log``: local y CI. Se retiene todo.

Retener es no llamar al proveedor y dejar un ``email.suppressed`` con los
metadatos y **solo** las variables que la ficha marca como enlaces de acción,
para poder completar un flujo leyendo el registro. Producción no arranca si
retiene algo (``config.py``), y es lo que hace aceptable que un enlace de un
solo uso acabe en un registro. Sustituye al repliegue SMTP hacia Mailhog de la
spec 011, que enviaba el HTML del código: ese HTML ya no existe.

El escapado
-----------
La documentación de Resend usa ``{{{VAR}}}`` —inserción sin escapar en la
familia Mustache— y no dice que escape. Así que **toda** cadena se escapa
aquí, venga o no de un usuario: decidir variable a variable cuál es «de
usuario» es justo lo que se olvida en el tipo dieciséis. La excepción es
:class:`~nexus_api.services.email_catalog.EmailLines`, que ya viene escapada.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from html import escape
from typing import Any

import httpx
import sqlalchemy as sa
import structlog

from nexus_api.config import get_settings
from nexus_api.services.email_catalog import (
    CATALOG,
    MAX_VARIABLE_CHARS,
    EmailKind,
    EmailLines,
    email_locale,
)

log = structlog.get_logger(__name__)

RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_S = 20.0


def _escaped(value: str) -> str:
    """Escapa y recorta a ``MAX_VARIABLE_CHARS`` sin partir una entidad."""
    if isinstance(value, EmailLines):
        return str(value)
    out = escape(value, quote=True)
    if len(out) <= MAX_VARIABLE_CHARS:
        return out
    # Se recorta el texto original, no el escapado: cortar el escapado puede
    # dejar un ``&am`` a medias que el cliente de correo pinta tal cual.
    # Escapar solo alarga, así que quitar tantos caracteres como sobran
    # converge en pocas vueltas.
    room = MAX_VARIABLE_CHARS - 1
    raw = value[:room]
    while (excess := len(escape(raw, quote=True)) - room) > 0:
        raw = raw[:-excess]
    return escape(raw, quote=True) + "…"


def _owner_fields(
    owner: str, partner_id: Any, tenant_id: Any, client_ref: str | None
) -> dict[str, Any]:
    """Garantía 6: el registro de un correo lleva el negocio al que pertenece."""
    fields: dict[str, Any] = {"owner": owner}
    if partner_id is not None:
        fields["partner_id"] = str(partner_id)
    if tenant_id is not None:
        fields["tenant_id"] = str(tenant_id)
    if client_ref is not None:
        fields["client_ref"] = client_ref
    return fields


async def send_template(
    kind: EmailKind,
    *,
    to: str | Sequence[str],
    subject: str,
    variables: Mapping[str, str],
    locale: str = "es",
    partner_id: Any = None,
    tenant_id: Any = None,
    client_ref: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """Envía ``kind`` a ``to`` en ``locale``. True si salió (o quedó registrado)."""
    settings = get_settings()
    spec = CATALOG[kind]
    recipients = [to] if isinstance(to, str) else list(to)
    template = spec.aliases.get(locale) or spec.aliases["es"]
    context = {
        "kind": kind.value,
        "template": template,
        "to": recipients,
        "subject": subject,
        **_owner_fields(spec.owner, partner_id, tenant_id, client_ref),
    }

    missing = sorted(spec.variables - set(variables))
    unexpected = sorted(set(variables) - spec.variables)
    if missing or unexpected:
        # Resend rechazaría el envío por una variable de menos, y una de más
        # es una plantilla y un código que ya no dicen lo mismo.
        log.error("email.variables_mismatch", missing=missing, unexpected=unexpected, **context)
        return False

    mode = settings.email_mode
    if mode == "log" or (mode == "access" and not spec.access):
        links = {k: variables[k] for k in sorted(spec.link_variables)}
        log.info("email.suppressed", links=links, **context)
        return True

    if not settings.email_delivers:
        log.warning("email.not_configured", **context)
        return False

    sender = (
        settings.receipt_from_email
        if spec.sender == "billing"
        else settings.notifications_from_email
    )
    payload: dict[str, object] = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "reply_to": reply_to or settings.email_reply_to,
        "template": {"id": template, "variables": {k: _escaped(v) for k, v in variables.items()}},
        "tags": [{"name": "kind", "value": kind.value}],
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(
                RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
    except httpx.HTTPError as exc:
        log.error("email.send_failed", error=str(exc), **context)
        return False
    if resp.status_code >= 300:
        log.error("email.send_failed", status=resp.status_code, body=resp.text[:500], **context)
        return False
    try:
        message_id = resp.json().get("id")
    except ValueError:
        message_id = None
    log.info("email.sent", message_id=message_id, **context)
    return True


def log_delivery_mode(service: str) -> None:
    """Deja escrito en el arranque cómo envía correo este proceso (R1.4).

    Fuera de producción y enviando de verdad sale como ``warning``: es staging
    escribiendo a personas reales, y tiene que poder encontrarse.
    """
    settings = get_settings()
    fields = {"service": service, "mode": settings.email_mode, "environment": settings.environment}
    if settings.email_mode == "resend" and not settings.is_prod:
        log.warning("email.delivery_mode", real_email_outside_production=True, **fields)
    else:
        log.info("email.delivery_mode", **fields)


async def recipient_locales(emails: Iterable[str]) -> dict[str, str]:
    """El idioma de la cuenta de consola de cada dirección; ``es`` si no la hay.

    En su propia sesión de plataforma: quien llama puede estar dentro de una
    transacción de tenant que no ve ``console_auth``. Si la consulta falla, el
    correo sale en español en vez de no salir.
    """
    wanted = {e.strip().lower() for e in emails if e and e.strip()}
    found: dict[str, str] = {}
    if wanted:
        from nexus_api.db.base import get_sessionmaker
        from nexus_api.db.models.console_identity import ConsoleAccount

        try:
            async with get_sessionmaker()() as session:
                rows = await session.execute(
                    sa.select(sa.func.lower(ConsoleAccount.email), ConsoleAccount.locale).where(
                        sa.func.lower(ConsoleAccount.email).in_(sorted(wanted))
                    )
                )
                found = {email: email_locale(loc) for email, loc in rows.all()}
        except Exception as exc:  # el idioma nunca impide un correo
            log.warning("email.locale_lookup_failed", error=str(exc))
    return {e: found.get(e.strip().lower(), "es") for e in emails}


async def send_localized(
    kind: EmailKind,
    *,
    to: str | Sequence[str],
    compose: Callable[[str], tuple[str, Mapping[str, str]]],
    locale: str | None = None,
    partner_id: Any = None,
    tenant_id: Any = None,
    client_ref: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """Envía ``kind`` a cada destinatario en el idioma de su cuenta.

    ``compose(locale)`` devuelve el asunto y las variables en ese idioma. Los
    destinatarios se agrupan por idioma: un correo por idioma, no por persona.
    Con ``locale`` dado, no se consulta nada y sale en ese idioma. Devuelve
    True solo si salieron todos los grupos.
    """
    recipients = [to] if isinstance(to, str) else list(to)
    if not recipients:
        return False
    if locale is not None:
        groups: dict[str, list[str]] = {email_locale(locale): recipients}
    else:
        groups = {}
        for email, loc in (await recipient_locales(recipients)).items():
            groups.setdefault(loc, []).append(email)
    ok = True
    for loc, group in groups.items():
        subject, variables = compose(loc)
        sent = await send_template(
            kind,
            to=group,
            subject=subject,
            variables=variables,
            locale=loc,
            partner_id=partner_id,
            tenant_id=tenant_id,
            client_ref=client_ref,
            reply_to=reply_to,
        )
        ok = ok and sent
    return ok


__all__ = [
    "RESEND_URL",
    "log_delivery_mode",
    "recipient_locales",
    "send_localized",
    "send_template",
]
