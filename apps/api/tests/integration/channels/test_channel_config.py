"""Spec 047, T104 — la página de cada canal (historia 11; requisito 32).

- **Secciones**: las cinco de la página, con la revisión y el ``ETag``.
- **«Solo mi equipo»**: exige un número de prueba; no responde ni marca como leído
  a nadie más, y sus mensajes se guardan.
- **«A todos»**: sus excepciones se guardan sin respuesta; exige agente publicado
  y saldo, con su código; no se elige con una plantilla de solo administradores.
- **Los números**: E.164 y sin duplicados.
- **Aislamiento**: la configuración de un canal no toca la de otro (garantía 9).
- **Al guardar**: vale desde el siguiente mensaje, queda en el historial con antes
  y después y se deshace durante 10 minutos; ``If-Match`` con 428 y 412.
- **Comprobaciones**: las de pruebas y escalado avisan sin bloquear.
- **Número recién conectado**: «Solo mi equipo» con el número de quien conectó;
  sin él, «Sin configurar».
- **Permisos del equipo**: se quedan en el agente.

La regla que decide vale para los números de WhatsApp de un partner con la
consola nueva; el resto sigue con la audiencia del agente (``admin_gate``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.admin_gate import audience_suppresses
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelConfigChange,
)
from nexus_api.services import channel_config

from ..business._business_world import Biz
from ._channel_world import (
    CUSTOMER,
    TEAM,
    _channel,
    _config,
    _inbound,
    _page,
    _published,
    _put,
    _say,
    _url,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# ── secciones ──────────────────────────────────────────────────────────────


async def test_the_page_has_its_five_sections_and_its_revision(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    channel_id = await _channel(db_session, biz, agent_id, "34911000001")
    page = await _page(client, biz, channel_id)
    config = page["config"]
    # A quién responde y excepciones, escalado, mensaje de espera y comprobaciones.
    assert config["audience"] == {"mode": "unset", "test_numbers": [], "exceptions": []}
    assert config["escalation"] == {"recipients": [], "summary": True}
    assert config["wait_message"] is None
    assert {c["code"] for c in page["checks"]} >= {"tests_up_to_date", "escalation_recipient"}
    assert page["revision"] == 0
    assert page["visible_state"]["code"] == "unconfigured"
    assert page["agent"]["id"] == str(agent_id)
    assert config["notify_from"] == "auphere"
    assert set(page["allowed"]) == {"configure", "pause", "disconnect"}


# ── «Solo mi equipo» ───────────────────────────────────────────────────────


async def test_team_only_needs_a_test_number_and_answers_nobody_else(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    channel_id = await _channel(db_session, biz, agent_id, "34911000002")
    refused = await _put(client, biz, channel_id, _config("team_only"), 0, expect=422)
    assert refused["detail"]["code"] == "channel_test_numbers_required"

    saved = await _put(client, biz, channel_id, _config("team_only", tests=[TEAM]), 0)
    assert saved["visible_state"]["code"] == "team_only"

    stranger = await _say(biz, channel_id, CUSTOMER, "hola, ¿abrís hoy?")
    assert stranger.calls == [], "«Solo mi equipo» no responde a otros números"
    kept = await _inbound(db_session, biz, "hola, ¿abrís hoy?")
    assert kept.skipped_reason == "not_admin", "se guarda en Conversaciones, sin respuesta"

    tester = await _say(biz, channel_id, TEAM.lstrip("+"), "prueba del equipo")
    assert len(tester.calls) == 1, "el número de prueba sí tiene respuesta"


async def test_the_read_receipt_follows_the_same_rule() -> None:
    """El webhook no marca como leído a quien el canal no responde (32.2): es la
    misma función que la puerta del turno."""
    team = {"mode": "team_only", "test": [TEAM], "exception": [], "strict": True}
    assert audience_suppresses(team, {}, CUSTOMER)
    assert not audience_suppresses(team, {}, "34600100100")
    everyone = {"mode": "everyone", "test": [], "exception": [CUSTOMER], "strict": True}
    assert audience_suppresses(everyone, {}, CUSTOMER)
    assert not audience_suppresses(everyone, {}, TEAM)
    unset = {"mode": "unset", "test": [], "exception": [], "strict": True}
    assert audience_suppresses(unset, {}, TEAM), "«Sin configurar» espera una decisión"
    # Fuera de la consola nueva manda la audiencia del agente, como antes.
    legacy = {**unset, "strict": False}
    assert not audience_suppresses(legacy, {}, TEAM)
    admin_only = {"admin_access": {"admin_only": True, "admin_phones": [TEAM]}}
    assert audience_suppresses(legacy, admin_only, CUSTOMER)


# ── «A todos» ──────────────────────────────────────────────────────────────


async def test_everyone_keeps_its_exceptions_without_an_answer(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    channel_id = await _channel(db_session, biz, agent_id, "34911000003")
    await _put(client, biz, channel_id, _config("everyone", exceptions=[CUSTOMER]), 0)

    excluded = await _say(biz, channel_id, CUSTOMER, "soy una excepción")
    assert excluded.calls == []
    assert (await _inbound(db_session, biz, "soy una excepción")).skipped_reason == "not_admin"
    anyone = await _say(biz, channel_id, "+34600300300", "quiero cita")
    assert len(anyone.calls) == 1


async def test_everyone_needs_a_published_agent_and_a_balance_with_its_code(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        draft = Agent(id=uuid.uuid4(), tenant_id=biz.tenant_id, name="Ventas")
        db_session.add(draft)
        await db_session.flush()
        db_session.add(
            AgentConfig(
                tenant_id=biz.tenant_id,
                agent_id=draft.id,
                version=1,
                status=AgentConfigStatus.STAGED,
                system_prompt_rendered="Borrador.",
                tools=[],
                channels=[],
                policies={},
            )
        )
    await db_session.commit()
    channel_id = await _channel(db_session, biz, draft.id, "34911000004")
    unpublished = await _put(client, biz, channel_id, _config("everyone"), 0, expect=409)
    assert unpublished["detail"]["code"] == "agent_not_published"
    assert unpublished["detail"]["fix"] == "publish_agent"

    agent_id = await _published(db_session, biz, "Recepción")
    other = await _channel(db_session, biz, agent_id, "34911000005")
    bag["has_balance"] = False
    empty = await _put(client, biz, other, _config("everyone"), 0, expect=409)
    assert empty["detail"]["code"] == "bag_empty"
    assert empty["detail"]["fix"] == "assign_balance"
    # «Solo mi equipo» no pide saldo: se prueba antes de pagar a todos.
    await _put(client, biz, other, _config("team_only", tests=[TEAM]), 0)
    page = await _page(client, biz, other)
    assert {"code": "bag_empty", "ok": False, "level": "block", "fix": "assign_balance"} not in (
        page["checks"]
    ), "las de «A todos» solo se enseñan cuando el canal está en «A todos» o sin configurar"


async def test_an_admin_only_template_cannot_open_to_everyone(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig).where(AgentConfig.agent_id == agent_id)
        )
        assert cfg is not None
        cfg.seed_template_ref = "cobranza_v1"
    await db_session.commit()
    channel_id = await _channel(db_session, biz, agent_id, "34911000006")
    page = await _page(client, biz, channel_id)
    assert page["admin_only_template"] is True, "la página dice por qué"
    refused = await _put(client, biz, channel_id, _config("everyone"), 0, expect=409)
    assert refused["detail"]["code"] == "audience_admin_only_template"


async def test_an_open_number_does_not_move_to_an_admin_only_agent(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    """32.5 al mover (34.2): un número en «A todos» no pasa a un agente de solo
    administradores; se queda donde estaba hasta que vuelva a «Solo mi equipo»."""
    open_agent = await _published(db_session, biz, "Recepción")
    cobranza = await _published(db_session, biz, "Cobranza")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig).where(AgentConfig.agent_id == cobranza)
        )
        assert cfg is not None
        cfg.seed_template_ref = "cobranza_v1"
        # Solo se mueve a un agente publicado o en pausa (34.2).
        await db_session.execute(
            sa.update(Agent).where(Agent.id == cobranza).values(lifecycle="published")
        )
    await db_session.commit()
    channel_id = await _channel(db_session, biz, open_agent, "34911000016")
    await _put(client, biz, channel_id, _config("everyone"), 0)
    url = f"/console/clients/{biz.ref}/channels/{channel_id}/move"
    refused = await client.post(url, json={"to_agent_id": str(cobranza)}, headers=biz.headers())
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "audience_admin_only_template"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        channel = await db_session.get(Channel, channel_id, populate_existing=True)
        assert channel is not None and channel.agent_id == open_agent
    page = await _page(client, biz, channel_id)
    await _put(client, biz, channel_id, _config("team_only", tests=[TEAM]), page["revision"])
    moved = await client.post(url, json={"to_agent_id": str(cobranza)}, headers=biz.headers())
    assert moved.status_code == 200, moved.text


# ── los números ────────────────────────────────────────────────────────────


async def test_numbers_are_international_and_never_repeated(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    channel_id = await _channel(db_session, biz, agent_id, "34911000007")
    bad = await _put(
        client, biz, channel_id, _config("team_only", tests=["600 100"]), 0, expect=422
    )
    assert bad["detail"] == {"code": "invalid_phone", "value": "600 100"}
    saved = await _put(
        client,
        biz,
        channel_id,
        _config("team_only", tests=["+34 600 100 100", "34600100100", "+34600100101"]),
        0,
    )
    assert saved["config"]["audience"]["test_numbers"] == ["+34600100100", "+34600100101"]


# ── aislamiento ────────────────────────────────────────────────────────────


async def test_one_channels_config_never_touches_another_of_the_same_agent(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    first = await _channel(db_session, biz, agent_id, "34911000008")
    second = await _channel(db_session, biz, agent_id, "34911000009")
    await _put(client, biz, first, _config("team_only", tests=[TEAM]), 0)
    await _put(client, biz, second, _config("everyone", exceptions=[TEAM]), 0)

    on_first = await _say(biz, first, TEAM, "hola por el primero")
    on_second = await _say(biz, second, TEAM, "hola por el segundo")
    assert len(on_first.calls) == 1 and on_second.calls == []
    assert (await _page(client, biz, first))["config"]["audience"]["exceptions"] == []

    # Otro cliente no ve el canal: un 404 que no dice si existe (garantía 9).
    stranger = await client.get(
        _url(biz, first).replace(biz.ref, "client-b-1"), headers=biz.headers()
    )
    assert stranger.status_code in (403, 404)


# ── guardar, historial y deshacer ─────────────────────────────────────────


async def test_saving_applies_from_the_next_message_with_history_and_undo(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    channel_id = await _channel(db_session, biz, agent_id, "34911000010")
    missing = await client.put(
        f"{_url(biz, channel_id)}/config", json=_config("everyone"), headers=biz.headers()
    )
    assert missing.status_code == 428

    first = await _put(client, biz, channel_id, _config("team_only", tests=[TEAM]), 0)
    assert first["revision"] == 1 and first["undo_until"] is not None
    assert (await _say(biz, channel_id, CUSTOMER, "antes")).calls == []

    opened = await _put(
        client, biz, channel_id, _config("everyone", wait="Enseguida te escribimos."), 1
    )
    assert opened["config"]["wait_message"] == "Enseguida te escribimos."
    assert len((await _say(biz, channel_id, CUSTOMER, "después")).calls) == 1, (
        "el cambio vale desde el siguiente mensaje"
    )

    stale = await _put(client, biz, channel_id, _config("everyone"), 1, expect=412)
    assert stale["detail"]["code"] == "revision_conflict"
    assert stale["detail"]["current"] == 2
    assert set(stale["detail"]["changes"]) == {"audience", "wait_message"}

    history = (await client.get(f"{_url(biz, channel_id)}/history", headers=biz.headers())).json()
    assert [h["after"]["audience"]["mode"] for h in history] == ["everyone", "team_only"]
    assert history[0]["before"]["audience"]["mode"] == "team_only"

    undone = await client.post(f"{_url(biz, channel_id)}/config/undo", headers=biz.headers())
    assert undone.status_code == 200, undone.text
    assert undone.json()["config"]["audience"]["mode"] == "team_only"
    assert undone.json()["config"]["wait_message"] is None
    assert (await _say(biz, channel_id, CUSTOMER, "tras deshacer")).calls == []

    # Pasados los 10 minutos no se puede deshacer.
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(ChannelConfigChange)
            .where(ChannelConfigChange.channel_id == channel_id)
            .values(undo_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    await db_session.commit()
    late = await client.post(f"{_url(biz, channel_id)}/config/undo", headers=biz.headers())
    assert late.status_code == 409 and late.json()["detail"]["code"] == "undo_window_closed"


# ── comprobaciones ─────────────────────────────────────────────────────────


async def test_the_tests_and_escalation_checks_warn_without_blocking(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    channel_id = await _channel(db_session, biz, agent_id, "34911000011")
    saved = await _put(client, biz, channel_id, _config("everyone"), 0)
    checks = {c["code"]: c for c in saved["checks"]}
    assert checks["tests_up_to_date"] == {
        "code": "tests_up_to_date",
        "ok": False,
        "level": "warn",
        "fix": "run_tests",
    }
    assert checks["escalation_recipient"]["ok"] is False
    assert checks["escalation_recipient"]["level"] == "warn"
    with_recipient = await _put(
        client,
        biz,
        channel_id,
        _config("everyone", recipients=[{"name": "Marta", "via": "inbox"}]),
        1,
    )
    assert {c["code"]: c["ok"] for c in with_recipient["checks"]}["escalation_recipient"] is True


# ── número recién conectado ────────────────────────────────────────────────


async def test_a_new_number_starts_in_test_mode_or_unconfigured(
    db_session: AsyncSession, biz: Biz
) -> None:
    agent_id = await _published(db_session, biz)
    with_phone = await _channel(db_session, biz, agent_id, "34911000012")
    without = await _channel(db_session, biz, agent_id, "34911000013")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        for channel_id, phone in ((with_phone, "+56 9 1234 5678"), (without, None)):
            channel = await db_session.get(Channel, channel_id)
            assert channel is not None
            await channel_config.start_in_test_mode(
                db_session, channel, connector_phone=phone, actor="link:test"
            )
    await db_session.commit()
    async with tenant_scoped_session(db_session, biz.tenant_id):
        a = await db_session.get(Channel, with_phone, populate_existing=True)
        b = await db_session.get(Channel, without, populate_existing=True)
        assert a is not None and b is not None
        assert a.audience_mode == "team_only"
        assert (await channel_config.read_config(db_session, a))["audience"]["test_numbers"] == [
            "+56912345678"
        ]
        assert b.audience_mode == "unset"


# ── permisos del equipo ────────────────────────────────────────────────────


async def test_team_permissions_stay_on_the_agent(
    client: Any, db_session: AsyncSession, biz: Biz, bag: dict[str, bool]
) -> None:
    agent_id = await _published(db_session, biz)
    team = {"admin_access": {"admins": [{"phone": TEAM, "role": "readonly"}]}}
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig).where(AgentConfig.agent_id == agent_id)
        )
        assert cfg is not None
        cfg.policies = team
    await db_session.commit()
    channel_id = await _channel(db_session, biz, agent_id, "34911000014")
    await _put(client, biz, channel_id, _config("team_only", tests=[TEAM]), 0)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig).where(AgentConfig.agent_id == agent_id),
            execution_options={"populate_existing": True},
        )
    assert cfg is not None and cfg.policies == team, "la página del canal no toca el agente"
