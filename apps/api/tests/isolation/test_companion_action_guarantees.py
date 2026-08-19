"""Las garantías del camino de escritura del Companion (CO-04).

Cuatro afirmaciones que, si dejan de ser ciertas, no se notan mirando la
pantalla — se notan cuando ya pasó algo:

- **C4** · una herramienta que escribe sin registro de confirmación rompe
  CI. ``console.apply`` es la única ``mutates`` del catálogo, y aplicar una
  acción no confirmada falla en el motor.
- **C5 (secreto)** · una clave de API no aparece en el transcripto. Ni en
  ``text.delta``, ni en ``preview``, ni en una cita, ni en el log durable.
- **C5 (verificación)** · ``verify.result`` lo produce código determinista.
  Ni un subagente ni una instrucción de "revisa tu trabajo" en ningún
  prompt.
- **C6** · el Companion no escala su propio permiso ni invita por encima
  del rol de quien le habla.

Estructural donde se puede (recorrer el catálogo, leer el código fuente) y
contra la app real donde hace falta.
"""

from __future__ import annotations

import inspect
import json
import uuid
from typing import Any

import pytest
import pytest_asyncio

from nexus_api.companion.tools import CompanionToolbelt
from nexus_api.companion.tools.catalog import (
    ACTION_KINDS,
    ALL_TOOLS,
    APPLY_TOOLS,
    PROPOSE_TOOLS,
    READ_TOOLS,
    ToolSpec,
)
from nexus_api.companion.tools.proposals import APPLY_ROUTES, ROLE_RANK
from nexus_api.core.console_auth import InProcessActor

pytestmark = [pytest.mark.isolation]


def _actor(side: dict[str, Any], user_id: str | None = None) -> InProcessActor:
    return InProcessActor(
        user_id=user_id or side["user_id"],
        partner_id=side["partner_id"],
        jti=f"companion:{uuid.uuid4()}",
    )


@pytest_asyncio.fixture
async def belt_for(client):
    """Un juego de herramientas contra la app real, con lifespan abierto."""
    from nexus_api.main import app

    made: list[CompanionToolbelt] = []

    async def _make(actor: InProcessActor, **kwargs: Any) -> CompanionToolbelt:
        belt = CompanionToolbelt(actor=actor, app=app, **kwargs)
        await belt.__aenter__()
        made.append(belt)
        return belt

    yield _make
    for belt in made:
        await belt.__aexit__(None, None, None)


# ── C4 · una sola puerta de escritura ──────────────────────────────────


def test_console_apply_is_the_only_tool_that_writes() -> None:
    """La afirmación entera de C4 en una línea: cualquier herramienta nueva
    que escribiera tendría que declararse ``mutates``, y aquí se vería."""
    mutating = [t.name for t in ALL_TOOLS if t.tool_class == "mutates"]
    assert mutating == ["console.apply"]


def test_a_mutating_tool_cannot_be_built_without_asking() -> None:
    """No es que rompa un test después: **no se puede construir**. Esa es la
    diferencia entre una invariante y una convención."""
    with pytest.raises(ValueError, match="always_ask"):
        ToolSpec(
            name="console.sneaky_write",
            path="/console/clients",
            description="x",
            label="x",
            tool_class="mutates",
            permission_policy="always_allow",
        )


def test_every_read_tool_is_always_allow_and_every_proposal_asks() -> None:
    for tool in READ_TOOLS:
        assert tool.tool_class == "read", tool.name
        assert tool.permission_policy == "always_allow", tool.name
    for tool in PROPOSE_TOOLS:
        assert tool.tool_class == "propose", tool.name
        assert tool.permission_policy == "always_ask", tool.name
    assert len(APPLY_TOOLS) == 1


def test_the_permission_policy_is_data_and_not_a_prompt_instruction() -> None:
    """§23.1 de Managed Agents. Si el prompt mencionara la política, el
    modelo podría razonar sobre ella — y razonar sobre si necesita permiso
    es exactamente lo que no queremos que haga."""
    from nexus_worker.runtime.companion.prompt import SYSTEM_PROMPT

    for token in ("always_ask", "always_allow", "permission_policy", "tool_class"):
        assert token not in SYSTEM_PROMPT


def test_the_eleven_kinds_are_the_eleven_of_the_contract() -> None:
    """Nueve en la v1.1 §3.1, **once** desde la v2 §4.1 con los dos de
    soporte. Escrito a mano a propósito: si alguien añade un ``kind``, este
    test se pone rojo en vez de encogerse en silencio."""
    assert set(ACTION_KINDS) == {
        "client",
        "prompt",
        "policy",
        "tools",
        "skills",
        "publish",
        "channel_role",
        "usage_alerts",
        "invite",
        "support_help",
        "support_capability",
    }
    assert set(APPLY_ROUTES) == set(ACTION_KINDS)


def test_no_write_route_touches_the_forbidden_list() -> None:
    """§6.5, lista cerrada: borrar clientes, facturación, claves. El mapa de
    aplicación es de nueve entradas y el modelo no puede añadirle una —el
    destino sale del ``kind``, no de un argumento."""
    for kind, (method, path) in APPLY_ROUTES.items():
        assert method in {"POST", "PUT", "PATCH"}, f"{kind} borra algo"
        for forbidden in ("/keys", "/billing", "/status", "/connectors"):
            assert forbidden not in path, f"{kind} llega a {forbidden}"
    # Y ningún verbo destructivo en todo el catálogo, ni siquiera preparado.
    #
    # Se comprueba por lista blanca y no por "todo es GET": CO-05 añade la
    # clase ``trial``, que hace POST contra el playground. Esa es la ÚNICA
    # excepción admitida, y se exige explícitamente —clase y política— en vez
    # de ensanchar la regla, para que una herramienta nueva que escriba con
    # POST siga rompiendo aquí.
    for tool in ALL_TOOLS:
        if tool.method == "GET":
            continue
        assert tool.method == "POST", f"{tool.name} usa un verbo destructivo"
        assert tool.tool_class == "trial", (
            f"{tool.name} no es GET y no es una prueba: la única puerta de "
            "escritura sigue siendo console.apply"
        )
        assert tool.permission_policy == "always_allow", tool.name
        assert tool.kind is None, f"{tool.name} no propone ninguna acción"
        # Y una prueba no toca la configuración del cliente: su ruta es la del
        # playground, que corre en seco y no llega a ningún cliente final.
        assert "/playground/" in tool.path, tool.name


def test_every_write_route_exists_in_the_application() -> None:
    """Una ruta que no existe convertiría cada confirmación en un 404 justo
    después de que la persona dijera que sí."""
    from nexus_api.main import app

    routes = {
        (getattr(r, "path", None), m)
        for r in app.routes
        for m in (getattr(r, "methods", None) or set())
    }
    missing = [
        (kind, method, path)
        for kind, (method, path) in APPLY_ROUTES.items()
        if (path.replace("{client_ref}", "{ref}"), method) not in routes
    ]
    assert not missing, f"rutas de aplicación inexistentes: {missing}"


def test_every_proposal_reads_a_console_route_that_exists() -> None:
    """El equivalente para las propuestas de lo que CO-02 comprueba sobre
    las lecturas: lo que la propuesta lee sale por un endpoint de la consola
    y por tanto ya pasó por el recorrido de ``test_console_scope.py``."""
    from nexus_api.main import app

    routes = {
        (getattr(r, "path", None), m)
        for r in app.routes
        for m in (getattr(r, "methods", None) or set())
    }
    for tool in PROPOSE_TOOLS:
        assert tool.path.startswith("/console/"), tool.name
        declared = tool.path.replace("{client_ref}", "{ref}")
        assert (declared, "GET") in routes, f"{tool.name} lee {declared}, que no existe"


def test_no_proposal_accepts_a_tenant_or_partner_id() -> None:
    """La regla CP-04, heredada tal cual por el carril de escritura."""
    for tool in (*PROPOSE_TOOLS, *APPLY_TOOLS):
        names = {p.name for p in tool.params}
        assert not (names & {"tenant_id", "partner_id", "tenant", "partner"}), tool.name


async def test_applying_an_unconfirmed_action_fails_in_the_engine(belt_for, console_world):
    """**C4, medida.** El modelo puede llamar a ``console.apply`` —está en el
    catálogo a propósito— y choca contra un ``if``, no contra una frase de
    prompt. Una puerta cerrada que nadie puede empujar no demuestra nada."""
    belt = await belt_for(_actor(console_world["a"]), principal_id=console_world["a"]["user_id"])
    out = await belt.call("console.apply", {"action_id": str(uuid.uuid4())})
    assert out.ok is False
    assert out.error_code in {"unknown_action", "not_confirmed"}


async def test_a_proposal_writes_nothing(belt_for, console_world):
    """El nombre lo dice, pero es la mitad del diseño: proponer es leer y
    calcular. Si una ``propose_*`` escribiera, la confirmación humana sería
    decorativa."""
    a = console_world["a"]
    belt = await belt_for(_actor(a), principal_id=a["user_id"])
    before = await belt.call("console.get_agent", {"client_ref": a["ref"]})

    await belt.call(
        "console.propose_prompt",
        {"client_ref": a["ref"], "system_prompt": "Un prompt distinto del que hay."},
    )

    other = await belt_for(_actor(a), principal_id=a["user_id"])
    after = await other.call("console.get_agent", {"client_ref": a["ref"]})
    assert after.content == before.content


# ── C6 · no escalar permisos ───────────────────────────────────────────


def test_the_role_ladder_has_no_rung_above_owner() -> None:
    assert ROLE_RANK["owner"] == max(ROLE_RANK.values())
    assert ROLE_RANK["builder"] < ROLE_RANK["admin"] < ROLE_RANK["owner"]


async def test_the_companion_cannot_invite_above_the_callers_role(
    belt_for, console_world, db_session
):
    """**C6, medida.** Un ``admin`` tiene ``team:manage``, así que el router
    le dejaría invitar a un ``owner``: el techo no lo pone el permiso, lo
    pone esta comprobación. Y el «no» llega con un motivo que el modelo
    puede decir en voz alta, no como un 403 opaco al aplicar."""
    from tests.conftest import add_console_member

    a = console_world["a"]
    admin = await add_console_member(db_session, partner_id=a["partner_id"], role="admin")
    belt = await belt_for(_actor(a, user_id=admin["user_id"]), principal_id=admin["user_id"])

    denied = await belt.call(
        "console.propose_invite", {"email": "nuevo@example.com", "role": "owner"}
    )
    assert denied.ok is False
    payload = json.loads(denied.content)
    assert payload["error"] == "role_escalation"
    assert "owner" in payload["message"]
    assert not belt.pending, "una propuesta rechazada no puede quedar pendiente"


async def test_the_companion_cannot_reach_a_write_its_human_cannot(
    belt_for, console_world, db_session
):
    """El permiso lo sigue comprobando el router con el rol de la FILA. Un
    ``analyst`` no puede proponer un cambio de prompt porque no puede LEER
    el borrador — y ni siquiera llega a la consola del Companion, porque
    ``companion:use`` no es suyo."""
    from tests.conftest import add_console_member

    a = console_world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    belt = await belt_for(_actor(a, user_id=analyst["user_id"]), principal_id=analyst["user_id"])

    denied = await belt.call(
        "console.propose_tools", {"client_ref": a["ref"], "tools": "calendar.list_slots"}
    )
    assert denied.ok is False
    assert not belt.pending


async def test_a_proposal_for_another_partners_client_is_the_opaque_404(belt_for, console_world):
    """C1 aplicada al carril nuevo: si el 404 del ref ajeno se distinguiera,
    el Companion sería un oráculo para averiguar la cartera de la
    competencia probando referencias."""
    a, b = console_world["a"], console_world["b"]
    belt = await belt_for(_actor(a), principal_id=a["user_id"])

    foreign = await belt.call(
        "console.propose_prompt", {"client_ref": b["ref"], "system_prompt": "x"}
    )
    missing = await belt.call(
        "console.propose_prompt", {"client_ref": "no-existe-jamas", "system_prompt": "x"}
    )
    assert foreign.ok is False and missing.ok is False
    assert foreign.content == missing.content
    assert not belt.pending


# ── C5 (secreto) · la clave no aparece en el transcripto ───────────────


def test_no_tool_can_reach_the_key_endpoints() -> None:
    """La forma de garantizar que una clave no sale por el chat es que no
    haya por dónde pedirla. No hay ``kind`` de claves y no se añade."""
    for tool in ALL_TOOLS:
        assert "/keys" not in tool.path, tool.name
        assert "key" not in (tool.kind or ""), tool.name


def test_the_event_catalogue_has_no_place_to_put_a_secret() -> None:
    """El catálogo cerrado ELIMINA lo que no declara, así que la garantía es
    que ninguna clave declarada se llame como un secreto."""
    from nexus_api.api.companion_streaming import COMPANION_EVENTS

    secretish = {"key", "secret", "token", "api_key", "credential", "password", "authorization"}
    for event, keys in COMPANION_EVENTS.items():
        assert not (keys & secretish), f"{event} declara una clave de secreto"


async def test_a_secret_never_reaches_the_durable_log(fake_redis) -> None:
    """Extremo a extremo del guardián sobre los cinco eventos nuevos: se
    intenta colar un secreto en cada uno y se comprueba que no sobrevive al
    log — que es de donde salen ``/events`` y el stream."""
    from nexus_api.api.companion_streaming import publish, read_events

    secret = "sk_live_" + uuid.uuid4().hex
    run_id = uuid.uuid4()
    payloads = {
        "plan.proposed": {"plan_id": "p", "steps": [], "risk": "low", "api_key": secret},
        "intake.missing": {"slots": [], "secret": secret},
        "hitl.requested": {"action_id": "a", "kind": "prompt", "token": secret},
        "hitl.resolved": {"action_id": "a", "decision": "confirm", "credential": secret},
        "verify.result": {"action_id": "a", "checks": [], "ok": True, "password": secret},
    }
    for i, (event, data) in enumerate(payloads.items(), start=1):
        await publish(fake_redis, run_id, seq=i, event=event, data=data)

    events, _gap = await read_events(fake_redis, run_id)
    assert len(events) == 5
    assert secret not in json.dumps([e.data for e in events])


async def test_a_preview_carries_no_full_third_party_email(belt_for, console_world):
    """Enmascarado en ORIGEN. Un correo entero que sale del backend ya está
    en el log durable, en el contexto del modelo y en la transcripción
    persistida: enmascararlo en la interfaz es hacerlo donde ya da igual."""
    a = console_world["a"]
    belt = await belt_for(_actor(a), principal_id=a["user_id"])

    out = await belt.call(
        "console.propose_invite", {"email": "maria@facelad.com", "role": "builder"}
    )
    assert out.ok, out.content
    assert "maria@facelad.com" not in out.content
    assert "m…a@facelad.com" in out.content
    # Y tampoco en lo que se persistiría como previsualización.
    assert "maria@facelad.com" not in json.dumps(belt.pending[0].preview)


# ── C5 (verificación) · código, no modelo ──────────────────────────────


def test_no_prompt_asks_the_model_to_verify_itself() -> None:
    """La guía de migración a Opus 5 es explícita: borrar las instrucciones
    de auto-verificación. Producen sobre-verificación sin ganancia — y un
    verificador que es el mismo modelo que acaba de actuar no verifica, solo
    repite su propia confianza."""
    from nexus_worker.runtime.companion import graph as graph_module
    from nexus_worker.runtime.companion.prompt import SYSTEM_PROMPT

    banned = (
        "revisa tu trabajo",
        "double-check",
        "double check",
        "verifica tu respuesta",
        "revisa otra vez",
        "comprueba tu trabajo",
        "subagente",
        "sub-agente",
        "paso final de verificación",
    )
    haystack = SYSTEM_PROMPT.lower()
    for phrase in banned:
        assert phrase not in haystack, f"el prompt pide auto-verificación: {phrase!r}"

    # Y tampoco en los textos que el motor le manda al reanudar.
    resume_text = " ".join(graph_module._RESUME_BRIEF.values()).lower()
    for phrase in banned:
        assert phrase not in resume_text, f"el brief de reanudación pide {phrase!r}"


def test_the_verification_node_calls_no_model() -> None:
    """Se lee del código porque es la única forma de fijarlo: el nodo
    ``verify`` no puede tener un proveedor a mano, así que no hay manera de
    que un día alguien "mejore" la verificación pidiéndosela al modelo."""
    from nexus_worker.runtime.companion.graph import make_verify

    # Solo el CÓDIGO: la prosa del docstring habla del modelo justamente
    # para explicar por qué no está, y buscarla ahí sería medir el
    # comentario en vez de la función.
    source = "".join(inspect.getsource(make_verify).split('"""')[::2])
    for token in ("provider", "astream", "acomplete", "messages", "model"):
        assert token not in source, f"el nodo verify menciona {token!r}"


def test_the_verifier_is_a_pure_comparison() -> None:
    """``verify_action`` relee y compara. Su firma recibe una función de
    lectura y una fila — nunca un proveedor de modelo."""
    from nexus_api.companion.tools.actions import verify_action

    params = list(inspect.signature(verify_action).parameters)
    assert params == ["read", "action"]
    source = inspect.getsource(verify_action)
    assert "provider" not in source and "llm" not in source.lower()
