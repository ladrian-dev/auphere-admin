"""Shared worker construction (WP-07, plataforma v2 Fase 1).

One process used to run all 21+ tasks; scaling any of them meant scaling all
of them (and duplicating crons — V5). This module extracts the construction
that every worker service shares, and groups the tasks into the three
families of the v2 service map (§2 of the plan):

- **runner**   — horizontally scalable, no locks: inbound consumer, stream
  claimer, owner-fanout consumer, promote subscriber (pub/sub — every
  replica must receive it: it is cache invalidation).
- **egress**   — scalable via ``SKIP LOCKED``: outbound dispatcher, owner
  outbox dispatcher.
- **scheduler**— the crons and sweeps. Runs as a singleton (WP-08 adds
  advisory locks so a second replica during rollout is harmless).

``entrypoints/{runner,scheduler,egress}.py`` each start one family;
``main.py`` keeps the all-in-one shape for local dev and as the instant
rollback path (returning to a single service is a startCommand change).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog
from nexus_api.config import Settings as NexusSettings
from nexus_api.config import get_settings
from nexus_api.core.metrics import isolation_event_drainer
from nexus_api.core.otel_metrics import ensure_queue_gauges, install_metrics
from nexus_api.core.redis_client import get_redis
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_channels.tiktok_bm import TikTokChannelAdapter, TikTokClient
from nexus_channels.tiktok_bm.credentials import TikTokCredentialsRepository
from nexus_channels.whatsapp_meta import MetaChannelAdapter, MetaClient
from nexus_channels.whatsapp_meta.credentials import resolve_send_credentials
from nexus_mcp.servers.agendapro_public.transport import (
    build_default_pool_from_env as build_agendapro_public_pool_from_env,
)
from nexus_mcp.servers.agendapro_public.transport import (
    set_default_transport as set_agendapro_public_transport,
)

from nexus_worker.config import WorkerSettings, get_api_settings, get_worker_settings
from nexus_worker.guardrails import OutcomeGrader
from nexus_worker.health import run_heartbeat
from nexus_worker.observability import init_langfuse
from nexus_worker.observability import shutdown as langfuse_shutdown
from nexus_worker.observability.otel import install_worker_tracing
from nexus_worker.runtime.agent_loader import AgentLoader
from nexus_worker.runtime.checkpointer import postgres_checkpointer
from nexus_worker.runtime.llm import LiteLLMProvider, build_default_router
from nexus_worker.runtime.pipeline import build_pipeline
from nexus_worker.runtime.promote_subscriber import run_promote_subscriber
from nexus_worker.streams.agent_sales_poll_cron import run_agent_sales_poll_cron
from nexus_worker.streams.async_booking_cron import run_async_booking_cron
from nexus_worker.streams.checkpoint_retention_cron import run_checkpoint_retention_cron
from nexus_worker.streams.claimer import run_stream_claimer
from nexus_worker.streams.connector_reconcile_cron import run_connector_reconcile_cron
from nexus_worker.streams.consumer import run_inbound_consumer
from nexus_worker.streams.continuous_eval_cron import run_continuous_eval_cron
from nexus_worker.streams.cost_rollup_cron import run_cost_rollup_cron
from nexus_worker.streams.data_retention_cron import run_data_retention_cron
from nexus_worker.streams.grade_consumer import run_grade_consumer
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
from nexus_worker.streams.partition_maintenance_cron import run_partition_maintenance_cron
from nexus_worker.streams.partner_receipt_cron import run_partner_receipt_cron
from nexus_worker.streams.platform_watcher import run_platform_watcher
from nexus_worker.streams.reminder_cron import run_reminder_cron
from nexus_worker.streams.tiktok_token_refresh_cron import run_tiktok_token_refresh_cron
from nexus_worker.streams.usage_alerts_cron import run_usage_alerts_cron
from nexus_worker.streams.whatsapp_health_cron import run_whatsapp_health_cron

log = structlog.get_logger(__name__)

# WP-08: advisory-lock name guarding the cron family. One lock for the whole
# family (the scheduler deploys as a singleton; per-cron sharding is a
# parameter change in run_exclusive if it is ever needed).
SCHEDULER_LEADER_LOCK = "nexus:scheduler"

# Task-name contract per family. The unit test in
# ``tests/unit/test_bootstrap_split.py`` asserts the families are disjoint
# and complete, so a new task can't silently run in two services (duplicated
# sends) or in none (silently dead).
RUNNER_TASK_NAMES = frozenset(
    {
        "heartbeat",
        "promote-subscriber",
        "inbound-consumer",
        "stream-claimer",
        "owner-fanout-consumer",
    }
)
EGRESS_TASK_NAMES = frozenset(
    {
        "heartbeat",
        "outbound-dispatcher",
        "owner-outbox-dispatcher",
    }
)
SCHEDULER_TASK_NAMES = frozenset(
    {
        "heartbeat",
        "operator-alerter",
        "grade-consumer",
        "platform-watcher",
        "reminder-cron",
        "agent-sales-poll-cron",
        "partner-receipt-cron",
        "isolation-event-drainer",
        "no-show-scrape-cron",
        "cost-rollup-cron",
        "isolation-watcher",
        "whatsapp-health-cron",
        "tiktok-token-refresh-cron",
        "async-booking-cron",
        "continuous-eval-cron",
        "memory-versions-retention-cron",
        "owner-consultation-timeout-sweep",
        "owner-fanout-sweep",
        "connector-reconcile-cron",
        "partition-maintenance-cron",
        "checkpoint-retention-cron",
        "data-retention-cron",
        "usage-alerts-cron",
    }
)


@dataclass
class WorkerContext:
    """Everything the task families share. Cheap to build — no I/O beyond
    lazy client construction; the Postgres checkpointer opens separately in
    ``pipeline_scope`` because only the runner needs it."""

    service_name: str
    api_settings: Any
    worker_settings: WorkerSettings
    nexus_settings: NexusSettings
    loader: AgentLoader
    router: Any
    redis: Any
    stop: asyncio.Event
    meta_client: MetaClient
    channel_adapters: dict[str, Any]
    agendapro_public_pool: Any
    outcome_grader: OutcomeGrader | None
    _cleanup: list[Any] = field(default_factory=list)


def build_context(service_name: str) -> WorkerContext:
    """Construct the shared context and install observability + signal
    handlers for this process. Call once per process, inside the running
    event loop."""
    api_settings = get_api_settings()
    worker_settings = get_worker_settings()
    nexus_settings = get_settings()

    # Block H: Langfuse must initialise BEFORE LiteLLM picks up the
    # ``litellm.success_callback`` hook. Noop client when keys are absent.
    init_langfuse(worker_settings)
    # WP-01/WP-05: tracing + SLI metrics, exported only when
    # NEXUS_OTEL_ENABLED + OTLP endpoint are set.
    install_worker_tracing(service_name)
    install_metrics(service_name)
    ensure_queue_gauges()

    loader = AgentLoader(max_size=worker_settings.agent_cache_size)
    # Fallback model is hardcoded same-vendor (Anthropic Haiku) — cross-
    # provider fallback was unworkable (Anthropic-only params in the
    # payload). See incident 2026-05-28.
    router = build_default_router(
        classify_model=worker_settings.llm_classify_model,
        respond_model=worker_settings.llm_respond_model,
        fallback_model="anthropic/claude-haiku-4-5",
        use_inmemory=worker_settings.llm_use_inmemory,
    )
    redis = get_redis()
    stop = asyncio.Event()

    # Meta Cloud API adapter — stateless past construction; credentials are
    # resolved per CHANNEL inside a fresh tenant-scoped session on each send
    # so RLS is the only authority on which rows are read.
    sm = get_sessionmaker()

    async def _load_meta_credentials(
        *, tenant_id: uuid.UUID, channel_id: uuid.UUID | None = None
    ) -> tuple[str, str]:
        async with sm() as cred_session, tenant_scoped_session(cred_session, tenant_id):
            pnid, token = await resolve_send_credentials(cred_session, channel_id=channel_id)
            return (pnid, token)

    meta_client = MetaClient(
        app_secret=nexus_settings.meta_app_secret,
        require_appsecret_proof=nexus_settings.meta_require_appsecret_proof,
    )
    meta_adapter = MetaChannelAdapter(meta_client, credentials_loader=_load_meta_credentials)

    # TikTok adapter — same shape; the ~24h token is kept alive by the
    # refresh cron (scheduler family), not by this loader.
    tiktok_client = TikTokClient(
        nexus_settings.tiktok_app_id,
        nexus_settings.tiktok_app_secret,
        base_url=nexus_settings.tiktok_api_base_url,
        api_version=nexus_settings.tiktok_api_version,
    )

    async def _load_tiktok_credentials(*, tenant_id: uuid.UUID) -> tuple[str, str]:
        async with sm() as cred_session, tenant_scoped_session(cred_session, tenant_id):
            creds = await TikTokCredentialsRepository(cred_session).get_or_raise()
            return (creds.business_id, creds.access_token)

    tiktok_adapter = TikTokChannelAdapter(
        tiktok_client, credentials_loader=_load_tiktok_credentials
    )
    channel_adapters = {"meta": meta_adapter, "tiktok": tiktok_adapter}

    # WP-11 (D10): the runner resolves inbound media (webhook publishes only
    # the provider media id). The Meta adapter's fetch_media_bytes carries
    # the per-channel credential scoping already.
    from nexus_worker.multimodal.media_fetch import set_media_fetcher

    set_media_fetcher(meta_adapter.fetch_media_bytes)

    # Los dos ticks azules también salen de aquí, no del webhook: el
    # handler decidía Y enviaba, y esa llamada a Meta dentro del ack hacía
    # inalcanzable el SLI de 50 ms. Este adaptador es de larga vida, así
    # que además desaparece el handshake TLS por mensaje.
    from nexus_worker.runtime.read_receipts import set_read_receipt_sender

    set_read_receipt_sender("meta", meta_adapter.mark_as_read)

    # Block O: AgendaPro public-link Node MCP subprocess pool (lazy —
    # tolerates missing Node binary in dev/test).
    agendapro_public_pool = build_agendapro_public_pool_from_env()
    set_agendapro_public_transport(agendapro_public_pool)

    # Fase C — outcome grader, independent provider so the guardrail call
    # doesn't ride the agent's retry chain.
    outcome_grader: OutcomeGrader | None = None
    if not worker_settings.llm_use_inmemory:
        outcome_grader = OutcomeGrader(provider=LiteLLMProvider())

    def _request_stop() -> None:
        log.info("worker.signal_received_stopping", service=service_name)
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_stop)

    return WorkerContext(
        service_name=service_name,
        api_settings=api_settings,
        worker_settings=worker_settings,
        nexus_settings=nexus_settings,
        loader=loader,
        router=router,
        redis=redis,
        stop=stop,
        meta_client=meta_client,
        channel_adapters=channel_adapters,
        agendapro_public_pool=agendapro_public_pool,
        outcome_grader=outcome_grader,
    )


@contextlib.asynccontextmanager
async def pipeline_scope(ctx: WorkerContext) -> AsyncIterator[Any]:
    """Open the Postgres checkpointer and compile the graph. Runner-only —
    egress and scheduler never touch conversational state."""
    # WP-15: el saver mantiene una conexión de sesión larga — va SIEMPRE
    # directo a Postgres, nunca a través del pooler en modo transaction.
    checkpointer_url = ctx.api_settings.database_url_direct or ctx.api_settings.database_url
    async with postgres_checkpointer(checkpointer_url) as saver:
        yield build_pipeline(
            agent_loader=ctx.loader,
            llm_router=ctx.router,
            checkpointer=saver,
            outcome_grader=ctx.outcome_grader,
        )


async def shutdown_context(ctx: WorkerContext) -> None:
    with contextlib.suppress(Exception):
        await ctx.meta_client.close()
    with contextlib.suppress(Exception):
        await ctx.agendapro_public_pool.shutdown()
    langfuse_shutdown()


def _spawn(name: str, coro: Any) -> asyncio.Task[None]:
    return asyncio.create_task(coro, name=name)


def _heartbeat_task(ctx: WorkerContext) -> asyncio.Task[None]:
    return _spawn("heartbeat", run_heartbeat(ctx.redis, service=ctx.service_name, stop=ctx.stop))


def runner_tasks(
    ctx: WorkerContext, pipeline: Any, *, heartbeat: bool = True
) -> list[asyncio.Task[None]]:
    ws = ctx.worker_settings
    return ([_heartbeat_task(ctx)] if heartbeat else []) + [
        # promote is pub/sub — EVERY runner replica must receive it (cache
        # invalidation), which is why it lives here and not in the scheduler.
        _spawn("promote-subscriber", run_promote_subscriber(ctx.redis, ctx.loader, stop=ctx.stop)),
        _spawn(
            "inbound-consumer",
            run_inbound_consumer(
                ctx.redis,
                pipeline,
                streams=ws.inbound_streams_list,
                group=ws.inbound_consumer_group,
                consumer_name=ws.inbound_consumer_name,
                stop=ctx.stop,
            ),
        ),
        _spawn(
            "stream-claimer",
            run_stream_claimer(
                ctx.redis,
                pipeline,
                streams=ws.inbound_streams_list,
                group=ws.inbound_consumer_group,
                consumer_name=f"{ws.inbound_consumer_name}-claimer",
                stop=ctx.stop,
            ),
        ),
        _spawn(
            "owner-fanout-consumer",
            run_owner_fanout_consumer(
                ctx.redis,
                pipeline,
                consumer_name=ws.inbound_consumer_name + ":ownerfanout",
                stop=ctx.stop,
            ),
        ),
    ]


def egress_tasks(ctx: WorkerContext, *, heartbeat: bool = True) -> list[asyncio.Task[None]]:
    return ([_heartbeat_task(ctx)] if heartbeat else []) + [
        _spawn(
            "outbound-dispatcher",
            run_outbound_dispatcher(adapters=ctx.channel_adapters, stop=ctx.stop),
        ),
        _spawn(
            "owner-outbox-dispatcher",
            run_owner_outbox_dispatcher(stop=ctx.stop, meta_client=ctx.meta_client),
        ),
    ]


def metering_tasks(ctx: WorkerContext, *, heartbeat: bool = True) -> list[asyncio.Task[None]]:
    """WP-18: ingesta de ``nexus:usage`` → ``usage_records``. Sin líder —
    el grupo de consumidores reparte y varias réplicas suman."""
    from nexus_worker.metering.consumer import run_metering_consumer

    return ([_heartbeat_task(ctx)] if heartbeat else []) + [
        _spawn(
            "metering-consumer",
            run_metering_consumer(
                ctx.redis,
                stop=ctx.stop,
                consumer_name=f"{ctx.worker_settings.inbound_consumer_name}:metering",
            ),
        ),
    ]


def scheduler_tasks(ctx: WorkerContext, *, heartbeat: bool = True) -> list[asyncio.Task[None]]:
    ws = ctx.worker_settings
    return ([_heartbeat_task(ctx)] if heartbeat else []) + [
        _spawn(
            "operator-alerter",
            run_operator_alerter(adapters=ctx.channel_adapters, stop=ctx.stop),
        ),
        # WP-21 — grader diferido. Va en el scheduler y NO en el runner
        # aunque el plan lo situara allí: mete llamadas de LLM y el runner
        # es el servicio cuya latencia mira el cliente. Aquí, como mucho,
        # retrasa una métrica de calidad.
        _spawn(
            "grade-consumer",
            run_grade_consumer(
                ctx.redis,
                grader=ctx.outcome_grader,
                stop=ctx.stop,
                consumer_name=f"{ws.inbound_consumer_name}:grade",
            ),
        ),
        _spawn("platform-watcher", run_platform_watcher(ctx.redis, stop=ctx.stop)),
        _spawn("reminder-cron", run_reminder_cron(stop=ctx.stop)),
        _spawn("agent-sales-poll-cron", run_agent_sales_poll_cron(stop=ctx.stop)),
        _spawn("partner-receipt-cron", run_partner_receipt_cron(stop=ctx.stop)),
        _spawn("isolation-event-drainer", isolation_event_drainer(ctx.stop)),
        _spawn(
            "no-show-scrape-cron",
            run_no_show_scrape_cron(stop=ctx.stop, tick_seconds=ws.no_show_scrape_tick_seconds),
        ),
        _spawn(
            "cost-rollup-cron",
            run_cost_rollup_cron(stop=ctx.stop, tick_seconds=ws.cost_rollup_tick_seconds),
        ),
        _spawn(
            "isolation-watcher",
            run_isolation_watcher(stop=ctx.stop, tick_seconds=ws.isolation_watcher_tick_seconds),
        ),
        _spawn("whatsapp-health-cron", run_whatsapp_health_cron(stop=ctx.stop)),
        _spawn("tiktok-token-refresh-cron", run_tiktok_token_refresh_cron(stop=ctx.stop)),
        _spawn("async-booking-cron", run_async_booking_cron(stop=ctx.stop)),
        _spawn(
            "continuous-eval-cron",
            run_continuous_eval_cron(
                stop=ctx.stop,
                enabled=ws.continuous_eval_enabled,
                tick_seconds=ws.continuous_eval_tick_seconds,
            ),
        ),
        _spawn(
            "memory-versions-retention-cron",
            run_memory_versions_retention_cron(
                stop=ctx.stop, tick_seconds=ws.memory_retention_tick_seconds
            ),
        ),
        _spawn(
            "owner-consultation-timeout-sweep",
            run_owner_consultation_timeout_sweep(stop=ctx.stop),
        ),
        _spawn("owner-fanout-sweep", run_owner_fanout_sweep(ctx.redis, stop=ctx.stop)),
        _spawn("connector-reconcile-cron", run_connector_reconcile_cron(stop=ctx.stop)),
        # WP-13: partitions ahead of the calendar + checkpoint pruning.
        _spawn("partition-maintenance-cron", run_partition_maintenance_cron(stop=ctx.stop)),
        _spawn("checkpoint-retention-cron", run_checkpoint_retention_cron(stop=ctx.stop)),
        # CP-24: partner usage caps — warns at 80 %/100 %, never cuts.
        _spawn("usage-alerts-cron", run_usage_alerts_cron(stop=ctx.stop)),
        # WP-29: retención por tipo de dato. Va en el scheduler (líder
        # único) porque suelta particiones: dos instancias compitiendo por
        # el mismo DROP no romperían nada, pero el log diría dos veces que
        # se borró algo que se borró una.
        _spawn(
            "data-retention-cron",
            run_data_retention_cron(
                stop=ctx.stop,
                media_days=ws.retention_media_days,
                message_months=ws.retention_message_months,
                usage_months=ws.retention_usage_months,
                tick_seconds=ws.retention_tick_seconds,
            ),
        ),
    ]


async def run_service(
    service_name: str,
    *,
    runner: bool = False,
    scheduler: bool = False,
    egress: bool = False,
    metering: bool = False,
) -> None:
    """Boot one worker service with the selected task families."""
    ctx = build_context(service_name)
    log.info(
        "worker.service_boot",
        service=service_name,
        runner=runner,
        scheduler=scheduler,
        egress=egress,
        metering=metering,
    )
    # One heartbeat per PROCESS, outside the leader gate: a hot-standby
    # scheduler must keep beating or the dead-worker alert pages for a
    # replica that is doing exactly its job.
    tasks: list[asyncio.Task[None]] = [_heartbeat_task(ctx)]
    try:
        if runner:
            async with pipeline_scope(ctx) as pipeline:
                tasks.extend(runner_tasks(ctx, pipeline, heartbeat=False))
                if scheduler:
                    tasks.append(_scheduler_leader_task(ctx))
                if egress:
                    tasks.extend(egress_tasks(ctx, heartbeat=False))
                if metering:
                    tasks.extend(metering_tasks(ctx, heartbeat=False))
                await asyncio.gather(*tasks)
        else:
            if scheduler:
                tasks.append(_scheduler_leader_task(ctx))
            if egress:
                tasks.extend(egress_tasks(ctx, heartbeat=False))
            if metering:
                tasks.extend(metering_tasks(ctx, heartbeat=False))
            await asyncio.gather(*tasks)
    finally:
        await shutdown_context(ctx)


def _scheduler_leader_task(ctx: WorkerContext) -> asyncio.Task[None]:
    """WP-08: the cron family only runs while holding the advisory lock —
    two scheduler replicas produce zero duplicated effects; the standby
    takes over automatically when the leader's connection dies."""
    from nexus_api.core.leader import run_exclusive

    return _spawn(
        "scheduler-leader",
        run_exclusive(
            SCHEDULER_LEADER_LOCK,
            stop=ctx.stop,
            start_tasks=lambda: scheduler_tasks(ctx, heartbeat=False),
        ),
    )
