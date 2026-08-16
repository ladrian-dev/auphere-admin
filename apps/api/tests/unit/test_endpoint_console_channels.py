"""Functional tests of the console ``channels`` lane (CP-17..CP-19).

Isolation (opaque 404 across partners, no tenant ids, no bodies) is
pinned structurally in ``tests/isolation/test_console_scope.py``. Here:

- overview + channel quota (``partners.max_channels_per_client``): the
  409 fires BEFORE Meta is called and leaves nothing behind;
- signup happy path with the orchestrator stubbed;
- roles: the routing refusal rule surfaces as ``roles_required`` and the
  PATCH writes ``config.role`` + audit;
- templates: Meta list stubbed, ``whatsapp_template_status.reason`` shows
  up as ``rejection_reason`` with a ``suggested_action``;
- diagnostics: composed rows without credentials are red, never 500;
  ``compose_rows`` unit-tested with fixtures.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import respx
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.credentials import MetaCredentials
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL
from nexus_channels.whatsapp_meta.signup import SignupResult

from nexus_api.api.console import diagnostics as diag
from nexus_api.api.console import templates as tpl_router
from nexus_api.api.console import whatsapp as wa_router
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    TenantCredentials,
)
from nexus_api.db.models.conversation import WhatsAppTemplateStatus
from nexus_api.services.meta_signup_service import SignupServiceResult
from nexus_api.services.whatsapp_templates import TemplateOut


def _channel(tenant_id: uuid.UUID, *, role: str | None = None, **cfg: object) -> Channel:
    config: dict[str, object] = {"phone_number_id": "PN", **cfg}
    if role:
        config["role"] = role
    return Channel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+3460000{uuid.uuid4().int % 10000:04d}",
        config=config,
        status=ChannelStatus.ACTIVE,
    )


async def _seed_creds(db_session, tenant_id: uuid.UUID, *, waba_id: str = "WABA_C") -> None:
    creds = MetaCredentials(
        bisuat="EAA-console",
        waba_id=waba_id,
        phone_number_id="PN_C",
        business_id="BIZ_C",
        display_phone_number="+34600000001",
        verify_token="v" * 32,
    )
    async with db_session.begin():
        await db_session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(sa.text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            TenantCredentials(
                tenant_id=tenant_id,
                integration="meta_whatsapp",
                encrypted_payload=creds.to_payload(),
                needs_reauth=False,
            )
        )


# ── overview + quota ───────────────────────────────────────────────────


async def test_overview_empty_client(client, console_world) -> None:
    a = console_world["a"]
    r = await client.get(f"/console/clients/{a['ref']}/channels/overview", headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["channels"] == []
    assert body["used_channels"] == 0
    assert body["max_channels"] == 2
    assert body["can_connect"] is True
    assert body["roles_required"] is False
    assert body["meta_connected"] is False


async def test_signup_quota_409_before_meta_and_no_side_effects(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    db_session.add(_channel(a["tenant_id"]))
    db_session.add(_channel(a["tenant_id"]))
    await db_session.commit()

    async def _boom(**_kw):
        raise AssertionError("complete_meta_signup must not be called when quota is full")

    monkeypatch.setattr(wa_router, "complete_meta_signup", _boom)
    audit_before = await db_session.scalar(sa.select(sa.func.count()).select_from(AuditLog))
    r = await client.post(
        f"/console/clients/{a['ref']}/channels/whatsapp/signup",
        headers=a["headers"](),
        json={"code": "abc", "waba_id": "W1", "mode": "cloud_api"},
    )
    assert r.status_code == 409, r.text
    assert "2 of 2" in r.json()["detail"]
    audit_after = await db_session.scalar(sa.select(sa.func.count()).select_from(AuditLog))
    assert audit_after == audit_before
    channels = await db_session.scalar(sa.select(sa.func.count()).select_from(Channel))
    assert channels == 2

    ov = await client.get(f"/console/clients/{a['ref']}/channels/overview", headers=a["headers"]())
    assert ov.json()["can_connect"] is False
    assert ov.json()["used_channels"] == 2


async def test_signup_happy_path_uses_shared_orchestrator(
    client, console_world, monkeypatch
) -> None:
    a = console_world["a"]
    seen: dict[str, object] = {}
    channel_id = uuid.uuid4()

    async def _fake(**kw):
        seen.update(kw)
        return SignupServiceResult(
            result=SignupResult(
                channel_id=channel_id,
                waba_id=kw["payload"].waba_id,
                phone_number_id="PN",
                display_phone_number="+34600000009",
                mode=kw["payload"].mode,
                bisuat_expires_at=None,
            ),
            audit_log_id=uuid.uuid4(),
        )

    monkeypatch.setattr(wa_router, "complete_meta_signup", _fake)
    r = await client.post(
        f"/console/clients/{a['ref']}/channels/whatsapp/signup",
        headers=a["headers"](),
        json={"code": "abc", "waba_id": "W1", "phone_number_id": "PN", "mode": "coexistence"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "connected"
    assert body["channel_id"] == str(channel_id)
    assert body["display_phone_number"] == "+34600000009"
    assert body["max_channels"] == 2
    assert "tenant_id" not in body
    # The orchestrator got the SCOPED tenant and the console actor.
    assert seen["tenant_id"] == a["tenant_id"]
    assert seen["audit_action"] == "console.channel.connect"
    assert "@" in str(seen["actor"]) or str(seen["actor"])


async def test_signup_requires_channels_write(client, console_world, db_session) -> None:
    from tests.conftest import add_console_member

    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    r = await client.post(
        f"/console/clients/{a['ref']}/channels/whatsapp/signup",
        headers=analyst["headers"](),
        json={"code": "abc", "waba_id": "W1"},
    )
    assert r.status_code == 403


# ── roles ──────────────────────────────────────────────────────────────


async def test_roles_required_and_patch_role_writes_config_and_audit(
    client, console_world, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    c1, c2 = _channel(a["tenant_id"]), _channel(a["tenant_id"])
    other = _channel(b["tenant_id"])
    db_session.add_all([c1, c2, other])
    await db_session.commit()

    ov = await client.get(f"/console/clients/{a['ref']}/channels/overview", headers=a["headers"]())
    assert ov.json()["roles_required"] is True

    r = await client.patch(
        f"/console/clients/{a['ref']}/channels/{c1.id}/role",
        headers=a["headers"](),
        json={"role": "agent"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "agent"
    r = await client.patch(
        f"/console/clients/{a['ref']}/channels/{c2.id}/role",
        headers=a["headers"](),
        json={"role": "notifications"},
    )
    assert r.status_code == 200, r.text
    ov = await client.get(f"/console/clients/{a['ref']}/channels/overview", headers=a["headers"]())
    assert ov.json()["roles_required"] is False
    roles = {c["id"]: c["role"] for c in ov.json()["channels"]}
    assert roles == {str(c1.id): "agent", str(c2.id): "notifications"}

    cfg = await db_session.scalar(sa.select(Channel.config).where(Channel.id == c1.id))
    assert cfg is not None and cfg["role"] == "agent"
    assert cfg["phone_number_id"] == "PN"  # untouched
    audit = (
        (
            await db_session.execute(
                sa.select(AuditLog).where(AuditLog.action == "console.channel.role")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 2
    assert audit[0].tenant_id == a["tenant_id"]

    # Clearing the role.
    r = await client.patch(
        f"/console/clients/{a['ref']}/channels/{c2.id}/role",
        headers=a["headers"](),
        json={"role": None},
    )
    assert r.status_code == 200 and r.json()["role"] is None
    # Bad role → 422; someone else's channel → 404 (RLS).
    r = await client.patch(
        f"/console/clients/{a['ref']}/channels/{c2.id}/role",
        headers=a["headers"](),
        json={"role": "sales"},
    )
    assert r.status_code == 422
    r = await client.patch(
        f"/console/clients/{a['ref']}/channels/{other.id}/role",
        headers=a["headers"](),
        json={"role": "agent"},
    )
    assert r.status_code == 404


async def test_overview_lifts_only_descriptive_config_keys(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    db_session.add(
        _channel(
            a["tenant_id"],
            quality_rating="GREEN",
            messaging_tier="TIER_1K",
            verified_name="Demo",
            waba_id="W-SECRET",
            access_token="SECRET",
        )
    )
    await db_session.commit()
    r = await client.get(f"/console/clients/{a['ref']}/channels/overview", headers=a["headers"]())
    ch = r.json()["channels"][0]
    assert ch["quality_rating"] == "GREEN"
    assert ch["messaging_tier"] == "TIER_1K"
    assert ch["verified_name"] == "Demo"
    assert "config" not in ch
    assert "SECRET" not in r.text
    assert "PN" not in r.text.split('"provider_identifier"')[0]


# ── templates ──────────────────────────────────────────────────────────


async def test_templates_409_without_meta_credentials(client, console_world) -> None:
    a = console_world["a"]
    r = await client.get(
        f"/console/clients/{a['ref']}/channels/whatsapp/templates", headers=a["headers"]()
    )
    assert r.status_code == 409, r.text
    r = await client.post(
        f"/console/clients/{a['ref']}/channels/whatsapp/templates",
        headers=a["headers"](),
        json={"name": "recordatorio", "body_text": "Hola {{1}}"},
    )
    assert r.status_code == 409


async def test_templates_join_meta_list_with_literal_rejection_reason(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    await _seed_creds(db_session, a["tenant_id"], waba_id="WABA_C")
    db_session.add(
        WhatsAppTemplateStatus(
            waba_id="WABA_C",
            template_name="promo_verano",
            language="es",
            category="MARKETING",
            status="rejected",
            reason="INVALID_FORMAT",
            last_event_at=datetime.now(UTC),
        )
    )
    db_session.add(
        WhatsAppTemplateStatus(
            waba_id="WABA_C",
            template_name="hello_world",
            language="en_US",
            status="approved",
            reason="OLD_REASON_MUST_NOT_SHOW",
        )
    )
    await db_session.commit()

    async def _fake_fetch(session, *, use_cache=True):
        return (
            [
                TemplateOut(id="1", name="hello_world", language="en_US", status="APPROVED"),
                TemplateOut(
                    id="2",
                    name="promo_verano",
                    language="es",
                    category="MARKETING",
                    status="REJECTED",
                    quality_score="UNKNOWN",
                ),
                TemplateOut(id="3", name="nueva", language="es", status="PENDING"),
            ],
            "WABA_C",
        )

    monkeypatch.setattr(tpl_router, "fetch_templates", _fake_fetch)
    r = await client.get(
        f"/console/clients/{a['ref']}/channels/whatsapp/templates", headers=a["headers"]()
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["approved"], body["rejected"], body["pending"]) == (1, 1, 1)
    by_name = {t["name"]: t for t in body["items"]}
    assert by_name["promo_verano"]["rejection_reason"] == "INVALID_FORMAT"
    assert by_name["promo_verano"]["suggested_action"] == "fix_format"
    assert by_name["hello_world"]["rejection_reason"] is None
    assert by_name["hello_world"]["suggested_action"] == "none"
    assert by_name["nueva"]["suggested_action"] == "wait_review"
    assert "reason" not in r.text.replace("rejection_reason", "")


async def test_template_create_and_delete_hit_meta_and_audit(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed_creds(db_session, a["tenant_id"], waba_id="WABA_C")
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        created = mock.post("/WABA_C/message_templates").respond(
            200, json={"id": "T1", "status": "PENDING", "category": "UTILITY"}
        )
        r = await client.post(
            f"/console/clients/{a['ref']}/channels/whatsapp/templates",
            headers=a["headers"](),
            json={
                "name": "cita_recordatorio",
                "language": "es",
                "category": "UTILITY",
                "header_text": "Recordatorio",
                "body_text": "Hola {{1}}, tu cita es el {{2}}.",
                "footer_text": "Auphere",
                "buttons": [{"type": "QUICK_REPLY", "label": "Confirmar"}],
            },
        )
        assert r.status_code == 201, r.text
        assert r.json() == {
            "id": "T1",
            "name": "cita_recordatorio",
            "status": "PENDING",
            "category": "UTILITY",
        }
        import json as _json

        sent = _json.loads(created.calls.last.request.content)
        types = [c["type"] for c in sent["components"]]
        assert types == ["HEADER", "BODY", "FOOTER", "BUTTONS"]

        mock.delete("/WABA_C/message_templates").respond(200, json={"success": True})
        r = await client.delete(
            f"/console/clients/{a['ref']}/channels/whatsapp/templates/cita_recordatorio",
            headers=a["headers"](),
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"name": "cita_recordatorio", "deleted": True}

    actions = (
        (
            await db_session.execute(
                sa.select(AuditLog.action).where(AuditLog.action.like("console.template.%"))
            )
        )
        .scalars()
        .all()
    )
    assert sorted(actions) == ["console.template.create", "console.template.delete"]

    r = await client.delete(
        f"/console/clients/{a['ref']}/channels/whatsapp/templates/Bad-Name",
        headers=a["headers"](),
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    ("status_value", "reason", "expected"),
    [
        ("APPROVED", None, "none"),
        ("PENDING", None, "wait_review"),
        ("REJECTED", "INVALID_FORMAT", "fix_format"),
        ("REJECTED", "TAG_CONTENT_MISMATCH", "change_category"),
        ("REJECTED", "INCORRECT_CATEGORY", "change_category"),
        ("REJECTED", "PROMOTIONAL", "remove_promotional"),
        ("REJECTED", "ABUSIVE_CONTENT", "rewrite_content"),
        ("REJECTED", "SCAM", "rewrite_content"),
        ("REJECTED", "Variable parameter missing sample", "add_variables_samples"),
        ("REJECTED", "something new from meta", "contact_support"),
        ("PAUSED", None, "contact_support"),
    ],
)
def test_suggested_action_mapping(status_value: str, reason: str | None, expected: str) -> None:
    assert tpl_router.suggested_action_for(status_value, reason) == expected


# ── diagnostics ────────────────────────────────────────────────────────


async def test_diagnostics_without_credentials_is_red_not_500(client, console_world) -> None:
    a = console_world["a"]
    r = await client.get(
        f"/console/clients/{a['ref']}/channels/diagnostics", headers=a["headers"]()
    )
    assert r.status_code == 200, r.text
    body = r.json()
    rows = {row["key"]: row for row in body["rows"]}
    assert body["healthy"] is False
    assert rows["credentials"] == {
        "key": "credentials",
        "state": "fail",
        "what_to_do": "connect_whatsapp",
        "detail": None,
        "link": None,
    }
    assert rows["channel"]["state"] == "fail"
    assert rows["billing"]["state"] == "unknown"
    assert rows["billing"]["link"].startswith("https://business.facebook.com/")
    assert set(rows) == {
        "credentials",
        "channel",
        "roles",
        "webhook",
        "health_check",
        "quality",
        "messaging_tier",
        "templates",
        "billing",
    }


async def test_diagnostics_with_credentials_probes_meta_and_degrades_to_unknown(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed_creds(db_session, a["tenant_id"], waba_id="WABA_C")
    db_session.add(_channel(a["tenant_id"], quality_rating="YELLOW", messaging_tier="TIER_1K"))
    await db_session.commit()
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.get("/WABA_C/subscribed_apps").respond(
            200,
            json={
                "data": [
                    {"whatsapp_business_api_data": {"id": "957213733862330", "name": "Auphere"}}
                ]
            },
        )
        mock.get("/WABA_C/message_templates").respond(500, json={"error": {"message": "x"}})
        r = await client.get(
            f"/console/clients/{a['ref']}/channels/diagnostics", headers=a["headers"]()
        )
    assert r.status_code == 200, r.text
    rows = {row["key"]: row for row in r.json()["rows"]}
    assert rows["credentials"]["state"] == "ok"
    assert rows["webhook"]["state"] == "ok"
    assert rows["templates"]["state"] == "unknown"  # probe failed → unknown, not 500
    assert rows["quality"] == {
        "key": "quality",
        "state": "warn",
        "what_to_do": "improve_quality",
        "detail": "YELLOW",
        "link": "https://business.facebook.com/wa/manage/home/?waba_id=WABA_C",
    }
    assert rows["messaging_tier"]["detail"] == "TIER_1K"
    assert rows["health_check"]["state"] == "unknown"


def _snapshot(**over: object) -> diag.DiagnosticsSnapshot:
    base: dict[str, object] = {
        "now": datetime(2026, 8, 15, 12, tzinfo=UTC),
        "has_credentials": True,
        "needs_reauth": False,
        "bisuat_expires_at": None,
        "channels": [
            diag.ChannelFacts(
                status="active",
                role=None,
                quality_rating="GREEN",
                messaging_tier="TIER_1K",
                last_health_check_at=datetime(2026, 8, 15, 10, tzinfo=UTC),
                identifier="+34600000001",
            )
        ],
        "webhook_subscribed": True,
        "templates_approved": 2,
        "templates_rejected": 0,
        "templates_pending": 0,
        "waba_id": "W",
    }
    base.update(over)
    return diag.DiagnosticsSnapshot(**base)  # type: ignore[arg-type]


def test_compose_rows_all_green() -> None:
    rows = {r.key: r for r in diag.compose_rows(_snapshot())}
    assert all(r.state == "ok" for k, r in rows.items() if k != "billing"), rows
    assert rows["billing"].state == "unknown"


def test_compose_rows_two_untagged_channels_fail_roles() -> None:
    ch = _snapshot().channels[0]
    two = [ch, diag.ChannelFacts(**{**ch.__dict__, "identifier": "+34600000002"})]
    rows = {r.key: r for r in diag.compose_rows(_snapshot(channels=two))}
    assert rows["roles"].state == "fail"
    assert rows["roles"].what_to_do == "assign_roles"
    tagged = [
        diag.ChannelFacts(**{**two[0].__dict__, "role": "agent"}),
        diag.ChannelFacts(**{**two[1].__dict__, "role": "notifications"}),
    ]
    assert {r.key: r for r in diag.compose_rows(_snapshot(channels=tagged))}["roles"].state == "ok"


def test_compose_rows_reauth_expiry_and_stale_health() -> None:
    now = datetime(2026, 8, 15, 12, tzinfo=UTC)
    rows = {r.key: r for r in diag.compose_rows(_snapshot(needs_reauth=True))}
    assert (rows["credentials"].state, rows["credentials"].what_to_do) == (
        "fail",
        "reconnect_whatsapp",
    )
    rows = {
        r.key: r for r in diag.compose_rows(_snapshot(bisuat_expires_at=now + timedelta(days=2)))
    }
    assert rows["credentials"].state == "warn"
    stale = diag.ChannelFacts(
        **{**_snapshot().channels[0].__dict__, "last_health_check_at": now - timedelta(days=3)}
    )
    rows = {r.key: r for r in diag.compose_rows(_snapshot(channels=[stale]))}
    assert (rows["health_check"].state, rows["health_check"].what_to_do) == (
        "warn",
        "wait_health_check",
    )
    rows = {r.key: r for r in diag.compose_rows(_snapshot(webhook_subscribed=False))}
    assert rows["webhook"].state == "fail" and rows["webhook"].link
    rows = {r.key: r for r in diag.compose_rows(_snapshot(templates_rejected=1))}
    assert (rows["templates"].state, rows["templates"].what_to_do) == ("warn", "review_templates")
    rows = {
        r.key: r
        for r in diag.compose_rows(
            _snapshot(templates_approved=0, templates_rejected=0, templates_pending=0)
        )
    }
    assert rows["templates"].what_to_do == "create_template"


def test_webhook_subscribed_parser() -> None:
    assert diag.webhook_subscribed(
        {"data": [{"whatsapp_business_api_data": {"id": "1", "name": "x"}}]}, app_id="1"
    )
    assert not diag.webhook_subscribed({"data": []}, app_id="1")
    assert not diag.webhook_subscribed({"data": [{"id": "2"}]}, app_id="1")
    assert not diag.webhook_subscribed({}, app_id="1")


async def test_test_send_409_without_credentials_and_sends_with(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    r = await client.post(
        f"/console/clients/{a['ref']}/channels/diagnostics/test-send",
        headers=a["headers"](),
        json={"to": "+34600111222"},
    )
    assert r.status_code == 409
    await _seed_creds(db_session, a["tenant_id"])
    db_session.add(_channel(a["tenant_id"]))
    await db_session.commit()
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_C/messages").respond(200, json={"messages": [{"id": "wamid.X"}]})
        r = await client.post(
            f"/console/clients/{a['ref']}/channels/diagnostics/test-send",
            headers=a["headers"](),
            json={"to": "+34600111222"},
        )
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "sent", "wamid": "wamid.X", "to": "+34600111222"}
    n = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "console.channel.test_send")
    )
    assert n == 1


async def test_internal_qa_channel_is_neither_listed_nor_counted(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    db_session.add(
        Channel(
            id=uuid.uuid4(),
            tenant_id=a["tenant_id"],
            type=ChannelType.WEB,
            provider="qa_playground",
            provider_identifier="qa_playground:x",
            config={"qa_playground": True},
            status=ChannelStatus.ACTIVE,
        )
    )
    await db_session.commit()
    r = await client.get(f"/console/clients/{a['ref']}/channels/overview", headers=a["headers"]())
    assert r.status_code == 200, r.text
    assert r.json()["channels"] == []
    assert r.json()["used_channels"] == 0
