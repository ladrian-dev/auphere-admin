"""Seed-dataset loader for the eval suite (roadmap E2.1).

The eval datasets that anchor the promotion gate are version-controlled
as JSON in ``seed_datasets/`` — not hand-typed into each tenant through
the admin UI. This module loads one of those JSON files into a tenant
as an :class:`EvalDataset` + its :class:`EvalCase` rows.

Idempotent: re-loading the same file replaces the dataset's cases in
full, so editing the JSON and re-running is the supported workflow.

CLI::

    uv run python -m nexus_api.services.evals.seed_loader <tenant_id> barbershop_v1
    uv run python -m nexus_api.services.evals.seed_loader <tenant_id> ./path/to/custom.json
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import EvalCase, EvalDataset
from nexus_api.services.evals.assertions import (
    AssertionValidationError,
    validate_assertions,
)

log = structlog.get_logger(__name__)

SEED_DATASETS_DIR = Path(__file__).parent / "seed_datasets"


def available_seeds() -> list[str]:
    """Names of the bundled seed datasets (without the ``.json``)."""
    return sorted(p.stem for p in SEED_DATASETS_DIR.glob("*.json"))


def resolve_seed_payload(ref: str) -> dict[str, Any]:
    """Load a seed payload by bundled name (``barbershop_v1``) or by an
    explicit filesystem path."""
    candidate = SEED_DATASETS_DIR / f"{ref}.json"
    path = candidate if candidate.is_file() else Path(ref)
    if not path.is_file():
        raise FileNotFoundError(
            f"seed dataset {ref!r} not found — bundled options: {available_seeds()}"
        )
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


async def load_seed_dataset(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    payload: dict[str, Any],
) -> EvalDataset:
    """Upsert one dataset + its cases into ``tenant_id``.

    The caller must have already scoped ``session`` to the tenant
    (``tenant_scoped_session``) so RLS accepts the writes. The dataset
    is matched by ``(tenant_id, name)``; its cases are deleted and
    re-inserted in full so the JSON is the single source of truth.
    """
    name = payload["name"]
    cases = payload.get("cases") or []

    # Validate every case BEFORE touching the DB — a bad seed file
    # should fail loudly without leaving a half-written dataset.
    for i, case in enumerate(cases):
        try:
            validate_assertions(case.get("assertions") or {})
        except AssertionValidationError as exc:
            raise ValueError(f"case[{i}] {case.get('name')!r}: {exc}") from exc

    dataset = (
        await session.execute(
            sa.select(EvalDataset)
            .where(EvalDataset.tenant_id == tenant_id)
            .where(EvalDataset.name == name)
        )
    ).scalar_one_or_none()

    threshold = payload.get("pass_threshold")
    if dataset is None:
        dataset = EvalDataset(
            tenant_id=tenant_id,
            name=name,
            description=payload.get("description"),
            version=1,
        )
        if threshold is not None:
            dataset.pass_threshold = Decimal(str(threshold))
        session.add(dataset)
        await session.flush()
    else:
        dataset.description = payload.get("description")
        if threshold is not None:
            dataset.pass_threshold = Decimal(str(threshold))
        dataset.archived_at = None
        # Replace the cases wholesale — the JSON is authoritative.
        await session.execute(sa.delete(EvalCase).where(EvalCase.dataset_id == dataset.id))
        await session.flush()

    for i, case in enumerate(cases):
        session.add(
            EvalCase(
                tenant_id=tenant_id,
                dataset_id=dataset.id,
                idx=case.get("idx", i),
                name=case["name"],
                user_message=case["user_message"],
                history=case.get("history") or [],
                assertions=case.get("assertions") or {},
            )
        )
    await session.flush()
    log.info(
        "evals.seed.loaded",
        tenant_id=str(tenant_id),
        dataset=name,
        case_count=len(cases),
    )
    return dataset


async def _amain(tenant_id: uuid.UUID, ref: str) -> None:
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker

    payload = resolve_seed_payload(ref)
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        dataset = await load_seed_dataset(session, tenant_id=tenant_id, payload=payload)
        print(
            f"loaded dataset {dataset.name!r} ({len(payload.get('cases') or [])} cases) "
            f"into tenant {tenant_id}"
        )


if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) != 3:
        print(
            "usage: python -m nexus_api.services.evals.seed_loader "
            "<tenant_id> <seed_name_or_path>\n"
            f"bundled seeds: {available_seeds()}"
        )
        raise SystemExit(2)
    asyncio.run(_amain(uuid.UUID(sys.argv[1]), sys.argv[2]))
