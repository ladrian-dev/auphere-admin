"""Spec 048 (requirement 3; T028) — the automatic pass to Reservas.

Called by ``apps/api/scripts/release.sh`` in the migration task, after
``alembic upgrade head`` and the connectors seed. Every client with an active
agent whose active version or draft names ``booking.*`` passes to Reservas,
each one in its own transaction under its RLS
(``services/reservations/auto_pass.py``).

It goes to the DIRECT database, like Alembic: the pooler's name does not
resolve in that task (``get_direct_engine``).

It exits 0 even when a client fails: that client is rolled back alone and
logged (``reservations.auto_pass_failed``), and the summary is
``reservations.auto_pass_done``. Only a crash outside a client exits 1, and
``release.sh`` goes on anyway: the deploy never stops here.

Manual usage (it can be repeated: a client that already passed is skipped)::

    uv run --directory apps/api python scripts/pass_booking_to_reservas.py
"""

from __future__ import annotations

import asyncio
import sys

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.base import dispose_engine, get_direct_engine
from nexus_api.logging import configure_logging
from nexus_api.services.reservations import auto_pass

log = structlog.get_logger(__name__)


async def main() -> int:
    factory = async_sessionmaker(get_direct_engine(), expire_on_commit=False)
    try:
        summary = await auto_pass.run(factory)
    except Exception as exc:
        log.error("reservations.auto_pass_crashed", error=auto_pass.describe_error(exc))
        print(f"reservas pass: crashed ({type(exc).__name__})")
        return 1
    finally:
        await dispose_engine()
    print(
        f"reservas pass: passed={len(summary.passed)} failed={len(summary.failed)} "
        f"published={summary.published} drafts={summary.drafts} "
        f"imported={summary.imported} not_imported={summary.not_imported}"
    )
    return 0


if __name__ == "__main__":
    configure_logging()
    sys.exit(asyncio.run(main()))
