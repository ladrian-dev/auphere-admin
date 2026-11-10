"""Lo común de las pruebas de Negocio (spec 047, T052 a T054).

Un cliente nacido con el alta en tres datos (su ficha y sus nueve secciones),
la consola de su partner con su token, y ayudas para escribir una sección con
``If-Match`` y para sembrar agentes con su versión activa.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Partner,
    PartnerTenant,
    Tenant,
)


@dataclass
class Biz:
    ref: str
    tenant_id: uuid.UUID
    partner_id: uuid.UUID
    headers: Any

    @property
    def url(self) -> str:
        return f"/console/clients/{self.ref}/business"


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    """Barbería Cultor, en Madrid, creada por la consola nueva."""
    return await new_business(client, db_session, console_world, name="Barbería Cultor")


async def new_business(
    client: Any,
    db_session: AsyncSession,
    console_world: dict[str, Any],
    *,
    name: str,
    label: str = "a",
    country: str = "ES",
    timezone: str = "Europe/Madrid",
    price_currency: str = "EUR",
) -> Biz:
    a = console_world[label]
    partner = await db_session.get(Partner, a["partner_id"])
    assert partner is not None
    partner.max_clients = 50
    await db_session.commit()
    resp = await client.post(
        "/console/clients",
        json={
            "name": name,
            "niche": "Barbería de barrio",
            "country": country,
            "timezone": timezone,
            "price_currency": price_currency,
        },
        headers=a["headers"](),
    )
    assert resp.status_code == 201, resp.text
    ref = resp.json()["ref"]
    async with db_session.begin():
        tenant_id = await db_session.scalar(
            sa.select(PartnerTenant.tenant_id).where(
                PartnerTenant.partner_id == a["partner_id"],
                PartnerTenant.external_client_ref == ref,
            )
        )
    assert tenant_id is not None
    return Biz(ref=ref, tenant_id=tenant_id, partner_id=a["partner_id"], headers=a["headers"])


def if_match(revision: int) -> dict[str, str]:
    return {"If-Match": f'"{revision}"'}


async def write(
    client: Any,
    biz: Biz,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    revision: int | None,
    expect: int = 200,
) -> dict[str, Any]:
    headers = biz.headers()
    if revision is not None:
        headers.update(if_match(revision))
    resp = await client.request(method, biz.url + path, json=body, headers=headers)
    assert resp.status_code == expect, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def read(client: Any, biz: Biz, path: str) -> dict[str, Any]:
    resp = await client.get(biz.url + path, headers=biz.headers())
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def seed_agent(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str,
    prompt: str,
    serves_all: bool = True,
    tools: list[str] | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Un agente con su versión activa. ``(agent_id, agent_config_id)``."""
    async with tenant_scoped_session(db_session, tenant_id):
        agent = Agent(
            id=uuid.uuid4(), tenant_id=tenant_id, name=name, serves_all_services=serves_all
        )
        db_session.add(agent)
        await db_session.flush()
        top = await db_session.scalar(
            sa.select(sa.func.coalesce(sa.func.max(AgentConfig.version), 0))
        )
        cfg = AgentConfig(
            tenant_id=tenant_id,
            agent_id=agent.id,
            version=int(top or 0) + 1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered=prompt,
            channels=[],
            tools=tools or [],
            policies={},
            seed_template_ref=None,
        )
        db_session.add(cfg)
        await db_session.flush()
        return agent.id, cfg.id


async def active_prompt(db_session: AsyncSession, tenant_id: uuid.UUID, cfg_id: uuid.UUID) -> str:
    async with tenant_scoped_session(db_session, tenant_id):
        prompt = await db_session.scalar(
            sa.select(AgentConfig.system_prompt_rendered)
            .where(AgentConfig.id == cfg_id)
            .execution_options(populate_existing=True)
        )
    assert prompt is not None
    return str(prompt)


async def projected_hours(db_session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, Any] | None:
    async with db_session.begin():
        tenant = await db_session.get(Tenant, tenant_id, populate_existing=True)
        assert tenant is not None
        return tenant.business_hours


def shifts(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"open": a, "close": b} for a, b in pairs]


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri")
SPLIT_WEEK = {d: shifts(("09:00", "14:00"), ("16:00", "20:00")) for d in WEEKDAYS}
