"""Block Q — admin endpoints for the prompt library + seed metrics.

Two read-only endpoints:

- ``GET /admin/prompt-library`` — list curated snippets the operator
  can paste into a draft. Optional filters: ``vertical`` (e.g.
  ``barbershop_v1``) and ``category``.
- ``GET /admin/seed-templates/:name/metrics`` — aggregate signal
  about how a seed template has performed across all tenants that
  applied it.

Both are global-scoped (no per-tenant data) — snippets are
Auphere-curated catalog; seed metrics aggregate cross-tenant. Auth
is the standard admin token.
"""

from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    EvalRun,
    EvalRunStatus,
)
from nexus_api.schemas.prompt_library import (
    PromptSnippetOut,
    SeedTemplateMetricsOut,
)
from nexus_api.services.prompt_library import list_snippets
from nexus_api.services.templating import list_seed_templates

router = APIRouter()
log = structlog.get_logger()


@router.get(
    "/prompt-library",
    response_model=list[PromptSnippetOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_prompt_library(
    vertical: str | None = Query(default=None, max_length=80),
    category: str | None = Query(default=None, max_length=40),
) -> list[PromptSnippetOut]:
    """Filtered list of curated snippets.

    - ``vertical=barbershop_v1`` → snippets whose ``verticals``
      includes ``barbershop_v1`` OR is empty/``generic`` (universal).
    - ``vertical`` omitted → all snippets.
    - ``category`` is an exact string match.
    """
    snippets = list_snippets(vertical=vertical, category=category)
    return [
        PromptSnippetOut(
            id=s.id,
            title=s.title,
            category=s.category,
            description=s.description,
            body=s.body,
            verticals=list(s.verticals),
            tags=list(s.tags),
        )
        for s in snippets
    ]


@router.get(
    "/seed-templates/{name}/metrics",
    response_model=SeedTemplateMetricsOut,
    dependencies=[Depends(require_admin_token)],
)
async def get_seed_template_metrics(
    name: str,
    session: AsyncSession = Depends(get_db_session),
) -> SeedTemplateMetricsOut:
    """Aggregate metrics for a seed template across all tenants.

    Computed live (cheap query, no caching). Numbers will be sparse
    in Phase 1 (only Cultor in prod) — that's by design; the field is
    forward-looking for when Auphere onboards more clients.
    """
    if name not in list_seed_templates():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"seed template {name!r} not found",
        )

    # Tenant counts come from the AgentConfig rows; this is global
    # data (no RLS scope needed — we'd be aggregating across tenants
    # anyway). The query uses DISTINCT tenant_id so multiple versions
    # per tenant don't inflate the count.
    tenant_count_row = await session.execute(
        sa.select(
            sa.func.count(sa.distinct(AgentConfig.tenant_id)),
            sa.func.max(AgentConfig.created_at),
        ).where(AgentConfig.seed_template_ref == name)
    )
    tenant_count, last_used_at = tenant_count_row.one()

    active_count = (
        await session.execute(
            sa.select(sa.func.count(sa.distinct(AgentConfig.tenant_id)))
            .where(AgentConfig.seed_template_ref == name)
            .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
        )
    ).scalar_one()

    # Pass-rate average: for each tenant that uses this seed, take
    # the most recent passed eval_run and average them. Tenants
    # without a passed run are ignored — we want the central
    # tendency of "what does success look like for this seed".
    pass_rate_query = (
        sa.select(EvalRun.tenant_id, sa.func.max(EvalRun.finished_at))
        .join(
            AgentConfig,
            sa.and_(
                AgentConfig.tenant_id == EvalRun.tenant_id,
                AgentConfig.version == EvalRun.agent_config_version,
            ),
        )
        .where(AgentConfig.seed_template_ref == name)
        .where(EvalRun.status == EvalRunStatus.PASSED.value)
        .group_by(EvalRun.tenant_id)
    )
    pairs = (await session.execute(pass_rate_query)).all()
    pass_rate_count = 0
    pass_rate_sum = 0.0
    for tenant_id, finished_at in pairs:
        latest = (
            await session.execute(
                sa.select(EvalRun.pass_rate)
                .where(EvalRun.tenant_id == tenant_id)
                .where(EvalRun.finished_at == finished_at)
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is not None:
            pass_rate_sum += float(latest)
            pass_rate_count += 1
    # Quantize to "0.000" so the JSON serialisation preserves trailing
    # zeros — operators read this in the panel; the precision shouldn't
    # flap between "0.95" and "0.950" depending on the values.
    pass_rate_avg: Decimal | None = (
        Decimal(str(pass_rate_sum / pass_rate_count)).quantize(Decimal("0.001"))
        if pass_rate_count > 0
        else None
    )

    return SeedTemplateMetricsOut(
        name=name,
        tenant_count=int(tenant_count or 0),
        active_count=int(active_count or 0),
        eval_pass_rate_avg=pass_rate_avg,
        eval_pass_rate_count=pass_rate_count,
        last_used_at=last_used_at,
    )
