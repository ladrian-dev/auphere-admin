"""Worker entry point.

Boots:
- Postgres checkpointer (``AsyncPostgresSaver`` with ``setup()``).
- AgentLoader + promote-channel subscriber.
- LiteLLM router.
- Redis Stream consumer (inbound).
- Outbound dispatcher (drains ``messages.status='pending'`` to Meta),
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
import uuid

import structlog
from nexus_api.config import get_settings
from nexus_api.core.metrics import isolation_event_drainer
from nexus_api.core.redis_client import get_redis
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_channels.whatsapp_meta import MetaChannelAdapter, MetaClient
from nexus_channels.whatsapp_meta.credentials import MetaCredentialsRepository
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
from nexus_worker.streams.connector_reconcile_cron import run_connector_reconcile_cron
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
from nexus_worker.streams.owner_consultation_timeout_cron import (
    run_owner_consultation_timeout_sweep,
)
from nexus_worker.streams.owner_fanout import run_owner_fanout_consumer
from nexus_worker.streams.owner_fanout_sweep import run_owner_fanout_sweep
from nexus_worker.streams.owner_outbox import run_owner_outbox_dispatcher
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
    # Fallback model is hardcoded same-vendor (Anthropic Haiku) — cross-
    # provider fallback to OpenAI was unworkable because the request
    # payload carries Anthropic-only params (``context_management``,
    # ``container.skills``) that OpenAI rejects. Not configurable by env
    # var — incident 2026-05-28 showed cross-vendor fallback is a
    # footgun, not a feature.
    router = build_default_router(
        classify_model=worker_settings.llm_classify_model,
        respond_model=worker_settings.llm_respond_model,
        fallback_model="anthropic/claude-haiku-4-5",
        use_inmemory=worker_settings.llm_use_inmemory,
    )
    redis = get_redis()
    stop = asyncio.Event()

    # Meta Cloud API adapter — direct Tech Provider integration. Each
    # tenant has its OWN encrypted BISUAT + phone_number_id
    # in ``tenant_credentials`` (integration="meta_whatsapp"). The adapter is
    # stateless past construction; the credentials loader resolves the
    # per-tenant ``(phone_number_id, bisuat)`` inside a fresh tenant-scoped
    # session on each send, so RLS is the only authority on which row is read.
    meta_sm = get_sessionmaker()

    async def _load_meta_credentials(*, tenant_id: uuid.UUID) -> tuple[str, str]:
        async with meta_sm() as cred_session, tenant_scoped_session(cred_session, tenant_id):
            creds = await MetaCredentialsRepository(cred_session).get_or_raise()
            return (creds.phone_number_id, creds.bisuat)

    meta_client = MetaClient(
        app_secret=nexus_settings.meta_app_secret,
        require_appsecret_proof=nexus_settings.meta_require_appsecret_proof,
    )
    meta_adapter = MetaChannelAdapter(meta_client, credentials_loader=_load_meta_credentials)

    # Provider registry. The outbound dispatcher and operator alerter pick
    # the adapter per ``channels.provider``. Meta is the only provider; the
    # registry stays so a future channel plugs in without re-threading.
    whatsapp_adapters = {"meta": meta_adapter}

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
            run_outbound_dispatcher(adapters=whatsapp_adapters, stop=stop),
            name="outbound-dispatcher",
        )
        alerter_task = asyncio.create_task(
            run_operator_alerter(adapters=whatsapp_adapters, stop=stop),
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
        # Phase 2 backchannel — three coordinating tasks:
        #
        # 1) ``owner-fanout-consumer`` drains ``nexus:owner_fanout`` and
        #    re-enters the pipeline with the owner's reply in scope.
        # 2) ``owner-consultation-timeout-sweep`` enforces the per-tenant
        #    SLA on rows the owner never answered (re-send + park as
        #    timed_out).
        # 3) ``owner-fanout-sweep`` covers the durability hole between the
        #    webhook XADD and the consumer ack: rows that are
        #    ``status='answered'`` but never got ``result_applied_at``
        #    stamped get re-enqueued, bounded by an age window so old
        #    answers don't suddenly surface to the customer.
        owner_fanout_consumer_task = asyncio.create_task(
            run_owner_fanout_consumer(
                redis,
                pipeline,
                consumer_name=worker_settings.inbound_consumer_name + ":ownerfanout",
                stop=stop,
            ),
            name="owner-fanout-consumer",
        )
        owner_timeout_task = asyncio.create_task(
            run_owner_consultation_timeout_sweep(stop=stop),
            name="owner-consultation-timeout-sweep",
        )
        owner_fanout_sweep_task = asyncio.create_task(
            run_owner_fanout_sweep(redis, stop=stop),
            name="owner-fanout-sweep",
        )
        # Composio connector status auto-reconciliation — closes the
        # webhook-miss gap (installs stuck in ``pending``) and detects
        # upstream token expiry without waiting for a failed tool call.
        connector_reconcile_task = asyncio.create_task(
            run_connector_reconcile_cron(stop=stop),
            name="connector-reconcile-cron",
        )
        # Owner outbox — drains ``owner_consultations.status='pending'``
        # and sends the consult template to the owner via the Auphere
        # backchannel number (Meta). Without this task the rows inserted
        # by ``operator.consult_owner`` were never delivered.
        owner_outbox_task = asyncio.create_task(
            run_owner_outbox_dispatcher(stop=stop, meta_client=meta_client),
            name="owner-outbox-dispatcher",
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
                owner_fanout_consumer_task,
                owner_timeout_task,
                owner_fanout_sweep_task,
                owner_outbox_task,
                connector_reconcile_task,
            )
        finally:
            with contextlib.suppress(Exception):
                await meta_client.close()
            with contextlib.suppress(Exception):
                await agendapro_public_pool.shutdown()
            langfuse_shutdown()


def run() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    run()
