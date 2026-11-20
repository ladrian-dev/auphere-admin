"""F2: allowlist A≠B, consola 422 fuera, extra 422, respuesta sin sk-."""

from __future__ import annotations

import json
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.respond_catalog import OFFERABLE_MODELS, RESPOND_MODEL_IDS

pytestmark = pytest.mark.asyncio

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"

KEY_A = "sk-vk-partner-a"
KEY_B = "sk-vk-partner-b"
MASTER = "test-litellm-admin-master"


def _models(partner_id: object) -> str:
    return f"/admin/partners/{partner_id}/models"


def _llm(partner_id: object) -> str:
    return f"/admin/partners/{partner_id}/llm"


def _assert_no_sk(resp: Any) -> None:
    assert "sk-" not in resp.text


async def test_admin_models_seeded_and_a_is_not_b(client, console_world, admin_headers) -> None:
    a, b = console_world["a"], console_world["b"]
    got_a = await client.get(_models(a["partner_id"]), headers=admin_headers)
    got_b = await client.get(_models(b["partner_id"]), headers=admin_headers)
    assert got_a.status_code == 200, got_a.text
    assert got_b.status_code == 200, got_b.text
    _assert_no_sk(got_a)
    _assert_no_sk(got_b)
    ids_a = [row["model_id"] for row in got_a.json()["items"] if row["allowed"]]
    ids_b = [row["model_id"] for row in got_b.json()["items"] if row["allowed"]]
    # Spec 065 (0238): los seis, también los de Anthropic sin habilitar.
    assert ids_a == [m for m, _ in OFFERABLE_MODELS]
    assert ids_b == [m for m, _ in OFFERABLE_MODELS]
    assert set(RESPOND_MODEL_IDS) <= set(ids_a)

    put_a = await client.put(
        _models(a["partner_id"]),
        headers=admin_headers,
        json={"model_ids": [SOL, LUNA]},
    )
    assert put_a.status_code == 200, put_a.text
    _assert_no_sk(put_a)
    allowed_a = {row["model_id"] for row in put_a.json()["items"] if row["allowed"]}
    assert allowed_a == {SOL, LUNA}
    assert TERRA not in allowed_a

    still_b = await client.get(_models(b["partner_id"]), headers=admin_headers)
    assert still_b.status_code == 200, still_b.text
    allowed_b = {row["model_id"] for row in still_b.json()["items"] if row["allowed"]}
    assert TERRA in allowed_b
    assert allowed_b == {m for m, _ in OFFERABLE_MODELS}


async def test_admin_models_rejects_extra_and_outside_catalog(
    client, console_world, admin_headers
) -> None:
    a = console_world["a"]
    pid = a["partner_id"]
    extra = await client.put(
        _models(pid),
        headers=admin_headers,
        json={"model_ids": [SOL], "note": "nope"},
    )
    in_body = await client.put(
        _models(pid),
        headers=admin_headers,
        json={"model_ids": [SOL], "partner_id": str(pid)},
    )
    bad = await client.put(
        _models(pid),
        headers=admin_headers,
        json={"model_ids": [SOL, "openai/gpt-4o"]},
    )
    assert extra.status_code == 422, extra.text
    assert in_body.status_code == 422, in_body.text
    assert bad.status_code == 422, bad.text
    _assert_no_sk(extra)
    _assert_no_sk(in_body)
    _assert_no_sk(bad)


async def test_admin_llm_block_a_does_not_touch_b(
    client, console_world, admin_headers, monkeypatch, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", "http://litellm.proxy.test")
    monkeypatch.setenv(
        "LITELLM_PROXY_VIRTUAL_KEYS",
        json.dumps({str(a["partner_id"]): KEY_A, str(b["partner_id"]): KEY_B}),
    )
    monkeypatch.setattr(
        "nexus_api.core.llm_proxy._settings_base_and_keys",
        lambda: (
            "http://litellm.proxy.test",
            json.dumps({str(a["partner_id"]): KEY_A, str(b["partner_id"]): KEY_B}),
        ),
    )
    monkeypatch.setattr(
        "nexus_api.core.llm_proxy.litellm_admin_master",
        lambda: MASTER,
    )

    seen: list[dict[str, Any]] = []

    async def fake_call(
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        seen.append({"method": method, "path": path, "json_body": json_body, "params": params})

        class _Resp:
            status_code = 200

            def json(self) -> dict[str, Any]:
                return {"blocked": True, "info": {"blocked": True}}

        return _Resp()

    monkeypatch.setattr("nexus_api.core.llm_proxy.litellm_admin_call", fake_call)

    extra = await client.post(
        f"{_llm(a['partner_id'])}/block",
        headers=admin_headers,
        json={"blocked": True, "partner_id": str(b["partner_id"])},
    )
    assert extra.status_code == 422, extra.text
    _assert_no_sk(extra)
    assert seen == []

    resp = await client.post(
        f"{_llm(a['partner_id'])}/block",
        headers=admin_headers,
        json={"blocked": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"blocked": True}
    _assert_no_sk(resp)
    assert MASTER not in resp.text

    bodies = [c.get("json_body") or {} for c in seen]
    assert any(body.get("key") == KEY_A for body in bodies)
    assert all(body.get("key") != KEY_B for body in bodies)
    params_keys = [(c.get("params") or {}).get("key") for c in seen]
    assert KEY_B not in params_keys
    assert any(c["path"] == "/key/block" for c in seen)
    assert all(c["path"] != "/key/update" for c in seen)

    from nexus_api.db.models import AuditLog

    audit = await db_session.scalar(
        sa.select(AuditLog)
        .where(AuditLog.action == "llm.block")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    assert audit is not None
    assert audit.tenant_id is None
    assert audit.actor == "admin:test-adm"
    assert audit.target == f"partner:{a['partner_id']}"
    assert "sk-" not in json.dumps(audit.after_json or {})
    assert "sk-" not in json.dumps(audit.before_json or {})


async def test_admin_llm_missing_vk_is_409(
    client, console_world, admin_headers, monkeypatch
) -> None:
    a = console_world["a"]
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", "http://litellm.proxy.test")
    monkeypatch.setenv("LITELLM_PROXY_VIRTUAL_KEYS", "{}")
    monkeypatch.setattr("nexus_api.core.llm_proxy._settings_base_and_keys", lambda: ("", ""))
    monkeypatch.setattr("nexus_api.core.llm_proxy.litellm_admin_master", lambda: MASTER)

    called = {"n": 0}

    async def fake_call(*_a: Any, **_k: Any) -> Any:
        called["n"] += 1
        raise AssertionError("must not call proxy without a VK")

    monkeypatch.setattr("nexus_api.core.llm_proxy.litellm_admin_call", fake_call)

    got = await client.get(_llm(a["partner_id"]), headers=admin_headers)
    post = await client.post(
        f"{_llm(a['partner_id'])}/block",
        headers=admin_headers,
        json={"blocked": True},
    )
    assert got.status_code == 409, got.text
    assert post.status_code == 409, post.text
    assert got.json()["detail"]["code"] == "llm_proxy_unavailable"
    _assert_no_sk(got)
    _assert_no_sk(post)
    assert called["n"] == 0


async def test_admin_models_audit_is_platform(
    client, console_world, admin_headers, db_session
) -> None:
    from nexus_api.db.models import AuditLog

    a = console_world["a"]
    resp = await client.put(
        _models(a["partner_id"]),
        headers=admin_headers,
        json={"model_ids": [SOL]},
    )
    assert resp.status_code == 200, resp.text
    audit = await db_session.scalar(
        sa.select(AuditLog)
        .where(AuditLog.action == "partner_models.set")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    assert audit is not None
    assert audit.tenant_id is None
    assert audit.actor == "admin:test-adm"
    assert audit.target == f"partner:{a['partner_id']}"
    assert "sk-" not in json.dumps(audit.after_json or {})
    assert set(audit.after_json["model_ids"]) == {SOL}


async def test_admin_llm_401_fail_closed(client, console_world, admin_headers, monkeypatch) -> None:
    from nexus_api.core.llm_proxy import LLMProxyUnavailable

    a = console_world["a"]
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", "http://litellm.proxy.test")
    monkeypatch.setenv(
        "LITELLM_PROXY_VIRTUAL_KEYS",
        json.dumps({str(a["partner_id"]): KEY_A}),
    )
    monkeypatch.setattr(
        "nexus_api.core.llm_proxy._settings_base_and_keys",
        lambda: (
            "http://litellm.proxy.test",
            json.dumps({str(a["partner_id"]): KEY_A}),
        ),
    )
    monkeypatch.setattr("nexus_api.core.llm_proxy.litellm_admin_master", lambda: MASTER)

    async def fake_call(*_a: Any, **_k: Any) -> Any:
        raise LLMProxyUnavailable("proxy unauthorized")

    monkeypatch.setattr("nexus_api.core.llm_proxy.litellm_admin_call", fake_call)

    got = await client.get(_llm(a["partner_id"]), headers=admin_headers)
    post = await client.post(
        f"{_llm(a['partner_id'])}/block",
        headers=admin_headers,
        json={"blocked": True},
    )
    assert got.status_code == 401, got.text
    assert post.status_code == 401, post.text
    assert got.json()["detail"]["code"] == "proxy_unauthorized"
    _assert_no_sk(got)
    _assert_no_sk(post)
    assert MASTER not in got.text
    assert MASTER not in post.text


# ── spec 016 · la allowlist reconcilia los bindings (R5.3) ────────────────────


async def _bound_model(db_session, tenant_id) -> str | None:
    row = (
        await db_session.execute(
            sa.text(
                "SELECT p.model_id FROM tenant_model_bindings b "
                "JOIN model_profiles p ON p.id = b.model_profile_id "
                "WHERE b.tenant_id = :t AND b.role = 'respond'"
            ),
            {"t": str(tenant_id)},
        )
    ).first()
    return None if row is None else str(row[0])


async def test_claude_can_go_on_a_partners_list_before_it_is_enabled(
    client, console_world, admin_headers
) -> None:
    """Spec 065 (T008; requisito 7.4): la lista se valida contra lo ofrecible, no contra lo
    habilitado. Auphere puede preparar la lista de un partner antes de la batería real."""
    a = console_world["a"]
    put = await client.put(
        _models(a["partner_id"]),
        headers=admin_headers,
        json={"model_ids": [SOL, "anthropic/claude-sonnet-5-5"]},
    )
    assert put.status_code == 200, put.text
    allowed = {row["model_id"] for row in put.json()["items"] if row["allowed"]}
    assert allowed == {SOL, "anthropic/claude-sonnet-5-5"}
    bad = await client.put(
        _models(a["partner_id"]),
        headers=admin_headers,
        json={"model_ids": [SOL, "anthropic/claude-sonnet-4-6"]},
    )
    assert bad.status_code == 422, "sin perfil de llamada no es ofrecible"


# Spec 065: la lista del partner ya no reconcilia la asignación de cliente; las elecciones
# de cada agente se reconcilian con T082/T083 (test_agent_model_admin.py).
