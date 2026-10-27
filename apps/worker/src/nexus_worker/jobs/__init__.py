"""Los trabajos largos de la consola — spec 047 (ola 0, research D43).

- ``registry``: un manejador por tipo de trabajo, con su plazo;
- ``store``: la fila del trabajo, con las transiciones de ``nexus_api.services.jobs``;
- ``consumer``: ``jobs-consumer``, que lee ``nexus:jobs`` y despacha por tipo.
"""

from __future__ import annotations

from nexus_worker.jobs.consumer import (
    JOBS_GROUP,
    drain_once,
    process_entry,
    reclaim_once,
    run_jobs_consumer,
)
from nexus_worker.jobs.registry import (
    INTERNAL,
    INTERRUPTED,
    NO_HANDLER,
    TIMEOUT,
    HandlerSpec,
    JobContext,
    JobFailed,
    JobHandler,
    JobOutcome,
    JobRegistry,
    StartedJob,
    default_registry,
)
from nexus_worker.jobs.store import DbJobStore, JobStore

# Los manejadores se registran en ``default_registry`` al importarse: el
# registro que usa ``jobs-consumer`` los tiene desde el arranque.
from nexus_worker.jobs import handlers  # noqa: F401  isort: skip

__all__ = [
    "INTERNAL",
    "INTERRUPTED",
    "JOBS_GROUP",
    "NO_HANDLER",
    "TIMEOUT",
    "DbJobStore",
    "HandlerSpec",
    "JobContext",
    "JobFailed",
    "JobHandler",
    "JobOutcome",
    "JobRegistry",
    "JobStore",
    "StartedJob",
    "default_registry",
    "drain_once",
    "process_entry",
    "reclaim_once",
    "run_jobs_consumer",
]
