"""Continuous eval cron — runs the eval suite against the ACTIVE config.

Roadmap E2.3: evals must run continuously in production, not only as a
pre-promotion gate. The admin endpoint runs a dataset against a STAGED
*candidate* before promotion; this cron runs the tenant's primary
dataset against whatever config is *currently ACTIVE*, on a schedule, so
a regression that slips past the gate (or a config drift) is caught
without a human clicking "Run evals".

Each tick (default 6h), for every ACTIVE tenant:

1. Pick the most recently updated, non-archived ``eval_datasets`` row.
2. Resolve the latest ACTIVE ``agent_config``.
3. Run every case through the real pipeline (``run_eval``) and persist
   one ``eval_runs`` row with ``actor='system:continuous'``.

This is feasible because the runner (roadmap E2) is independent of any
request transaction — it builds its own pipeline and seeds its own
ephemeral conversations.

OFF by default (``NEXUS_CONTINUOUS_EVAL_ENABLED``). When enabled it
makes real LLM calls per case, so it is opt-in per environment. Bounded
to ONE dataset per tenant per tick to keep cost predictable.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    EvalCase,
    EvalDataset,
    EvalRun,
    EvalRunStatus,
    Tenant,
    TenantStatus,
)
from nexus_api.services.evals import LiteLLMJudgeProvider, run_eval

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 21_600.0  # 6 hours
ACTOR = "system:continuous"


async def run_continuous_eval_cron(
    *,
    stop: asyncio.Event,
    enabled: bool,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. One pass per ``tick_seconds`` when ``enabled``.

    When disabled the task still starts (so the worker wiring is
    uniform) but every tick is a no-op — it just waits on ``stop``.
    """
    log.info("continuous_eval_cron.start", enabled=enabled, tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        if enabled:
            try:
                await _process(sm)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("continuous_eval_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("continuous_eval_cron.stopped")


async def _process(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        tenant_ids = [r[0] for r in rows]

    for tid in tenant_ids:
        try:
            await _run_for_tenant(sm, tid)
        except Exception as exc:
            log.error(
                "continuous_eval_cron.tenant_failed",
                tenant_id=str(tid),
                error=str(exc),
            )


async def _run_for_tenant(sm: sa.orm.sessionmaker, tenant_id: uuid.UUID) -> None:  # type: ignore[type-arg]
    """Run the tenant's primary dataset against its ACTIVE config.

    The whole run happens inside one tenant-scoped transaction: the
    ``eval_runs`` / ``eval_run_results`` rows are flushed by ``run_eval``
    and committed when the context exits. The per-case conversation
    seeding and the graph itself open their own sessions.
    """
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        dataset = (
            await session.execute(
                sa.select(EvalDataset)
                .where(EvalDataset.archived_at.is_(None))
                .order_by(EvalDataset.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if dataset is None:
            return

        cases = list(
            (
                await session.execute(
                    sa.select(EvalCase)
                    .where(EvalCase.dataset_id == dataset.id)
                    .order_by(EvalCase.idx.asc())
                )
            )
            .scalars()
            .all()
        )
        if not cases:
            return

        agent_config = (
            await session.execute(
                sa.select(AgentConfig)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
                .order_by(AgentConfig.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if agent_config is None:
            return

        run = EvalRun(
            tenant_id=tenant_id,
            dataset_id=dataset.id,
            dataset_version=dataset.version,
            agent_config_version=agent_config.version,
            agent_config_status=agent_config.status.value,
            status=EvalRunStatus.PENDING.value,
            actor=ACTOR,
            started_at=datetime.now(UTC),
        )
        session.add(run)
        await session.flush()

        try:
            outcome = await run_eval(
                session,
                tenant_id=tenant_id,
                run=run,
                dataset=dataset,
                cases=cases,
                agent_config=agent_config,
                judge_provider=LiteLLMJudgeProvider(),
            )
        except Exception as exc:
            run.status = EvalRunStatus.ERROR.value
            run.error_message = str(exc)
            run.finished_at = datetime.now(UTC)
            await session.flush()
            log.error(
                "continuous_eval_cron.run_aborted",
                tenant_id=str(tenant_id),
                run_id=str(run.id),
                error=str(exc),
            )
            return

        log.info(
            "continuous_eval_cron.run_complete",
            tenant_id=str(tenant_id),
            run_id=str(run.id),
            dataset=dataset.name,
            agent_config_version=agent_config.version,
            status=outcome.status.value,
            pass_rate=str(outcome.pass_rate),
        )


__all__ = ["ACTOR", "DEFAULT_TICK_SECONDS", "run_continuous_eval_cron"]
