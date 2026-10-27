"""Spec 047, historia 2 — el borrador de un agente nunca pierde cambios (T038).

Requisito 3, criterio por criterio:

- **3.1** como mucho un borrador por agente, y todo cambio de comportamiento se
  escribe en él: los editores de hoy (ajustes, herramientas, prompt), la ruta
  nueva ``PATCH …/agents/{agent_id}/draft``, el admin y la API de partners;
- **3.2** el borrador parte de la versión activa, o de la última guardada si no
  hay activa, con todos sus campos;
- **3.3** dos escrituras sobre la misma revisión: la segunda recibe ``412`` con lo
  que cambió la primera, y no se pierde ninguna;
- **3.4** «v{n} de {agente}»: el número va por agente y el ``version`` de cada
  cliente no cambia;
- **3.5** descartar vuelve a la activa sin tocarla;
- **3.6** cada versión guarda su autor, su fecha, su nota y la versión de partida.

Las rutas viven bajo su cliente (garantía 9 y ``contracts/console-api.md`` §4):
un agente de otro cliente es el mismo 404 opaco que uno que no existe.
"""

from __future__ import annotations

import asyncio
import itertools
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, PartnerMembership
from nexus_api.services.agent_config_service import AgentConfigService
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio

ACTIVE_PROMPT = "Atiende a los clientes de la panadería."
CONSOLE = {
    "schema_version": 1,
    "identity": {"name": "Recepción", "persona": ""},
    "tone": {"style": "cercano", "guidance": ""},
    "ai_disclosure": {
        "enabled": True,
        "decided_by": "console:owner-a@example.com",
        "decided_at": "2026-10-01T09:00:00Z",
    },
}
ACTIVE_POLICIES: dict[str, Any] = {
    "console": CONSOLE,
    "llm": {"respond_model": "anthropic/claude-sonnet-4-6"},
    "admin_access": {"admin_only": False},
}


def _version(
    tenant_id: uuid.UUID,
    *,
    version: int,
    status: AgentConfigStatus,
    agent_id: uuid.UUID | None = None,
    prompt: str = ACTIVE_PROMPT,
    published: bool | None = None,
    **extra: Any,
) -> AgentConfig:
    was_published = status is AgentConfigStatus.ACTIVE if published is None else published
    fields: dict[str, Any] = {
        "tools": ["notification.send_text"],
        "channels": [{"type": "whatsapp"}],
        "policies": ACTIVE_POLICIES,
        "seed_template_ref": "panaderia_v1",
        "runtime_skills": [{"skill_id": "skill_resumen", "version": "latest"}],
        "runtime_memory_tool": True,
        "runtime_outcome_grader": True,
        "created_by": "console:owner-a@example.com",
    }
    fields.update(extra)
    return AgentConfig(
        tenant_id=tenant_id,
        agent_id=agent_id,
        version=version,
        status=status,
        system_prompt_rendered=prompt,
        promoted_at=datetime.now(UTC) if was_published else None,
        promoted_by="console:owner-a@example.com" if was_published else None,
        **fields,
    )


async def _with_active(db_session, tenant_id: uuid.UUID) -> tuple[uuid.UUID, AgentConfig]:
    """v1 activa del agente principal (lo crea la base al insertar sin agente)."""
    cfg = _version(tenant_id, version=1, status=AgentConfigStatus.ACTIVE)
    db_session.add(cfg)
    await db_session.commit()
    await db_session.refresh(cfg)
    assert cfg.agent_id is not None
    return cfg.agent_id, cfg


async def _second_agent(db_session, tenant_id: uuid.UUID, name: str = "Ventas") -> uuid.UUID:
    agent = Agent(id=uuid.uuid4(), tenant_id=tenant_id, name=name)
    db_session.add(agent)
    await db_session.commit()
    return agent.id


def _draft(w: dict[str, Any], agent_id: uuid.UUID) -> str:
    return f"/console/clients/{w['ref']}/agents/{agent_id}/draft"


async def _read(client, w: dict[str, Any], agent_id: uuid.UUID, headers=None) -> dict[str, Any]:
    r = await client.get(_draft(w, agent_id), headers=(headers or w["headers"])())
    assert r.status_code == 200, r.text
    assert r.headers["etag"] == f'"{r.json()["revision"]}"'
    return r.json()


async def _patch(client, w, agent_id, revision: int | None, body: dict[str, Any], headers=None):
    h = dict((headers or w["headers"])())
    if revision is not None:
        h["If-Match"] = f'"{revision}"'
    return await client.patch(_draft(w, agent_id), headers=h, json=body)


async def _staged(db_session, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> list[AgentConfig]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                sa.select(AgentConfig).where(
                    AgentConfig.tenant_id == tenant_id,
                    AgentConfig.agent_id == agent_id,
                    AgentConfig.status == AgentConfigStatus.STAGED,
                )
            )
        )
        .scalars()
        .all()
    )


def _settings(view: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """The settings the screen read, with ``changes`` on top (what a form sends)."""
    out = dict(view["settings"])
    out.update(changes)
    return out


# ── 3.1 · un solo borrador ────────────────────────────────────────────────


async def test_the_database_refuses_a_second_draft_of_one_agent(db_session, console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    agent_id, _ = await _with_active(db_session, tenant_id)
    db_session.add(
        _version(tenant_id, version=2, status=AgentConfigStatus.STAGED, agent_id=agent_id)
    )
    await db_session.commit()
    db_session.add(
        _version(tenant_id, version=3, status=AgentConfigStatus.STAGED, agent_id=agent_id)
    )
    with pytest.raises(IntegrityError, match="uq_agent_configs_one_draft"):
        await db_session.commit()
    await db_session.rollback()


async def test_every_writer_writes_into_the_one_draft(
    client, db_session, console_world, admin_headers
) -> None:
    """El admin, el servicio y la consola: el mismo borrador, el mismo número."""
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])

    first = await client.put(
        f"/admin/tenants/{a['tenant_id']}/agent-config",
        headers=admin_headers,
        json={"system_prompt_rendered": "Del admin.", "tools": [], "policies": ACTIVE_POLICIES},
    )
    assert first.status_code == 201, first.text
    again = await client.put(
        f"/admin/tenants/{a['tenant_id']}/agent-config",
        headers=admin_headers,
        json={
            "system_prompt_rendered": "Del admin, otra vez.",
            "tools": [],
            "policies": ACTIVE_POLICIES,
        },
    )
    assert again.status_code == 201, again.text
    assert again.json()["version"] == first.json()["version"]

    with tenant_context(a["tenant_id"]):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, a["tenant_id"]):
            cfg = await AgentConfigService(s).stage_new_version(
                actor="test",
                system_prompt_rendered="Del servicio.",
                channels=[],
                tools=[],
                policies=ACTIVE_POLICIES,
                agent_id=agent_id,
            )
            assert cfg.version == first.json()["version"]

    view = await _read(client, a, agent_id)
    r = await _patch(client, a, agent_id, view["revision"], {"system_prompt": "De la consola."})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == first.json()["version"]

    (draft,) = await _staged(db_session, a["tenant_id"], agent_id)
    assert draft.system_prompt_rendered == "De la consola."


@pytest.mark.parametrize("order", list(itertools.permutations(("settings", "tools", "prompt"))))
async def test_three_changes_in_any_order_end_in_the_same_draft(
    order: tuple[str, ...], client, db_session, console_world
) -> None:
    """Escenario 1 de la historia 2: ninguno queda en una versión ignorada."""
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])
    view = await _read(client, a, agent_id)
    assert view["exists"] is False and view["revision"] == 0
    bodies = {
        "settings": {"settings": _settings(view, tone={"style": "formal", "guidance": ""})},
        "tools": {"tools": ["notification.send_text", "escalate.escalate_to_human"]},
        "prompt": {"system_prompt": "Atiende con calma."},
    }
    revision = view["revision"]
    for kind in order:
        r = await _patch(client, a, agent_id, revision, bodies[kind])
        assert r.status_code == 200, (kind, r.text)
        assert r.json()["revision"] == revision + 1
        revision = r.json()["revision"]

    (draft,) = await _staged(db_session, a["tenant_id"], agent_id)
    assert draft.system_prompt_rendered == "Atiende con calma."
    assert draft.tools == ["notification.send_text", "escalate.escalate_to_human"]
    assert draft.policies["console"]["tone"]["style"] == "formal"
    # Lo que nadie tocó sigue siendo lo de la activa (3.2).
    assert draft.policies["llm"] == ACTIVE_POLICIES["llm"]
    view = await _read(client, a, agent_id)
    assert view["exists"] is True and view["revision"] == revision
    assert set(view["screens"]) == {"settings", "capabilities", "prompt"}


async def test_the_editors_of_today_write_into_the_same_draft(
    client, db_session, console_world
) -> None:
    """El fallo de hoy: guardar ajustes y después el prompt dejaba los ajustes
    en una versión que nadie iba a publicar."""
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])
    base = f"/console/clients/{a['ref']}"
    revision = (await _read(client, a, agent_id))["revision"]

    current = (await client.get(f"{base}/agent/settings", headers=a["headers"]())).json()
    settings = dict(current["settings"], objective="vender pan")
    s = await client.put(
        f"{base}/agent/settings", headers=a["headers"](), json={"settings": settings}
    )
    assert s.status_code == 200, s.text
    p = await client.post(
        f"{base}/agent/versions", headers=a["headers"](), json={"system_prompt": "Nuevo prompt."}
    )
    assert p.status_code == 201, p.text
    t = await client.put(
        f"{base}/tools", headers=a["headers"](), json={"tools": ["notification.send_text"]}
    )
    assert t.status_code == 200, t.text

    (draft,) = await _staged(db_session, a["tenant_id"], agent_id)
    assert p.json()["version"] == s.json()["version"] == draft.version
    assert draft.policies["console"]["objective"] == "vender pan"
    assert draft.system_prompt_rendered == "Nuevo prompt."
    # Cada escritura cuenta: otra pestaña con la revisión de antes ve el conflicto.
    assert (await _read(client, a, agent_id))["revision"] > revision


# ── 3.2 · de dónde parte ──────────────────────────────────────────────────


async def test_a_draft_starts_from_the_active_version_with_every_field(
    client, db_session, console_world
) -> None:
    a = console_world["a"]
    agent_id, active = await _with_active(db_session, a["tenant_id"])
    copied = (
        active.tools,
        active.channels,
        active.policies,
        active.seed_template_ref,
        active.runtime_skills,
    )
    active_id, active_number = active.id, active.agent_version_number
    r = await _patch(client, a, agent_id, 0, {"system_prompt": "Solo cambio el prompt."})
    assert r.status_code == 200, r.text
    assert r.json()["base_number"] == active_number

    (draft,) = await _staged(db_session, a["tenant_id"], agent_id)
    assert draft.base_version_id == active_id
    assert (
        draft.tools,
        draft.channels,
        draft.policies,
        draft.seed_template_ref,
        draft.runtime_skills,
    ) == copied
    assert draft.runtime_memory_tool is True and draft.runtime_outcome_grader is True


async def test_without_an_active_version_it_starts_from_the_last_saved_one(
    client, db_session, console_world
) -> None:
    """La última **guardada**: un borrador descartado no es una versión guardada."""
    a = console_world["a"]
    tenant_id = a["tenant_id"]
    saved = _version(tenant_id, version=1, status=AgentConfigStatus.ARCHIVED, published=True)
    db_session.add(saved)
    await db_session.commit()
    await db_session.refresh(saved)
    assert saved.agent_id is not None
    discarded = _version(
        tenant_id,
        version=2,
        status=AgentConfigStatus.ARCHIVED,
        agent_id=saved.agent_id,
        prompt="Lo que alguien descartó.",
        published=False,
    )
    db_session.add(discarded)
    await db_session.commit()
    saved_id, agent_id, skills = saved.id, saved.agent_id, saved.runtime_skills

    r = await _patch(client, a, agent_id, 0, {"tools": ["escalate.escalate_to_human"]})
    assert r.status_code == 200, r.text
    (draft,) = await _staged(db_session, tenant_id, agent_id)
    assert draft.system_prompt_rendered == ACTIVE_PROMPT
    assert draft.base_version_id == saved_id
    assert draft.runtime_skills == skills


# ── 3.3 · dos personas a la vez ───────────────────────────────────────────


async def test_a_stale_save_is_refused_with_the_first_ones_changes(
    client, db_session, console_world
) -> None:
    """Escenario 2: «Hay cambios más nuevos de Luis», qué cambió, y no se pierde nada."""
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])
    luis = await add_console_member(db_session, partner_id=a["partner_id"], role="admin")
    luis_email = await db_session.scalar(
        sa.select(PartnerMembership.email).where(PartnerMembership.id == luis["membership_id"])
    )

    lucia_view = await _read(client, a, agent_id)
    luis_view = await _read(client, a, agent_id, headers=luis["headers"])
    assert lucia_view["revision"] == luis_view["revision"]

    first = await _patch(
        client,
        a,
        agent_id,
        luis_view["revision"],
        {"settings": _settings(luis_view, tone={"style": "formal", "guidance": ""})},
        headers=luis["headers"],
    )
    assert first.status_code == 200, first.text

    second = await _patch(
        client, a, agent_id, lucia_view["revision"], {"system_prompt": "El prompt de Lucía."}
    )
    assert second.status_code == 412, second.text
    detail = second.json()["detail"]
    assert detail["code"] == "revision_conflict"
    assert detail["current"]["revision"] == first.json()["revision"]
    assert detail["current"]["settings"]["tone"]["style"] == "formal"
    assert detail["current"]["system_prompt"] == ACTIVE_PROMPT
    assert detail["changes"] == [
        {
            "revision": first.json()["revision"],
            "kind": "edit",
            "by": luis_email,
            "at": detail["changes"][0]["at"],
            "fields": ["settings.tone"],
        }
    ]

    # Nada de la segunda entró y nada de la primera se perdió.
    (draft,) = await _staged(db_session, a["tenant_id"], agent_id)
    assert draft.system_prompt_rendered == ACTIVE_PROMPT
    assert draft.policies["console"]["tone"]["style"] == "formal"

    # Lucía decide guardar lo suyo encima, ya con la revisión nueva: quedan los dos.
    retry = await _patch(
        client, a, agent_id, detail["current"]["revision"], {"system_prompt": "El prompt de Lucía."}
    )
    assert retry.status_code == 200, retry.text
    (draft,) = await _staged(db_session, a["tenant_id"], agent_id)
    assert draft.system_prompt_rendered == "El prompt de Lucía."
    assert draft.policies["console"]["tone"]["style"] == "formal"


async def test_two_simultaneous_saves_one_lands_and_the_other_sees_it(
    client, db_session, console_world
) -> None:
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])
    view = await _read(client, a, agent_id)
    first, second = await asyncio.gather(
        _patch(client, a, agent_id, view["revision"], {"system_prompt": "Uno."}),
        _patch(client, a, agent_id, view["revision"], {"tools": ["escalate.escalate_to_human"]}),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 412], (first.text, second.text)
    winner, loser = (first, second) if first.status_code == 200 else (second, first)
    changed = [c["fields"] for c in loser.json()["detail"]["changes"]]
    assert changed == [["system_prompt"]] or changed == [["tools"]]
    assert len(await _staged(db_session, a["tenant_id"], agent_id)) == 1
    assert winner.json()["revision"] == view["revision"] + 1


async def test_writes_name_the_revision_they_read(client, db_session, console_world) -> None:
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])
    missing = await _patch(client, a, agent_id, None, {"system_prompt": "Sin revisión."})
    assert missing.status_code == 428, missing.text
    assert missing.json()["detail"]["code"] == "revision_required"
    garbage = await client.patch(
        _draft(a, agent_id),
        headers={**a["headers"](), "If-Match": '"abc"'},
        json={"system_prompt": "x"},
    )
    assert garbage.status_code == 400
    assert garbage.json()["detail"]["code"] == "revision_invalid"
    weak = await client.patch(
        _draft(a, agent_id),
        headers={**a["headers"](), "If-Match": 'W/"0"'},
        json={"system_prompt": "Con etiqueta débil."},
    )
    assert weak.status_code == 200, weak.text
    assert weak.headers["etag"] == '"1"'


async def test_an_operator_save_keeps_what_the_partner_had_in_the_draft(
    client, db_session, console_world, admin_headers
) -> None:
    """El admin edita desde la activa; lo que el partner tenía en el borrador sigue."""
    a = console_world["a"]
    agent_id, active = await _with_active(db_session, a["tenant_id"])
    view = await _read(client, a, agent_id)
    r = await _patch(
        client, a, agent_id, view["revision"], {"settings": _settings(view, objective="vender pan")}
    )
    assert r.status_code == 200, r.text

    op = await client.put(
        f"/admin/tenants/{a['tenant_id']}/agent-config?agent_id={agent_id}",
        headers=admin_headers,
        json={
            "system_prompt_rendered": active.system_prompt_rendered,
            "channels": active.channels,
            "tools": ["notification.send_text", "escalate.escalate_to_human"],
            "policies": active.policies,
            "seed_template_ref": active.seed_template_ref,
        },
    )
    assert op.status_code == 201, op.text
    (draft,) = await _staged(db_session, a["tenant_id"], agent_id)
    assert draft.policies["console"]["objective"] == "vender pan"
    assert draft.tools == ["notification.send_text", "escalate.escalate_to_human"]

    stale = await _patch(client, a, agent_id, r.json()["revision"], {"system_prompt": "x"})
    assert stale.status_code == 412
    assert stale.json()["detail"]["changes"][-1]["by"] == "Auphere"
    assert stale.json()["detail"]["changes"][-1]["fields"] == ["tools"]


async def test_publishing_the_draft_is_news_for_a_tab_that_still_edits_it(
    client, db_session, console_world
) -> None:
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])
    r = await _patch(client, a, agent_id, 0, {"system_prompt": "Para publicar."})
    assert r.status_code == 200, r.text
    published = await client.post(
        f"/console/clients/{a['ref']}/agent/versions/{r.json()['version']}/publish?agent={agent_id}",
        headers=a["headers"](),
    )
    assert published.status_code == 200, published.text
    stale = await _patch(client, a, agent_id, r.json()["revision"], {"system_prompt": "Tarde."})
    assert stale.status_code == 412
    assert stale.json()["detail"]["changes"][-1]["kind"] == "publish"
    assert stale.json()["detail"]["current"]["exists"] is False


async def test_changing_the_admins_from_the_partner_api_keeps_the_draft(
    db_session, console_world
) -> None:
    """``set_admin_access`` publica al momento; el borrador pendiente no se pierde
    ni se publica, y lleva la lista nueva para que publicarlo no la deshaga."""
    tenant_id = console_world["a"]["tenant_id"]
    agent_id, active = await _with_active(db_session, tenant_id)
    db_session.add(
        _version(
            tenant_id,
            version=2,
            status=AgentConfigStatus.STAGED,
            agent_id=agent_id,
            prompt="El borrador del partner.",
        )
    )
    await db_session.commit()
    with tenant_context(tenant_id):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
            live = await AgentConfigService(s).set_admin_access(
                actor="partner:test", admin_phones=["+34600111222"]
            )
            assert live.status is AgentConfigStatus.ACTIVE
            assert live.system_prompt_rendered == active.system_prompt_rendered
            assert live.policies["admin_access"]["admin_phones"] == ["+34600111222"]
    (draft,) = await _staged(db_session, tenant_id, agent_id)
    assert draft.system_prompt_rendered == "El borrador del partner."
    assert draft.policies["admin_access"]["admin_phones"] == ["+34600111222"]


# ── 3.4 y 3.6 · el número por agente, el autor, la fecha y la nota ───────────


async def test_versions_count_per_agent_and_the_client_number_stays(
    client, db_session, console_world
) -> None:
    a = console_world["a"]
    reception, _ = await _with_active(db_session, a["tenant_id"])
    sales = await _second_agent(db_session, a["tenant_id"])

    s = await _patch(client, a, sales, 0, {"system_prompt": "Vende."})
    assert s.status_code == 200, s.text
    assert (s.json()["number"], s.json()["version"]) == (1, 2)
    assert s.json()["agent_name"] == "Ventas"
    r = await _patch(client, a, reception, 0, {"system_prompt": "Recibe."})
    assert r.status_code == 200, r.text
    assert (r.json()["number"], r.json()["version"]) == (2, 3)
    assert r.json()["active_number"] == 1

    history = await client.get(
        f"/console/clients/{a['ref']}/agents/{reception}/versions", headers=a["headers"]()
    )
    assert history.status_code == 200, history.text
    assert [(v["number"], v["version"], v["status"]) for v in history.json()] == [
        (2, 3, "staged"),
        (1, 1, "active"),
    ]
    other = await client.get(
        f"/console/clients/{a['ref']}/agents/{sales}/versions", headers=a["headers"]()
    )
    assert [(v["number"], v["version"]) for v in other.json()] == [(1, 2)]


async def test_each_version_keeps_its_author_date_note_and_base(
    client, db_session, console_world
) -> None:
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])
    r = await _patch(
        client, a, agent_id, 0, {"system_prompt": "Con nota.", "note": "Más corto y más claro"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["change_note"] == "Más corto y más claro"
    published = await client.post(
        f"/console/clients/{a['ref']}/agent/versions/{r.json()['version']}/publish?agent={agent_id}",
        headers=a["headers"](),
    )
    assert published.status_code == 200, published.text

    history = (
        await client.get(
            f"/console/clients/{a['ref']}/agents/{agent_id}/versions", headers=a["headers"]()
        )
    ).json()
    newest = history[0]
    assert newest["number"] == 2 and newest["status"] == "active"
    assert newest["author"] == "owner-a@example.com"
    assert newest["created_at"] and newest["published_at"]
    assert newest["published_by"] == "owner-a@example.com"
    assert newest["change_note"] == "Más corto y más claro"
    assert newest["base_number"] == 1
    assert history[1]["number"] == 1 and history[1]["base_number"] is None


async def test_the_note_has_a_limit(client, db_session, console_world) -> None:
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])
    r = await _patch(client, a, agent_id, 0, {"system_prompt": "x", "note": "n" * 501})
    assert r.status_code == 422
    empty = await _patch(client, a, agent_id, 0, {})
    assert empty.status_code == 422


# ── 3.5 · descartar ───────────────────────────────────────────────────────


async def test_discarding_goes_back_to_the_active_version_untouched(
    client, db_session, console_world
) -> None:
    a = console_world["a"]
    agent_id, active = await _with_active(db_session, a["tenant_id"])
    before = (active.updated_at, active.system_prompt_rendered, active.policies, active.tools)
    r = await _patch(client, a, agent_id, 0, {"system_prompt": "Lo voy a tirar."})
    assert r.status_code == 200, r.text
    draft_id = (await _staged(db_session, a["tenant_id"], agent_id))[0].id

    stale = await client.delete(_draft(a, agent_id), headers={**a["headers"](), "If-Match": '"0"'})
    assert stale.status_code == 412
    gone = await client.delete(
        _draft(a, agent_id), headers={**a["headers"](), "If-Match": f'"{r.json()["revision"]}"'}
    )
    assert gone.status_code == 200, gone.text
    body = gone.json()
    assert body["exists"] is False
    assert body["system_prompt"] == ACTIVE_PROMPT
    assert body["revision"] == r.json()["revision"] + 1

    assert not await _staged(db_session, a["tenant_id"], agent_id)
    # Borrar no existe (§IV): el borrador queda archivado, nunca publicado.
    kept = await db_session.get(AgentConfig, draft_id)
    assert kept is not None and kept.status is AgentConfigStatus.ARCHIVED
    assert kept.promoted_at is None
    await db_session.refresh(active)
    assert active.status is AgentConfigStatus.ACTIVE
    assert (
        active.updated_at,
        active.system_prompt_rendered,
        active.policies,
        active.tools,
    ) == before

    again = await client.delete(
        _draft(a, agent_id), headers={**a["headers"](), "If-Match": f'"{body["revision"]}"'}
    )
    assert again.status_code == 404
    assert again.json()["detail"]["code"] == "no_draft"

    # El siguiente cambio abre otro borrador, otra vez desde la activa.
    fresh = await _patch(client, a, agent_id, body["revision"], {"tools": []})
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["number"] == 3 and fresh.json()["base_number"] == 1
    assert fresh.json()["system_prompt"] == ACTIVE_PROMPT


# ── el agente dentro de su cliente ─────────────────────────────────────────


async def test_another_clients_agent_is_the_same_opaque_404(
    client, db_session, console_world
) -> None:
    a, b = console_world["a"], console_world["b"]
    foreign, _ = await _with_active(db_session, b["tenant_id"])
    mine, _ = await _with_active(db_session, a["tenant_id"])
    for method in ("GET", "PATCH", "DELETE"):
        h = {**a["headers"](), "If-Match": '"0"'}
        body = {"system_prompt": "x"} if method == "PATCH" else None
        theirs = await client.request(method, _draft(a, foreign), headers=h, json=body)
        h = {**a["headers"](), "If-Match": '"0"'}
        nobody = await client.request(method, _draft(a, uuid.uuid4()), headers=h, json=body)
        assert theirs.status_code == nobody.status_code == 404, (method, theirs.text)
        assert theirs.json() == nobody.json()
    history = await client.get(
        f"/console/clients/{a['ref']}/agents/{foreign}/versions", headers=a["headers"]()
    )
    assert history.status_code == 404
    # Nothing was written on B's agent.
    assert not await _staged(db_session, b["tenant_id"], foreign)

    # An archived agent of the client is not editable either.
    await db_session.execute(sa.update(Agent).where(Agent.id == mine).values(status="archived"))
    await db_session.commit()
    archived = await client.get(_draft(a, mine), headers=a["headers"]())
    assert archived.status_code == 404


async def test_an_analyst_reads_the_draft_but_cannot_write_it(
    client, db_session, console_world
) -> None:
    a = console_world["a"]
    agent_id, _ = await _with_active(db_session, a["tenant_id"])
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.id == a["membership_id"])
        .values(role="analyst")
    )
    await db_session.commit()
    view = await _read(client, a, agent_id)
    assert view["allowed"] == []
    r = await _patch(client, a, agent_id, view["revision"], {"system_prompt": "x"})
    assert r.status_code == 403
    d = await client.delete(_draft(a, agent_id), headers={**a["headers"](), "If-Match": '"0"'})
    assert d.status_code == 403
