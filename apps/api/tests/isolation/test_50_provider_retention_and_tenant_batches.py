"""Garantía 7 — sin retención en el proveedor y sin lotes que mezclen clientes
(spec 047, T019 · requisitos 56.7, 41.3 y 40.12).

``test_7_*`` fija que el transporte no agrupa llamadas de clientes distintos.
La 047 abre proveedores y despliegues nuevos (Bedrock, Scaleway, Responses
API…) y lotes nuevos (pruebas, certificación, sugerencias). Esto barre las dos
cosas con lo que hay hoy, de forma que lo nuevo entre en rojo hasta tener su
regla:

**Retención.** Cada ruta de proveedor del catálogo de plataforma
(``HOP_MODEL_IDS``, espejo de ``model_profiles``) tiene su regla escrita en
``RETENTION_RULES``, y se comprueba **sobre lo que sale de verdad** del
transporte del runtime (``LiteLLMProvider`` con ``litellm.acompletion``
interceptado), con y sin herramientas. Una ruta nueva sin regla es roja; las de
la 047 entran con la suya (``store=false`` en Responses, ``data_retention_mode:
none`` en Bedrock). Además, todo sitio del código que llama a un proveedor está
declarado (``PROVIDER_CALL_SITES``) y ninguno pide ``store=True``.

**Lotes.** No se usa ninguna API de lotes de proveedor (``batch_completion``,
Message Batches…) en ningún sitio, y cada sitio que arma un lote de evaluación
(``run_eval``) tiene su caso: el lote es de un solo cliente aunque la base
tenga, por una FK de una columna de las de antes (test_43), un caso de otro
cliente colgado de su conjunto.
"""

from __future__ import annotations

import ast
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from nexus_worker.runtime.llm import LiteLLMProvider

from nexus_api.core.respond_catalog import HOP_MODEL_IDS
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfigStatus,
    EvalCase,
    EvalDataset,
    EvalRun,
    EvalRunStatus,
)

from .conftest import seed_active_agent_config

pytestmark = [pytest.mark.isolation]  # asyncio_mode=auto

APPS = Path(__file__).resolve().parents[3]
SOURCE_ROOTS = tuple(APPS / part / "src" for part in ("api", "worker", "mcp", "channels"))

# ── retención ──────────────────────────────────────────────────────────────


def _no_store_anywhere(kwargs: dict[str, Any]) -> list[str]:
    out = []
    if kwargs.get("store") is True:
        out.append("store=True")
    if isinstance(kwargs.get("extra_body"), dict) and kwargs["extra_body"].get("store") is True:
        out.append("extra_body.store=True")
    return out


def _anthropic(kwargs: dict[str, Any]) -> list[str]:
    """Messages API: la retención cero es del contrato de la organización (no
    hay parámetro por petición). Lo que sí se comprueba es que la llamada no
    pide guardar nada ni va por la API de lotes."""
    return _no_store_anywhere(kwargs)


def _openai(kwargs: dict[str, Any]) -> list[str]:
    """Chat Completions, donde ``store`` vale ``false`` por defecto: nunca se
    pide ``true``. Y la llamada no se desvía a la Responses API —que guarda por
    defecto—: con herramientas, ``reasoning_effort`` va en ``extra_body`` porque
    como kwarg litellm la reencaminaría a ``/responses`` (``llm.py``)."""
    out = _no_store_anywhere(kwargs)
    if kwargs.get("tools") and "reasoning_effort" in kwargs:
        out.append("reasoning_effort de primer nivel con herramientas → Responses API")
    return out


def _bedrock(kwargs: dict[str, Any]) -> list[str]:
    """AWS Bedrock (T142): la retención cero se pide en cada petición,
    ``data_retention_mode: none``, y nada pide guardar."""
    out = _no_store_anywhere(kwargs)
    if kwargs.get("data_retention_mode") != "none":
        out.append(f"data_retention_mode={kwargs.get('data_retention_mode')!r}, no 'none'")
    return out


def _scaleway(kwargs: dict[str, Any]) -> list[str]:
    """Scaleway (T142), por su API compatible con OpenAI: ``store=false``
    explícito en cada petición (además de su retención cero por defecto)."""
    out = _no_store_anywhere(kwargs)
    if kwargs.get("store") is not False:
        out.append(f"store={kwargs.get('store')!r}, no False")
    return out


#: Prefijo de ruta → la regla que lo que sale tiene que cumplir. Una ruta nueva
#: (``openai/responses/``…) entra con la suya: ``store=false`` explícito en
#: Responses y ``data_retention_mode: none`` en Bedrock (requisito 41.3).
RETENTION_RULES = {
    "anthropic": _anthropic,
    "openai": _openai,
    "bedrock": _bedrock,
    "scaleway": _scaleway,
}

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "client.get_history",
            "description": "x",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


@pytest.fixture
def captured(monkeypatch) -> list[dict[str, Any]]:
    """Lo que el transporte entrega a ``litellm.acompletion``, sin salir a la red."""
    import litellm

    calls: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"choices": [{"message": {"content": "ok", "tool_calls": []}}]}

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return calls


def test_every_catalog_route_has_a_retention_rule() -> None:
    routes = {model.split("/", 1)[0] for model in HOP_MODEL_IDS}
    missing = sorted(routes - RETENTION_RULES.keys())
    assert not missing, (
        f"rutas de proveedor sin regla de retención: {missing}. Toda ruta nueva sale "
        "con store=false o data_retention_mode: none, según su API (requisito 41.3)."
    )


@pytest.mark.parametrize("model", HOP_MODEL_IDS)
@pytest.mark.parametrize("with_tools", [False, True], ids=["sin_tools", "con_tools"])
async def test_what_leaves_for_the_provider_keeps_nothing(
    model: str, with_tools: bool, captured
) -> None:
    provider = LiteLLMProvider(context_management=None)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "hola"}]
    tenant = uuid.uuid4()
    if with_tools:
        await provider.acomplete_with_tools(
            tenant_id=tenant, role="info", model=model, messages=messages, tools=_TOOLS
        )
    else:
        await provider.acomplete(tenant_id=tenant, role="info", model=model, messages=messages)

    assert len(captured) == 1, "una llamada del turno, una petición al proveedor"
    sent = captured[0]
    rule = RETENTION_RULES[model.split("/", 1)[0]]
    assert not rule(sent), f"{model}: {rule(sent)}"
    # Y el cliente no viaja como metadato al proveedor.
    assert str(tenant) not in repr(sent.get("metadata")), sent.get("metadata")


# ── retención por despliegue (T141, requisito 41.3) ───────────────────────
#
# Con el router, la regla ya no la pone el prefijo de la ruta sino la fila del
# catálogo: ``retention_how`` dice cómo se fuerza la retención cero de ese
# despliegue, y el transporte la aplica. Lo que se barre es **la base**: todo
# despliegue que declara retención cero tiene un ``retention_how`` que el
# transporte sabe aplicar, y lo que sale al proveedor la lleva.


async def test_every_zero_retention_deployment_has_a_rule_the_transport_applies(
    db_session,
) -> None:
    import sqlalchemy as sa
    from nexus_worker.runtime.llm import RETENTION_WIRE

    rows = (
        await db_session.execute(
            sa.text(
                "SELECT model_id, retention_how FROM model_profiles "
                "WHERE zero_retention OR status = 'active'"
            )
        )
    ).all()
    unknown = sorted(
        f"{model_id}: {how!r}"
        for model_id, how in rows
        if how is not None and how not in RETENTION_WIRE
    )
    assert not unknown, f"retenciones que el transporte no sabe aplicar: {unknown}"
    declared_zero = (
        (
            await db_session.execute(
                sa.text(
                    "SELECT model_id FROM model_profiles WHERE zero_retention AND retention_how IS NULL"
                )
            )
        )
        .scalars()
        .all()
    )
    assert not declared_zero, f"retención cero sin decir cómo se fuerza: {declared_zero}"


@pytest.mark.parametrize("how", ["store=false", "data_retention_mode:none"])
@pytest.mark.parametrize("with_tools", [False, True], ids=["sin_tools", "con_tools"])
async def test_a_routed_call_carries_its_deployments_retention(
    how: str, with_tools: bool, captured
) -> None:
    from nexus_worker.runtime.llm import RETENTION_WIRE, RouteHop, routed

    from nexus_api.core import respond_catalog
    from nexus_api.services.router_catalog import deployment_from_row

    key = "openai/gpt-5.6-luna"
    deployment = deployment_from_row(
        {
            "id": uuid.uuid4(),
            "provider": "openai",
            "model_id": key,
            "display_name": key,
            "family": "openai-gpt",
            "residency": "global",
            "zero_retention": True,
            "retention_how": how,
            "contract_dpa": True,
            "subprocessor_listed": True,
            "status": "active",
            "capabilities": {
                "tools": True,
                "cache_mode": "implicit",
                "tool_name_charset": "no_dots",
            },
        },
        prices=[],
    )
    respond_catalog.reset()
    provider = LiteLLMProvider(context_management=None)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "hola"}]
    with routed(RouteHop(task="tool_turn", deployment=deployment, decision_id=uuid.uuid4())):
        if with_tools:
            await provider.acomplete_with_tools(
                tenant_id=uuid.uuid4(), role="info", model=key, messages=messages, tools=_TOOLS
            )
        else:
            await provider.acomplete(
                tenant_id=uuid.uuid4(), role="info", model=key, messages=messages
            )
    sent = captured[-1]
    for wire_key, value in RETENTION_WIRE[how].items():
        assert sent[wire_key] == value, (how, sent.get(wire_key))
    assert not _no_store_anywhere(sent)


# ── las rutas nuevas, también en borrador (T142, requisitos 41.3 y 41.5) ───


async def test_every_route_of_the_catalog_has_a_rule_even_in_draft(db_session) -> None:
    """Un despliegue en borrador todavía no recibe nada, pero el día que pasa a
    certificar ya ejecuta: su ruta tiene que llegar con su regla."""
    import sqlalchemy as sa

    keys = (await db_session.execute(sa.text("SELECT model_id FROM model_profiles"))).scalars()
    routes = {str(k).split("/", 1)[0] for k in keys.all()}
    assert {"bedrock", "scaleway"} <= routes, "la 0185 siembra Bedrock y Scaleway en borrador"
    missing = sorted(routes - RETENTION_RULES.keys())
    assert not missing, f"rutas del catálogo sin regla de retención: {missing}"


def _draft(key: str) -> Any:
    """Una fila de la 0185, como si su retención cero ya estuviera firmada."""
    import importlib.util

    from nexus_api.services.router_catalog import deployment_from_row

    path = APPS / "api" / "alembic" / "versions" / "0185_bedrock_scaleway_drafts.py"
    spec = importlib.util.spec_from_file_location("_mig_0185", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    [row] = [r for r in module.DRAFTS if r["model_id"] == key]
    return deployment_from_row(
        {
            **row,
            "id": uuid.uuid4(),
            "residency": "eu",
            "zero_retention": True,
            "contract_dpa": True,
            "subprocessor_listed": True,
            "status": "active",
        },
        prices=[],
    )


@pytest.mark.parametrize(
    "key",
    [
        "bedrock/eu.anthropic.claude-haiku-5-5",
        "bedrock/eu.anthropic.claude-sonnet-5-5",
        "scaleway/gpt-oss-120b",
        "scaleway/gpt-oss-20b",
    ],
)
@pytest.mark.parametrize("with_tools", [False, True], ids=["sin_tools", "con_tools"])
async def test_bedrock_and_scaleway_leave_with_their_retention_on_the_wire(
    key: str, with_tools: bool, captured
) -> None:
    """Lo que sale del transporte hacia una ruta de la 0185 cumple su regla, con
    y sin herramientas. Que el proveedor la acepte se comprueba en su
    certificación, antes de activarla (la puerta lo exige)."""
    from nexus_worker.runtime.llm import RouteHop, routed

    from nexus_api.core import respond_catalog

    deployment = _draft(key)
    # Ejecutable como el día que pase a certificar: un borrador no sale nunca
    # (``require_hop_model``), y eso ya lo fija la prueba de la 0185.
    respond_catalog.refresh_from_rows([{"model_id": key, "status": "certifying"}])
    provider = LiteLLMProvider(context_management=None)
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "hola"}]
    with routed(RouteHop(task="tool_turn", deployment=deployment, decision_id=uuid.uuid4())):
        if with_tools:
            await provider.acomplete_with_tools(
                tenant_id=uuid.uuid4(), role="info", model=key, messages=messages, tools=_TOOLS
            )
        else:
            await provider.acomplete(
                tenant_id=uuid.uuid4(), role="info", model=key, messages=messages
            )
    sent = captured[-1]
    respond_catalog.reset()
    rule = RETENTION_RULES[key.split("/", 1)[0]]
    assert not rule(sent), f"{key}: {rule(sent)}"


#: Todo sitio del código de producto que llama a un proveedor de modelos, y su
#: ruta. Uno nuevo se declara aquí —con su regla— o el test es rojo.
PROVIDER_CALL_SITES: dict[str, str] = {
    "worker/src/nexus_worker/runtime/llm.py": (
        "El transporte del runtime (``_proxied_acompletion``): lo barre "
        "test_what_leaves_for_the_provider_keeps_nothing."
    ),
    "worker/src/nexus_worker/multimodal/processor.py": (
        "Visión (acompletion) y transcripción (atranscription) de un adjunto, "
        "una petición por adjunto del turno; mismas rutas del catálogo."
    ),
    "api/src/nexus_api/services/evals/judge.py": "El juez de las evaluaciones, una pregunta por llamada.",
    "api/src/nexus_api/services/prompt_improver/service.py": "Mejora del prompt, a petición.",
    "api/src/nexus_api/services/test_agent/service.py": "Prueba del agente desde el panel.",
    "api/src/nexus_api/core/litellm_smoke.py": "Comprobación de arranque, sin datos de clientes.",
}
#: APIs de lotes de proveedor: una sola petición con trabajo de varios.
BATCH_APIS = frozenset(
    {"batch_completion", "abatch_completion", "acreate_batch", "create_batch", "batches"}
)


def _provider_calls() -> tuple[dict[str, list[ast.Call]], list[str]]:
    """Las llamadas ``litellm.x(...)``/``openai.x(...)``/``anthropic.x(...)`` por
    módulo, y todo uso de una API de lotes."""
    calls: dict[str, list[ast.Call]] = {}
    batches: list[str] = []
    for root in SOURCE_ROOTS:
        for path in root.rglob("*.py"):
            where = str(path.relative_to(APPS))
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in {"litellm", "openai", "anthropic"}
                ):
                    calls.setdefault(where, []).append(node)
                elif isinstance(node, ast.Attribute) and node.attr in BATCH_APIS:
                    batches.append(f"{where}:{node.lineno} usa una API de lotes ({node.attr})")
    return calls, batches


def test_every_provider_call_site_is_declared_and_asks_to_keep_nothing() -> None:
    sites, batches = _provider_calls()
    assert "worker/src/nexus_worker/runtime/llm.py" in sites, "el barrido no ve el transporte"
    undeclared = sorted(sites.keys() - PROVIDER_CALL_SITES.keys())
    assert not undeclared, f"llamadas a proveedores sin declarar: {undeclared}"
    assert not PROVIDER_CALL_SITES.keys() - sites.keys(), "sitios declarados que ya no llaman"
    assert not batches, f"lotes de proveedor (mezclan peticiones en una): {batches}"
    offenders = []
    for path, nodes in sites.items():
        for node in nodes:
            for kw in node.keywords:
                if kw.arg == "store" and not (
                    isinstance(kw.value, ast.Constant) and kw.value.value is False
                ):
                    offenders.append(f"{path}:{node.lineno} pasa store={ast.unparse(kw.value)}")
    assert not offenders, offenders


# ── lotes por cliente ─────────────────────────────────────────────────────

#: Sitios que arman un lote de evaluación (llaman a ``run_eval``) y su caso.
EVAL_BATCH_BUILDERS: dict[str, str] = {
    "api/src/nexus_api/api/admin/evals.py": "test_the_admin_eval_batch_is_one_clients",
    "worker/src/nexus_worker/streams/continuous_eval_cron.py": (
        "test_the_continuous_eval_batch_is_one_clients"
    ),
}


def test_every_eval_batch_builder_has_its_case() -> None:
    builders = set()
    for root in SOURCE_ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(
                isinstance(n, ast.Call) and getattr(n.func, "id", None) == "run_eval"
                for n in ast.walk(tree)
            ):
                builders.add(str(path.relative_to(APPS)))
    assert builders == EVAL_BATCH_BUILDERS.keys(), sorted(builders)
    for case in EVAL_BATCH_BUILDERS.values():
        assert callable(globals().get(case)), f"caso que no existe: {case}"


async def _two_clients_with_datasets(db_session, tenants_ab) -> dict[str, Any]:
    """A y B con su conjunto, sus casos y su versión activa; y un caso de B
    colgado del conjunto de A (la FK de una columna lo permite)."""
    out: dict[str, Any] = {}
    for key in ("a", "b"):
        tenant = tenants_ab[key]
        cfg = await seed_active_agent_config(
            db_session, tenant_id=tenant, system_prompt=key, tools=[]
        )
        dataset = EvalDataset(tenant_id=tenant, name=f"ds-{key}", description="", version=1)
        db_session.add(dataset)
        await db_session.flush()
        for idx in range(2):
            db_session.add(
                EvalCase(
                    tenant_id=tenant,
                    dataset_id=dataset.id,
                    idx=idx,
                    name=f"CASO-{key.upper()}-{idx}",
                    user_message=f"MENSAJE-{key.upper()}-{idx}",
                    history=[],
                    assertions={},
                )
            )
        await db_session.commit()
        out[key] = {"tenant": tenant, "dataset": dataset, "config": cfg}
    db_session.add(
        EvalCase(
            tenant_id=tenants_ab["b"],
            dataset_id=out["a"]["dataset"].id,
            idx=9,
            name="CASO-B-COLADO",
            user_message="MENSAJE-B-COLADO",
            history=[],
            assertions={},
        )
    )
    await db_session.commit()
    return out


def _single_client(batch: dict[str, Any], tenant: uuid.UUID) -> None:
    assert batch["tenant_id"] == tenant
    assert batch["dataset"] == tenant
    assert batch["agent_config"] == tenant
    assert batch["cases"], "el lote salió vacío"
    owners = {owner for owner, _message in batch["cases"]}
    assert owners == {tenant}, f"el lote mezcla clientes: {owners}"
    assert "MENSAJE-B" not in repr(batch["cases"])


@pytest.fixture
def recorded_batches(monkeypatch) -> list[dict[str, Any]]:
    """Sustituye ``run_eval`` en los dos sitios que arman lotes: se graba lo que
    reciben y no se llama a ningún modelo."""
    import nexus_worker.streams.continuous_eval_cron as cron

    from nexus_api.api.admin import evals as admin_evals

    batches: list[dict[str, Any]] = []

    async def record(session, **kwargs: Any) -> Any:
        # De quién es cada pieza, leído aquí: la sesión del lote se cierra luego.
        batches.append(
            {
                "tenant_id": kwargs["tenant_id"],
                "dataset": kwargs["dataset"].tenant_id,
                "agent_config": kwargs["agent_config"].tenant_id,
                "cases": [(c.tenant_id, c.user_message) for c in kwargs["cases"]],
            }
        )
        raise RuntimeError("lote grabado; no se ejecuta")

    monkeypatch.setattr(cron, "run_eval", record)
    monkeypatch.setattr(admin_evals, "run_eval", record)
    return batches


async def test_the_continuous_eval_batch_is_one_clients(
    db_session, tenants_ab, recorded_batches
) -> None:
    from nexus_worker.streams.continuous_eval_cron import _run_for_tenant

    world = await _two_clients_with_datasets(db_session, tenants_ab)
    await _run_for_tenant(get_sessionmaker(), world["a"]["tenant"])
    assert len(recorded_batches) == 1
    _single_client(recorded_batches[0], world["a"]["tenant"])


async def test_the_admin_eval_batch_is_one_clients(
    db_session, tenants_ab, recorded_batches
) -> None:
    from nexus_api.api.admin.evals import _run_eval_background
    from nexus_api.services.evals import FakeJudgeProvider

    world = await _two_clients_with_datasets(db_session, tenants_ab)
    a = world["a"]
    run = EvalRun(
        tenant_id=a["tenant"],
        dataset_id=a["dataset"].id,
        dataset_version=1,
        agent_config_version=a["config"].version,
        agent_config_status=AgentConfigStatus.ACTIVE.value,
        status=EvalRunStatus.PENDING.value,
        actor="iso50",
        started_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.commit()

    judge = FakeJudgeProvider()
    await _run_eval_background(a["tenant"], run.id, a["dataset"].id, a["config"].id, judge)
    assert len(recorded_batches) == 1
    _single_client(recorded_batches[0], a["tenant"])

    # El conjunto o la versión de otro cliente, nombrados bajo A: no hay lote.
    b = world["b"]
    await _run_eval_background(a["tenant"], run.id, b["dataset"].id, a["config"].id, judge)
    await _run_eval_background(a["tenant"], run.id, a["dataset"].id, b["config"].id, judge)
    assert len(recorded_batches) == 1, "se armó un lote con piezas de otro cliente"
