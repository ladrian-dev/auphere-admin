"""Fase 3 RAG: two tables, FORCE playbook RLS, channel vs Companion inject."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    KnowledgeDocument,
    KnowledgeDocumentKind,
    KnowledgeDocumentStatus,
    PartnerKnowledgeDocument,
)
from nexus_api.services.knowledge_retrieve import load_companion_knowledge_blocks
from tests.conftest import add_console_member

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

PLAYBOOK_MARK = "PLAYBOOK_SECRET_TOKEN_A1"
CLIENT_MARK = "CLIENT_KB_SECRET_TOKEN_B2"


async def _seed_playbook(partner_id: uuid.UUID, title: str, text: str) -> uuid.UUID:
    doc_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        session.add(
            PartnerKnowledgeDocument(
                id=doc_id,
                partner_id=partner_id,
                kind=KnowledgeDocumentKind.URL.value,
                title=title,
                source_url="https://example.com/playbook",
                mime="text/plain",
                size_bytes=len(text),
                status=KnowledgeDocumentStatus.INDEXED.value,
                content_text=text,
                chunk_count=1,
                indexed_at=datetime.now(UTC),
            )
        )
    return doc_id


async def _seed_client_kb(tenant_id: uuid.UUID, title: str, text: str) -> uuid.UUID:
    doc_id = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        session.add(
            KnowledgeDocument(
                id=doc_id,
                tenant_id=tenant_id,
                kind=KnowledgeDocumentKind.FILE.value,
                title=title,
                mime="text/plain",
                size_bytes=len(text),
                status=KnowledgeDocumentStatus.INDEXED.value,
                content_text=text,
                chunk_count=1,
                indexed_at=datetime.now(UTC),
            )
        )
    return doc_id


async def test_partner_a_cannot_list_bs_playbook(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    await _seed_playbook(b["partner_id"], "Playbook B", PLAYBOOK_MARK)
    listed = await client.get("/console/knowledge", headers=a["headers"]())
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert "content_text" not in body
    assert not any("content_text" in item for item in body["items"])

    b_list = await client.get("/console/knowledge", headers=b["headers"]())
    assert b_list.status_code == 200
    assert b_list.json()["total"] == 1
    assert b_list.json()["items"][0]["title"] == "Playbook B"
    assert "content_text" not in b_list.json()["items"][0]


async def test_foreign_client_knowledge_is_opaque_404(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    foreign = await client.get(f"/console/clients/{b['ref']}/knowledge", headers=a["headers"]())
    missing = await client.get("/console/clients/does-not-exist/knowledge", headers=a["headers"]())
    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Unknown client reference"}


async def test_partner_id_in_playbook_body_is_422(client, console_world) -> None:
    a = console_world["a"]
    resp = await client.post(
        "/console/knowledge/url",
        headers=a["headers"](),
        json={"url": "https://example.com/x", "partner_id": str(a["partner_id"])},
    )
    assert resp.status_code == 422


async def test_analyst_cannot_write_playbook(client, console_world, db_session) -> None:
    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    resp = await client.post(
        "/console/knowledge/url",
        headers=analyst["headers"](),
        json={"url": "https://example.com/x"},
    )
    assert resp.status_code == 403


async def test_no_guc_yields_zero_playbook_rows(console_world) -> None:
    a = console_world["a"]
    await _seed_playbook(a["partner_id"], "Hidden without GUC", PLAYBOOK_MARK)
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(sa.text("SELECT set_config('app.partner_id', '', false)"))
        await session.execute(sa.text("SET ROLE nexus_app"))
        n = await session.scalar(sa.text("SELECT count(*) FROM partner_knowledge_documents"))
        assert n == 0


async def test_channel_turn_does_not_carry_playbook(console_world) -> None:
    from nexus_worker.runtime.console_context import load_knowledge_block

    a = console_world["a"]
    await _seed_playbook(a["partner_id"], "Partner playbook", PLAYBOOK_MARK)
    await _seed_client_kb(a["tenant_id"], "Client kb", CLIENT_MARK)
    block = await load_knowledge_block(a["tenant_id"])
    assert PLAYBOOK_MARK not in block
    assert "partner_playbook" not in block
    assert CLIENT_MARK in block
    assert "<knowledge_document" in block


async def test_companion_without_client_ref_is_playbook_only(console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    await _seed_playbook(a["partner_id"], "Partner playbook", PLAYBOOK_MARK)
    await _seed_client_kb(a["tenant_id"], "Client kb", CLIENT_MARK)
    await _seed_client_kb(b["tenant_id"], "Other client", "OTHER_CLIENT_KB")

    only_playbook = await load_companion_knowledge_blocks(a["partner_id"], client_ref=None)
    assert PLAYBOOK_MARK in only_playbook
    assert "<partner_playbook" in only_playbook
    assert CLIENT_MARK not in only_playbook
    assert "OTHER_CLIENT_KB" not in only_playbook

    both = await load_companion_knowledge_blocks(a["partner_id"], client_ref=a["ref"])
    assert PLAYBOOK_MARK in both and CLIENT_MARK in both
    assert "OTHER_CLIENT_KB" not in both

    foreign = await load_companion_knowledge_blocks(a["partner_id"], client_ref=b["ref"])
    assert PLAYBOOK_MARK in foreign
    assert CLIENT_MARK not in foreign
    assert "OTHER_CLIENT_KB" not in foreign


async def test_client_delete_keeps_playbook(client, console_world) -> None:
    a = console_world["a"]
    playbook_id = await _seed_playbook(a["partner_id"], "Survives", PLAYBOOK_MARK)
    await _seed_client_kb(a["tenant_id"], "Goes away", CLIENT_MARK)
    archived = await client.post(
        f"/console/clients/{a['ref']}/status",
        headers=a["headers"](),
        json={"status": "archived"},
    )
    assert archived.status_code == 200, archived.text
    gone = await client.request(
        "DELETE",
        f"/console/clients/{a['ref']}",
        headers=a["headers"](),
        json={"confirm_name": "Client A One"},
    )
    assert gone.status_code == 204, gone.text
    sm = get_sessionmaker()
    async with sm() as session:
        left = await session.get(PartnerKnowledgeDocument, playbook_id)
        assert left is not None
        kb = await session.scalar(
            sa.select(sa.func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == a["tenant_id"])
        )
        assert int(kb or 0) == 0


async def test_partner_delete_cascades_playbook() -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        rule = await session.scalar(
            sa.text("SELECT confdeltype FROM pg_constraint WHERE conname = 'fk_pkd_partner'")
        )
        assert rule in {"c", b"c"}

    partner_id = uuid.uuid4()
    playbook_id = uuid.uuid4()
    async with sm() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO partners (id, name, slug, status, console_enabled) "
                "VALUES (:id, :n, :s, 'active', true)"
            ),
            {"id": str(partner_id), "n": "tmp-pb", "s": f"tmp-pb-{partner_id.hex[:8]}"},
        )
        session.add(
            PartnerKnowledgeDocument(
                id=playbook_id,
                partner_id=partner_id,
                kind=KnowledgeDocumentKind.URL.value,
                title="Dies",
                mime="text/plain",
                status=KnowledgeDocumentStatus.INDEXED.value,
                content_text=PLAYBOOK_MARK,
            )
        )
    async with sm() as session, session.begin():
        await session.execute(sa.text("DELETE FROM partners WHERE id = :p"), {"p": str(partner_id)})
    async with sm() as session:
        assert await session.get(PartnerKnowledgeDocument, playbook_id) is None


class _Ok:
    status_code = 200

    def json(self) -> dict:
        return {"items": []}


async def test_propose_knowledge_apply_body_has_no_partner_id() -> None:
    from nexus_api.companion.tools.proposals import ProposalBuilder

    async def read(path: str, params: dict) -> _Ok:
        return _Ok()

    proposal = await ProposalBuilder(read).build(
        "knowledge",
        {"scope": "partner", "url": "https://example.com/playbook.md"},
    )
    assert proposal.kind == "knowledge"
    assert "playbook" in proposal.title.lower()
    assert proposal.apply_body == {"url": "https://example.com/playbook.md"}
    assert "partner_id" not in (proposal.apply_body or {})
    assert proposal.apply_path == "/console/knowledge/url"


async def test_admin_partner_a_cannot_list_bs_playbook(
    client, console_world, admin_headers
) -> None:
    a, b = console_world["a"], console_world["b"]
    await _seed_playbook(b["partner_id"], "Playbook B", PLAYBOOK_MARK)
    await _seed_playbook(a["partner_id"], "Playbook A", "A_PLAYBOOK_MARK")

    listed = await client.get(f"/admin/partners/{a['partner_id']}/knowledge", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 1
    assert body["prompt_char_cap"] == 20000
    assert body["items"][0]["title"] == "Playbook A"
    assert "content_text" not in body
    assert not any("content_text" in item for item in body["items"])
    assert PLAYBOOK_MARK not in listed.text
    assert "A_PLAYBOOK_MARK" not in listed.text
    assert "sk-" not in listed.text

    b_list = await client.get(f"/admin/partners/{b['partner_id']}/knowledge", headers=admin_headers)
    assert b_list.status_code == 200, b_list.text
    assert b_list.json()["total"] == 1
    assert b_list.json()["items"][0]["title"] == "Playbook B"
    assert "content_text" not in b_list.json()["items"][0]
    assert PLAYBOOK_MARK not in b_list.text
    assert "sk-" not in b_list.text


async def test_admin_unknown_partner_knowledge_is_404(client, admin_headers) -> None:
    missing = uuid.uuid4()
    resp = await client.get(f"/admin/partners/{missing}/knowledge", headers=admin_headers)
    assert resp.status_code == 404
    assert resp.json() == {"detail": f"partner {missing} not found"}
