"""Spec 065: la batería en el cable de los perfiles de respuesta (research.md §D9.1).

Las llamadas van por ``LiteLLMProvider`` real hasta un servidor local que hace de OpenAI y de
Anthropic, con la puerta de LiteLLM (mapa fijo y entradas registradas). Sin coste y sin red.
El turno es el de producción: el manejador de ``pipeline.py`` y ``LLMRouter.respond_with_tools``
sin salto enrutado (el router está aparcado, research.md §D6), que es por donde un perfil tiene
que llegar al cable. Todo corre en **un** subproceso, una vez: LiteLLM lee
``LITELLM_LOCAL_MODEL_COST_MAP`` al importarse y la puerta tiene que fijarla, como en prod.

- T013 (requisito 10.3, garantía 7): las llamadas de dos clientes salen en peticiones
  separadas, cada una solo con lo suyo, sin lote, también las de la reserva cruzada.
- T035 (requisito 12.5): un modelo heredado sin perfil (Claude Sonnet 4.6) sale con los
  parámetros de hoy, byte a byte: la misma petición que con el mecanismo de perfiles apagado.
  Y GPT-5.6, que ya responde hoy, también: con y sin herramientas, y en el cierre.
- T050 (requisitos 4.1-4.4, 4.6, 4.7, 4.10, 11.3): por perfil y escenario, lo que sale; que
  en un turno con Claude solo se añade; el razonamiento que vuelve; el saneado hacia OpenAI;
  el cruce de GPT-5.6 a Sonnet 5.5; el rechazo; el plazo y la caché hacia Claude.

El servidor de eco responde según un guion por familia: cada elemento es lo que contesta a la
siguiente llamada de esa familia, y el último se repite. ``auto`` llama a la herramienta salvo
con ``tool_choice: none``, así que un turno ``auto`` corre hasta el cierre.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import cache
from itertools import pairwise
from typing import Any

import pytest

SCRIPT = r"""
import asyncio, json, os, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

calls = []
SCEN = {}
COUNT = {"anthropic": 0, "openai": 0}
TEXT = {"anthropic": "Respuesta de Claude.", "openai": "Respuesta de GPT."}


def next_kind(family):
    seq = SCEN.get(family) or ["auto"]
    n = COUNT[family]
    COUNT[family] += 1
    return seq[min(n, len(seq) - 1)], n


def tool_name(body, family):
    for tool in body.get("tools") or []:
        name = tool.get("name") if family == "anthropic" else (tool.get("function") or {}).get("name")
        if name and name not in {"code_execution", "memory"}:
            return name
    return "x"


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        family = "anthropic" if "/messages" in self.path else "openai"
        kind, n = next_kind(family)
        if kind == "auto":
            kind = "text" if body.get("tool_choice") in ("none", {"type": "none"}) else "tool"
        calls.append({"path": self.path, "family": family, "kind": kind, "body": body,
                      "beta": self.headers.get("anthropic-beta") or ""})
        status = 200
        if kind == "error":
            status = 500
            out = ({"type": "error", "error": {"type": "api_error", "message": "boom"}}
                   if family == "anthropic" else
                   {"error": {"message": "boom", "type": "server_error", "code": None}})
        elif family == "anthropic":
            usage = {"input_tokens": 10, "output_tokens": 2}
            thinking = [{"type": "thinking", "thinking": "pienso", "signature": f"SIG-{n}"},
                        {"type": "redacted_thinking", "data": f"RED-{n}"}]
            if kind == "tool":
                content = thinking + [{"type": "text", "text": "Miro"},
                                      {"type": "tool_use", "id": f"toolu_{n}",
                                       "name": tool_name(body, family), "input": {}}]
                stop = "tool_use"
            elif kind == "refusal":
                content, stop = [{"type": "text", "text": "parcial"}], "refusal"
            elif kind == "refusal_empty":
                content, stop = [], "refusal"
            else:
                content, stop = [{"type": "text", "text": TEXT["anthropic"]}], "end_turn"
            out = {"id": f"m{n}", "type": "message", "role": "assistant", "model": body["model"],
                   "content": content, "stop_reason": stop, "stop_sequence": None, "usage": usage}
        else:
            if kind == "tool":
                message = {"role": "assistant", "content": None, "tool_calls": [
                    {"id": f"call_{n}", "type": "function",
                     "function": {"name": tool_name(body, family), "arguments": "{}"}}]}
                finish = "tool_calls"
            else:
                message, finish = {"role": "assistant", "content": TEXT["openai"]}, "stop"
            out = {"id": f"c{n}", "object": "chat.completion", "created": 1, "model": body["model"],
                   "choices": [{"index": 0, "finish_reason": finish, "message": message}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
        raw = json.dumps(out).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
os.environ.update({"ANTHROPIC_API_BASE": base, "ANTHROPIC_API_KEY": "k",
                   "OPENAI_API_BASE": base + "/v1", "OPENAI_BASE_URL": base + "/v1",
                   "OPENAI_API_KEY": "k"})

from nexus_api.core import respond_catalog
from nexus_api.core.litellm_map import litellm_module
from nexus_api.core.respond_profiles import PROFILES
from nexus_api.services.activations import ToolPolicy
from nexus_mcp import MCPRegistry

import nexus_worker.runtime.llm as llm_module
import nexus_worker.runtime.pipeline as pipeline
from nexus_worker.runtime import booking_brake
from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.llm import LiteLLMProvider, LLMRouter, TurnModelPin

# Los seis, habilitados para responder en este entorno; Sonnet 4.6 ejecutable y sin oferta.
def install(unavailable=frozenset()):
    # El catálogo de la prueba; ``unavailable``: modelos que dejan de ser ejecutables.
    def status(m):
        return "unavailable" if m in unavailable else "active"
    respond_catalog.refresh_from_rows(
        [{"model_id": m, "status": status(m), "offer_label": m, "price_input_per_mtok": 1,
          "respond_enabled_at": "2026-11-20"} for m in PROFILES]
        + [{"model_id": m, "status": status(m), "offer_label": None, "price_input_per_mtok": 1,
            "respond_enabled_at": None}
           for m in respond_catalog.BOOT_HOP_MODEL_IDS if m not in PROFILES]
    )


install()

SPY = []
_lm = litellm_module()
_real = _lm.acompletion


async def _spy(**kwargs):
    SPY.append({"model": kwargs.get("model"), "timeout": kwargs.get("timeout"),
                "max_tokens": kwargs.get("max_tokens"),
                "allowed_openai_params": kwargs.get("allowed_openai_params")})
    return await _real(**kwargs)


_lm.acompletion = _spy
llm_module._RETRY_BACKOFF_S = 0.0

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
AGENT = uuid.UUID("00000000-0000-0000-0000-00000000a9e1")
TOOL = "client.get_history"
DISPATCHED = []
BRAKE = []


async def _nothing(*_a, **_k):
    return ""


async def _no_history(*_a, **_k):
    return []


async def _no_knowledge(*_a, **_k):
    return "", []


async def _no_gates(_tenant):
    return frozenset()


async def _policy(*_a, **_k):
    return ToolPolicy(closed=True)


async def _dispatch(_registry, call, _available, intent, conversation_id=None):
    DISPATCHED.append(call.id)
    return {"tool": call.name, "intent": intent, "status": "ok", "result": {"visits": 2}}


async def _claim(*_a, **_k):
    return BRAKE.pop(0) if BRAKE else False


async def _record_brake(**_k):
    return None


pipeline._load_recent_history = _no_history
pipeline._load_kg_snapshot_text = _nothing
pipeline._load_knowledge = _no_knowledge
pipeline._load_gated_tools = _no_gates
pipeline._load_tool_policy = _policy
pipeline._dispatch_tool = _dispatch
pipeline._now_note = lambda _tz: "Hoy es sábado, 10:00."
booking_brake.unbacked_claim = _claim
booking_brake.record_brake = _record_brake


class Registry(MCPRegistry):
    def get_openai_tools(self, names):
        return [{"type": "function", "function": {"name": n, "description": "Historial",
                 "parameters": {"type": "object"}}} for n in names]

    def is_side_effecting(self, name):
        return False

    def names(self):
        return (TOOL,)


class Loader:
    def __init__(self, bundle):
        self.bundle = bundle

    async def load(self, _tenant, _agent=None):
        return self.bundle


def router(fallback="openai/gpt-5.6-sol"):
    return LLMRouter(provider=LiteLLMProvider(max_retries=0),
                     classify_model="anthropic/claude-haiku-5-5",
                     respond_model="openai/gpt-5.6-sol", fallback_model=fallback,
                     retry_backoff_s=0.0)


def reset(scen, brake=()):
    SCEN.clear()
    SCEN.update(scen)
    COUNT.update(anthropic=0, openai=0)
    BRAKE[:] = list(brake)
    return len(calls), len(SPY), len(DISPATCHED)


def since(mark, **more):
    c, s, d = mark
    return {"calls": calls[c:], "spy": SPY[s:], "dispatched": DISPATCHED[d:], **more}


async def turn(chosen, scen, brake=()):
    mark = reset(scen, brake)
    bundle = AgentBundle(tenant_id=TENANT, version=1, version_id=uuid.uuid4(),
                         system_prompt="PROMPT-DEL-AGENTE", tools=frozenset({TOOL}), policies={},
                         agent_id=AGENT, respond_model=chosen, respond_model_set_by="partner")
    state = {"tenant_id": str(TENANT), "agent_id": str(AGENT),
             "conversation_id": "00000000-0000-0000-0000-00000000c0c0",
             "inbound_message_id": "turn-1", "customer_id": str(uuid.uuid4()),
             "channel_type": "whatsapp", "user_message": "Quiero cita el martes", "history": [],
             "intent": "info", "classification": {}, "router_turn": {}}
    handler = pipeline.make_handler_node("info", Loader(bundle), router(), Registry())
    out = await handler(state)
    return since(mark, out={k: out.get(k) for k in ("response", "response_model",
                                                     "response_fell_back", "turn_failure")})


TOOLS = [{"type": "function", "function": {"name": "reservas_slots", "description": "Huecos",
          "parameters": {"type": "object", "properties": {"dia": {"type": "string"}}}}}]


def chat(marker):
    return [{"role": "system", "content": "Recepción"},
            {"role": "user", "content": "Soy " + marker}]


async def one(model, marker, *, tools=TOOLS, extra=None, fallback=""):
    llm = router(fallback=fallback)
    pin = TurnModelPin(chosen=model, reserve=fallback or None)
    await llm.respond_with_tools(tenant_id=uuid.uuid4(), role="info", messages=chat(marker),
                                 tools=tools, extra=extra, pin=pin)


async def without_profiles(flow):
    original = llm_module.profile_for
    llm_module.profile_for = lambda *_: None
    try:
        return await flow()
    finally:
        llm_module.profile_for = original


async def router_flow(model, **kw):
    mark = reset({"anthropic": ["text"], "openai": ["text"]})
    await one(model, "CLIENTE", **kw)
    return since(mark)


async def rewrite_flow(model):
    # La reescritura del juez (``pipeline._ask_agent_to_rewrite``): ``respond`` sin herramientas.
    mark = reset({"anthropic": ["text"], "openai": ["text"]})
    await router(fallback="").respond(tenant_id=uuid.uuid4(), messages=chat("CLIENTE"),
                                      model_override=model)
    return since(mark)


async def main():
    out = {}
    for model in PROFILES:
        out["turn:" + model] = await turn(model, {"anthropic": ["auto"], "openai": ["auto"]})
    out["brake"] = await turn("anthropic/claude-sonnet-5-5",
                              {"anthropic": ["tool", "text", "tool", "text"]}, brake=[True, False])
    out["sanitize"] = await turn("anthropic/claude-opus-5-5",
                                 {"anthropic": ["tool", "error"], "openai": ["auto"]})
    out["cross"] = await turn("openai/gpt-5.6-sol",
                              {"openai": ["tool", "error"], "anthropic": ["auto"]})
    out["cross_first"] = await turn("openai/gpt-5.6-sol", {"openai": ["error"], "anthropic": ["auto"]})
    for kind in ("refusal", "refusal_empty"):
        out[kind] = await turn("anthropic/claude-opus-5-5", {"anthropic": [kind], "openai": ["text"]})
    # T084: el modelo elegido deja de ser ejecutable (retirado o no disponible).
    install(unavailable={"anthropic/claude-opus-5-5"})
    out["unexecutable"] = await turn("anthropic/claude-opus-5-5",
                                     {"anthropic": ["auto"], "openai": ["auto"]})
    install()

    mark = reset({"anthropic": ["text"], "openai": ["text"]})
    await asyncio.gather(one("openai/gpt-5.6-terra", "CLIENTE-A"),
                         one("openai/gpt-5.6-terra", "CLIENTE-B"))
    out["two_clients:openai"] = since(mark)
    mark = reset({"anthropic": ["text"], "openai": ["text"]})
    await asyncio.gather(one("anthropic/claude-sonnet-5-5", "CLIENTE-A"),
                         one("anthropic/claude-sonnet-5-5", "CLIENTE-B"))
    out["two_clients:anthropic"] = since(mark)
    mark = reset({"anthropic": ["text"], "openai": ["error"]})
    await asyncio.gather(
        one("openai/gpt-5.6-sol", "CLIENTE-A", fallback="anthropic/claude-sonnet-5-5"),
        one("openai/gpt-5.6-sol", "CLIENTE-B", fallback="anthropic/claude-sonnet-5-5"))
    out["two_clients:cross"] = since(mark)

    legacy = "anthropic/claude-sonnet-4-6"
    out["legacy:now"] = await router_flow(legacy)
    out["legacy:before"] = await without_profiles(lambda: router_flow(legacy))
    for model in ("openai/gpt-5.6-sol", "openai/gpt-5.6-terra"):
        for shape, kw in (("tools", {}), ("closing", {"extra": {"tool_choice": "none"}}),
                          ("no_tools", {"tools": []})):
            out[f"today:{model}:{shape}:now"] = await router_flow(model, **kw)
            out[f"today:{model}:{shape}:before"] = await without_profiles(
                lambda model=model, kw=kw: router_flow(model, **kw))
    for model in ("anthropic/claude-opus-5-5", "openai/gpt-5.6-sol", legacy):
        out[f"rewrite:{model}:now"] = await rewrite_flow(model)
        out[f"rewrite:{model}:before"] = await without_profiles(
            lambda model=model: rewrite_flow(model))
    print("RESULT" + json.dumps(out))


asyncio.run(main())
"""

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"
OPUS = "anthropic/claude-opus-5-5"
SONNET = "anthropic/claude-sonnet-5-5"
HAIKU = "anthropic/claude-haiku-5-5"
GPT = (SOL, TERRA, LUNA)
CLAUDE = (OPUS, SONNET, HAIKU)
TIMEOUTS = {SOL: 30, TERRA: 30, LUNA: 30, OPUS: 90, SONNET: 60, HAIKU: 45}
BINDING_BETA = "thinking-binding-controls-2026-08-01"
#: Lo que solo existe en la memoria del turno y nunca sale (``runtime/llm.py``).
PRIVATE = "nexus_served_by"
FINAL_NOTE_HEAD = "Es tu última respuesta de este turno"


@cache
def _run() -> dict[str, Any]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "LITELLM_PROXY_API_BASE",
            "LITELLM_PROXY_VIRTUAL_KEYS",
            "LITELLM_LOCAL_MODEL_COST_MAP",
        }
    }
    env["NEXUS_CONTEXT_EDITING_ENABLED"] = "1"
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=300
    )
    assert done.returncode == 0, done.stderr[-4000:]
    line = next(x for x in done.stdout.splitlines() if x.startswith("RESULT"))
    out: dict[str, Any] = json.loads(line[len("RESULT") :])
    return out


def _flow(name: str) -> dict[str, Any]:
    flow: dict[str, Any] = _run()[name]
    for call in flow["calls"]:
        assert PRIVATE not in json.dumps(call["body"]), f"{name}: la marca del turno salió"
    return flow


def _ok(flow: dict[str, Any], family: str | None = None) -> list[dict[str, Any]]:
    """Las peticiones que el proveedor contestó (no las que hizo fallar el guion)."""
    return [
        c
        for c in flow["calls"]
        if c["kind"] != "error" and (family is None or c["family"] == family)
    ]


def _carried(body: dict[str, Any]) -> str:
    return json.dumps(body.get("messages"), ensure_ascii=False) + json.dumps(
        body.get("system"), ensure_ascii=False
    )


def _is_closing(body: dict[str, Any]) -> bool:
    return body.get("tool_choice") in ("none", {"type": "none"})


# ── T013: una petición por cliente ─────────────────────────────────────────


def _assert_one_request_per_client(calls: list[dict[str, Any]]) -> None:
    assert len(calls) == 2, f"una petición por cliente, sin lote: {len(calls)}"
    seen = sorted("A" if "CLIENTE-A" in _carried(c["body"]) else "B" for c in calls)
    assert seen == ["A", "B"]
    for call in calls:
        carried = _carried(call["body"])
        assert ("CLIENTE-A" in carried) != ("CLIENTE-B" in carried), "dos clientes en una petición"


def test_two_clients_on_openai_go_in_separate_requests() -> None:
    _assert_one_request_per_client(_flow("two_clients:openai")["calls"])


def test_two_clients_on_claude_go_in_separate_requests() -> None:
    _assert_one_request_per_client(_flow("two_clients:anthropic")["calls"])


def test_two_clients_on_the_cross_reserve_go_in_separate_requests() -> None:
    flow = _flow("two_clients:cross")
    assert {c["family"] for c in flow["calls"] if c["kind"] == "error"} == {"openai"}
    _assert_one_request_per_client(_ok(flow, "anthropic"))


# ── T035: lo que ya responde hoy sale como hoy ─────────────────────────────


def test_a_legacy_model_without_a_profile_goes_out_as_today() -> None:
    now = _flow("legacy:now")["calls"]
    before = _flow("legacy:before")["calls"]
    assert len(now) == len(before) == 1
    assert now[0]["path"] == before[0]["path"]
    assert now[0]["body"] == before[0]["body"], "byte a byte, como antes de la 065"
    assert now[0]["beta"] == before[0]["beta"]
    body = now[0]["body"]
    assert "output_config" not in body, "el effort de Claude 5.5 no llega a un heredado"
    assert body.get("thinking", {}).get("type") != "between_tools"


@pytest.mark.parametrize("model", [SOL, "anthropic/claude-sonnet-4-6"])
def test_the_rewrite_of_what_answers_today_goes_out_as_today(model: str) -> None:
    now, before = _flow(f"rewrite:{model}:now"), _flow(f"rewrite:{model}:before")
    assert [c["body"] for c in now["calls"]] == [c["body"] for c in before["calls"]]
    assert [s["timeout"] for s in now["spy"]] == [s["timeout"] for s in before["spy"]]


def test_the_rewrite_with_claude_goes_out_with_its_profile() -> None:
    """El juez pide al agente que reescriba con ``LLMRouter.respond``, sin herramientas:
    también ahí, el perfil de su modelo."""
    flow = _flow(f"rewrite:{OPUS}:now")
    [call] = flow["calls"]
    body = call["body"]
    assert "tools" not in body
    assert body["output_config"] == {"effort": "low"}
    assert body["max_tokens"] == 8192
    assert body["thinking"]["type"] == "adaptive"
    assert BINDING_BETA in call["beta"]
    assert body["cache_control"] == {"type": "ephemeral"}
    assert [s["timeout"] for s in flow["spy"]] == [TIMEOUTS[OPUS]]


@pytest.mark.parametrize("model", [SOL, TERRA])
@pytest.mark.parametrize("shape", ["tools", "closing", "no_tools"])
def test_gpt_56_goes_out_as_today(model: str, shape: str) -> None:
    """Sol y Terra ya responden en prod: su perfil no cambia ni un byte de lo que sale."""
    now = _flow(f"today:{model}:{shape}:now")
    before = _flow(f"today:{model}:{shape}:before")
    assert [c["body"] for c in now["calls"]] == [c["body"] for c in before["calls"]]
    assert [c["path"] for c in now["calls"]] == [c["path"] for c in before["calls"]]
    assert [s["timeout"] for s in now["spy"]] == [s["timeout"] for s in before["spy"]]


# ── T050: lo que sale a cada familia ───────────────────────────────────────


@pytest.mark.parametrize("model", GPT)
def test_gpt_56_with_tools_goes_by_chat_completions_without_reasoning(model: str) -> None:
    flow = _flow("turn:" + model)
    calls = flow["calls"]
    assert calls and all(c["family"] == "openai" for c in calls), "sin cruces ni desvíos"
    for call in calls:
        assert call["path"].endswith("/chat/completions"), "nunca a /responses"
        body = call["body"]
        assert body["reasoning_effort"] == "none"
        for key in ("thinking", "output_config", "cache_control", "context_management"):
            assert key not in body, key
        assert "max_tokens" not in body and "max_completion_tokens" not in body
    closing = calls[-1]["body"]
    assert closing["tool_choice"] == "none", "el cierre con GPT-5.6 sale (T014)"
    assert any(
        m.get("role") == "system" and FINAL_NOTE_HEAD in json.dumps(m, ensure_ascii=False)
        for m in closing["messages"]
    ), "con GPT-5.6 el cierre sigue como hoy, con su nota"
    assert flow["out"]["response"] == "Respuesta de GPT."
    assert flow["out"]["response_model"] == model


@pytest.mark.parametrize("model", CLAUDE)
def test_claude_55_goes_out_with_its_profile(model: str) -> None:
    flow = _flow("turn:" + model)
    calls = flow["calls"]
    assert len(calls) >= 3 and all(c["path"] == "/v1/messages" for c in calls)
    for call in calls:
        body = call["body"]
        assert body["output_config"] == {"effort": "low"}
        assert body["max_tokens"] == 8192
        assert body["thinking"] == {
            "type": "adaptive",
            "block_binding": {"prefix_mismatch_behavior": "drop_block"},
        }
        assert BINDING_BETA in call["beta"].split(","), call["beta"]
        for key in ("temperature", "top_p", "top_k", "reasoning_effort"):
            assert key not in body, key
        assert body.get("tool_choice") in (None, {"type": "none"}), "nunca forzada"
        assert body["messages"][-1]["role"] != "assistant", "sin respuesta empezada"
    assert _is_closing(calls[-1]["body"])
    assert not any(_is_closing(c["body"]) for c in calls[:-1])
    assert flow["out"]["response"] == "Respuesta de Claude."
    assert flow["out"]["response_model"] == model


@pytest.mark.parametrize("model", CLAUDE)
def test_with_claude_the_turn_only_appends(model: str) -> None:
    """Requisito 4.10: el ``system``, las herramientas y lo anterior, byte a byte, de la
    primera llamada a la última. El cierre solo añade ``tool_choice: none``: sin la nota del
    cierre y con las mismas herramientas."""
    bodies = [c["body"] for c in _flow("turn:" + model)["calls"]]
    first = bodies[0]
    for earlier, later in pairwise(bodies):
        assert later["system"] == earlier["system"]
        assert later["tools"] == earlier["tools"]
        assert later["messages"][: len(earlier["messages"])] == earlier["messages"]
        assert len(later["messages"]) > len(earlier["messages"])
    closing = bodies[-1]
    assert set(closing) - set(first) == {"tool_choice"}
    for key in set(first) - {"messages"}:
        assert closing[key] == first[key], key
    assert FINAL_NOTE_HEAD not in json.dumps(closing, ensure_ascii=False)


@pytest.mark.parametrize("model", CLAUDE)
def test_the_reasoning_goes_back_before_the_tool_use_intact(model: str) -> None:
    calls = _flow("turn:" + model)["calls"]
    for n, call in enumerate(calls[1:]):
        assistant = [m for m in call["body"]["messages"] if m["role"] == "assistant"]
        assert len(assistant) == n + 1
        content = assistant[n]["content"]
        assert content[0] == {"type": "thinking", "thinking": "pienso", "signature": f"SIG-{n}"}
        assert content[1] == {"type": "redacted_thinking", "data": f"RED-{n}"}
        assert content[-1]["type"] == "tool_use"


@pytest.mark.parametrize("model", list(TIMEOUTS))
def test_each_call_has_its_profiles_timeout(model: str) -> None:
    spy = _flow("turn:" + model)["spy"]
    assert spy and {s["timeout"] for s in spy} == {TIMEOUTS[model]}
    if model in CLAUDE:
        assert {s["allowed_openai_params"] == ["thinking"] for s in spy} == {True}


@pytest.mark.parametrize("model", CLAUDE)
def test_claude_caches_the_system_and_the_conversation(model: str) -> None:
    """Research §D14: la marca fija en el último bloque del ``system`` y la caché automática
    de la conversación (el ``cache_control`` de arriba, que no toca los mensajes), 5 min."""
    for call in _flow("turn:" + model)["calls"]:
        body = call["body"]
        assert body["system"][-1]["cache_control"] == {"type": "ephemeral"}
        assert body["cache_control"] == {"type": "ephemeral"}
        for message in body["messages"]:
            for block in message["content"] if isinstance(message["content"], list) else []:
                assert "cache_control" not in block, "ninguna marca que se mueva"


def test_the_brake_retry_takes_nothing_away() -> None:
    """El reintento del freno de reservas en un turno con Claude no retira nada: lo anterior
    sigue byte a byte y su nota es lo único nuevo (LiteLLM la sube al ``system`` como un
    bloque al final; si eso cuenta como edición lo decide la batería real, T055)."""
    flow = _flow("brake")
    bodies = [c["body"] for c in flow["calls"]]
    assert len(bodies) == 4, [c["kind"] for c in flow["calls"]]
    draft, retry = bodies[1], bodies[2]
    assert retry["system"][: len(draft["system"])] == draft["system"]
    [note] = retry["system"][len(draft["system"]) :]
    assert note["text"].startswith("Tu respuesta anterior daba por hecha una cita")
    assert retry["messages"][: len(draft["messages"])] == draft["messages"]
    assert retry["tools"] == draft["tools"]
    for key in set(draft) - {"messages", "system"}:
        assert retry[key] == draft[key], key
    assert flow["out"]["response"] == "Respuesta de Claude."


def test_falling_to_gpt_56_leaves_the_reasoning_behind() -> None:
    """Opus llama a una herramienta y cae: Terra recibe el historial saneado y sigue el
    resto del turno."""
    flow = _flow("sanitize")
    anthropic = [c for c in flow["calls"] if c["family"] == "anthropic"]
    assert [c["kind"] for c in anthropic] == ["tool", "error", "error"]
    openai = flow["calls"][len(anthropic) :]
    assert openai and all(c["family"] == "openai" for c in openai), "la reserva se queda"
    for call in openai:
        for message in call["body"]["messages"]:
            for key in ("thinking_blocks", "reasoning_content", "provider_specific_fields"):
                assert key not in message, key
            for tool_call in message.get("tool_calls") or []:
                assert "index" not in tool_call
        assert call["body"]["reasoning_effort"] == "none"
    assert flow["out"]["response_model"] == TERRA
    assert flow["out"]["response_fell_back"] is True
    assert len(flow["dispatched"]) == len(set(flow["dispatched"])), "ninguna herramienta dos veces"


def test_gpt_56_falls_to_sonnet_with_reasoning_off_for_the_rest_of_the_turn() -> None:
    """Research §D5.4: tras herramientas de GPT-5.6, Sonnet 5.5 sale con ``between_tools`` y
    nada más dentro de ``thinking``, sin ``block_binding`` ni su beta; sus bloques de progreso
    vuelven a Sonnet."""
    flow = _flow("cross")
    openai = [c for c in flow["calls"] if c["family"] == "openai"]
    assert [c["kind"] for c in openai] == ["tool", "error", "error"]
    sonnet = flow["calls"][len(openai) :]
    assert len(sonnet) >= 2 and all(c["family"] == "anthropic" for c in sonnet)
    for n, call in enumerate(sonnet):
        body = call["body"]
        assert body["thinking"] == {"type": "between_tools"}
        assert BINDING_BETA not in call["beta"]
        assert body["output_config"] == {"effort": "low"}
        assistant = [m for m in body["messages"] if m["role"] == "assistant"]
        assert all(b["type"] != "thinking" for b in assistant[0]["content"]), "GPT no razonó"
        if n:
            mine = assistant[n]["content"]
            assert mine[0] == {
                "type": "thinking",
                "thinking": "pienso",
                "signature": f"SIG-{n - 1}",
            }
    assert flow["out"]["response_model"] == SONNET
    assert flow["out"]["response"] == "Respuesta de Claude."


def test_falling_to_sonnet_on_the_first_call_reasons_as_usual() -> None:
    sonnet = [c for c in _flow("cross_first")["calls"] if c["family"] == "anthropic"]
    assert sonnet
    for call in sonnet:
        assert call["body"]["thinking"]["type"] == "adaptive"
        assert call["body"]["thinking"]["block_binding"] == {
            "prefix_mismatch_behavior": "drop_block"
        }
        assert BINDING_BETA in call["beta"]


@pytest.mark.parametrize("kind", ["refusal", "refusal_empty"])
def test_a_refusal_never_reaches_the_customer_and_goes_to_the_reserve(kind: str) -> None:
    flow = _flow(kind)
    anthropic = [c for c in flow["calls"] if c["family"] == "anthropic"]
    assert len(anthropic) == 1, "un rechazo no se reintenta en el mismo modelo"
    assert flow["out"]["response"] == "Respuesta de GPT."
    assert "parcial" not in json.dumps(flow["out"], ensure_ascii=False)
    assert flow["out"]["response_model"] == TERRA
    assert flow["out"]["response_fell_back"] is True


def test_a_chosen_model_that_is_no_longer_executable_answers_with_the_reserve() -> None:
    """T084 (requisitos 4.4 y 8.1): Opus, elegido por el agente, pasa a no disponible. La
    puerta del catálogo lo para antes de salir y el turno lo termina su reserva, Terra."""
    flow = _flow("unexecutable")
    assert not [c for c in flow["calls"] if c["family"] == "anthropic"], "Opus no sale al cable"
    assert _ok(flow, "openai"), "la reserva responde"
    assert flow["out"]["response_model"] == TERRA
    assert flow["out"]["response_fell_back"] is True
