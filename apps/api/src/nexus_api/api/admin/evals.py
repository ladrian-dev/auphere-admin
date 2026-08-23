"""Block P — admin endpoints for the eval suite.

Routes (all RLS-scoped under ``/admin/tenants/:id``):

- ``POST   .../eval-datasets`` — create dataset
- ``GET    .../eval-datasets`` — list datasets
- ``GET    .../eval-datasets/:dataset_id`` — detail (with cases)
- ``PUT    .../eval-datasets/:dataset_id`` — update name / desc / threshold
- ``DELETE .../eval-datasets/:dataset_id`` — soft-archive

- ``POST   .../eval-datasets/:dataset_id/cases`` — add case
- ``PUT    .../eval-cases/:case_id`` — update case
- ``DELETE .../eval-cases/:case_id`` — delete case

- ``POST   .../eval-datasets/:dataset_id/run`` — trigger run (synchronous;
  blocks until the run completes — typical 10-60s)
- ``GET    .../eval-runs/:run_id`` — run detail (with per-case results)
- ``GET    .../eval-runs`` — list runs (optionally filter by
  ``agent_config_version`` query param so the panel can show
  "latest run for v7")

The runner is synchronous on purpose for v1: the operator clicks
"Run evals", we run, we respond. Async/queued runs come later if
datasets get fat enough to warrant it.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import ro_scoped_session_from_path, scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    EvalCase,
    EvalDataset,
    EvalRun,
    EvalRunResult,
    EvalRunStatus,
)
from nexus_api.schemas.evals import (
    EvalCaseCreateIn,
    EvalCaseOut,
    EvalCaseUpdateIn,
    EvalDatasetCreateIn,
    EvalDatasetDetailOut,
    EvalDatasetOut,
    EvalDatasetUpdateIn,
    EvalRunDetailOut,
    EvalRunOut,
    EvalRunResultOut,
    EvalRunStartIn,
)
from nexus_api.services.evals import (
    AssertionValidationError,
    FakeJudgeProvider,
    JudgeProvider,
    LiteLLMJudgeProvider,
    run_eval,
    validate_assertions,
)

router = APIRouter()
log = structlog.get_logger()

# Strong refs to in-flight background eval tasks. Without this the event
# loop only keeps a weak reference and the task can be garbage-collected
# mid-run (see CPython docs on ``asyncio.create_task``).
_background_eval_tasks: set[asyncio.Task[None]] = set()


# ── Judge provider DI ─────────────────────────────────────────────────────


_judge_singleton: JudgeProvider | None = None


def get_judge_provider() -> JudgeProvider:
    global _judge_singleton
    if _judge_singleton is None:
        _judge_singleton = LiteLLMJudgeProvider()
    return _judge_singleton


def set_judge_provider(provider: JudgeProvider | None) -> None:
    """Test hook."""
    global _judge_singleton
    _judge_singleton = provider


# ── helpers ───────────────────────────────────────────────────────────────


async def _get_dataset(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    dataset_id: uuid.UUID,
) -> EvalDataset:
    ds = (
        await session.execute(sa.select(EvalDataset).where(EvalDataset.id == dataset_id))
    ).scalar_one_or_none()
    if ds is None or ds.tenant_id != tenant_id or ds.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"eval dataset {dataset_id} not found",
        )
    return ds


async def _next_case_idx(session: AsyncSession, dataset_id: uuid.UUID) -> int:
    row = (
        await session.execute(
            sa.select(sa.func.coalesce(sa.func.max(EvalCase.idx), -1)).where(
                EvalCase.dataset_id == dataset_id
            )
        )
    ).scalar_one()
    return int(row) + 1


async def _resolve_agent_config(
    session: AsyncSession,
    *,
    version: int | None,
) -> AgentConfig:
    """Default: latest STAGED, else latest ACTIVE. Explicit ``version``
    wins. 404 if nothing exists."""
    if version is not None:
        row = (
            await session.execute(sa.select(AgentConfig).where(AgentConfig.version == version))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail=f"agent_config version {version} not found",
            )
        return row

    row = (
        await session.execute(
            sa.select(AgentConfig)
            .where(AgentConfig.status == AgentConfigStatus.STAGED)
            .order_by(AgentConfig.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = (
        await session.execute(
            sa.select(AgentConfig)
            .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            .order_by(AgentConfig.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=("no agent_config exists for this tenant — apply a seed template first"),
        )
    return row


def _validate_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for i, msg in enumerate(history):
        role = msg.get("role")
        content = msg.get("content")
        if role not in {"user", "assistant"}:
            raise HTTPException(
                status_code=400,
                detail=f"history[{i}].role must be 'user' or 'assistant'",
            )
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=400,
                detail=f"history[{i}].content must be a non-empty string",
            )
        cleaned.append({"role": role, "content": content})
    return cleaned


# ── Dataset CRUD ──────────────────────────────────────────────────────────


@router.post(
    "/tenants/{tenant_id}/eval-datasets",
    response_model=EvalDatasetOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_dataset(
    tenant_id: Annotated[uuid.UUID, Path()],
    body: EvalDatasetCreateIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> EvalDatasetOut:
    ds = EvalDataset(
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        version=1,
    )
    if body.pass_threshold is not None:
        ds.pass_threshold = body.pass_threshold
    session.add(ds)
    try:
        await session.flush()
    except sa.exc.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail=f"dataset {body.name!r} already exists"
        ) from exc
    await session.refresh(ds)
    return EvalDatasetOut.model_validate(ds)


@router.get(
    "/tenants/{tenant_id}/eval-datasets",
    response_model=list[EvalDatasetOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_datasets(
    tenant_id: Annotated[uuid.UUID, Path()],
    session: AsyncSession = Depends(ro_scoped_session_from_path),
) -> list[EvalDatasetOut]:
    rows = (
        (
            await session.execute(
                sa.select(EvalDataset)
                .where(EvalDataset.archived_at.is_(None))
                .order_by(EvalDataset.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [EvalDatasetOut.model_validate(r) for r in rows]


@router.get(
    "/tenants/{tenant_id}/eval-datasets/{dataset_id}",
    response_model=EvalDatasetDetailOut,
    dependencies=[Depends(require_admin_token)],
)
async def get_dataset(
    tenant_id: Annotated[uuid.UUID, Path()],
    dataset_id: Annotated[uuid.UUID, Path()],
    session: AsyncSession = Depends(ro_scoped_session_from_path),
) -> EvalDatasetDetailOut:
    ds = await _get_dataset(session, tenant_id=tenant_id, dataset_id=dataset_id)
    cases = (
        (
            await session.execute(
                sa.select(EvalCase)
                .where(EvalCase.dataset_id == dataset_id)
                .order_by(EvalCase.idx.asc())
            )
        )
        .scalars()
        .all()
    )
    return EvalDatasetDetailOut(
        **EvalDatasetOut.model_validate(ds).model_dump(),
        cases=[EvalCaseOut.model_validate(c) for c in cases],
    )


@router.put(
    "/tenants/{tenant_id}/eval-datasets/{dataset_id}",
    response_model=EvalDatasetOut,
)
async def update_dataset(
    tenant_id: Annotated[uuid.UUID, Path()],
    dataset_id: Annotated[uuid.UUID, Path()],
    body: EvalDatasetUpdateIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> EvalDatasetOut:
    ds = await _get_dataset(session, tenant_id=tenant_id, dataset_id=dataset_id)
    payload = body.model_dump(exclude_unset=True)
    if "name" in payload:
        ds.name = payload["name"]
    if "description" in payload:
        ds.description = payload["description"]
    if "pass_threshold" in payload and payload["pass_threshold"] is not None:
        ds.pass_threshold = payload["pass_threshold"]
    await session.flush()
    await session.refresh(ds)
    return EvalDatasetOut.model_validate(ds)


@router.delete(
    "/tenants/{tenant_id}/eval-datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_dataset(
    tenant_id: Annotated[uuid.UUID, Path()],
    dataset_id: Annotated[uuid.UUID, Path()],
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> None:
    ds = await _get_dataset(session, tenant_id=tenant_id, dataset_id=dataset_id)
    ds.archived_at = datetime.now(UTC)
    await session.flush()


# ── Case CRUD ─────────────────────────────────────────────────────────────


@router.post(
    "/tenants/{tenant_id}/eval-datasets/{dataset_id}/cases",
    response_model=EvalCaseOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_case(
    tenant_id: Annotated[uuid.UUID, Path()],
    dataset_id: Annotated[uuid.UUID, Path()],
    body: EvalCaseCreateIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> EvalCaseOut:
    await _get_dataset(session, tenant_id=tenant_id, dataset_id=dataset_id)
    cleaned_history = _validate_history(body.history)
    assertions = body.assertions.model_dump(exclude_none=True)
    try:
        validate_assertions(assertions)
    except AssertionValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    idx = body.idx if body.idx is not None else await _next_case_idx(session, dataset_id)
    case = EvalCase(
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        idx=idx,
        name=body.name,
        user_message=body.user_message,
        history=cleaned_history,
        assertions=assertions,
    )
    session.add(case)
    try:
        await session.flush()
    except sa.exc.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail=f"case idx {idx} already used in dataset"
        ) from exc
    await session.refresh(case)
    return EvalCaseOut.model_validate(case)


@router.put(
    "/tenants/{tenant_id}/eval-cases/{case_id}",
    response_model=EvalCaseOut,
)
async def update_case(
    tenant_id: Annotated[uuid.UUID, Path()],
    case_id: Annotated[uuid.UUID, Path()],
    body: EvalCaseUpdateIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> EvalCaseOut:
    case = (
        await session.execute(sa.select(EvalCase).where(EvalCase.id == case_id))
    ).scalar_one_or_none()
    if case is None or case.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")

    payload = body.model_dump(exclude_unset=True)
    if "name" in payload:
        case.name = payload["name"]
    if "user_message" in payload:
        case.user_message = payload["user_message"]
    if "history" in payload and payload["history"] is not None:
        case.history = _validate_history(payload["history"])
    if "assertions" in payload and payload["assertions"] is not None:
        new_assertions = body.assertions.model_dump(exclude_none=True) if body.assertions else {}
        try:
            validate_assertions(new_assertions)
        except AssertionValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        case.assertions = new_assertions
    if "idx" in payload and payload["idx"] is not None:
        case.idx = payload["idx"]
    await session.flush()
    await session.refresh(case)
    return EvalCaseOut.model_validate(case)


@router.delete(
    "/tenants/{tenant_id}/eval-cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_case(
    tenant_id: Annotated[uuid.UUID, Path()],
    case_id: Annotated[uuid.UUID, Path()],
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> None:
    case = (
        await session.execute(sa.select(EvalCase).where(EvalCase.id == case_id))
    ).scalar_one_or_none()
    if case is None or case.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    await session.delete(case)
    await session.flush()


# ── Runs ──────────────────────────────────────────────────────────────────


async def _run_eval_background(
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    dataset_id: uuid.UUID,
    agent_config_id: uuid.UUID,
    judge_provider: JudgeProvider,
) -> None:
    """Background driver for an eval run.

    Opens its own session (the request session has already committed and
    is gone) under ``tenant_scoped_session`` so RLS accepts the writes,
    re-fetches the pinned entities by id, and drives ``run_eval`` to
    completion. On any exception the run row is flipped to ``error`` with
    a redacted message; the request handler is long gone by then.

    The background task is fire-and-forget from the endpoint's view —
    callers poll ``GET /eval-runs/{run_id}`` to see progress (the runner
    flushes ``EvalRunResult`` rows incrementally) and final status.

    Crash recovery: if the API container restarts mid-run, the EvalRun
    stays in ``running`` with stale ``updated_at``. A future sweep cron
    can mark such rows as ``error`` with reason ``api_restart``; for the
    pre-promote use case the operator just re-triggers the run, which is
    safe — datasets and cases are immutable inputs.
    """
    session_factory = get_sessionmaker()
    try:
        async with session_factory() as session, tenant_scoped_session(session, tenant_id):
            run = (
                await session.execute(sa.select(EvalRun).where(EvalRun.id == run_id))
            ).scalar_one()
            dataset = (
                await session.execute(sa.select(EvalDataset).where(EvalDataset.id == dataset_id))
            ).scalar_one()
            cases = (
                (
                    await session.execute(
                        sa.select(EvalCase)
                        .where(EvalCase.dataset_id == dataset_id)
                        .order_by(EvalCase.idx.asc())
                    )
                )
                .scalars()
                .all()
            )
            agent_config = (
                await session.execute(
                    sa.select(AgentConfig).where(AgentConfig.id == agent_config_id)
                )
            ).scalar_one()

            from nexus_api.core.llm_proxy import (
                llm_proxy_partner_scope,
                partner_id_for_tenant_standalone,
            )

            partner_id = await partner_id_for_tenant_standalone(tenant_id)

            async def _drive() -> None:
                await run_eval(
                    session,
                    tenant_id=tenant_id,
                    run=run,
                    dataset=dataset,
                    cases=list(cases),
                    agent_config=agent_config,
                    judge_provider=judge_provider,
                )

            if partner_id is not None:
                with llm_proxy_partner_scope(partner_id):
                    await _drive()
            else:
                await _drive()
    except Exception as exc:  # pragma: no cover — defensive top-level
        log.exception(
            "evals.run.background_aborted",
            run_id=str(run_id),
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        try:
            # Nested with kept on purpose: the inner block has its own
            # try/except and flattening it obscures the scope boundary.
            async with session_factory() as session:  # noqa: SIM117
                async with tenant_scoped_session(session, tenant_id):
                    run = (
                        await session.execute(sa.select(EvalRun).where(EvalRun.id == run_id))
                    ).scalar_one()
                    run.status = EvalRunStatus.ERROR.value
                    run.error_message = str(exc)[:1024]
                    run.finished_at = datetime.now(UTC)
        except Exception:
            log.exception("evals.run.error_marker_failed", run_id=str(run_id))


@router.post(
    "/tenants/{tenant_id}/eval-datasets/{dataset_id}/run",
    response_model=EvalRunDetailOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_run(
    tenant_id: Annotated[uuid.UUID, Path()],
    dataset_id: Annotated[uuid.UUID, Path()],
    body: EvalRunStartIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    judge_provider: JudgeProvider = Depends(get_judge_provider),
    actor: str = Depends(require_admin_token),
) -> EvalRunDetailOut:
    """Trigger an eval run.

    Returns 202 immediately with an ``EvalRun`` row in ``pending`` state
    and an empty results list. The actual run drives in the background
    (see ``_run_eval_background``); clients poll ``GET /eval-runs/{id}``
    to see progress and final status.

    Returning synchronously here was the v1 shape and broke under prod
    proxy timeouts (Vercel server-action 60s on Pro, Cloudflare 100s)
    once the dataset grew past ~3 cases. The runner itself stays
    sequential — the change is purely how the HTTP request hands off
    control to the work. The polling shape on the client side is the
    other half of this fix.
    """
    dataset = await _get_dataset(session, tenant_id=tenant_id, dataset_id=dataset_id)

    if type(judge_provider).__name__.startswith("LiteLLM"):
        from nexus_api.core.llm_proxy import LLMProxyUnavailable, require_litellm_proxy
        from nexus_api.metering.wallet import partner_id_for_tenant

        partner_id = await partner_id_for_tenant(session, tenant_id)
        try:
            require_litellm_proxy(partner_id)
        except LLMProxyUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "llm_proxy_unavailable"},
            ) from exc

    cases = (
        (
            await session.execute(
                sa.select(EvalCase)
                .where(EvalCase.dataset_id == dataset_id)
                .order_by(EvalCase.idx.asc())
            )
        )
        .scalars()
        .all()
    )
    if not cases:
        raise HTTPException(
            status_code=400,
            detail="dataset has no cases — add at least one before running",
        )

    agent_config = await _resolve_agent_config(session, version=body.agent_config_version)

    run = EvalRun(
        tenant_id=tenant_id,
        dataset_id=dataset.id,
        dataset_version=dataset.version,
        agent_config_version=agent_config.version,
        agent_config_status=agent_config.status.value,
        status=EvalRunStatus.PENDING.value,
        case_count=len(cases),
        actor=f"admin:{actor[:8]}",
        started_at=datetime.now(UTC),
    )
    # El row se crea en su PROPIA transacción, no en la del request.
    #
    # Antes se hacía ``session.add`` + ``flush`` sobre la sesión del
    # endpoint, que vive dentro del ``session.begin()`` de la dependencia y
    # NO commitea hasta que el handler retorna. ``asyncio.create_task``
    # arranca la corrutina en cuanto el handler cede el control, así que su
    # primer ``scalar_one()`` podía ejecutarse ANTES del COMMIT y no ver la
    # fila: ``NoResultFound`` → ``evals.run.background_aborted`` y el run
    # muerto sin resultados. Carrera real, no artefacto de test: en CI
    # (2026-08-19) tumbó ``test_run_judge_error_marks_case_error`` y con
    # ella todos los despliegues a producción.
    #
    # ``BackgroundTasks`` de FastAPI no lo arregla: en 0.136 corren ANTES
    # del teardown de las dependencias con ``yield``, o sea antes del
    # commit. Comprobado, no deducido.
    #
    # Commitear aquí garantiza la visibilidad pase lo que pase con el orden
    # del framework. ``expire_on_commit=False`` en el sessionmaker deja los
    # atributos cargados utilizables tras cerrar la sesión, y el ``refresh``
    # trae los server-defaults antes de que el objeto quede desasociado.
    run_session_factory = get_sessionmaker()
    async with (
        run_session_factory() as run_session,
        tenant_scoped_session(run_session, tenant_id),
    ):
        run_session.add(run)
        await run_session.flush()
        await run_session.refresh(run)

    run_id = run.id
    agent_config_id = agent_config.id

    # Con la fila ya commiteada, la corrutina puede abrir su propia sesión
    # bajo ``tenant_scoped_session`` y encontrarla siempre.
    task = asyncio.create_task(
        _run_eval_background(
            tenant_id=tenant_id,
            run_id=run_id,
            dataset_id=dataset.id,
            agent_config_id=agent_config_id,
            judge_provider=judge_provider,
        ),
        name=f"eval-run-{run_id}",
    )
    _background_eval_tasks.add(task)
    task.add_done_callback(_background_eval_tasks.discard)

    log.info(
        "evals.run.scheduled",
        run_id=str(run_id),
        tenant_id=str(tenant_id),
        dataset_id=str(dataset.id),
        case_count=len(cases),
        agent_config_version=agent_config.version,
    )

    return EvalRunDetailOut(
        **EvalRunOut.model_validate(run).model_dump(),
        results=[],
    )


@router.get(
    "/tenants/{tenant_id}/eval-runs/{run_id}",
    response_model=EvalRunDetailOut,
    dependencies=[Depends(require_admin_token)],
)
async def get_run(
    tenant_id: Annotated[uuid.UUID, Path()],
    run_id: Annotated[uuid.UUID, Path()],
    session: AsyncSession = Depends(ro_scoped_session_from_path),
) -> EvalRunDetailOut:
    run = (
        await session.execute(sa.select(EvalRun).where(EvalRun.id == run_id))
    ).scalar_one_or_none()
    if run is None or run.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    results = (
        (
            await session.execute(
                sa.select(EvalRunResult)
                .where(EvalRunResult.run_id == run.id)
                .order_by(EvalRunResult.case_idx.asc())
            )
        )
        .scalars()
        .all()
    )
    return EvalRunDetailOut(
        **EvalRunOut.model_validate(run).model_dump(),
        results=[EvalRunResultOut.model_validate(r) for r in results],
    )


@router.get(
    "/tenants/{tenant_id}/eval-runs",
    response_model=list[EvalRunOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_runs(
    tenant_id: Annotated[uuid.UUID, Path()],
    session: AsyncSession = Depends(ro_scoped_session_from_path),
    agent_config_version: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[EvalRunOut]:
    stmt = sa.select(EvalRun).order_by(EvalRun.started_at.desc())
    if agent_config_version is not None:
        stmt = stmt.where(EvalRun.agent_config_version == agent_config_version)
    stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [EvalRunOut.model_validate(r) for r in rows]


__all__ = [
    "FakeJudgeProvider",
    "get_judge_provider",
    "router",
    "set_judge_provider",
]
