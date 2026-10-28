"""La evaluación del constructor — spec 047, T100 (requisito 54.4; CE-002 y CE-003).

Auphere mide el constructor contra un banco fijo de 100 descripciones
(``eval_bank_v1.json``, seis sectores) y compara con la vez anterior:

- **el validador a la primera**: el porcentaje de borradores que el modelo dio ya
  válidos, sin que el saneado tuviera que quitar ninguna herramienta ni el
  validador encontrara nada (CE-002);
- **la batería sin edición**: el porcentaje de borradores que pasan la batería de
  su sector sin tocarlos (CE-003). Necesita correr pruebas: solo si se da con qué
  (``battery``); si no, queda vacía y se dice;
- **el p90 del borrador** en milisegundos (objetivo: < 30 s).

Corre sin escribir nada en ningún cliente: el borrador se construye contra un
catálogo y una ficha de ejemplo. Las de plataforma se guardan en ``builder_eval_runs``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.agent_spec import BuilderEvalRun
from nexus_api.services.agent_spec.validator import Context
from nexus_api.services.builder.agent_draft import (
    BuilderUnavailable,
    DraftRequest,
    build_messages,
    parse_output,
    sanitize,
)
from nexus_api.services.business.compilation import Facts

BANK_VERSION: Final = "v1"
BANK: Final = Path(__file__).with_name("eval_bank_v1.json")

Complete = Callable[[list[dict[str, str]]], Awaitable[str]]
Battery = Callable[[Any], Awaitable[bool]]


def bank() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(BANK.read_text(encoding="utf-8"))
    return data


def _p90(values: Sequence[float]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return int(ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))])


async def evaluate(
    complete: Complete,
    *,
    ctx: Context,
    items: Sequence[Mapping[str, Any]] | None = None,
    battery: Battery | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    timings: list[float] = []
    for item in items if items is not None else bank():
        request = DraftRequest.clean(str(item["name"]), str(item["description"]))
        facts = Facts(name=str(item.get("niche") or "Negocio"), niche=str(item.get("niche") or ""))
        started = time.perf_counter()
        try:
            raw = parse_output(await complete(build_messages(request, facts, ctx)))
            draft = sanitize(raw, request, ctx, facts, model_policy=None)
        except BuilderUnavailable as exc:
            timings.append((time.perf_counter() - started) * 1000)
            results.append({"id": item["id"], "ok": False, "first_pass": False, "error": str(exc)})
            continue
        timings.append((time.perf_counter() - started) * 1000)
        first_pass = not draft.dropped_tools
        passed = await battery(draft) if battery is not None else None
        results.append(
            {
                "id": item["id"],
                "ok": True,
                "first_pass": first_pass,
                "battery": passed,
                "questions": len(draft.questions),
                "tests": len(draft.tests),
            }
        )
    total = len(results) or 1
    first = sum(1 for r in results if r.get("first_pass"))
    with_battery = [r for r in results if r.get("battery") is not None]
    return {
        "results": results,
        "validator_first_pass_pct": round(100.0 * first / total, 2),
        "sector_pass_unedited_pct": (
            round(100.0 * sum(1 for r in with_battery if r["battery"]) / len(with_battery), 2)
            if with_battery
            else None
        ),
        "draft_p90_ms": _p90(timings),
    }


async def record(session: AsyncSession, report: Mapping[str, Any], *, by: str) -> BuilderEvalRun:
    row = BuilderEvalRun(
        bank_version=BANK_VERSION,
        results=list(report["results"]),
        validator_first_pass_pct=Decimal(str(report["validator_first_pass_pct"])),
        sector_pass_unedited_pct=(
            Decimal(str(report["sector_pass_unedited_pct"]))
            if report.get("sector_pass_unedited_pct") is not None
            else None
        ),
        draft_p90_ms=report.get("draft_p90_ms"),
        created_by=by,
    )
    session.add(row)
    await session.flush()
    return row


async def history(session: AsyncSession, limit: int = 20) -> list[dict[str, Any]]:
    """Las evaluaciones, la última primero, con la diferencia con la anterior."""
    rows = (
        await session.scalars(
            sa.select(BuilderEvalRun).order_by(BuilderEvalRun.created_at.desc()).limit(limit)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        prev = rows[i + 1] if i + 1 < len(rows) else None

        def delta(a: Any, b: Any) -> float | None:
            return None if a is None or b is None else round(float(a) - float(b), 2)

        out.append(
            {
                "id": str(row.id),
                "bank_version": row.bank_version,
                "created_at": row.created_at,
                "created_by": row.created_by,
                "validator_first_pass_pct": float(row.validator_first_pass_pct or 0),
                "sector_pass_unedited_pct": (
                    float(row.sector_pass_unedited_pct)
                    if row.sector_pass_unedited_pct is not None
                    else None
                ),
                "draft_p90_ms": row.draft_p90_ms,
                "vs_previous": {
                    "validator_first_pass_pct": delta(
                        row.validator_first_pass_pct,
                        prev.validator_first_pass_pct if prev else None,
                    ),
                    "sector_pass_unedited_pct": delta(
                        row.sector_pass_unedited_pct,
                        prev.sector_pass_unedited_pct if prev else None,
                    ),
                    "draft_p90_ms": delta(row.draft_p90_ms, prev.draft_p90_ms if prev else None),
                }
                if prev
                else None,
            }
        )
    return out


__all__ = ["BANK_VERSION", "bank", "evaluate", "history", "record"]
