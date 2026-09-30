"""Worker logging configuration.

Block H formalises what the API has had since block A: in dev the
console renderer (colorful, human-readable); in prod (everywhere
``NEXUS_ENVIRONMENT`` != ``dev``) the JSON renderer for ingestion by
Railway / Loki / Datadog.

Each log record automatically carries:

- ``request_id`` (set by the inbound consumer per turn)
- ``tenant_id`` + ``channel_id`` (set by the dispatcher)
- ``trace_id`` (set when a Langfuse trace is active — block H)

Bindings live in ``structlog.contextvars`` so any module's logger
inherits them without explicit forwarding.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from nexus_api.config import settings


def configure_logging() -> None:
    """Idempotent — safe to call from worker ``main`` and from tests."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
    ]

    if settings.environment == "dev":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    # A token in a query string ends up in the log line httpx writes at
    # INFO ("HTTP Request: GET https://…?access_token=…"). The Meta client
    # sends it in a header now (2026-09-30), and this keeps httpx quiet
    # unless something is actually wrong.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
