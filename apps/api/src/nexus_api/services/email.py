"""Minimal transactional-email sender (Resend HTTP API).

Deliberately tiny: one ``send_email`` coroutine. When no real API key is
configured (``NEXUS_RESEND_API_KEY`` unset or still the dev placeholder) it
logs a warning and returns ``False`` instead of raising — callers treat email
as best-effort so a missing key never blocks the work that produced the mail
(e.g. the monthly receipt is still generated and shown in the panel).
"""

from __future__ import annotations

import httpx
import structlog

from nexus_api.config import get_settings

log = structlog.get_logger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT_S = 20.0


async def send_email(
    *,
    to: str | list[str],
    subject: str,
    html: str,
    from_addr: str | None = None,
    reply_to: str | None = None,
) -> bool:
    """Send an HTML email. Returns True on a 2xx, False otherwise (never raises)."""
    settings = get_settings()
    recipients = [to] if isinstance(to, str) else list(to)
    if not settings.email_enabled:
        log.warning("email.not_configured", to=recipients, subject=subject)
        return False

    payload: dict[str, object] = {
        "from": from_addr or settings.receipt_from_email,
        "to": recipients,
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(
                _RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
        if resp.status_code >= 300:
            log.error(
                "email.send_failed", status=resp.status_code, body=resp.text[:500], to=recipients
            )
            return False
    except httpx.HTTPError as exc:
        log.error("email.send_error", error=str(exc), to=recipients)
        return False

    log.info("email.sent", to=recipients, subject=subject)
    return True
