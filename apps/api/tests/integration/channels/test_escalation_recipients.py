"""Spec 047, T105 — el escalado por canal (historia 11; requisito 33).

- **Destinatarios**: hasta 10, cada uno con nombre y vía (WhatsApp con número,
  correo o la Bandeja).
- **Al escalar**: el aviso a cada uno por su vía, con el resumen opcional; ni el
  dueño ni el operador de antes cuando el canal tiene los suyos.
- **WhatsApp**: sale del número del canal si su WABA tiene la plantilla de aviso
  aprobada; si no, del de Auphere. La configuración dice cuál se usará.
- **El resumen**: mínimo (quién y por qué) y nunca a una persona del partner.
- **Disparadores**: los del agente, en solo lectura.
- **Sin destinatarios**: la revisión del agente lo avisa.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.streams import operator_alerts
from nexus_worker.streams.operator_alerts import _process_pending

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    Channel,
    Customer,
    OperatorNotification,
    PartnerMembership,
    WhatsAppTemplateStatus,
)
from nexus_api.services import channel_config
from nexus_api.services.agent_spec.review import load_input, review
from nexus_api.services.agent_spec.schema import AgentSpec
from nexus_api.services.channel_config import ChannelConfigError, ConfigIn, Recipient
from nexus_api.services.email_catalog import EmailKind

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

WABA = "WABA-ESC-1"


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Lo que sale por el número de Auphere y por correo, sin salir a Meta ni a
    Resend."""
    out: dict[str, list[Any]] = {"auphere": [], "email": []}

    async def _auphere(phone: str, template: str, params: list[str]) -> None:
        out["auphere"].append((phone, template, params))

    async def _email(kind: EmailKind, **kw: Any) -> bool:
        out["email"].append({"kind": kind, **kw})
        return True

    monkeypatch.setattr(operator_alerts, "send_from_auphere", _auphere)
    monkeypatch.setattr("nexus_api.services.email.send_template", _email)
    return out


def _shown(mail: dict[str, Any]) -> str:
    """Todo lo que lee quien abre el correo: el asunto y las variables."""
    return json.dumps([mail["subject"], mail["variables"]], ensure_ascii=False)


async def _configure(
    info: dict[str, Any], recipients: list[Recipient], *, summary: bool = True
) -> None:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, info["tenant_id"]):
        channel = await s.get(Channel, info["channel_id"])
        assert channel is not None
        channel.config = {**(channel.config or {}), "waba_id": WABA}
        await channel_config.write_config(
            s,
            channel,
            ConfigIn(
                mode="team_only",
                test_numbers=["+34600100100"],
                recipients=recipients,
                summary=summary,
            ),
            revision=None,
            actor="test",
        )
        await s.commit()


async def _escalate(info: dict[str, Any], reason: str = "Quiere hablar con el dueño") -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, info["tenant_id"]):
        customer = await s.get(Customer, info["customer_id"])
        assert customer is not None
        customer.name = "Lucía"
        audit = AuditLog(
            tenant_id=info["tenant_id"],
            actor="system:agent",
            action="conversation.escalated",
            target=str(info["conversation_id"]),
            after_json={"status": "escalated", "reason": reason},
        )
        s.add(audit)
        await s.commit()
        return audit.id


async def _approve_template() -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        s.add(
            WhatsAppTemplateStatus(
                waba_id=WABA,
                template_name=channel_config.ESCALATION_TEMPLATE,
                language="es_CL",
                status="approved",
                last_event_payload={},
            )
        )
        await s.commit()


async def _notify_from(info: dict[str, Any]) -> str:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, info["tenant_id"]):
        channel = await s.get(Channel, info["channel_id"])
        assert channel is not None
        return str((await channel_config.read_config(s, channel))["notify_from"])


# ── destinatarios ──────────────────────────────────────────────────────────


async def test_up_to_ten_recipients_each_with_a_name_and_a_way(
    two_tenants_with_channels: dict[str, Any],
) -> None:
    info = two_tenants_with_channels["a"]
    many = [Recipient(name=f"P{n}", via="inbox") for n in range(11)]
    with pytest.raises(ChannelConfigError) as too_many:
        await _configure(info, many)
    assert too_many.value.code == "too_many_recipients" and too_many.value.status == 422
    with pytest.raises(ChannelConfigError) as no_phone:
        await _configure(info, [Recipient(name="Marta", via="whatsapp")])
    assert no_phone.value.code == "recipient_phone_required"
    with pytest.raises(ChannelConfigError) as bad_mail:
        await _configure(info, [Recipient(name="Recepción", via="email", email="no-es-correo")])
    assert bad_mail.value.code == "recipient_email_invalid"

    await _configure(info, many[:10])
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, info["tenant_id"]):
        assert len(await channel_config.recipients_of(s, info["channel_id"])) == 10


# ── al escalar ─────────────────────────────────────────────────────────────


async def test_each_recipient_hears_by_its_way_from_the_channel_number(
    two_tenants_with_channels: dict[str, Any], fake_adapter: Any, sent: dict[str, list[Any]]
) -> None:
    info = two_tenants_with_channels["a"]
    await _approve_template()
    await _configure(
        info,
        [
            Recipient(name="Marta", via="whatsapp", phone_e164="+34 600 555 001"),
            Recipient(name="Recepción", via="email", email="Recepcion@cultor.es"),
            Recipient(name="Todos", via="inbox"),
        ],
    )
    assert await _notify_from(info) == "channel"
    audit_id = await _escalate(info)
    await _process_pending(get_sessionmaker(), {"meta": fake_adapter})

    # WhatsApp, desde el número del canal, con quién y por qué (33.2, 33.3).
    assert len(fake_adapter.template_calls) == 1
    call = fake_adapter.template_calls[0]
    assert call["from_phone"] == info["business_phone"]
    assert call["recipient"] == "+34600555001"
    assert call["params"] == {"body": ["Lucía", "Quiere hablar con el dueño"]}
    # El correo, con el mismo resumen mínimo (spec 051, catálogo §17).
    [mail] = sent["email"]
    assert mail["to"] == ["recepcion@cultor.es"]
    assert mail["kind"] == EmailKind.CONVERSATION_ESCALATED
    assert mail["subject"] == "Una conversación con Lucía necesita tu atención"
    assert mail["variables"]["CONTACT"] == "Lucía"
    assert mail["variables"]["REASON_LINE"] == (
        "El motivo que ha indicado el agente es: «Quiere hablar con el dueño»."
    )
    assert mail["variables"]["INBOX_URL"].endswith("/inbox")
    assert mail["variables"]["INBOX_URL"].startswith("http"), "R2.6: enlace absoluto"
    assert mail["tenant_id"] == info["tenant_id"], "garantía 6: el correo lleva el negocio"
    # Ni el dueño de antes ni el número de Auphere: el canal tiene los suyos.
    assert sent["auphere"] == []
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, info["tenant_id"]):
        notif = await s.scalar(
            sa.select(OperatorNotification).where(OperatorNotification.audit_log_id == audit_id)
        )
    assert notif is not None and notif.status.value == "sent"


async def test_without_the_approved_template_whatsapp_comes_from_auphere(
    two_tenants_with_channels: dict[str, Any], fake_adapter: Any, sent: dict[str, list[Any]]
) -> None:
    info = two_tenants_with_channels["b"]
    await _configure(info, [Recipient(name="Marta", via="whatsapp", phone_e164="+34600555002")])
    assert await _notify_from(info) == "auphere", "la configuración dice cuál se usará"
    await _escalate(info)
    await _process_pending(get_sessionmaker(), {"meta": fake_adapter})
    assert fake_adapter.template_calls == []
    assert sent["auphere"] == [
        ("+34600555002", "alert_escalation_v1", ["Lucía", "Quiere hablar con el dueño"])
    ]


async def test_the_summary_is_optional_and_never_reaches_a_partner_person(
    two_tenants_with_channels: dict[str, Any],
    fake_adapter: Any,
    sent: dict[str, list[Any]],
    console_world: dict[str, Any],
    db_session: Any,
) -> None:
    info = two_tenants_with_channels["a"]
    partner_person = await db_session.scalar(
        sa.select(PartnerMembership.email).where(
            PartnerMembership.partner_id == console_world["a"]["partner_id"]
        )
    )
    assert partner_person
    await _configure(info, [Recipient(name="Ana", via="email", email=partner_person)])
    await _escalate(info, "Reclama un cobro")
    await _process_pending(get_sessionmaker(), {"meta": fake_adapter})
    [mail] = sent["email"]
    shown = _shown(mail)
    assert "Lucía" not in shown and "Reclama un cobro" not in shown, (
        "nunca a una persona del partner"
    )
    assert mail["variables"]["CONTACT"] == "un cliente"
    assert mail["variables"]["REASON_LINE"] == "Abre la conversación para ver los detalles."
    assert mail["subject"] == "Una conversación con un cliente necesita tu atención"

    sent["email"].clear()
    await _configure(
        info, [Recipient(name="Marta", via="whatsapp", phone_e164="+34600555003")], summary=False
    )
    await _escalate(info, "Otra queja")
    await _process_pending(get_sessionmaker(), {"meta": fake_adapter})
    assert sent["auphere"][-1][2] == operator_alerts._NO_SUMMARY, "sin resumen, ni quién ni qué"


# ── disparadores y revisión ────────────────────────────────────────────────


async def test_triggers_are_the_agents_and_a_channel_without_recipients_is_reviewed(
    two_tenants_with_channels: dict[str, Any],
) -> None:
    info = two_tenants_with_channels["a"]
    spec = {
        "schema_version": "1",
        "mode": "instructions",
        "identity": {"name": "Recepción", "description": "Atiende la barbería."},
        "instructions": {"legacy_text": "Eres la recepción."},
        "escalation": {"triggers": ["asks_for_human", {"custom": "Si pregunta por facturas"}]},
        "ai_disclosure": {"decided": True, "mode": "first_message", "text": "Soy un asistente."},
        "model_policy": {"kind": "profile", "profile": "auto"},
        "memory": {"scope": "shared"},
    }
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, info["tenant_id"]):
        agent = Agent(id=uuid.uuid4(), tenant_id=info["tenant_id"], name="Recepción")
        s.add(agent)
        await s.flush()
        s.add(
            AgentConfig(
                tenant_id=info["tenant_id"],
                agent_id=agent.id,
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered="Eres la recepción.",
                tools=[],
                channels=[],
                policies={},
                spec=spec,
            )
        )
        channel = await s.get(Channel, info["channel_id"])
        assert channel is not None
        channel.agent_id = agent.id
        await s.flush()
        assert await channel_config.escalation_triggers(s, channel) == [
            "asks_for_human",
            {"custom": "Si pregunta por facturas"},
        ]
        parsed = AgentSpec.model_validate(spec)
        found = review(await load_input(s, agent_id=agent.id, spec=parsed, partner_id=None))
        codes = [f.code for f in found.findings]
        assert "channel_without_recipients" in codes, "la revisión avisa (33.6)"
        await s.commit()
    await _configure(info, [Recipient(name="Todos", via="inbox")])
    async with sm() as s, tenant_scoped_session(s, info["tenant_id"]):
        again = review(await load_input(s, agent_id=agent.id, spec=parsed, partner_id=None))
    assert "channel_without_recipients" not in [f.code for f in again.findings]
