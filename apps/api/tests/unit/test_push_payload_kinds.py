"""Todo tipo de aviso que una persona puede encender sale hacia Apple y Google.

``KIND_CONFIG`` da a cada tipo su categoría de iOS y su canal de Android. Un
tipo de ``NOTICE_KINDS`` sin entrada tumba el reparto con un ``KeyError`` justo
al enviar, y el aviso se pierde sin que nada lo diga (spec 043: los tres de
Reservas). Los ids son los que la app crea (``reservations_v1``,
``reservations``); cambiarlos aquí sin cambiarlos allí deja el aviso sin canal.
"""

from __future__ import annotations

import pytest

from nexus_api.db.models.client_phone import NOTICE_KINDS
from nexus_api.services import push_payloads
from nexus_api.services.push_payloads import KIND_CONFIG, Notice


@pytest.mark.parametrize("kind", sorted(NOTICE_KINDS))
def test_every_notice_kind_has_a_channel_and_a_category(kind: str) -> None:
    notice = Notice(kind=kind, title="t", body="b", url="u", thread="th", badge=1)
    _, apns = push_payloads.apns(notice, topic="app")
    fcm = push_payloads.fcm(notice, token="tok")
    assert apns["aps"]["category"] == KIND_CONFIG[kind]["category"]
    assert fcm["message"]["data"]["channelId"] == KIND_CONFIG[kind]["channel"]
    # expo-notifications no admite «:» ni «-» en la categoría.
    assert ":" not in KIND_CONFIG[kind]["category"]
    assert "-" not in KIND_CONFIG[kind]["category"]


def test_reservas_go_through_the_channel_the_app_creates() -> None:
    for kind in ("reservas.agent_change", "reservas.cancelled_today", "reservas.waitlist_accepted"):
        assert KIND_CONFIG[kind]["channel"] == "reservations_v1"
        assert KIND_CONFIG[kind]["category"] == "reservations"
