"""Quién responde una conversación: el agente o una persona — spec 030 (D14).

La regla de concurrencia que el admin estrenó (Bloque C) y que la Bandeja
necesita igual: dos personas que actúan a la vez sobre la misma conversación
no se pisan en silencio. ``agent_active_version`` sube en cada cambio; quien
llega con una versión vieja (``If-Match``) recibe el estado real.

Aquí vive solo el **cambio de estado** —comprobar la versión, poner en pausa,
reanudar—. Quién actúa, cómo se audita y qué se publica lo decide cada
llamante (``api/admin/conversations.py`` y ``api/console/lite/inbox.py``),
porque son actores distintos con vocabularios distintos. Copiar esto en los
dos sitios dejaba dos versiones del ``If-Match`` que acabarían divergiendo.

Al reanudar se **deja** ``takeover_context``: el despachador lo convierte en un
resumen de lo que hizo la persona para el siguiente turno del agente, y lo
limpia él (Bloque C). Limpiarlo aquí dejaría al agente sin saberlo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nexus_api.db.models import Conversation


class VersionMismatch(Exception):
    """La conversación cambió desde que quien actúa la vio."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected {expected}, actual {actual}")
        self.expected = expected
        self.actual = actual

    def detail(self) -> dict[str, Any]:
        return {"error": "version_mismatch", "expected": self.expected, "actual": self.actual}


def parse_if_match(raw: str | None) -> int | None:
    """``If-Match: 7`` o ``If-Match: "7"`` → 7. ``None`` si no viene.
    ``ValueError`` si no es un entero."""
    if raw is None:
        return None
    return int(raw.strip().strip('"'))


def check_version(conversation: Conversation, expected: int | None) -> None:
    if expected is not None and expected != conversation.agent_active_version:
        raise VersionMismatch(expected, conversation.agent_active_version)


def pause(
    conversation: Conversation,
    *,
    reason: str | None,
    notes: str | None,
    operator_label: str,
) -> None:
    """El agente deja de responder; una persona toma el relevo."""
    conversation.agent_active = False
    conversation.agent_active_version += 1
    conversation.takeover_context = {
        "reason": reason,
        "notes": notes,
        "started_at": datetime.now(UTC).isoformat(),
        "operator_id": operator_label,
    }


def bump(conversation: Conversation) -> None:
    """Un cambio de quién responde sin cambiar si responde el agente (otra
    persona toma el relevo de una que ya lo tenía)."""
    conversation.agent_active_version += 1


def resume(conversation: Conversation) -> None:
    """El agente vuelve a responder desde el siguiente mensaje del contacto."""
    conversation.agent_active = True
    conversation.agent_active_version += 1


__all__ = ["VersionMismatch", "bump", "check_version", "parse_if_match", "pause", "resume"]
