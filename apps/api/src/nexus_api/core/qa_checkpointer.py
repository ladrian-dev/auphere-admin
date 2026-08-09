"""Process-wide ``AsyncPostgresSaver`` for the QA Playground (ADR-021, Fase 1).

The streaming Playground invokes the agent graph in-process and needs a
durable checkpointer so:
  - resumability works after a server restart;
  - ``interrupt()``-based HITL has a place to store the paused state;
  - history hydration on a thread can fall back to LangGraph state when
    the operator hasn't seen the messages this session.

We use ``langgraph.checkpoint.postgres.aio.AsyncPostgresSaver`` (OSS,
Apache 2.0) backed by a single ``psycopg_pool.AsyncConnectionPool`` open
for the lifetime of the FastAPI app. The pool, the saver, and the
``setup()`` call are all process-wide singletons that ``main.lifespan``
manages.

Schema isolation
----------------
The saver creates its tables (``checkpoints``, ``checkpoint_writes``,
``checkpoint_blobs``, ``checkpoint_migrations``) with unqualified names,
landing them in the connection's first ``search_path`` schema. We force
that to ``langgraph,public`` via the connection-string ``options`` so
the saver's tables land in the dedicated schema created by migration
0029, and any incidental query the saver runs against ``public`` (e.g.
``gen_random_uuid``) still resolves.

RLS / isolation
---------------
The saver opens its own connections from the pool — they do NOT go
through ``apply_operator_to_session`` / ``SET LOCAL ROLE nexus_app``.
This is by design: the saver speaks DDL during setup and the saver's
own data model has no operator column. Isolation is enforced one layer
up: an operator can only reach the saver via a ``qa.threads.id`` they
own (RLS on ``qa.threads`` + ``qa.runs``), so they can only request
checkpoints whose ``thread_id`` is their thread. There is no path from
the API that lets an operator pass an arbitrary ``thread_id`` to the
saver.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

import structlog

from nexus_api.config import settings

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool

log = structlog.get_logger(__name__)


_pool: AsyncConnectionPool | None = None
_saver: AsyncPostgresSaver | None = None


def _psycopg_conn_string() -> str:
    """Turn the SQLAlchemy + asyncpg URL into a plain psycopg URL.

    SQLAlchemy uses ``postgresql+asyncpg://`` but psycopg expects
    ``postgresql://``. We also append ``options=-c search_path=langgraph,public``
    so the saver's CREATE TABLE / INSERT / SELECT all land in the
    dedicated schema instead of polluting ``public``.

    WP-15: SIEMPRE por la URL directa — PgBouncer rechaza el parámetro de
    arranque ``options`` ("unsupported startup parameter"), y este saver
    mantiene un pool de sesión larga que no gana nada multiplexado.
    """
    url = settings.database_url_direct or settings.database_url
    # Strip the SQLAlchemy driver prefix — psycopg uses the bare scheme.
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
        if url.startswith(prefix):
            url = "postgresql://" + url[len(prefix) :]
            break
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}options={quote('-c search_path=langgraph,public')}"


async def init_qa_checkpointer() -> AsyncPostgresSaver:
    """Open the pool, run ``setup()`` once, cache the saver.

    Idempotent: subsequent calls return the cached saver. Called from
    the FastAPI lifespan at app startup.
    """
    global _pool, _saver
    if _saver is not None:
        return _saver

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    conn_string = _psycopg_conn_string()
    # ``dict_row`` factory is required by AsyncPostgresSaver (it expects
    # row dicts, not tuples). Same default ``from_conn_string`` would set.
    pool = AsyncConnectionPool(
        conninfo=conn_string,
        # Bounded: even under a burst of concurrent QA turns we won't
        # outpace ``apps/api/src/nexus_api/db/base.py`` pool sizing.
        min_size=1,
        max_size=8,
        # The saver does autocommit operations + its own transactions
        # depending on the call. Default is fine.
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open(wait=True, timeout=10.0)
    saver = AsyncPostgresSaver(conn=pool)  # type: ignore[arg-type]
    await saver.setup()
    _pool = pool
    _saver = saver
    log.info("qa.checkpointer.ready", schema="langgraph")
    return saver


def get_qa_checkpointer() -> AsyncPostgresSaver:
    """Return the cached saver. Must run after ``init_qa_checkpointer``."""
    if _saver is None:
        raise RuntimeError(
            "qa checkpointer not initialised — main.lifespan should call "
            "init_qa_checkpointer() at startup before any /qa endpoint runs"
        )
    return _saver


async def close_qa_checkpointer() -> None:
    """Tear down the pool. Called from the FastAPI lifespan at shutdown."""
    global _pool, _saver
    if _pool is not None:
        await _pool.close()
    _pool = None
    _saver = None
    log.info("qa.checkpointer.closed")
