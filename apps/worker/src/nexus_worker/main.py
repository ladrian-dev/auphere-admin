"""Worker entry point.

Boots:
- Postgres checkpointer (``AsyncPostgresSaver`` with ``setup()``).
- AgentLoader + promote-channel subscriber.
- LiteLLM router.
- Redis Stream consumer (inbound).
- Outbound dispatcher (drains ``messages.status='pending'`` to YCloud),
  operator alerter (audit_log → WhatsApp template to operator), reminder
  cron (drains ``scheduled_jobs`` of kind=reminder).

ADR-017 / migration 0021 removed the AgendaPro admin browser MCP and
the per-tenant subprocess pool that booted it. The new public-link
MCP (future session) will register its transport here when it lands.

Production runs this; tests build the same components piece-by-piece in
fixtures so they can substitute the in-memory provider, the in-memory
checkpointer and a fake Redis.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

import structlog
from nexus_api.config import get_settings
from nexus_api.core.metrics import isolation_event_drainer
from nexus_api.core.redis_client import get_redis
from nexus_channels.whatsapp_ycloud.adapter import WhatsAppYCloudAdapter
from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudClient

from nexus_worker.config import get_api_settings, get_worker_settings
from nexus_worker.logging import configure_logging
from nexus_worker.observability import init_langfuse
from nexus_worker.observability import shutdown as langfuse_shutdown
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.checkpointer import postgres_checkpointer
from nexus_worker.runtime.llm import build_default_router
from nexus_worker.runtime.pipeline import build_pipeline
from nexus_worker.runtime.promote_subscriber import run_promote_subscriber
from nexus_worker.streams.consumer import run_inbound_consumer
from nexus_worker.streams.cost_rollup_cron import run_cost_rollup_cron
from nexus_worker.streams.isolation_watcher import run_isolation_watcher
from nexus_worker.streams.no_show_scrape_cron import run_no_show_scrape_cron
from nexus_worker.streams.operator_alerts import run_operator_alerter
from nexus_worker.streams.outbound import run_outbound_dispatcher
from nexus_worker.streams.reminder_cron import run_reminder_cron
from nexus_worker.streams.whatsapp_health_cron import run_whatsapp_health_cron

configure_logging()

log = structlog.get_logger(__name__)


async def _amain() -> None:
    api_settings = get_api_settings()
    worker_settings = get_worker_settings()
    nexus_settings = get_settings()

    # Block H: Langfuse must initialise BEFORE LiteLLM picks up the
    # ``litellm.success_callback`` hook. Noop client when keys are
    # absent (dev/test).
    init_langfuse(worker_settings)

    loader = AgentLoader(max_size=worker_settings.agent_cache_size)
    router = build_default_router(
        classify_model=worker_settings.llm_classify_model,
        respond_model=worker_settings.llm_respond_model,
        fallback_model=worker_settings.llm_fallback_model,
        use_inmemory=worker_settings.llm_use_inmemory,
    )
    redis = get_redis()
    stop = asyncio.Event()

    # Block F: a single YCloud client + adapter shared across the outbound
    # dispatcher and the operator alerter. Per-tenant API keys are a Phase
    # 4+ white-label concern; the BSP-level key here is Auphere's.
    ycloud_client = YCloudClient(
        api_key=nexus_settings.ycloud_api_key,
        base_url=nexus_settings.ycloud_api_base_url,
    )
    whatsapp_adapter = WhatsAppYCloudAdapter(ycloud_client)

    def _request_stop() -> None:
        log.info("worker.signal_received_stopping")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_stop)

    async with postgres_checkpointer(api_settings.database_url) as saver:
        pipeline = build_pipeline(agent_loader=loader, llm_router=router, checkpointer=saver)
        promote_task = asyncio.create_task(
            run_promote_subscriber(redis, loader, stop=stop), name="promote-subscriber"
        )
        consumer_task = asyncio.create_task(
            run_inbound_consumer(
                redis,
                pipeline,
                stream=worker_settings.inbound_stream,
                group=worker_settings.inbound_consumer_group,
                consumer_name=worker_settings.inbound_consumer_name,
                stop=stop,
            ),
            name="inbound-consumer",
        )
        outbound_task = asyncio.create_task(
            run_outbound_dispatcher(adapter=whatsapp_adapter, stop=stop),
            name="outbound-dispatcher",
        )
        alerter_task = asyncio.create_task(
            run_operator_alerter(adapter=whatsapp_adapter, stop=stop),
            name="operator-alerter",
        )
        reminder_task = asyncio.create_task(
            run_reminder_cron(stop=stop),
            name="reminder-cron",
        )
        # Block H: persistent isolation events drainer + 3 cron streams
        # (no_show_scrape, cost_rollup, isolation_watcher). The AgendaPro
        # health-check cron was removed with the admin browser MCP
        # (migration 0021).
        drainer_task = asyncio.create_task(
            isolation_event_drainer(stop), name="isolation-event-drainer"
        )
        no_show_task = asyncio.create_task(
            run_no_show_scrape_cron(
                stop=stop, tick_seconds=worker_settings.no_show_scrape_tick_seconds
            ),
            name="no-show-scrape-cron",
        )
        cost_rollup_task = asyncio.create_task(
            run_cost_rollup_cron(stop=stop, tick_seconds=worker_settings.cost_rollup_tick_seconds),
            name="cost-rollup-cron",
        )
        isolation_watcher_task = asyncio.create_task(
            run_isolation_watcher(
                stop=stop, tick_seconds=worker_settings.isolation_watcher_tick_seconds
            ),
            name="isolation-watcher",
        )
        # Block N: WhatsApp WABA health (quality_rating + display_name).
        whatsapp_health_task = asyncio.create_task(
            run_whatsapp_health_cron(stop=stop),
            name="whatsapp-health-cron",
        )
        try:
            await asyncio.gather(
                consumer_task,
                promote_task,
                outbound_task,
                alerter_task,
                reminder_task,
                drainer_task,
                no_show_task,
                cost_rollup_task,
                isolation_watcher_task,
                whatsapp_health_task,
            )
        finally:
            await ycloud_client.close()
            langfuse_shutdown()


def run() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
