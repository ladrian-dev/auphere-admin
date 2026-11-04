import logging
import sys
from typing import Any

import structlog

from nexus_api.config import settings
from nexus_api.core.logging_context import RedactAccessLog


def configure_logging() -> None:
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
    # Spec 052 (CE-005): abrir un enlace con token no lo deja en el registro.
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactAccessLog) for f in access.filters):
        access.addFilter(RedactAccessLog())
