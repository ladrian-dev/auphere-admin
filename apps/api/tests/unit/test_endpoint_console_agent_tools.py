"""Functional tests of lane ``agent-tools`` (CP-11 · CP-13 · CP-14 · CP-15 ·
CP-31). Isolation is pinned by ``tests/isolation/test_console_scope.py``;
this file pins BEHAVIOUR and the measurable acceptance criteria:

- CP-11: settings saved on a draft, published, and the active version
  carries ``policies.console`` (schedule + languages + escalation).
- CP-31: publish without an explicit disclosure decision → 409; console
  drafts carry the default → 200.
- CP-13: enable a tool → after publish it is in ``tools`` of the active
  version; connectors never expose secrets; TikTok is excluded.
- CP-14: the catalogue lists exactly the skills in the source tree;
  enabling one lands ``runtime_skills`` with its ``skill_id``.
- CP-15: TXT → ``indexed`` with ``chunk_count>0``; bad URL → ``failed``
  with ``error_code``; the text never leaves through the API.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from nexus_api.api.admin import connectors as admin_connectors
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    KnowledgeDocument,
    TenantConnector,
)
from nexus_api.services.connectors import catalog as connector_catalog
from nexus_api.services.connectors.composio_client import ComposioTool, FakeComposioClient
from nexus_api.services.connectors.seed_loader import load_all_seeds
from nexus_api.services.connectors.seed_runner import apply_seeds
from nexus_api.services.skills_catalog import SKILLS_DIR

pytestmark = pytest.mark.asyncio


# ── helpers ────────────────────────────────────────────────────────────


async def _stage_and_publish(client, w, *, prompt: str = "You are the assistant.") -> int:
    r = await client.post(
        f"/console/clients/{w['ref']}/agent/versions",
        headers=w["headers"](),
        json={"system_prompt": prompt},
    )
    assert r.status_code == 201, r.text
    v = r.json()["version"]
    p = await client.post(
        f"/console/clients/{w['ref']}/agent/versions/{v}/publish", headers=w["headers"]()
    )
    assert p.status_code == 200, p.text
    return int(v)


async def _active(db_session, tenant_id: uuid.UUID) -> AgentConfig:
    db_session.expire_all()
    row = await db_session.scalar(
        sa.select(AgentConfig).where(
            AgentConfig.tenant_id == tenant_id, AgentConfig.status == AgentConfigStatus.ACTIVE
        )
    )
    assert row is not None
    return row


SETTINGS = {
    "identity": {"name": "Sofía", "persona": "recepcionista de la clínica"},
    "tone": {"style": "formal", "guidance": "sin emojis"},
    "objective": "agendar citas",
    "schedule": {
        "timezone": "Europe/Madrid",
        "weekly": [
            {"day": "mon", "open": "09:00", "close": "18:00"},
            {"day": "sat", "open": "10:00", "close": "14:00"},
        ],
        "closed_message": "Estamos cerrados, te respondemos mañana.",
    },
    "languages": {"primary": "es", "allowed": ["en", "pt"]},
    "escalation": {
        "enabled": True,
        "triggers": ["user_asks_human", "after_n_turns"],
        "after_n_turns": 6,
        "handoff_message": "Te paso con una persona.",
    },
    "ai_disclosure": {"enabled": True, "disclosure_message": "Soy un asistente virtual."},
}


# ── CP-11 · settings ───────────────────────────────────────────────────


async def test_settings_roundtrip_draft_publish_active(client, console_world, db_session) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/agent"

    empty = await client.get(f"{base}/settings", headers=h())
    assert empty.status_code == 200
    assert empty.json()["version"] is None and empty.json()["settings"]["ai_disclosure"]["enabled"]

    v1 = await _stage_and_publish(client, a)

    saved = await client.put(f"{base}/settings", headers=h(), json={"settings": SETTINGS})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["draft_created"] is True and body["version"] == v1 + 1
    assert body["version_status"] == "staged" and body["active_version"] == v1
    assert body["settings"]["schedule"]["timezone"] == "Europe/Madrid"
    assert body["settings"]["languages"]["allowed"] == ["es", "en", "pt"]
    assert body["settings"]["ai_disclosure"]["decided_by"] == "console:owner-a@example.com"

    # Second save reuses the draft.
    again = await client.put(f"{base}/settings", headers=h(), json={"settings": SETTINGS})
    assert again.status_code == 200 and again.json()["draft_created"] is False
    assert again.json()["version"] == v1 + 1

    # GET returns the draft (what a PUT edits).
    got = await client.get(f"{base}/settings", headers=h())
    assert got.json()["version"] == v1 + 1 and got.json()["has_draft"] is True

    # Draft copied prompt from the active version (not empty).
    bundle = (await client.get(base, headers=h())).json()
    draft = next(v for v in bundle["versions"] if v["version"] == v1 + 1)
    assert draft["system_prompt"] == "You are the assistant."

    pub = await client.post(f"{base}/versions/{v1 + 1}/publish", headers=h())
    assert pub.status_code == 200, pub.text
    active = await _active(db_session, a["tenant_id"])
    console = active.policies["console"]
    assert console["schedule"]["weekly"][0] == {"day": "mon", "open": "09:00", "close": "18:00"}
    assert console["languages"]["primary"] == "es"
    assert console["escalation"]["after_n_turns"] == 6
    assert (await client.get(f"{base}/settings", headers=h())).json()["version"] == v1 + 1


async def test_settings_validation_is_strict(client, console_world) -> None:
    a = console_world["a"]
    base = f"/console/clients/{a['ref']}/agent/settings"
    bad_tz = await client.put(
        base, headers=a["headers"](), json={"settings": {"schedule": {"timezone": "Mars/Olympus"}}}
    )
    assert bad_tz.status_code == 422
    bad_hours = await client.put(
        base,
        headers=a["headers"](),
        json={
            "settings": {
                "schedule": {"weekly": [{"day": "mon", "open": "18:00", "close": "09:00"}]}
            }
        },
    )
    assert bad_hours.status_code == 422
    unknown_key = await client.put(
        base, headers=a["headers"](), json={"settings": {"admin_access": {"admin_only": False}}}
    )
    assert unknown_key.status_code == 422
    viewer = await client.get(base, headers=a["headers"]())
    assert viewer.status_code == 200


# ── CP-31 · AI Act disclosure ──────────────────────────────────────────


async def test_publish_requires_disclosure_decision(client, console_world, db_session) -> None:
    from nexus_api.core.tenant_context import _current_tenant, apply_tenant_to_session
    from nexus_api.services.agent_config_service import AgentConfigService

    a = console_world["a"]
    h = a["headers"]
    # A version staged OUTSIDE the console (backoffice/seed) — no decision.
    token = _current_tenant.set(a["tenant_id"])
    try:
        async with db_session.begin():
            await apply_tenant_to_session(db_session, a["tenant_id"])
            cfg = await AgentConfigService(db_session).stage_new_version(
                actor="admin:test",
                system_prompt_rendered="seeded prompt",
                channels=[],
                tools=[],
                policies={"llm": {"respond_model": "x"}},
            )
            version = cfg.version
    finally:
        _current_tenant.reset(token)

    r = await client.post(
        f"/console/clients/{a['ref']}/agent/versions/{version}/publish", headers=h()
    )
    assert r.status_code == 409, r.text
    assert "AI-disclosure" in r.json()["detail"] and "settings" in r.json()["detail"]
    row = await db_session.scalar(sa.select(AgentConfig).where(AgentConfig.id == cfg.id))
    assert row is not None and row.status is AgentConfigStatus.STAGED

    # Staged from the console → default decision (enabled=true) → publishes.
    v = await client.post(
        f"/console/clients/{a['ref']}/agent/versions", headers=h(), json={"system_prompt": "p"}
    )
    policies = await db_session.scalar(
        sa.select(AgentConfig.policies).where(
            AgentConfig.tenant_id == a["tenant_id"], AgentConfig.version == v.json()["version"]
        )
    )
    assert policies["console"]["ai_disclosure"]["enabled"] is True
    assert policies["console"]["ai_disclosure"]["decided_by"] == "console:owner-a@example.com"
    # Policies come from the ACTIVE version (none yet) — the seeded staged
    # one is not copied; the console default is the only console key.
    assert set(policies) == {"console"}
    ok = await client.post(
        f"/console/clients/{a['ref']}/agent/versions/{v.json()['version']}/publish", headers=h()
    )
    assert ok.status_code == 200, ok.text

    # Explicitly turning it off is a decision too — publishable, attributed.
    off = dict(SETTINGS, ai_disclosure={"enabled": False})
    s = await client.put(
        f"/console/clients/{a['ref']}/agent/settings", headers=h(), json={"settings": off}
    )
    assert s.status_code == 200 and s.json()["settings"]["ai_disclosure"]["enabled"] is False
    p = await client.post(
        f"/console/clients/{a['ref']}/agent/versions/{s.json()['version']}/publish", headers=h()
    )
    assert p.status_code == 200


# ── CP-13 · tools + connectors ─────────────────────────────────────────


@pytest.fixture
async def fake_composio():
    c = FakeComposioClient()
    c.register_tools(
        "googlecalendar",
        [
            ComposioTool(
                slug="GOOGLECALENDAR_LIST_EVENTS",
                description="List",
                input_schema={"type": "object"},
            )
        ],
    )
    c.register_auth_config(
        "googlecalendar",
        "ac_test_gc",
        display_name="Google Calendar",
        vendor="Google",
        category="Calendar",
    )
    admin_connectors.set_composio_client_for_tests(c)
    connector_catalog._TOOLKIT_METADATA_CACHE.clear()
    yield c
    admin_connectors.set_composio_client_for_tests(None)
    connector_catalog._TOOLKIT_METADATA_CACHE.clear()


@pytest.fixture
async def seeded_connectors(db_session) -> None:
    await apply_seeds(db_session, load_all_seeds())
    await db_session.commit()


async def test_tools_enable_and_publish(
    client, console_world, db_session, seeded_connectors, fake_composio
) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}"
    await _stage_and_publish(client, a)

    cat = await client.get(f"{base}/tools", headers=h())
    assert cat.status_code == 200, cat.text
    names = {t["name"]: t for t in cat.json()["tools"]}
    assert (
        "booking.check_availability" in names and not names["booking.check_availability"]["enabled"]
    )
    assert "agendapro.get_today_appointments" not in names  # internal
    assert all(t["connector_slug"] != "tiktok_bm" for t in names.values())
    bound = [t for t in names.values() if t["connector_required"]]
    for t in bound:  # not installed → never usable, even if whitelisted
        assert t["connector_status"] is None and not t["usable"]

    saved = await client.put(
        f"{base}/tools",
        headers=h(),
        json={"tools": ["booking.check_availability", "escalate.escalate_to_human"]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft_created"] is True
    by = {t["name"]: t for t in saved.json()["tools"]}
    assert (
        by["booking.check_availability"]["enabled"] and by["booking.check_availability"]["usable"]
    )
    assert not by["booking.check_availability"]["enabled_in_active"]

    unknown = await client.put(f"{base}/tools", headers=h(), json={"tools": ["nope.tool"]})
    assert unknown.status_code == 422
    internal = await client.put(
        f"{base}/tools", headers=h(), json={"tools": ["agendapro.scrape_no_shows"]}
    )
    assert internal.status_code == 422

    v = saved.json()["version"]
    pub = await client.post(f"{base}/agent/versions/{v}/publish", headers=h())
    assert pub.status_code == 200, pub.text
    active = await _active(db_session, a["tenant_id"])
    assert sorted(active.tools) == ["booking.check_availability", "escalate.escalate_to_human"]
    bundle = (await client.get(f"{base}/agent", headers=h())).json()
    assert bundle["active_version"] == v

    # Gating override: immediate, not versioned.
    mode = await client.put(
        f"{base}/tools/booking.check_availability/mode",
        headers=h(),
        json={"mode": "needs_approval"},
    )
    assert mode.status_code == 200 and mode.json()["set_by"] == "console:owner-a@example.com"
    t = next(
        x
        for x in (await client.get(f"{base}/tools", headers=h())).json()["tools"]
        if x["name"] == "booking.check_availability"
    )
    assert t["effective_mode"] == "needs_approval" and t["override_mode"] == "needs_approval"
    gone = await client.delete(f"{base}/tools/booking.check_availability/mode", headers=h())
    assert gone.status_code == 204
    assert (
        await client.delete(f"{base}/tools/booking.check_availability/mode", headers=h())
    ).status_code == 404


async def test_connectors_never_leak_secrets_and_consent_once(
    client, console_world, db_session, seeded_connectors, fake_composio
) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/connectors"

    lst = await client.get(base, headers=h())
    assert lst.status_code == 200, lst.text
    slugs = {c["slug"]: c for c in lst.json()}
    assert "tiktok_bm" not in slugs and "whatsapp_meta" not in slugs  # channel_only
    assert "googlecalendar" in slugs and slugs["googlecalendar"]["installed"] is False
    assert "woocommerce" in slugs and slugs["woocommerce"]["auth_kind"] == "api_key"
    assert [f["field"] for f in slugs["woocommerce"]["credentials_form"]][:1] == ["store_url"]
    for c in lst.json():
        assert "credentials_ref" not in c and "consent_token" not in c

    consent = await client.post(f"{base}/googlecalendar/consent", headers=h())
    assert consent.status_code == 201, consent.text
    assert "consent_token=" in consent.json()["signed_consent_url"]
    tc = await db_session.scalar(
        sa.select(TenantConnector).where(TenantConnector.tenant_id == a["tenant_id"])
    )
    assert tc is not None and tc.status == "pending"

    lst2 = {c["slug"]: c for c in (await client.get(base, headers=h())).json()}
    assert lst2["googlecalendar"]["installed"] and lst2["googlecalendar"]["status"] == "pending"
    assert "signed_consent_url" not in lst2["googlecalendar"]

    # API-key bootstrap: secrets in, never out.
    key = await client.post(
        f"{base}/woocommerce/api-key",
        headers=h(),
        json={
            "secrets": {"consumer_key": "ck_1", "consumer_secret": "cs_1"},
            "endpoint_meta": {"store_url": "https://s.example"},
        },
    )
    assert key.status_code == 201, key.text
    assert key.json()["status"] == "connected" and "ck_1" not in key.text and "cs_1" not in key.text

    paused = await client.post(f"{base}/woocommerce/pause", headers=h())
    assert paused.status_code == 200 and paused.json()["status"] == "paused"
    resumed = await client.post(f"{base}/woocommerce/resume", headers=h())
    assert resumed.status_code == 200 and resumed.json()["status"] == "connected"
    off = await client.post(f"{base}/woocommerce/disconnect", headers=h())
    assert off.status_code == 200 and off.json()["status"] == "disconnected"

    tik = await client.post(f"{base}/tiktok_bm/consent", headers=h())
    assert tik.status_code == 404
    # Partner B sees nothing of A.
    b = console_world["b"]
    lb = {
        c["slug"]: c
        for c in (
            await client.get(f"/console/clients/{b['ref']}/connectors", headers=b["headers"]())
        ).json()
    }
    assert lb["googlecalendar"]["installed"] is False


# ── CP-14 · skills ─────────────────────────────────────────────────────


def _skill_dirs() -> list[Path]:
    return [p for p in sorted(SKILLS_DIR.iterdir()) if p.is_dir() and (p / "SKILL.md").is_file()]


async def test_skills_catalogue_matches_source_tree_and_enables(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/skills"
    expected = _skill_dirs()
    assert len(expected) == 10, [p.name for p in expected]

    r = await client.get(base, headers=h())
    assert r.status_code == 200, r.text
    skills = r.json()["skills"]
    assert len(skills) == 10
    assert all(s["description"] for s in skills)
    assert not any(s["enabled"] for s in skills)
    activatable = [s for s in skills if s["activatable"]]
    assert activatable, "manifest has no uploaded skill"
    pick = activatable[0]["name"]

    await _stage_and_publish(client, a)
    saved = await client.put(base, headers=h(), json={"skills": [pick]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft_created"] is True
    on = [s for s in saved.json()["skills"] if s["enabled"]]
    assert [s["name"] for s in on] == [pick] and not on[0]["enabled_in_active"]

    draft_version = saved.json()["version"]
    draft = await db_session.scalar(
        sa.select(AgentConfig).where(
            AgentConfig.tenant_id == a["tenant_id"], AgentConfig.version == draft_version
        )
    )
    assert draft is not None and draft.runtime_skills is not None
    from nexus_api.services.skills_catalog import load_manifest

    assert draft.runtime_skills[0]["skill_id"] == load_manifest()[pick]["skill_id"]

    unknown = await client.put(base, headers=h(), json={"skills": ["no-such-skill"]})
    assert unknown.status_code == 422

    pub = await client.post(
        f"/console/clients/{a['ref']}/agent/versions/{draft_version}/publish", headers=h()
    )
    assert pub.status_code == 200, pub.text
    active = await _active(db_session, a["tenant_id"])
    assert (
        active.runtime_skills
        and active.runtime_skills[0]["skill_id"] == draft.runtime_skills[0]["skill_id"]
    )
    after = (await client.get(base, headers=h())).json()
    assert next(s for s in after["skills"] if s["name"] == pick)["enabled_in_active"] is True

    # Turning all off keeps the draft flow.
    none = await client.put(base, headers=h(), json={"skills": []})
    assert none.status_code == 200 and not any(s["enabled"] for s in none.json()["skills"])


# ── CP-15 · knowledge ──────────────────────────────────────────────────


async def test_knowledge_upload_url_delete_reindex(
    client, console_world, db_session, monkeypatch
) -> None:
    from nexus_api.db.models import KnowledgeErrorCode
    from nexus_api.services import knowledge_indexer

    a = console_world["a"]
    h = a["headers"]
    base = f"/console/clients/{a['ref']}/knowledge"

    empty = await client.get(base, headers=h())
    assert empty.status_code == 200 and empty.json() == {
        "items": [],
        "total": 0,
        "indexed_chars": 0,
        "prompt_char_cap": 20000,
    }

    txt = ("Horario de la clínica: lunes a viernes de 9 a 18.\n" * 40).encode()
    up = await client.post(
        base,
        headers=h(),
        files={"file": ("horario.txt", txt, "text/plain")},
        data={"title": "Horario"},
    )
    assert up.status_code == 201, up.text
    doc = up.json()
    assert doc["status"] == "indexed" and doc["chunk_count"] > 0 and doc["kind"] == "file"
    assert doc["title"] == "Horario" and doc["mime"] == "text/plain" and doc["error_code"] is None
    assert "content" not in doc and "text" not in doc and "content_text" not in doc

    row = await db_session.scalar(
        sa.select(KnowledgeDocument).where(KnowledgeDocument.id == uuid.UUID(doc["id"]))
    )
    assert row is not None and row.content_text and "Horario de la clínica" in row.content_text

    bad_type = await client.post(
        base, headers=h(), files={"file": ("x.bin", b"\x00\x01", "application/octet-stream")}
    )
    assert bad_type.status_code == 201 and bad_type.json()["status"] == "failed"
    assert bad_type.json()["error_code"] == "unsupported_type"

    empty_file = await client.post(
        base, headers=h(), files={"file": ("e.txt", b"   ", "text/plain")}
    )
    assert empty_file.json()["status"] == "failed" and empty_file.json()["error_code"] == "empty"

    # URL: unreachable host → failed with fetch_failed (201, listed, re-indexable).
    async def _boom(url, **kw):
        raise knowledge_indexer.IndexingError(KnowledgeErrorCode.FETCH_FAILED)

    monkeypatch.setattr(knowledge_indexer, "fetch_url", _boom)
    url = await client.post(
        f"{base}/url", headers=h(), json={"url": "https://invalid.example.invalid/x"}
    )
    assert url.status_code == 201, url.text
    assert url.json()["status"] == "failed" and url.json()["error_code"] == "fetch_failed"
    assert url.json()["kind"] == "url" and url.json()["source_url"].startswith("https://")

    # URL: now the fetch works → reindex flips it to indexed and picks the page title.
    async def _ok(url, **kw):
        ex = knowledge_indexer.extract_text(
            b"<html><head><title>Precios</title></head><body><p>Corte 20 EUR</p></body></html>",
            mime="text/html",
        )
        return knowledge_indexer.FetchedUrl(extracted=ex, title="Precios")

    monkeypatch.setattr(knowledge_indexer, "fetch_url", _ok)
    re = await client.post(f"{base}/{url.json()['id']}/reindex", headers=h())
    assert (
        re.status_code == 200 and re.json()["status"] == "indexed" and re.json()["chunk_count"] == 1
    )

    lst = await client.get(base, headers=h())
    assert lst.json()["total"] == 4 and lst.json()["indexed_chars"] > 0
    assert not any("content_text" in i for i in lst.json()["items"])
    bad_scheme = await client.post(f"{base}/url", headers=h(), json={"url": "ftp://x/y"})
    assert bad_scheme.status_code == 422

    # Partner B: cannot see or delete A's document (RLS + opaque 404).
    b = console_world["b"]
    assert (
        await client.get(f"/console/clients/{b['ref']}/knowledge", headers=b["headers"]())
    ).json()["total"] == 0
    other = await client.delete(
        f"/console/clients/{b['ref']}/knowledge/{doc['id']}", headers=b["headers"]()
    )
    assert other.status_code == 404

    gone = await client.delete(f"{base}/{doc['id']}", headers=h())
    assert gone.status_code == 204
    assert (await client.delete(f"{base}/{doc['id']}", headers=h())).status_code == 404
    assert (await client.get(base, headers=h())).json()["total"] == 3

    # Permission family: an analyst reads but cannot write.
    from tests.conftest import add_console_member

    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    assert (await client.get(base, headers=analyst["headers"]())).status_code == 200
    denied = await client.post(
        f"{base}/url", headers=analyst["headers"](), json={"url": "https://e.example/"}
    )
    assert denied.status_code == 403


async def test_knowledge_upload_too_large_is_413(client, console_world) -> None:
    from nexus_api.services import knowledge_indexer

    a = console_world["a"]
    big = b"a" * (knowledge_indexer.MAX_UPLOAD_BYTES + 1)
    r = await client.post(
        f"/console/clients/{a['ref']}/knowledge",
        headers=a["headers"](),
        files={"file": ("big.txt", big, "text/plain")},
    )
    assert r.status_code == 413
