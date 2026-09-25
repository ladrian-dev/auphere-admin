"""Spec 017 (R3.1, R3.2): a draft is visible from every tab of the record,
and what it changes can be read before publishing.

Two readings, no new state: ``draft_screens`` says WHICH screens of the
record differ between the draft and the active version, so the tabs can
carry a dot; ``draft-diff`` says WHAT differs, in stable keys — the console
turns them into sentences, never the API.

Reading a draft is a read: ``agents:read`` is enough. Deciding to publish
it is not, and that is a different permission on a different route.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AgentConfig, AgentConfigStatus, PartnerMembership

pytestmark = pytest.mark.asyncio

ACTIVE_POLICIES = {
    "console": {
        "schema_version": 1,
        "schedule": {"always": True},
        "languages": {"codes": ["es"]},
    }
}


def _version(
    tenant_id: uuid.UUID,
    *,
    version: int,
    status: AgentConfigStatus,
    prompt: str = "Atiende a los clientes de la panadería.",
    tools: list[str] | None = None,
    policies: dict | None = None,
    skills: list[dict[str, str]] | None = None,
) -> AgentConfig:
    return AgentConfig(
        tenant_id=tenant_id,
        version=version,
        status=status,
        system_prompt_rendered=prompt,
        tools=tools if tools is not None else ["consultar_pedido"],
        policies=policies if policies is not None else dict(ACTIVE_POLICIES),
        runtime_skills=skills,
        seed_template_ref="panaderia_v1",
    )


async def _seed_active(db_session, tenant_id: uuid.UUID) -> None:
    db_session.add(_version(tenant_id, version=1, status=AgentConfigStatus.ACTIVE))
    await db_session.commit()


async def test_the_bundle_says_which_screens_the_draft_touches(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed_active(db_session, a["tenant_id"])

    # No draft: nothing to publish, so no screen is marked.
    body = (await client.get(f"/console/clients/{a['ref']}/agent", headers=a["headers"]())).json()
    assert body["draft_screens"] == []

    # A draft that only changes the schedule marks «Ajustes» and nothing else.
    draft = _version(
        a["tenant_id"],
        version=2,
        status=AgentConfigStatus.STAGED,
        policies={
            "console": {
                "schema_version": 1,
                "schedule": {"always": False, "days": ["mon"]},
                "languages": {"codes": ["es"]},
            }
        },
    )
    db_session.add(draft)
    await db_session.commit()
    body = (await client.get(f"/console/clients/{a['ref']}/agent", headers=a["headers"]())).json()
    assert body["draft_screens"] == ["settings"]

    # Turning a capability on adds «Capacidades», in a stable order.
    draft.tools = ["consultar_pedido", "reservar_cita"]
    await db_session.commit()
    body = (await client.get(f"/console/clients/{a['ref']}/agent", headers=a["headers"]())).json()
    assert body["draft_screens"] == ["settings", "capabilities"]

    # And rewriting the prompt adds «Prompt».
    draft.system_prompt_rendered = "Otro texto."
    await db_session.commit()
    body = (await client.get(f"/console/clients/{a['ref']}/agent", headers=a["headers"]())).json()
    assert body["draft_screens"] == ["settings", "capabilities", "prompt"]


async def test_the_diff_answers_in_keys_not_in_sentences(client, console_world, db_session) -> None:
    a = console_world["a"]
    await _seed_active(db_session, a["tenant_id"])
    db_session.add(
        _version(
            a["tenant_id"],
            version=2,
            status=AgentConfigStatus.STAGED,
            prompt="Otro texto.",
            tools=["reservar_cita"],
            policies={
                "console": {
                    "schema_version": 1,
                    "schedule": {"always": False},
                    "languages": {"codes": ["es", "en"]},
                }
            },
            skills=[{"name": "resumen"}],
        )
    )
    await db_session.commit()

    r = await client.get(f"/console/clients/{a['ref']}/agent/draft-diff", headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["version"] == {"draft": 2, "active": 1}

    # Settings: one row per policy field that differs, with its own key.
    changed = {row["field"]: row for row in body["settings"]}
    assert set(changed) == {"schedule", "languages"}
    assert changed["languages"]["before"] == {"codes": ["es"]}
    assert changed["languages"]["after"] == {"codes": ["es", "en"]}

    # Capabilities: what was turned on, what was turned off, tools and skills alike.
    caps = {(row["name"], row["kind"]): row["change"] for row in body["capabilities"]}
    assert caps == {
        ("consultar_pedido", "tool"): "disabled",
        ("reservar_cita", "tool"): "enabled",
        ("resumen", "skill"): "enabled",
    }

    # The prompt is a before/after, not a word diff: the console renders it.
    assert body["prompt"] == {
        "before": "Atiende a los clientes de la panadería.",
        "after": "Otro texto.",
    }
    # Knowledge documents are not versioned with the agent, so there is
    # nothing to compare — the key exists so the console never branches on
    # its absence.
    assert body["knowledge"] == []


async def test_without_a_draft_there_is_nothing_to_diff(client, console_world, db_session) -> None:
    a = console_world["a"]
    await _seed_active(db_session, a["tenant_id"])
    r = await client.get(f"/console/clients/{a['ref']}/agent/draft-diff", headers=a["headers"]())
    assert r.status_code == 404
    assert r.json()["detail"] == "no_draft"


async def test_a_first_draft_compares_against_nothing(client, console_world, db_session) -> None:
    """A client with no active version yet: the whole draft is «after»."""
    a = console_world["a"]
    db_session.add(_version(a["tenant_id"], version=1, status=AgentConfigStatus.STAGED))
    await db_session.commit()
    body = (
        await client.get(f"/console/clients/{a['ref']}/agent/draft-diff", headers=a["headers"]())
    ).json()
    assert body["version"] == {"draft": 1, "active": None}
    assert body["prompt"]["before"] == ""
    assert [row["change"] for row in body["capabilities"]] == ["enabled"]


async def test_reading_a_draft_only_needs_agents_read(client, console_world, db_session) -> None:
    a = console_world["a"]
    await _seed_active(db_session, a["tenant_id"])
    db_session.add(
        _version(a["tenant_id"], version=2, status=AgentConfigStatus.STAGED, prompt="Otro.")
    )
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.id == a["membership_id"])
        .values(role="analyst")
    )
    await db_session.commit()

    r = await client.get(f"/console/clients/{a['ref']}/agent/draft-diff", headers=a["headers"]())
    assert r.status_code == 200, r.text
    assert r.json()["version"]["draft"] == 2


async def test_another_partner_never_sees_this_draft(client, console_world, db_session) -> None:
    a, b = console_world["a"], console_world["b"]
    await _seed_active(db_session, a["tenant_id"])
    db_session.add(
        _version(a["tenant_id"], version=2, status=AgentConfigStatus.STAGED, prompt="Otro.")
    )
    await db_session.commit()
    r = await client.get(f"/console/clients/{a['ref']}/agent/draft-diff", headers=b["headers"]())
    assert r.status_code == 404


# ── publicar desde la barra (R3.3) ─────────────────────────────────────


async def _publishable(tenant_id: uuid.UUID) -> AgentConfig:
    """Una versión que la consola sí deja publicar: con decisión explícita
    de divulgación de IA (CP-31) y con prompt."""
    cfg = _version(tenant_id, version=2, status=AgentConfigStatus.STAGED, prompt="Otro texto.")
    cfg.policies = {
        "console": {
            "schema_version": 1,
            "schedule": {"always": True},
            "languages": {"codes": ["es"]},
            "ai_disclosure": {"enabled": True},
        }
    }
    return cfg


async def test_publishing_records_where_the_partner_pressed(
    client, console_world, db_session
) -> None:
    """R3.3: publicar desde la barra del borrador y desde la pestaña Agente
    son el mismo acto, pero la auditoría distingue de dónde salió — sin eso
    no se puede saber si la barra sirve para algo."""
    from nexus_api.db.models import AuditLog

    a = console_world["a"]
    await _seed_active(db_session, a["tenant_id"])
    db_session.add(await _publishable(a["tenant_id"]))
    await db_session.commit()

    r = await client.post(
        f"/console/clients/{a['ref']}/agent/versions/2/publish",
        headers=a["headers"](),
        json={"from": "draft_bar"},
    )
    assert r.status_code == 200, r.text

    rows = (
        (
            await db_session.execute(
                sa.select(AuditLog)
                .where(AuditLog.action == "agent_config.promote")
                .order_by(AuditLog.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    assert rows, "promoting has to leave an audit row"
    assert rows[0].after_json["version"] == 2
    assert rows[0].after_json["from"] == "draft_bar"


async def test_publishing_without_saying_where_defaults_to_the_agent_tab(
    client, console_world, db_session
) -> None:
    from nexus_api.db.models import AuditLog

    a = console_world["a"]
    await _seed_active(db_session, a["tenant_id"])
    db_session.add(await _publishable(a["tenant_id"]))
    await db_session.commit()

    r = await client.post(
        f"/console/clients/{a['ref']}/agent/versions/2/publish", headers=a["headers"]()
    )
    assert r.status_code == 200, r.text
    rows = (
        (
            await db_session.execute(
                sa.select(AuditLog)
                .where(AuditLog.action == "agent_config.promote")
                .order_by(AuditLog.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    assert rows[0].after_json["from"] == "agent_tab"


async def test_an_unknown_origin_is_refused(client, console_world, db_session) -> None:
    a = console_world["a"]
    await _seed_active(db_session, a["tenant_id"])
    db_session.add(await _publishable(a["tenant_id"]))
    await db_session.commit()
    r = await client.post(
        f"/console/clients/{a['ref']}/agent/versions/2/publish",
        headers=a["headers"](),
        json={"from": "wherever"},
    )
    assert r.status_code == 422
