"""Spec 049, requisito 7.3: la Bandeja distingue la ventana de una persona de la
del agente.

En WhatsApp las dos son de 24 horas. En Instagram y Messenger, con Human Agent
aprobado, una persona puede responder hasta 7 días después del último mensaje
del contacto, y el agente solo 24 horas. La Bandeja tiene que poder decir «el
agente ya no puede, tú sí, hasta tal día» sin calcular plazos en el navegador.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.services.inbox_view import reply_windows

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("kind", ["instagram", "messenger"])
def test_social_with_human_agent_after_24h_person_can_agent_cannot(kind: str) -> None:
    last = NOW - timedelta(hours=30)
    w = reply_windows(kind, last, now=NOW, human_agent_approved=True)
    assert w.open is True
    assert w.closes_at == last + timedelta(days=7)
    assert w.agent_open is False


@pytest.mark.parametrize("kind", ["instagram", "messenger"])
def test_social_within_24h_both_can(kind: str) -> None:
    w = reply_windows(kind, NOW - timedelta(hours=2), now=NOW, human_agent_approved=True)
    assert w.open is True and w.agent_open is True


def test_social_without_human_agent_both_close_at_24h() -> None:
    last = NOW - timedelta(hours=30)
    w = reply_windows("instagram", last, now=NOW, human_agent_approved=False)
    assert w.open is False and w.agent_open is False
    assert w.closes_at == last + timedelta(hours=24)


def test_whatsapp_person_and_agent_share_the_24h_window() -> None:
    last = NOW - timedelta(hours=30)
    w = reply_windows("whatsapp", last, now=NOW, human_agent_approved=True)
    assert w.open is False and w.agent_open is False
    assert w.closes_at == last + timedelta(hours=24)


def test_no_inbound_message_means_no_window() -> None:
    w = reply_windows("instagram", None, now=NOW, human_agent_approved=True)
    assert w.open is False and w.agent_open is False and w.closes_at is None


def test_unknown_channel_uses_24h() -> None:
    last = NOW - timedelta(hours=2)
    w = reply_windows(None, last, now=NOW, human_agent_approved=True)
    assert w.open is True and w.agent_open is True
    assert w.closes_at == last + timedelta(hours=24)
