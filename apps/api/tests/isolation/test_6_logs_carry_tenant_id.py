"""Garantía 6 — Log + trace tagging.

Once a request resolves a tenant, structlog binds tenant_id; every subsequent
log call within the request carries it. structlog's ConsoleRenderer (dev) and
JSONRenderer (prod) both pull from contextvars via the merge_contextvars
processor.
"""

from __future__ import annotations

import io
import uuid

import pytest
import structlog

from nexus_api.core.logging_context import bind_tenant

pytestmark = [pytest.mark.isolation]


@pytest.fixture(autouse=True)
def _restore_structlog_config():
    """Devolver structlog EXACTAMENTE como estaba, no a la config de prod.

    Estos tests reconfiguran structlog para leer su salida. La versión
    anterior restauraba llamando a ``configure_logging()``, que impone la
    configuración de producción — y con ella
    ``cache_logger_on_first_use=True`` — al resto del proceso. A partir de
    ahí, ``structlog.testing.capture_logs()`` de cualquier test posterior
    no intercepta nada (el logger ya está cacheado en su proxy) y el test
    ve una lista vacía: eso hacía fallar
    ``test_direct_message_log_trail`` cuando CI corre aislamiento e
    integración en el MISMO proceso, que es lo que hace.
    """
    saved = structlog.get_config()
    try:
        yield
    finally:
        structlog.contextvars.clear_contextvars()
        structlog.configure(**saved)


def _fresh_capture():
    """Reconfigure structlog to write into a StringIO and return it.

    We rebuild the configuration from scratch (cache_logger_on_first_use is
    OFF here) so each test gets a clean buffer.
    """
    buffer = io.StringIO()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(10),
        logger_factory=structlog.PrintLoggerFactory(file=buffer),
        cache_logger_on_first_use=False,
    )
    return buffer


def _restore_default_logging():
    """No-op: la restauración la hace el fixture ``_restore_structlog_config``,
    que devuelve la configuración previa en vez de imponer la de producción.
    Se conserva la llamada en los ``finally`` para no tocar la forma de los
    tests."""


def test_bind_tenant_attaches_to_log_records():
    structlog.contextvars.clear_contextvars()
    buffer = _fresh_capture()
    try:
        tid = uuid.uuid4()
        bind_tenant(tid, channel_id=uuid.uuid4())
        log = structlog.get_logger()
        log.info("test.event", foo="bar")
        output = buffer.getvalue()
        assert "tenant_id" in output
        assert str(tid) in output
        assert "channel_id" in output
    finally:
        structlog.contextvars.clear_contextvars()
        _restore_default_logging()


def test_bind_tenant_with_no_tenant_is_noop():
    structlog.contextvars.clear_contextvars()
    buffer = _fresh_capture()
    try:
        bind_tenant(None)
        log = structlog.get_logger()
        log.info("test.no_tenant")
        output = buffer.getvalue()
        assert "tenant_id" not in output
    finally:
        structlog.contextvars.clear_contextvars()
        _restore_default_logging()


def test_distinct_tenants_log_distinct_ids():
    """Repeated bind_tenant calls update the binding (last writer wins per request)."""
    structlog.contextvars.clear_contextvars()
    buffer = _fresh_capture()
    try:
        a = uuid.uuid4()
        b = uuid.uuid4()
        bind_tenant(a)
        log = structlog.get_logger()
        log.info("event_a")
        structlog.contextvars.clear_contextvars()
        bind_tenant(b)
        log.info("event_b")
        output = buffer.getvalue()
        a_line = next(line for line in output.splitlines() if "event_a" in line)
        b_line = next(line for line in output.splitlines() if "event_b" in line)
        assert str(a) in a_line
        assert str(b) in b_line
        assert str(b) not in a_line
        assert str(a) not in b_line
    finally:
        structlog.contextvars.clear_contextvars()
        _restore_default_logging()
