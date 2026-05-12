"""Apply Connector seed YAMLs to the database. Idempotent.

Called by ``apps/api/scripts/release.sh`` after ``alembic upgrade head``.
Re-runs on each deploy update the catalog rows in place via
``ON CONFLICT (slug) DO UPDATE``. A change to ``auth_kind`` raises rather
than silently rewriting (would invalidate ``tenant_connectors.credentials_ref``).

Manual usage::

    uv run python apps/api/scripts/seed_connectors.py
"""

from __future__ import annotations

import asyncio
import sys

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.base import dispose_engine, get_engine
from nexus_api.logging import configure_logging
from nexus_api.services.connectors.seed_loader import load_all_seeds
from nexus_api.services.connectors.seed_runner import (
    ConnectorAuthKindChanged,
    apply_seeds,
)

configure_logging()
log = structlog.get_logger(__name__)


async def main() -> int:
    seeds = load_all_seeds()
    if not seeds:
        log.warning("seed_connectors.no_yamls_found")
        return 0
    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await apply_seeds(session, seeds)
    except ConnectorAuthKindChanged as exc:
        log.error("seed_connectors.auth_kind_changed", error=str(exc))
        return 2
    finally:
        await dispose_engine()
    log.info(
        "seed_connectors.done",
        inserted=result.inserted,
        updated=result.updated,
        unchanged=result.unchanged,
    )
    print(
        f"connectors: inserted={result.inserted} "
        f"updated={result.updated} unchanged={result.unchanged}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
