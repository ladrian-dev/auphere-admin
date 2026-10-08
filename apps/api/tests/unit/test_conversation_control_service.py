"""Spec 030 T059 — quién responde una conversación, en un solo sitio (D14).

``services/conversation_control`` es lo que el admin estrenó en el Bloque C y
ahora usa también la Bandeja: comprobar la versión (``If-Match``), poner en
pausa y reanudar. Lo que fija este archivo es el contrato del servicio; que el
admin no cambió de comportamiento lo fijan sus propios tests
(``test_endpoint_conversations.py``), que corren sin tocar.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from nexus_api.services import conversation_control as cc


def _conv(**kw: Any) -> Any:
    return SimpleNamespace(
        agent_active=kw.get("agent_active", True),
        agent_active_version=kw.get("version", 3),
        takeover_context=kw.get("takeover_context"),
    )


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, None), ("7", 7), ('"7"', 7), (" 7 ", 7), ('W/"x"', "error")]
)
def test_if_match_is_an_integer_version(raw: str | None, expected: object) -> None:
    if expected == "error":
        with pytest.raises(ValueError):
            cc.parse_if_match(raw)
    else:
        assert cc.parse_if_match(raw) == expected


def test_a_stale_version_says_the_real_one() -> None:
    conv = _conv(version=5)
    cc.check_version(conv, None)  # sin If-Match no se comprueba
    cc.check_version(conv, 5)
    with pytest.raises(cc.VersionMismatch) as exc:
        cc.check_version(conv, 4)
    assert exc.value.detail() == {"error": "version_mismatch", "expected": 4, "actual": 5}


def test_pause_silences_and_leaves_the_context_for_the_agent() -> None:
    conv = _conv(version=1)
    cc.pause(conv, reason="inbox", notes="lo llevo yo", operator_label="Valeria Ríos")
    assert conv.agent_active is False
    assert conv.agent_active_version == 2
    ctx = conv.takeover_context
    assert ctx["reason"] == "inbox"
    assert ctx["notes"] == "lo llevo yo"
    assert ctx["operator_id"] == "Valeria Ríos"
    assert ctx["started_at"]

    cc.bump(conv)
    assert conv.agent_active_version == 3 and conv.agent_active is False

    cc.resume(conv)
    assert conv.agent_active is True
    assert conv.agent_active_version == 4
    # El despachador lo convierte en el resumen del siguiente turno y lo limpia él.
    assert conv.takeover_context is ctx
