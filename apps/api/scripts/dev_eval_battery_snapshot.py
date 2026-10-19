"""La batería de evaluación de los clientes, antes y después de un cambio — spec 030 (T109, CE-006).

CE-006 pide que, tras el multiagente (0152-0153), los clientes existentes
respondan igual: su batería da el mismo resultado que antes. Este script hace la
comparación de verdad, con el código de cada lado:

1. ``seed`` (con el código ANTERIOR y la base en su cabeza): un cliente por
   vertical que tiene batería semilla, con dos números de WhatsApp, su
   configuración activa sacada de la plantilla y su conjunto de evaluación.
2. ``snapshot --out antes.json`` (código anterior): corre la batería de cada
   cliente por el pipeline real con un modelo determinista y guarda la foto.
3. ``alembic upgrade head`` con el código NUEVO sobre la misma base.
4. ``snapshot --out despues.json`` (código nuevo) y ``compare antes.json
   despues.json``.

El modelo es determinista y **depende de lo que recibe**: llama a la primera
herramienta que se le ofrece y responde con lo que ha visto. La foto guarda, por
caso, el estado, las aserciones, las herramientas despachadas con su estado y la
respuesta, y un resumen (sha256) de cada llamada al modelo —rol, modelo,
mensajes y herramientas ofrecidas— con los identificadores y las horas
normalizados. Dos fotos iguales dicen que cada cliente recibió exactamente el
mismo contexto y produjo exactamente lo mismo. Con el código nuevo la foto
también anota qué configuración contesta en cada número (``agent_for_channel``):
tiene que ser la misma para los dos números y la misma que la activa de antes.

Solo usa APIs que existen a los dos lados del cambio. Solo para desarrollo: se
niega a correr en producción o contra una base que no sea local.

Uso (lee NEXUS_DATABASE_URL del entorno; una base propia, nunca la de pytest)::

    uv run python scripts/dev_eval_battery_snapshot.py seed
    uv run python scripts/dev_eval_battery_snapshot.py snapshot --out antes.json
    uv run python scripts/dev_eval_battery_snapshot.py compare antes.json despues.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    EvalCase,
    EvalDataset,
    EvalRun,
    EvalRunResult,
    EvalRunStatus,
    Tenant,
    TenantPlan,
)
from nexus_api.repositories.agent_config import AgentConfigRepository
from nexus_api.services.evals import FakeJudgeProvider, run_eval, set_eval_llm_router
from nexus_api.services.evals.seed_loader import (
    available_seeds,
    load_seed_dataset,
    resolve_seed_payload,
)
from nexus_api.services.templating.seed_templates import list_seed_templates, load_seed_template

SLUG_PREFIX = "t109-"
ACTOR = "dev:eval-battery-snapshot"
#: The classifier's vocabulary (``VALID_INTENTS`` of the pipeline, the same on both sides).
INTENTS = ("book", "queue", "info", "escalate", "fallback")

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?")
_TIME = re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b")


def _refuse_outside_dev() -> None:
    settings = get_settings()
    host = urlparse(settings.database_url.replace("+asyncpg", "")).hostname or ""
    if settings.is_prod or host not in {"localhost", "127.0.0.1"}:
        sys.exit(f"dev_eval_battery_snapshot: solo en local (host={host!r}).")


def _normal(value: Any) -> Any:
    """Ids and clock readings differ between two runs of the same code."""
    if isinstance(value, str):
        return _TIME.sub("<hh:mm>", _DATETIME.sub("<ts>", _UUID.sub("<uuid>", value)))
    if isinstance(value, list | tuple):
        return [_normal(v) for v in value]
    if isinstance(value, dict):
        return {k: _normal(v) for k, v in sorted(value.items())}
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _verticals() -> list[str]:
    return sorted(set(available_seeds()) & set(list_seed_templates()))


async def seed() -> None:
    sm = get_sessionmaker()
    for i, vertical in enumerate(_verticals(), start=1):
        slug = f"{SLUG_PREFIX}{vertical.replace('_', '-')}"
        async with sm() as session:
            if await session.scalar(sa.select(Tenant.id).where(Tenant.slug == slug)):
                print(f"  {slug}: ya existe")
                continue
            tenant_id = uuid.uuid4()
            session.add(
                Tenant(id=tenant_id, name=f"T109 {vertical}", slug=slug, plan=TenantPlan.PRO)
            )
            await session.commit()
        template = load_seed_template(vertical)
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            for n in (1, 2):
                session.add(
                    Channel(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        type=ChannelType.WHATSAPP,
                        provider="meta",
                        provider_identifier=f"+3410{i:02d}0000{n}",
                        config={"role": "agent"},
                        status=ChannelStatus.ACTIVE,
                    )
                )
            session.add(
                AgentConfig(
                    tenant_id=tenant_id,
                    version=1,
                    status=AgentConfigStatus.ACTIVE,
                    system_prompt_rendered=template.system_prompt,
                    tools=list(template.tools_required),
                    policies=dict(template.policies_default),
                    channels=[],
                )
            )
            await load_seed_dataset(
                session, tenant_id=tenant_id, payload=resolve_seed_payload(vertical)
            )
        print(f"  {slug}: sembrado ({len(template.tools_required)} herramientas)")


def _model() -> tuple[Any, Any]:
    from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter, ToolCall

    def _tool_names(call: Any) -> list[str]:
        out = []
        for tool in getattr(call, "tools", ()) or ():
            fn = tool.get("function", tool) if isinstance(tool, dict) else {}
            if fn.get("name"):
                out.append(str(fn["name"]))
        return out

    def _seen_tool(call: Any) -> bool:
        return any(m.get("role") == "tool" for m in getattr(call, "messages", []))

    def responder(call: Any) -> str:
        if getattr(call, "role", "") == "classify":
            # The intent comes from the customer's words, so the battery walks
            # every handler and its share of the whitelist. Always «info»
            # left most of the whitelist out: a control that removed a tool
            # only offered while booking passed unnoticed.
            said = next(
                (m.get("content", "") for m in reversed(call.messages) if m.get("role") == "user"),
                "",
            )
            return INTENTS[int(hashlib.sha256(str(said).encode()).hexdigest(), 16) % len(INTENTS)]
        names = _tool_names(call)
        return f"[{call.role}] vistas {len(names)} herramientas; resultado de herramienta: {_seen_tool(call)}"

    def tool_caller(call: Any) -> list[Any]:
        names = _tool_names(call)
        if names and not _seen_tool(call):
            return [ToolCall(id="t109", name=names[0], arguments={})]
        return []

    provider = InMemoryProvider()
    provider.responder = responder
    provider.tool_caller = tool_caller
    router = LLMRouter(
        provider=provider, classify_model="t/c", respond_model="t/r", fallback_model="t/f"
    )
    return provider, router


async def _answering_config(session: Any, channel_id: uuid.UUID) -> uuid.UUID | None:
    """Which config answers on this number. Before spec 030 there is one per client."""
    try:
        from nexus_api.services.agents import agent_for_channel  # spec 030
    except ImportError:
        active = await AgentConfigRepository(session).get_active()
        return active.id if active else None
    agent_id = await agent_for_channel(session, channel_id)
    active = await AgentConfigRepository(session).get_active(agent_id=agent_id)
    return active.id if active else None


async def snapshot(out: Path) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        tenants = (
            await session.execute(
                sa.select(Tenant.id, Tenant.slug)
                .where(Tenant.slug.like(f"{SLUG_PREFIX}%"))
                .order_by(Tenant.slug)
            )
        ).all()
    if not tenants:
        sys.exit("No hay clientes sembrados: corre antes `seed`.")
    shot: dict[str, Any] = {"taken_at": datetime.now(UTC).isoformat(), "clients": {}}
    for tenant_id, slug in tenants:
        provider, router = _model()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            dataset = (
                await session.execute(
                    sa.select(EvalDataset)
                    .where(EvalDataset.archived_at.is_(None))
                    .order_by(EvalDataset.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one()
            cases = list(
                (
                    await session.execute(
                        sa.select(EvalCase)
                        .where(EvalCase.dataset_id == dataset.id)
                        .order_by(EvalCase.idx)
                    )
                ).scalars()
            )
            config = await AgentConfigRepository(session).get_active()
            assert config is not None, slug
            channels = list(
                (
                    await session.execute(
                        sa.select(Channel.id).order_by(Channel.provider_identifier)
                    )
                ).scalars()
            )
            per_number = [await _answering_config(session, ch) for ch in channels]
            run = EvalRun(
                tenant_id=tenant_id,
                dataset_id=dataset.id,
                dataset_version=dataset.version,
                agent_config_version=config.version,
                agent_config_status=config.status.value,
                status=EvalRunStatus.PENDING.value,
                actor=ACTOR,
                started_at=datetime.now(UTC),
            )
            session.add(run)
            await session.flush()
            set_eval_llm_router(router)
            try:
                outcome = await run_eval(
                    session,
                    tenant_id=tenant_id,
                    run=run,
                    dataset=dataset,
                    cases=cases,
                    agent_config=config,
                    judge_provider=FakeJudgeProvider(),
                )
            finally:
                set_eval_llm_router(None)
            results = list(
                (
                    await session.execute(
                        sa.select(EvalRunResult).where(EvalRunResult.run_id == run.id)
                    )
                ).scalars()
            )
            by_case = {r.case_id: r for r in results}
            case_rows = []
            for case in cases:
                r = by_case[case.id]
                transcript = r.transcript or {}
                case_rows.append(
                    {
                        "idx": case.idx,
                        "status": str(getattr(r.status, "value", r.status)),
                        "assertions": _normal(r.assertion_results),
                        "tool_calls": [
                            {"name": t.get("name"), "status": t.get("status")}
                            for t in transcript.get("tool_calls") or []
                        ],
                        "assistant_message": _normal(transcript.get("assistant_message")),
                    }
                )
            calls = [
                _normal(
                    {
                        "role": c.role,
                        "model": c.model,
                        "messages": c.messages,
                        "tools": list(c.tools),
                    }
                )
                for c in provider.calls
            ]
            shot["clients"][slug] = {
                "run_status": str(getattr(outcome.status, "value", outcome.status)),
                "pass_rate": str(outcome.pass_rate),
                "config": {"id": str(config.id), "version": config.version},
                "config_per_number": [str(x) if x else None for x in per_number],
                "cases": case_rows,
                "llm_calls": len(calls),
                "llm_calls_sha256": [_digest(c) for c in calls],
                "llm_calls_full": calls,
            }
        print(
            f"  {slug}: {shot['clients'][slug]['run_status']} · pass_rate {shot['clients'][slug]['pass_rate']} · {len(calls)} llamadas al modelo"
        )
    out.write_text(json.dumps(shot, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Foto en {out}")


def compare(before: Path, after: Path) -> int:
    a = json.loads(before.read_text(encoding="utf-8"))["clients"]
    b = json.loads(after.read_text(encoding="utf-8"))["clients"]
    problems: list[str] = []
    if sorted(a) != sorted(b):
        problems.append(f"clientes distintos: {sorted(a)} ≠ {sorted(b)}")
    for slug in sorted(set(a) & set(b)):
        x, y = a[slug], b[slug]
        for key in ("run_status", "pass_rate", "cases", "llm_calls", "llm_calls_sha256"):
            if x[key] != y[key]:
                problems.append(f"{slug}: {key} cambia")
        if x["config"] != y["config"]:
            problems.append(
                f"{slug}: la configuración activa cambia ({x['config']} → {y['config']})"
            )
        if len(set(y["config_per_number"])) != 1 or y["config_per_number"][0] != x["config"]["id"]:
            problems.append(
                f"{slug}: no contesta la misma configuración en cada número ({y['config_per_number']})"
            )
        print(
            f"  {slug}: {x['run_status']}/{y['run_status']} · pass_rate {x['pass_rate']}/{y['pass_rate']} · "
            f"{x['llm_calls']}/{y['llm_calls']} llamadas · {'igual' if not [p for p in problems if p.startswith(slug)] else 'DISTINTO'}"
        )
    for p in problems:
        print(f"✗ {p}")
    print(
        "✓ Misma batería, mismo resultado." if not problems else f"✗ {len(problems)} diferencias."
    )
    return 1 if problems else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Batería de evaluación antes/después (spec 030, T109).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    s = sub.add_parser("snapshot")
    s.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("before", type=Path)
    c.add_argument("after", type=Path)
    args = p.parse_args()
    if args.cmd == "compare":
        return compare(args.before, args.after)
    _refuse_outside_dev()
    asyncio.run(seed() if args.cmd == "seed" else snapshot(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
