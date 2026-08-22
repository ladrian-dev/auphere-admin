"""Functional tests of the ``onboarding`` console lane (CP-10 seed wizard,
CP-29 notifications + onboarding checklist + activation metric).

Isolation of every route is covered by ``tests/isolation/test_console_scope.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.api.console.seed_templates import describe_placeholders
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    ConsoleNotification,
    NotificationKind,
    Partner,
    Tenant,
    TenantStatus,
)
from nexus_api.services.console_notifications import emit, record_client_activation
from nexus_api.services.templating.seed_templates import load_seed_template
from tests.conftest import add_console_member, mint_console_token

pytestmark = pytest.mark.asyncio


def _svc_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_console_token(user_id='bff', partner_id=None, service=True)}"
    }


# ── seed templates (CP-10) ─────────────────────────────────────────────


def test_describe_placeholders_barbershop_and_cobranza() -> None:
    barber = {p.key: p for p in describe_placeholders(load_seed_template("barbershop_v1"))}
    assert "tenant.name" not in barber and "tenant.timezone" not in barber
    assert barber["tenant.address"].required and not barber["tenant.address"].secret
    clinic = {p.key: p for p in describe_placeholders(load_seed_template("aesthetic_clinic_v1"))}
    assert clinic["clinical.titular_name"].required is True
    assert not clinic["tenant.front_desk_phone_label"].secret
    assert barber["agent.name"].required is False and barber["agent.name"].example == "Alex"
    assert barber["policies.no_show.fee_pct"].required is False
    assert barber["policies.no_show.fee_pct"].kind == "number"
    assert barber["policies.no_show.fee_pct"].example == "100"
    # required first
    keys = [p.key for p in describe_placeholders(load_seed_template("barbershop_v1"))]
    first_optional = next(i for i, k in enumerate(keys) if not barber[k].required)
    assert all(barber[k].required for k in keys[:first_optional])

    cobranza = {p.key: p for p in describe_placeholders(load_seed_template("cobranza_v1"))}
    phones = cobranza["policies.admin_access.admin_phones"]
    assert phones.required and phones.secret and phones.kind == "list"
    assert not any(k.startswith("policies.payment") for k in cobranza)


async def test_list_seed_templates_has_no_prompt(client, console_world, db_session) -> None:
    a = console_world["a"]
    r = await client.get("/console/seed-templates", headers=a["headers"]())
    assert r.status_code == 200, r.text
    names = {t["name"] for t in r.json()}
    assert {"generic_v1", "barbershop_v1", "cobranza_v1"} <= names
    for tpl in r.json():
        assert "system_prompt" not in tpl
        assert tpl["vertical"]
        assert isinstance(tpl["placeholders"], list)
    # billing role has no agents:read
    billing = await add_console_member(db_session, partner_id=a["partner_id"], role="billing")
    r = await client.get("/console/seed-templates", headers=billing["headers"]())
    assert r.status_code == 403


async def test_from_seed_stages_draft_v1_with_disclosure_and_409_on_second(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    h = a["headers"]
    r = await client.post(
        f"/console/clients/{a['ref']}/agent/from-seed",
        headers=h(),
        json={"seed_template": "barbershop_v1", "placeholders": {"agent.name": "Diego"}},
    )
    assert r.status_code == 422, r.text
    assert "tenant.address" in r.json()["detail"] or "business_hours" in r.json()["detail"]

    r = await client.post(
        f"/console/clients/{a['ref']}/agent/from-seed",
        headers=h(),
        json={
            "seed_template": "barbershop_v1",
            "placeholders": {
                "agent.name": "Diego",
                "tenant.address": "Las Condes",
                "tenant.business_hours_label": "Lun-Sáb 10-19",
                "policies.no_show.fee_pct": "50",
                "tenant.name": "IGNORED",  # tenant row wins
            },
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1 and body["status"] == "staged"
    assert body["seed_template_ref"] == "barbershop_v1"
    assert "IGNORED" not in body["system_prompt"]
    assert "Diego" in body["system_prompt"]
    assert "tenant_id" not in body

    row = await db_session.scalar(
        sa.select(AgentConfig).where(AgentConfig.tenant_id == a["tenant_id"])
    )
    assert row is not None
    assert row.policies["console"]["ai_disclosure"]["enabled"] is True
    assert row.policies["no_show"]["fee_pct"] == "50"

    again = await client.post(
        f"/console/clients/{a['ref']}/agent/from-seed",
        headers=h(),
        json={"seed_template": "generic_v1", "placeholders": {}},
    )
    assert again.status_code == 409

    ghost = await client.post(
        f"/console/clients/{a['ref']}/agent/from-seed",
        headers=h(),
        json={"seed_template": "ghost_v9", "placeholders": {}},
    )
    assert ghost.status_code == 404


async def test_create_client_with_seed_template_stages_draft(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    r = await client.post(
        "/console/clients",
        headers=a["headers"](),
        json={
            "external_client_ref": "wiz-1",
            "name": "Wizard Co",
            "seed_template": "generic_v1",
            "placeholders": {"tenant.address": "Calle 1", "tenant.business_hours_label": "9-18"},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["agent_status"] == "staged"
    agent = await client.get("/console/clients/wiz-1/agent", headers=a["headers"]())
    assert agent.status_code == 200
    assert [v["version"] for v in agent.json()["versions"]] == [1]
    # Idempotent retry: no second draft.
    r2 = await client.post(
        "/console/clients",
        headers=a["headers"](),
        json={"external_client_ref": "wiz-1", "name": "Wizard Co", "seed_template": "generic_v1"},
    )
    assert r2.status_code == 201
    assert r2.json()["agent_status"] == "already_provisioned"
    agent = await client.get("/console/clients/wiz-1/agent", headers=a["headers"]())
    assert len(agent.json()["versions"]) == 1


# ── notifications (CP-29) ─────────────────────────────────────────────


async def test_notifications_list_read_and_isolation(client, console_world, db_session) -> None:
    a, b = console_world["a"], console_world["b"]
    admin = await add_console_member(db_session, partner_id=a["partner_id"], role="admin")
    async with db_session.begin():
        # broadcast to partner A, referring to A's client
        await emit(
            db_session,
            partner_id=a["partner_id"],
            kind=NotificationKind.USAGE_THRESHOLD,
            severity="warning",
            data={"percent": 80, "period": "2026-08"},
            external_client_ref=a["ref"],
            dedupe_key=f"partner:{a['partner_id']}:usage:80:2026-08",
        )
        # personal to A's owner
        await emit(
            db_session,
            partner_id=a["partner_id"],
            kind=NotificationKind.ONBOARDING_STEP,
            data={"step": "team"},
            recipient_user_id=a["user_id"],
        )
        # personal to someone else in A (invisible to owner)
        await emit(
            db_session,
            partner_id=a["partner_id"],
            kind=NotificationKind.ONBOARDING_STEP,
            data={"step": "x"},
            recipient_user_id=admin["user_id"],
        )
        # partner B's
        await emit(
            db_session,
            partner_id=b["partner_id"],
            kind=NotificationKind.MEMBER_JOINED,
            data={"email": "x@b.test", "role": "admin"},
        )
        # dedupe
        dup = await emit(
            db_session,
            partner_id=a["partner_id"],
            kind=NotificationKind.USAGE_THRESHOLD,
            data={"percent": 80},
            dedupe_key=f"partner:{a['partner_id']}:usage:80:2026-08",
        )
        assert dup is None

    r = await client.get("/console/notifications", headers=a["headers"]())
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["unread"] == 2
    kinds = [n["kind"] for n in page["items"]]
    assert sorted(kinds) == ["onboarding.step", "usage.threshold"]
    usage = next(n for n in page["items"] if n["kind"] == "usage.threshold")
    assert usage["external_client_ref"] == a["ref"]
    assert usage["severity"] == "warning" and usage["read"] is False
    assert usage["data"]["percent"] == 80
    for n in page["items"]:
        assert "tenant_id" not in n and "payload" not in n

    r = await client.get("/console/notifications/unread-count", headers=a["headers"]())
    assert r.json() == {"unread": 2}

    # mark one (broadcast → per-user read row); admin still sees it unread
    r = await client.post(f"/console/notifications/{usage['id']}/read", headers=a["headers"]())
    assert r.status_code == 200 and r.json()["read"] is True
    assert (
        await client.get("/console/notifications/unread-count", headers=a["headers"]())
    ).json() == {"unread": 1}
    assert (
        await client.get("/console/notifications/unread-count", headers=admin["headers"]())
    ).json() == {"unread": 2}

    # unread filter + read-all
    r = await client.get("/console/notifications?unread=true", headers=a["headers"]())
    assert [n["kind"] for n in r.json()["items"]] == ["onboarding.step"]
    r = await client.post("/console/notifications/read-all", headers=a["headers"]())
    assert r.json() == {"marked": 1}
    assert (
        await client.get("/console/notifications/unread-count", headers=a["headers"]())
    ).json() == {"unread": 0}

    # B cannot read A's notification (opaque 404)
    r = await client.post(f"/console/notifications/{usage['id']}/read", headers=b["headers"]())
    assert r.status_code == 404
    r = await client.get("/console/notifications", headers=b["headers"]())
    assert [n["kind"] for n in r.json()["items"]] == ["member.joined"]


async def test_notifications_cursor_paging(client, console_world, db_session) -> None:
    a = console_world["a"]
    async with db_session.begin():
        for i in range(5):
            await emit(
                db_session,
                partner_id=a["partner_id"],
                kind=NotificationKind.ONBOARDING_STEP,
                data={"step": i},
            )
    r = await client.get("/console/notifications?limit=2", headers=a["headers"]())
    first = r.json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    seen = [n["id"] for n in first["items"]]
    r = await client.get(
        f"/console/notifications?limit=2&cursor={first['next_cursor']}", headers=a["headers"]()
    )
    second = r.json()
    assert len(second["items"]) == 2 and not (set(seen) & {n["id"] for n in second["items"]})
    r = await client.get(
        f"/console/notifications?limit=2&cursor={second['next_cursor']}", headers=a["headers"]()
    )
    third = r.json()
    assert len(third["items"]) == 1 and third["next_cursor"] is None
    r = await client.get("/console/notifications?cursor=%%%", headers=a["headers"]())
    assert r.status_code == 422


async def test_member_joined_is_emitted_on_invitation_accept(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    inv = await client.post(
        "/console/team/invitations",
        headers=a["headers"](),
        json={"email": "newbie@example.com", "role": "builder"},
    )
    assert inv.status_code == 201, inv.text
    token = inv.json()["accept_path"].rsplit("/", 1)[-1]
    acc = await client.post(
        f"/console/invitations/{token}/accept",
        headers=_svc_headers(),
        json={"password": "console-dev-2026!!", "display_name": "N"},
    )
    assert acc.status_code == 200, acc.text
    r = await client.get("/console/notifications", headers=a["headers"]())
    joined = [n for n in r.json()["items"] if n["kind"] == "member.joined"]
    assert len(joined) == 1
    assert joined[0]["data"] == {"email": "newbie@example.com", "role": "builder"}


# ── activation metric + onboarding (CP-29) ────────────────────────────


async def test_activation_metric_first_time_only_and_dedupe(console_world, db_session) -> None:
    a = console_world["a"]
    created = datetime.now(UTC) - timedelta(hours=2)
    await db_session.execute(
        sa.update(Partner).where(Partner.id == a["partner_id"]).values(created_at=created)
    )
    await db_session.commit()
    async with db_session.begin():
        first = await record_client_activation(
            db_session, partner_id=a["partner_id"], external_client_ref=a["ref"]
        )
        again = await record_client_activation(
            db_session, partner_id=a["partner_id"], external_client_ref=a["ref"]
        )
        other = await record_client_activation(
            db_session, partner_id=a["partner_id"], external_client_ref="c2"
        )
    assert first is True and again is False and other is False
    partner = await db_session.get(Partner, a["partner_id"])
    assert partner is not None and partner.activated_at is not None
    assert partner.activated_at - created >= timedelta(hours=2) - timedelta(seconds=5)
    n = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(ConsoleNotification)
        .where(
            ConsoleNotification.partner_id == a["partner_id"],
            ConsoleNotification.kind == "client.activated",
        )
    )
    assert n == 2  # one per client, never twice for the same client


async def test_status_active_with_published_agent_activates_partner(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    h = a["headers"]
    # Fresh partner: nothing activated, checklist mostly empty.
    r = await client.get("/console/onboarding", headers=h())
    assert r.status_code == 200, r.text
    ob = r.json()
    assert ob["activated_at"] is None and ob["time_to_first_active_client_seconds"] is None
    steps = {s["key"]: s for s in ob["steps"]}
    assert steps["first_client"]["done"] is True  # console_world seeds one client
    assert steps["agent_published"]["done"] is False
    assert steps["team"]["done"] is False
    assert steps["agent_published"]["href"] == f"/clients/{a['ref']}/agent"

    # Publish v1 via seed, then activate.
    await db_session.execute(
        sa.update(Tenant)
        .where(Tenant.id == a["tenant_id"])
        .values(status=TenantStatus.PROVISIONING)
    )
    await db_session.commit()
    r = await client.post(
        f"/console/clients/{a['ref']}/agent/from-seed",
        headers=h(),
        json={
            "seed_template": "generic_v1",
            "placeholders": {"tenant.address": "x", "tenant.business_hours_label": "y"},
        },
    )
    assert r.status_code == 201, r.text
    r = await client.post(f"/console/clients/{a['ref']}/agent/versions/1/publish", headers=h())
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/console/clients/{a['ref']}/status", headers=h(), json={"status": "active"}
    )
    assert r.status_code == 200, r.text

    partner = await db_session.get(Partner, a["partner_id"])
    assert partner is not None
    await db_session.refresh(partner)
    assert partner.activated_at is not None

    r = await client.get("/console/onboarding", headers=h())
    ob = r.json()
    assert ob["activated_at"] is not None
    assert isinstance(ob["time_to_first_active_client_seconds"], int)
    assert ob["time_to_first_active_client_seconds"] >= 0
    steps = {s["key"]: s for s in ob["steps"]}
    assert steps["agent_published"]["done"] is True
    assert ob["done_count"] == 2 and ob["complete"] is False

    r = await client.get("/console/notifications", headers=h())
    activated = [n for n in r.json()["items"] if n["kind"] == "client.activated"]
    assert len(activated) == 1
    assert activated[0]["external_client_ref"] == a["ref"]
    assert activated[0]["data"]["first"] is True

    # Pause + reactivate: no second activation notification, activated_at unchanged.
    stamp = partner.activated_at
    for target in ("paused", "active"):
        r = await client.post(
            f"/console/clients/{a['ref']}/status", headers=h(), json={"status": target}
        )
        assert r.status_code == 200
    await db_session.refresh(partner)
    assert partner.activated_at == stamp
    r = await client.get("/console/notifications", headers=h())
    assert len([n for n in r.json()["items"] if n["kind"] == "client.activated"]) == 1

    # Team step: one invitation is enough.
    inv = await client.post(
        "/console/team/invitations", headers=h(), json={"email": "t@example.com", "role": "analyst"}
    )
    assert inv.status_code == 201
    r = await client.get("/console/onboarding", headers=h())
    assert {s["key"]: s["done"] for s in r.json()["steps"]}["team"] is True


async def test_agent_config_versions_status_enum_is_used(console_world) -> None:
    # Guard: the enum name this lane relies on for "published".
    assert AgentConfigStatus.ACTIVE.value == "active"
