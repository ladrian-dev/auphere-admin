"""La consola nueva es la de todos los partners (Andrés, 2026-10-29).

- la versión sale de ``console_v2_enabled_at``: con fecha, la nueva;
- un partner que nace (desde el panel o dándose de alta solo) ya la tiene, con
  quién se la dio: el alta, no una persona.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Partner
from nexus_api.services import console_v2


def test_a_partner_with_the_date_sees_the_new_console() -> None:
    assert console_v2.console_version(Partner(console_v2_enabled_at=datetime.now(UTC))) == "v2"


def test_a_row_without_the_date_is_the_console_of_before() -> None:
    # Solo una fila escrita a mano puede no tenerla: la 0204 se la dio a todos.
    assert console_v2.console_version(Partner(console_v2_enabled_at=None)) == "v1"


async def test_a_partner_is_born_on_the_new_console(db_session: AsyncSession) -> None:
    pid = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            console_v2.born_on_new_console(Partner(id=pid, name="Nace", slug=f"nace-{pid.hex[:8]}"))
        )
    async with db_session.begin():
        partner = await db_session.scalar(sa.select(Partner).where(Partner.id == pid))
    assert partner is not None
    assert partner.console_v2_enabled_at is not None
    assert partner.console_v2_enabled_by == console_v2.BORN_ACTOR
    assert console_v2.console_version(partner) == "v2"
