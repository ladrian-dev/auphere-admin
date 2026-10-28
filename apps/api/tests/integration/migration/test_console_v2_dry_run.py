"""Spec 047, T179 — el ensayo y la activación de la consola nueva (requisitos 55.1,
55.4 y 55.5; CE-009).

Con los datos de un partner de hoy, cada agente compila el mismo prompt y sigue en
su modelo, y cada número responde a los mismos; el informe se escribe; cualquier
diferencia bloquea la activación; y desactivar solo se puede hasta confirmar el
reparto en bolsas.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConfig,
    Channel,
    ChannelAudienceNumber,
    Partner,
    WalletMigrationProposal,
)
from nexus_api.services.agent_spec.legacy import spec_from_version
from nexus_api.services.agent_spec.schema import dump
from tests.integration.clients._client_world import add_agent

pytestmark = [pytest.mark.integration]


async def _operator(db_session: Any, admin_headers: dict[str, str]) -> dict[str, str]:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return {**admin_headers, "X-Operator-Id": str(account.id)}


async def _legacy_agent(
    db_session: Any, tenant_id: uuid.UUID, name: str, policies: dict[str, Any]
) -> dict[str, Any]:
    """Un agente de hoy, migrado como lo deja la 0189 (AgentSpec «instrucciones») y
    con su número aún sin audiencia de canal (``unset``), como antes de la 0192."""
    agent = await add_agent(db_session, tenant_id, name, audience="unset")
    async with tenant_scoped_session(db_session, tenant_id):
        version = await db_session.scalar(
            sa.select(AgentConfig).where(AgentConfig.agent_id == agent["agent_id"])
        )
        assert version is not None
        version.policies = policies
        version.spec = dump(
            spec_from_version(
                agent_name=name,
                system_prompt_rendered=version.system_prompt_rendered,
                tools=list(version.tools or []),
                policies=policies,
            )
        )
    await db_session.commit()
    return agent


async def test_a_clean_dry_run_reports_and_lets_activate(
    client: Any, db_session: Any, console_world: dict[str, Any], admin_headers: dict[str, str]
) -> None:
    a = console_world["a"]
    headers = await _operator(db_session, admin_headers)
    team = await _legacy_agent(
        db_session,
        a["tenant_id"],
        "Citas",
        {"admin_access": {"admin_only": True, "admin_phones": ["+34 600 111 222"]}},
    )
    await _legacy_agent(db_session, a["tenant_id"], "Ventas", {})
    base = f"/admin/partners/{a['partner_id']}/console-v2"

    early = await client.post(f"{base}/enable", headers=headers)
    assert early.status_code == 409 and early.json()["detail"]["code"] == "dry_run_required"

    run = await client.post(
        f"{base}/dry-run", json={"reason": "Ensayo antes del piloto"}, headers=headers
    )
    assert run.status_code == 200, run.text
    report = run.json()
    assert report["status"] == "clean", report
    assert {a_["agent_name"] for a_ in report["agents"]} == {"Citas", "Ventas"}
    assert {a_["prompt_identical"] for a_ in report["agents"]} == {True}
    assert {a_["model_pinned"] for a_ in report["agents"]} == {True}
    by_channel = {c["channel_id"]: c for c in report["channels"]}
    citas = by_channel[str(team["channel_id"])]
    assert citas["before"] == {"mode": "team_only", "numbers": ["+34600111222"]}
    assert citas["pending_migration"] is True and citas["same"] is True
    async with tenant_scoped_session(db_session, a["tenant_id"]):
        channel = await db_session.get(Channel, team["channel_id"], populate_existing=True)
        assert channel is not None and channel.audience_mode == "unset", "el ensayo no cambia nada"
    await db_session.commit()

    enabled = await client.post(f"{base}/enable", headers=headers)
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["version"] == "v2"
    async with tenant_scoped_session(db_session, a["tenant_id"]):
        channel = await db_session.get(Channel, team["channel_id"], populate_existing=True)
        assert channel is not None and channel.audience_mode == "team_only"
        numbers = (
            await db_session.scalars(
                sa.select(ChannelAudienceNumber.phone_e164).where(
                    ChannelAudienceNumber.channel_id == team["channel_id"]
                )
            )
        ).all()
    await db_session.commit()
    assert list(numbers) == ["+34600111222"], "la misma audiencia, ahora en el canal"
    reports = (await client.get(f"{base}/reports", headers=headers)).json()
    assert [r["kind"] for r in reports] == ["activation", "dry_run"]
    assert reports[1]["reason"] == "Ensayo antes del piloto"
    assert {c["client_name"] for c in reports[1]["channels"]} == {"Client A One"}
    assert all(c["identifier"] for c in reports[1]["channels"])
    state = (await client.get(base, headers=headers)).json()
    assert state["version"] == "v2" and state["enabled_by"]


async def test_any_difference_blocks_the_activation(
    client: Any, db_session: Any, console_world: dict[str, Any], admin_headers: dict[str, str]
) -> None:
    a = console_world["a"]
    headers = await _operator(db_session, admin_headers)
    agent = await _legacy_agent(db_session, a["tenant_id"], "Citas", {})
    async with tenant_scoped_session(db_session, a["tenant_id"]):
        version = await db_session.scalar(
            sa.select(AgentConfig).where(AgentConfig.agent_id == agent["agent_id"])
        )
        assert version is not None
        # Alguien tocó el prompt de hoy después de migrarlo: ya no son los mismos bytes.
        version.system_prompt_rendered = "Eres Citas. Y otra cosa."
        channel = await db_session.get(Channel, agent["channel_id"])
        assert channel is not None
        channel.audience_mode = "everyone"
        db_session.add(
            ChannelAudienceNumber(
                tenant_id=a["tenant_id"],
                channel_id=channel.id,
                kind="exception",
                phone_e164="+56911112222",
            )
        )
    await db_session.commit()
    base = f"/admin/partners/{a['partner_id']}/console-v2"
    run = (await client.post(f"{base}/dry-run", headers=headers)).json()
    assert run["status"] == "diff"
    (row,) = run["agents"]
    assert row["prompt_identical"] is False
    (channel_row,) = run["channels"]
    assert channel_row["same"] is False and channel_row["after"]["exceptions"] == ["+56911112222"]
    blocked = await client.post(f"{base}/enable", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "dry_run_has_differences"
    partner = await db_session.get(Partner, a["partner_id"], populate_existing=True)
    assert partner is not None and partner.console_v2_enabled_at is None


async def test_disabling_is_possible_only_until_the_wallet_split_is_confirmed(
    client: Any, db_session: Any, console_world: dict[str, Any], admin_headers: dict[str, str]
) -> None:
    a = console_world["a"]
    headers = await _operator(db_session, admin_headers)
    base = f"/admin/partners/{a['partner_id']}/console-v2"
    assert (await client.post(f"{base}/dry-run", headers=headers)).json()["status"] == "clean"
    assert (await client.post(f"{base}/enable", headers=headers)).status_code == 200
    back = await client.post(f"{base}/disable", headers=headers)
    assert back.status_code == 200 and back.json()["version"] == "v1"

    assert (await client.post(f"{base}/dry-run", headers=headers)).status_code == 200
    assert (await client.post(f"{base}/enable", headers=headers)).status_code == 200
    async with db_session.begin():
        await apply_partner_to_session(db_session, a["partner_id"])
        db_session.add(
            WalletMigrationProposal(
                partner_id=a["partner_id"],
                proposal={},
                confirmed_at=datetime.now(UTC),
                confirmed_by="console:owner",
            )
        )
    stuck = await client.post(f"{base}/disable", headers=headers)
    assert stuck.status_code == 409
    assert stuck.json()["detail"]["code"] == "wallet_split_confirmed"
