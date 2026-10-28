"""La consola nueva es la de todos los partners (Andrés, 2026-10-29).

Ya no se activa partner a partner: lo que el panel enciende o apaga por partner
son los módulos (spec 032). Por eso:

- un partner nace con la consola nueva, lo cree Auphere desde el panel o se dé de
  alta solo (el registro lo prueba ``test_signup_flow``);
- el ensayo, la activación y la desactivación desaparecen de la API del panel.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Partner

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_a_partner_created_from_the_panel_is_born_on_the_new_console(
    client: Any, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    slug = f"todos-{uuid.uuid4().hex[:8]}"
    created = await client.post(
        "/admin/partners", headers=admin_headers, json={"name": "Agencia Todos", "slug": slug}
    )
    assert created.status_code == 201, created.text
    async with db_session.begin():
        partner = await db_session.scalar(sa.select(Partner).where(Partner.slug == slug))
    assert partner is not None
    assert partner.console_v2_enabled_at is not None


async def test_the_panel_no_longer_switches_the_console_per_partner(
    client: Any, db_session: AsyncSession, admin_headers: dict[str, str]
) -> None:
    pid = uuid.uuid4()
    async with db_session.begin():
        db_session.add(Partner(id=pid, name="Sin interruptor", slug=f"sin-{pid.hex[:8]}"))
    for path in ("console-v2", "console-v2/reports"):
        resp = await client.get(f"/admin/partners/{pid}/{path}", headers=admin_headers)
        assert resp.status_code == 404, path
    for action in ("dry-run", "enable", "disable"):
        resp = await client.post(
            f"/admin/partners/{pid}/console-v2/{action}", headers=admin_headers, json={}
        )
        assert resp.status_code in (404, 405), action
