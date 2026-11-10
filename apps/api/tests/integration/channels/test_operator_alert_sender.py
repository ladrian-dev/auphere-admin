"""De qué número y en qué idioma sale un aviso por WhatsApp (bug
``el-aviso-de-escalada-no-llega``; spec 047, requisito 33.3).

La vía de siempre (un canal sin destinatarios propios: el dueño y los
revisores) mandaba la plantilla desde el número del cliente sin mirar si su
WABA la tenía, y siempre en ``es_CL``. Meta respondía ``(#132001) Template
name does not exist in the translation`` y el aviso no llegaba. Ahora:

- **Del número del cliente**, solo si su WABA tiene la plantilla aprobada, y en
  el idioma en que está aprobada (el español primero si hay varios).
- **Si no, del número de avisos de Auphere**, en el idioma configurado
  (``NEXUS_AUPHERE_ALERT_TEMPLATE_LANGUAGE``, ``es_CL`` por defecto).
- **Si tampoco hay número de Auphere**, el aviso no sale y no se marca como
  enviado: queda el motivo ``escalation_whatsapp_unavailable`` y un solo evento
  por cliente en el log, no uno por tic.

Nada sale a Meta: el número del cliente es el adaptador falso y el de Auphere,
o se sustituye, o no existe (el registro está vacío).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
import structlog
from nexus_worker.streams import operator_alerts
from nexus_worker.streams.operator_alerts import _process_pending

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog, OperatorNotification, OperatorNotificationStatus

from .conftest import give_alert_templates

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ESCALATION = "alert_escalation_v1"


@pytest.fixture
def from_auphere(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, list[str], str]]:
    """Lo que sale por el número de Auphere, sin salir a Meta."""
    out: list[tuple[str, str, list[str], str]] = []

    async def _auphere(phone: str, template: str, params: list[str], language: str) -> None:
        out.append((phone, template, params, language))

    monkeypatch.setattr(operator_alerts, "send_from_auphere", _auphere)
    return out


@pytest.fixture(autouse=True)
def _fresh_unavailable_log() -> None:
    """El aviso de «no puede salir» se recuerda por cliente en el proceso."""
    operator_alerts._unavailable_logged.clear()


async def _audit(info: dict[str, Any], action: str, after: dict[str, Any]) -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, info["tenant_id"]):
        row = AuditLog(
            tenant_id=info["tenant_id"],
            actor="system:test",
            action=action,
            target=f"tenant:{info['tenant_id']}",
            after_json=after,
        )
        s.add(row)
        await s.flush()
        return row.id


async def _escalate(info: dict[str, Any], reason: str = "queja formal") -> uuid.UUID:
    return await _audit(
        info,
        "conversation.escalated",
        {"customer_id": str(info["customer_id"]), "reason": reason},
    )


async def _notification(info: dict[str, Any], audit_id: uuid.UUID) -> OperatorNotification:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, info["tenant_id"]):
        found = await s.scalar(
            sa.select(OperatorNotification).where(OperatorNotification.audit_log_id == audit_id)
        )
    assert found is not None
    return found


# ── del número del cliente, en su idioma ───────────────────────────────────


@pytest.mark.parametrize(
    ("approved", "expected"),
    [(["es"], "es"), (["es_CL"], "es_CL"), (["en_US", "es_ES"], "es_ES")],
)
async def test_the_client_number_sends_in_the_language_its_template_is_approved_in(
    db_session: Any,
    two_tenants_with_channels: dict[str, Any],
    fake_adapter: Any,
    from_auphere: list[Any],
    approved: list[str],
    expected: str,
) -> None:
    info = two_tenants_with_channels["a"]
    for language in approved:
        await give_alert_templates(
            db_session, info["channel_id"], waba_id="WABA-A", language=language
        )
    audit_id = await _escalate(info)
    await _process_pending(get_sessionmaker(), {"meta": fake_adapter})

    [call] = fake_adapter.template_calls
    assert call["template_name"] == ESCALATION
    assert call["from_phone"] == info["business_phone"]
    assert call["language"] == expected, "en el idioma aprobado, no siempre en es_CL"
    assert from_auphere == []
    notif = await _notification(info, audit_id)
    assert notif.status is OperatorNotificationStatus.SENT


# ── sin la plantilla, del número de Auphere ────────────────────────────────


async def test_without_the_approved_template_the_alert_goes_from_auphere(
    db_session: Any,
    two_tenants_with_channels: dict[str, Any],
    fake_adapter: Any,
    from_auphere: list[Any],
) -> None:
    info = two_tenants_with_channels["a"]
    # El WABA del cliente tiene otras plantillas, y esta solo rechazada.
    await give_alert_templates(
        db_session, info["channel_id"], waba_id="WABA-A", templates=("reminder_24h",)
    )
    await give_alert_templates(
        db_session,
        info["channel_id"],
        waba_id="WABA-A",
        templates=(ESCALATION,),
        status="REJECTED",
    )
    escalated = await _escalate(info)
    reauth = await _audit(info, "connector.needs_reauth", {})
    await _process_pending(get_sessionmaker(), {"meta": fake_adapter})

    assert fake_adapter.template_calls == [], "el número del cliente no tiene la plantilla"
    owner = "+56999990001"
    assert sorted(from_auphere) == sorted(
        [
            (owner, ESCALATION, [info["customer_identifier"], "queja formal"], "es_CL"),
            (owner, "alert_needs_reauth_v1", [], "es_CL"),
        ]
    ), "a la misma persona, desde Auphere, en el idioma configurado"
    for audit_id in (escalated, reauth):
        assert (await _notification(info, audit_id)).status is OperatorNotificationStatus.SENT


async def test_auphere_sends_in_the_configured_language(
    monkeypatch: pytest.MonkeyPatch,
    two_tenants_with_channels: dict[str, Any],
    fake_adapter: Any,
    from_auphere: list[Any],
) -> None:
    assert get_settings().auphere_alert_template_language == "es_CL", "por defecto"
    monkeypatch.setattr(get_settings(), "auphere_alert_template_language", "es")
    info = two_tenants_with_channels["b"]
    await _escalate(info)
    await _process_pending(get_sessionmaker(), {"meta": fake_adapter})
    assert [(t, lang) for _p, t, _b, lang in from_auphere] == [(ESCALATION, "es")]


# ── sin plantilla y sin número de Auphere ──────────────────────────────────


async def test_without_template_or_auphere_number_it_fails_clearly_once_per_tenant(
    two_tenants_with_channels: dict[str, Any], fake_adapter: Any
) -> None:
    """El registro de números de Auphere está vacío (como en staging): el aviso
    no sale, no se marca como enviado y el log lo dice una vez por cliente."""
    info = two_tenants_with_channels["a"]
    sm = get_sessionmaker()
    with structlog.testing.capture_logs() as logs:
        first = await _escalate(info)
        await _process_pending(sm, {"meta": fake_adapter})
        second = await _escalate(info, "otra queja")
        await _process_pending(sm, {"meta": fake_adapter})
        await _process_pending(sm, {"meta": fake_adapter})

    assert fake_adapter.template_calls == []
    for audit_id in (first, second):
        notif = await _notification(info, audit_id)
        assert notif.status is OperatorNotificationStatus.FAILED, "no se marca como enviado"
        assert notif.sent_at is None
        assert notif.last_error == "escalation_whatsapp_unavailable"
    unavailable = [e for e in logs if e["event"] == "operator_alerter.whatsapp_unavailable"]
    assert len(unavailable) == 1, "un evento por cliente, no uno por tic ni por aviso"
    assert unavailable[0]["tenant_id"] == str(info["tenant_id"])
    assert unavailable[0]["reason"] == "escalation_whatsapp_unavailable"
    assert unavailable[0]["log_level"] == "warning"
    assert not [e for e in logs if e["event"] == "operator_alerter.send_failed"]
