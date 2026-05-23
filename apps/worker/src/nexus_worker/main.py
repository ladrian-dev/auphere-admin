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
from nexus_mcp.servers.agendapro_public.transport import (
    build_default_pool_from_env as build_agendapro_public_pool_from_env,
)
from nexus_mcp.servers.agendapro_public.transport import (
    set_default_transport as set_agendapro_public_transport,
)

from nexus_worker.config import get_api_settings, get_worker_settings
from nexus_worker.guardrails import OutcomeGrader
from nexus_worker.logging import configure_logging
from nexus_worker.observability import init_langfuse
from nexus_worker.observability import shutdown as langfuse_shutdown
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.checkpointer import postgres_checkpointer
from nexus_worker.runtime.llm import LiteLLMProvider, build_default_router
from nexus_worker.runtime.pipeline import build_pipeline
from nexus_worker.runtime.promote_subscriber import run_promote_subscriber
from nexus_worker.streams.async_booking_cron import run_async_booking_cron
from nexus_worker.streams.consumer import run_inbound_consumer
from nexus_worker.streams.continuous_eval_cron import run_continuous_eval_cron
from nexus_worker.streams.cost_rollup_cron import run_cost_rollup_cron
from nexus_worker.streams.isolation_watcher import run_isolation_watcher
from nexus_worker.streams.memory_versions_retention import (
    run_memory_versions_retention_cron,
)
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

    # Block O: AgendaPro public-link Node MCP subprocess pool. Configured
    # lazily so the worker can boot in test/dev where the Node binary or
    # Browserbase keys may be absent — the cron picks up the absence and
    # parks jobs with a descriptive error instead of crashing the worker.
    agendapro_public_pool = build_agendapro_public_pool_from_env()
    set_agendapro_public_transport(agendapro_public_pool)

    def _request_stop() -> None:
        log.info("worker.signal_received_stopping")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_stop)

    # Fase C — outcome grader. Independent provider (no router) so the
    # guardrail call doesn't ride the agent's retry chain. When
    # ``llm_use_inmemory`` is on (dev/test) we skip construction so
    # the pipeline doesn't try to call out without API keys.
    outcome_grader: OutcomeGrader | None = None
    if not worker_settings.llm_use_inmemory:
        outcome_grader = OutcomeGrader(provider=LiteLLMProvider())

    async with postgres_checkpointer(api_settings.database_url) as saver:
        pipeline = build_pipeline(
            agent_loader=loader,
            llm_router=router,
            checkpointer=saver,
            outcome_grader=outcome_grader,
        )
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
        # Block O: AgendaPro public-link async booking cron — drains
        # ``scheduled_jobs(kind=async_booking)`` and drives the public
        # wizard via the Node MCP subprocess pool.
        async_booking_task = asyncio.create_task(
            run_async_booking_cron(stop=stop),
            name="async-booking-cron",
        )
        # Roadmap E2.3: continuous evals against each tenant's ACTIVE
        # config. OFF unless ``NEXUS_CONTINUOUS_EVAL_ENABLED`` is set.
        continuous_eval_task = asyncio.create_task(
            run_continuous_eval_cron(
                stop=stop,
                enabled=worker_settings.continuous_eval_enabled,
                tick_seconds=worker_settings.continuous_eval_tick_seconds,
            ),
            name="continuous-eval-cron",
        )
        # Fase B: drain agent_memory_versions older than the retention
        # window (default 30 days). One sweep per day is plenty.
        memory_retention_task = asyncio.create_task(
            run_memory_versions_retention_cron(
                stop=stop,
                tick_seconds=worker_settings.memory_retention_tick_seconds,
            ),
            name="memory-versions-retention-cron",
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
                async_booking_task,
                continuous_eval_task,
                memory_retention_task,
            )
        finally:
            await ycloud_client.close()
            with contextlib.suppress(Exception):
                await agendapro_public_pool.shutdown()
            langfuse_shutdown()


def run() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
