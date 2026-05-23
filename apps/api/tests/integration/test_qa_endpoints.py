"""Integration tests for the /qa/* HTTP surface (ADR-020 Phase 3)."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


# ── helpers ──────────────────────────────────────────────────────────────────


def qa_headers(operator_id: str, admin_headers: dict[str, str]) -> dict[str, str]:
    """Compose admin Bearer + X-Operator-Id for a QA request."""
    return {**admin_headers, "X-Operator-Id": operator_id}


def _op_id() -> str:
    """Opaque operator id (post-migration 0026 — TEXT, not UUID)."""
    import secrets

    return secrets.token_urlsafe(16)


@pytest.fixture
async def tenant_id(db_session) -> uuid.UUID:
    from nexus_api.db.models import Tenant, TenantPlan

    tid = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            Tenant(id=tid, name="QA-Test", slug=f"qa-{tid.hex[:6]}", plan=TenantPlan.PRO)
        )
    return tid


# ── auth ─────────────────────────────────────────────────────────────────────


async def test_create_thread_requires_bearer(client, tenant_id):
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id)},
    )
    assert r.status_code == 401


async def test_create_thread_requires_operator_header(client, admin_headers, tenant_id):
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id)},
        headers=admin_headers,
    )
    assert r.status_code == 400
    assert "X-Operator-Id" in r.json()["detail"]


async def test_create_thread_rejects_blank_operator(client, admin_headers, tenant_id):
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id)},
        headers={**admin_headers, "X-Operator-Id": "   "},
    )
    assert r.status_code == 400
    assert "blank" in r.json()["detail"]


async def test_create_thread_rejects_too_long_operator(client, admin_headers, tenant_id):
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id)},
        headers={**admin_headers, "X-Operator-Id": "x" * 200},
    )
    assert r.status_code == 400
    assert "120" in r.json()["detail"]


# ── happy path ───────────────────────────────────────────────────────────────


async def test_create_then_list_thread(client, admin_headers, tenant_id, db_session):
    op = _op_id()
    h = qa_headers(op, admin_headers)

    create = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "First"},
        headers=h,
    )
    assert create.status_code == 201
    payload = create.json()
    assert payload["title"] == "First"
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["operator_id"] == op
    assert payload["archived_at"] is None
    thread_id = payload["id"]

    # Debug: confirm the row exists in the DB (superuser → bypasses RLS)
    from sqlalchemy import text

    res = await db_session.execute(
        text("SELECT id, operator_id::text FROM qa.threads WHERE id = :id"),
        {"id": thread_id},
    )
    rows = list(res)
    assert rows, f"thread {thread_id} not in qa.threads after POST"

    listed = await client.get(
        f"/qa/threads?tenant_id={tenant_id}",
        headers=h,
    )
    assert listed.status_code == 200
    ids = [t["id"] for t in listed.json()]
    assert thread_id in ids


async def test_create_thread_404_on_unknown_tenant(client, admin_headers):
    op = _op_id()
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(uuid.uuid4()), "title": "x"},
        headers=qa_headers(op, admin_headers),
    )
    assert r.status_code == 404


async def test_get_thread_detail(client, admin_headers, tenant_id):
    op = _op_id()
    h = qa_headers(op, admin_headers)
    create = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "Detail"},
        headers=h,
    )
    thread_id = create.json()["id"]

    detail = await client.get(f"/qa/threads/{thread_id}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["title"] == "Detail"


async def test_patch_thread_renames_and_archives(client, admin_headers, tenant_id):
    op = _op_id()
    h = qa_headers(op, admin_headers)
    create = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "Original"},
        headers=h,
    )
    thread_id = create.json()["id"]

    rename = await client.patch(
        f"/qa/threads/{thread_id}",
        json={"title": "Renamed"},
        headers=h,
    )
    assert rename.status_code == 200
    assert rename.json()["title"] == "Renamed"
    assert rename.json()["archived_at"] is None

    archive = await client.patch(
        f"/qa/threads/{thread_id}",
        json={"archived": True},
        headers=h,
    )
    assert archive.status_code == 200
    assert archive.json()["archived_at"] is not None

    # Archived rows hidden from default list, present with include_archived
    visible = await client.get(
        f"/qa/threads?tenant_id={tenant_id}",
        headers=h,
    )
    assert thread_id not in [t["id"] for t in visible.json()]

    full = await client.get(
        f"/qa/threads?tenant_id={tenant_id}&include_archived=true",
        headers=h,
    )
    assert thread_id in [t["id"] for t in full.json()]

    # Un-archive
    unarchive = await client.patch(
        f"/qa/threads/{thread_id}",
        json={"archived": False},
        headers=h,
    )
    assert unarchive.json()["archived_at"] is None


async def test_patch_thread_rejects_empty_body(client, admin_headers, tenant_id):
    op = _op_id()
    h = qa_headers(op, admin_headers)
    create = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id)},
        headers=h,
    )
    thread_id = create.json()["id"]

    r = await client.patch(f"/qa/threads/{thread_id}", json={}, headers=h)
    assert r.status_code == 400


# ── cross-operator isolation via HTTP ────────────────────────────────────────


async def test_operator_b_cannot_see_operator_a_thread(client, admin_headers, tenant_id):
    op_a = _op_id()
    op_b = _op_id()

    created = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "Owner: A"},
        headers=qa_headers(op_a, admin_headers),
    )
    a_id = created.json()["id"]

    # Operator B lists → should NOT see A's thread.
    listed_b = await client.get(
        f"/qa/threads?tenant_id={tenant_id}",
        headers=qa_headers(op_b, admin_headers),
    )
    assert listed_b.status_code == 200
    assert a_id not in [t["id"] for t in listed_b.json()]

    # Operator B tries to read A's thread by id → RLS makes it look like 404.
    detail_b = await client.get(
        f"/qa/threads/{a_id}",
        headers=qa_headers(op_b, admin_headers),
    )
    assert detail_b.status_code == 404


async def test_audit_endpoint_returns_thread_side_effects(
    client, admin_headers, tenant_id, db_session
):
    """Insert a side-effect audit row directly, then read it back through
    the HTTP endpoint. Confirms the RLS scoping + serialization both work.
    """
    from nexus_api.core.operator_context import qa_scoped_session
    from nexus_api.db.models.qa import QASideEffectAudit

    op = _op_id()
    h = qa_headers(op, admin_headers)
    create = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "Audited"},
        headers=h,
    )
    thread_id = uuid.UUID(create.json()["id"])

    # Insert a side-effect audit row scoped to this operator.
    async with (
        db_session.begin(),
        qa_scoped_session(db_session, operator_id=op, tenant_id=tenant_id),
    ):
        db_session.add(
            QASideEffectAudit(
                operator_id=op,
                tenant_id=tenant_id,
                thread_id=thread_id,
                tool_name="booking.create_appointment",
                tool_args={"when": "tomorrow 10am"},
                synthetic_result={"ok": True, "blocked_by": "dry_run"},
                blocked_reason="dry_run",
                run_id="run-001",
            )
        )

    r = await client.get(f"/qa/threads/{thread_id}/audit", headers=h)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["tool_name"] == "booking.create_appointment"
    assert rows[0]["blocked_reason"] == "dry_run"
    assert rows[0]["tool_args"] == {"when": "tomorrow 10am"}


# ── ADR-024 · per-thread dry_run / live toggle ──────────────────────────────


async def test_create_thread_defaults_to_dry_run(client, admin_headers, tenant_id) -> None:
    """The safe default must be preserved — a thread created without
    specifying ``dry_run`` is born dry."""
    h = qa_headers(_op_id(), admin_headers)
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "default-dry"},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["dry_run"] is True


async def test_create_thread_can_open_in_live_mode(client, admin_headers, tenant_id) -> None:
    """An operator can explicitly create a live thread — the response
    surfaces the flag so the UI can warn."""
    h = qa_headers(_op_id(), admin_headers)
    r = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "born-live", "dry_run": False},
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["dry_run"] is False


async def test_patch_thread_flips_dry_run(client, admin_headers, tenant_id) -> None:
    """PATCH ``dry_run=false`` flips an existing thread to live; the
    response carries the new value and a subsequent GET sees it too."""
    h = qa_headers(_op_id(), admin_headers)
    created = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "flip"},
        headers=h,
    )
    thread_id = created.json()["id"]
    assert created.json()["dry_run"] is True

    patched = await client.patch(
        f"/qa/threads/{thread_id}",
        json={"dry_run": False},
        headers=h,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["dry_run"] is False

    fetched = await client.get(f"/qa/threads/{thread_id}", headers=h)
    assert fetched.json()["dry_run"] is False


async def test_patch_thread_accepts_only_dry_run(client, admin_headers, tenant_id) -> None:
    """``dry_run`` alone is a valid PATCH body (no title/archived needed)."""
    h = qa_headers(_op_id(), admin_headers)
    created = await client.post(
        "/qa/threads",
        json={"tenant_id": str(tenant_id), "title": "lone-flag"},
        headers=h,
    )
    thread_id = created.json()["id"]
    r = await client.patch(
        f"/qa/threads/{thread_id}",
        json={"dry_run": False},
        headers=h,
    )
    assert r.status_code == 200


async def test_send_message_selects_pipeline_by_thread_dry_run(
    client, admin_headers, tenant_id, monkeypatch
) -> None:
    """The core guarantee of ADR-024: ``send_message`` picks the dry vs
    live pipeline based on ``thread.dry_run``. A dry thread routes to
    the dry pipeline; a live thread routes to the live pipeline. The
    selection happens per turn, so a PATCH-flip is honoured next send.
    """

    class _Fake:
        def __init__(self, label: str) -> None:
            self.label = label
            self.called = 0

        async def ainvoke(self, state, config):
            self.called += 1
            return {
                "tenant_id": state["tenant_id"],
                "response": f"reply-from-{self.label}",
                "ucm": None,
                "intent": "info",
                "tool_calls": [],
            }

    fakes = {True: _Fake("live"), False: _Fake("dry")}

    def _picker(*, live: bool):
        return fakes[live]

    monkeypatch.setattr("nexus_api.api.qa._get_qa_pipeline", _picker)

    op = _op_id()
    h = qa_headers(op, admin_headers)
    dry_thread = (
        await client.post(
            "/qa/threads",
            json={"tenant_id": str(tenant_id), "title": "dry"},
            headers=h,
        )
    ).json()
    live_thread = (
        await client.post(
            "/qa/threads",
            json={"tenant_id": str(tenant_id), "title": "live", "dry_run": False},
            headers=h,
        )
    ).json()

    r_dry = await client.post(
        f"/qa/threads/{dry_thread['id']}/send",
        json={"message": "hola dry"},
        headers=h,
    )
    assert r_dry.status_code == 200, r_dry.text
    assert r_dry.json()["response"] == "reply-from-dry"

    r_live = await client.post(
        f"/qa/threads/{live_thread['id']}/send",
        json={"message": "hola live"},
        headers=h,
    )
    assert r_live.status_code == 200, r_live.text
    assert r_live.json()["response"] == "reply-from-live"

    # Each pipeline saw exactly one invocation — the selection by
    # ``thread.dry_run`` was respected, not the global default.
    assert fakes[False].called == 1
    assert fakes[True].called == 1
