"""Spec 058 (requirement 3; T011) — release the waits a pause opened for contacts
outside the audience of their number. By hand only.

Until spec 058, a contact outside the audience who wrote to a paused client (or
to a paused channel or agent) opened «Espera a una persona» and notified the
client's people. The turn no longer does it. This closes the waits that are
already there (``services/audience_cleanup.py``).

**Dry run unless ``--apply``**: it prints what it would release per client and
touches nothing. **No deploy runs it** (requirement 3.6): ``release.sh`` does not
call it, like ``pass_booking_to_reservas.py`` since 2026-11-10.

It goes to the DIRECT database, like Alembic: the pooler's name does not
resolve in a one-off task (``get_direct_engine``).

It exits 0 even when a client fails: that client is rolled back alone and logged
(``inbox.audience_cleanup.tenant_failed``), and the summary is
``inbox.audience_cleanup.done``. Only a crash outside a client exits 1.

Usage (it can be repeated: a second run releases nothing)::

    uv run --directory apps/api python scripts/release_out_of_audience_waits.py
    uv run --directory apps/api python scripts/release_out_of_audience_waits.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.base import dispose_engine, get_direct_engine
from nexus_api.logging import configure_logging
from nexus_api.services import audience_cleanup

log = structlog.get_logger(__name__)


async def main(*, apply: bool) -> int:
    factory = async_sessionmaker(get_direct_engine(), expire_on_commit=False)
    try:
        summary = await audience_cleanup.run(factory, apply=apply)
    except Exception as exc:
        log.error("inbox.audience_cleanup.crashed", error=type(exc).__name__)
        print(f"audience cleanup: crashed ({type(exc).__name__})")
        return 1
    finally:
        await dispose_engine()
    verb = "released" if apply else "would release (dry run; --apply to write)"
    print(
        f"audience cleanup: {verb}={summary.released} tenants={summary.tenants} "
        f"skipped_not_strict={summary.skipped_not_strict} failed={summary.failed}"
    )
    return 0


def _args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the changes; without it, only count (dry run)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    configure_logging()
    sys.exit(asyncio.run(main(apply=_args(sys.argv[1:]).apply)))
