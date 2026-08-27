"""F3: admin knowledge/packs GET-only, A≠B 404, sin content_text."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    KnowledgeDocumentKind,
    KnowledgeDocumentStatus,
    PartnerKnowledgeDocument,
)
from nexus_api.db.models.workflow import WorkflowPack, WorkflowRun

pytestmark = pytest.mark.asyncio


def _knowledge(partner_id: object) -> str:
    return f"/admin/partners/{partner_id}/knowledge"


def _workflow(partner_id: object, ref: str) -> str:
    return f"/admin/partners/{partner_id}/clients/{ref}/workflow"


async def _seed_playbook(partner_id: uuid.UUID, title: str, text: str) -> None:
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        session.add(
            PartnerKnowledgeDocument(
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


async def test_admin_knowledge_lists_own_playbook_without_content_text(
    client, console_world, admin_headers
) -> None:
    a, b = console_world["a"], console_world["b"]
    secret = "ADMIN_KB_SECRET_SHOULD_NOT_LEAK"
    await _seed_playbook(a["partner_id"], "Playbook A", secret)
    await _seed_playbook(b["partner_id"], "Playbook B", "OTHER_SECRET")

    resp = await client.get(_knowledge(a["partner_id"]), headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["prompt_char_cap"] == 20000
    assert body["indexed_chars"] == len(secret)
    item = body["items"][0]
    assert item["title"] == "Playbook A"
    assert "content_text" not in body
    assert "content_text" not in item
    assert secret not in resp.text
    assert "OTHER_SECRET" not in resp.text
    assert "sk-" not in resp.text
    assert set(item) == {
        "id",
        "kind",
        "title",
        "source_url",
        "mime",
        "size_bytes",
        "status",
        "error_code",
        "chunk_count",
        "created_by",
        "created_at",
        "updated_at",
        "indexed_at",
    }


async def test_admin_knowledge_has_no_write(client, console_world, admin_headers) -> None:
    a = console_world["a"]
    path = _knowledge(a["partner_id"])
    put = await client.put(path, headers=admin_headers, json={"title": "x"})
    post = await client.post(path, headers=admin_headers, json={"url": "https://example.com"})
    delete = await client.delete(path, headers=admin_headers)
    assert put.status_code == 405, put.text
    assert post.status_code == 405, post.text
    assert delete.status_code == 405, delete.text


async def test_admin_workflow_reads_own_pack_and_runs(client, console_world, admin_headers) -> None:
    a, b = console_world["a"], console_world["b"]
    empty = await client.get(_workflow(a["partner_id"], a["ref"]), headers=admin_headers)
    assert empty.status_code == 200, empty.text
    assert empty.json()["is_set"] is False
    assert empty.json()["client_ref"] == a["ref"]
    empty_runs = await client.get(
        _workflow(a["partner_id"], a["ref"]) + "/runs", headers=admin_headers
    )
    assert empty_runs.status_code == 200, empty_runs.text
    assert empty_runs.json() == {"items": []}

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        pack = WorkflowPack(
            partner_id=a["partner_id"],
            client_ref=a["ref"],
            yaml={
                "trigger": "cron",
                "steps": ["send_template", "end"],
                "template_id": "hello_world",
                "enabled": True,
            },
            version=1,
        )
        session.add(pack)
        await session.flush()
        session.add(
            WorkflowRun(
                partner_id=a["partner_id"],
                pack_id=pack.id,
                thread_id="thread-a-1",
                status="success",
            )
        )

    got = await client.get(_workflow(a["partner_id"], a["ref"]), headers=admin_headers)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["is_set"] is True
    assert body["version"] == 1
    assert body["trigger"] == "cron"
    assert body["steps"] == ["send_template", "end"]

    runs = await client.get(_workflow(a["partner_id"], a["ref"]) + "/runs", headers=admin_headers)
    assert runs.status_code == 200, runs.text
    assert runs.json()["items"] == [{"thread_id": "thread-a-1", "status": "success"}]

    foreign = await client.get(_workflow(a["partner_id"], b["ref"]), headers=admin_headers)
    missing = await client.get(_workflow(a["partner_id"], "no-such"), headers=admin_headers)
    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Unknown client reference"}
