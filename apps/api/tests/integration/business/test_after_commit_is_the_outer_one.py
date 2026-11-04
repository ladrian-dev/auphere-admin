"""``writes.after_commit`` corre al confirmar la transacción de fuera, como dice.

SQLAlchemy dispara ``after_commit`` también al soltar un *savepoint*, y toda escritura
de la ficha va en uno (``section_write``). Así, el aviso de un trabajo salía antes de que
su fila existiera. Lo de staging, el 2026-10-31 a las 21:26:35: ``jobs.not_startable``
con ``status: null`` para el trabajo ``tests`` ``a024f2f8``. El consumidor no ve la fila,
acusa el aviso, y el trabajo queda en cola sin nadie que lo corra.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.base import get_sessionmaker
from nexus_api.services.business.writes import after_commit, drain_after_commit

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _note(seen: list[str], name: str) -> Any:
    async def fn() -> None:
        seen.append(name)

    return fn


async def _session() -> AsyncSession:
    return get_sessionmaker()()


async def test_releasing_a_savepoint_does_not_run_it_and_the_outer_commit_does() -> None:
    seen: list[str] = []
    async with await _session() as session:
        async with session.begin():
            async with session.begin_nested():
                after_commit(session, _note(seen, "dentro"))
            await session.execute(sa.text("SELECT 1"))
            await drain_after_commit()
            assert seen == [], "la transacción de fuera aún puede deshacerlo"
        await drain_after_commit()
    assert seen == ["dentro"]


async def test_rolling_back_the_outer_transaction_drops_what_a_savepoint_left() -> None:
    seen: list[str] = []

    class Boom(Exception):
        pass

    async with await _session() as session:
        with pytest.raises(Boom):
            async with session.begin():
                async with session.begin_nested():
                    after_commit(session, _note(seen, "dentro"))
                raise Boom
        await drain_after_commit()
    assert seen == []


async def test_a_savepoint_that_rolls_back_only_drops_its_own() -> None:
    """Un ``412`` en una escritura no se lleva lo que la petición ya había dejado."""
    seen: list[str] = []

    class Boom(Exception):
        pass

    async with await _session() as session:
        async with session.begin():
            after_commit(session, _note(seen, "fuera"))
            async with session.begin_nested():
                after_commit(session, _note(seen, "buena"))
            with pytest.raises(Boom):
                async with session.begin_nested():
                    after_commit(session, _note(seen, "mala"))
                    async with session.begin_nested():
                        after_commit(session, _note(seen, "mala por dentro"))
                    raise Boom
        await drain_after_commit()
    assert seen == ["fuera", "buena"]


async def test_each_commit_of_the_same_session_runs_its_own() -> None:
    seen: list[str] = []
    async with await _session() as session:
        async with session.begin():
            after_commit(session, _note(seen, "primera"))
        await drain_after_commit()
        async with session.begin():
            after_commit(session, _note(seen, "segunda"))
        await drain_after_commit()
    assert seen == ["primera", "segunda"]
