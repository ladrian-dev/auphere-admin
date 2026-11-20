"""Spec 065: la batería en el cable de los perfiles de respuesta (research.md §D9.1).

Las llamadas van por ``LiteLLMProvider`` real hasta un servidor local que hace de OpenAI y de
Anthropic, con la puerta de LiteLLM (mapa fijo y entradas registradas). Sin coste y sin red.

- T013 (requisito 10.3, garantía 7): las llamadas de dos clientes salen en peticiones
  separadas, cada una solo con lo suyo, sin lote. La reserva cruzada se añade aquí con su
  implementación (T051).
- T035 (requisito 12.5): un modelo heredado sin perfil (Claude Sonnet 4.6), que un agente
  recibe de la migración 0240, sale con los parámetros de hoy, byte a byte: la misma petición
  que con el mecanismo de perfiles apagado.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

SCRIPT = r"""
import asyncio, json, os, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

calls = []


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        calls.append({"path": self.path, "body": body})
        if "/messages" in self.path:
            out = {"id": "m", "type": "message", "role": "assistant", "model": body["model"],
                   "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
                   "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 2}}
        else:
            out = {"id": "c", "object": "chat.completion", "created": 1, "model": body["model"],
                   "choices": [{"index": 0, "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "ok"}}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
        raw = json.dumps(out).encode()
        self.send_response(200)
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

from nexus_worker.runtime.llm import LiteLLMProvider

TOOLS = [{"type": "function", "function": {"name": "reservas_slots", "description": "Huecos",
          "parameters": {"type": "object", "properties": {"dia": {"type": "string"}}}}}]


async def one(model, marker):
    await LiteLLMProvider(context_management=None).acomplete_with_tools(
        tenant_id=uuid.uuid4(), role="respond", model=model,
        messages=[{"role": "system", "content": "Recepción"},
                  {"role": "user", "content": "Soy " + marker}],
        tools=TOOLS)


async def main():
    flow = os.environ["PROBE_FLOW"]
    if flow == "two_clients":
        model = os.environ["PROBE_MODEL"]
        await asyncio.gather(one(model, "CLIENTE-A"), one(model, "CLIENTE-B"))
    elif flow == "legacy":
        if os.environ.get("PROBE_NO_PROFILES"):
            # El camino de antes de la 065: ningún modelo tiene perfil de respuesta.
            import nexus_worker.runtime.llm as llm_module
            llm_module.profile_for = lambda *_: None
        await LiteLLMProvider(context_management=None).acomplete_with_tools(
            tenant_id=uuid.UUID(int=65), role="respond", model=os.environ["PROBE_MODEL"],
            messages=[{"role": "system", "content": "Recepción"},
                      {"role": "user", "content": "Quiero cita el martes"}],
            tools=TOOLS)
    print("RESULT" + json.dumps({"calls": calls}))


asyncio.run(main())
"""


def _run(flow: str, **env_extra: str) -> dict[str, Any]:
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
    env.update(PROBE_FLOW=flow, **env_extra)
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=180
    )
    assert done.returncode == 0, done.stderr[-3000:]
    line = next(x for x in done.stdout.splitlines() if x.startswith("RESULT"))
    out: dict[str, Any] = json.loads(line[len("RESULT") :])
    return out


def _carried(body: dict[str, Any]) -> str:
    return json.dumps(body.get("messages"), ensure_ascii=False) + json.dumps(
        body.get("system"), ensure_ascii=False
    )


def _assert_one_request_per_client(calls: list[dict[str, Any]]) -> None:
    assert len(calls) == 2, f"una petición por cliente, sin lote: {len(calls)}"
    seen = sorted("A" if "CLIENTE-A" in _carried(c["body"]) else "B" for c in calls)
    assert seen == ["A", "B"]
    for call in calls:
        carried = _carried(call["body"])
        assert ("CLIENTE-A" in carried) != ("CLIENTE-B" in carried), "dos clientes en una petición"


def test_two_clients_on_openai_go_in_separate_requests() -> None:
    _assert_one_request_per_client(_run("two_clients", PROBE_MODEL="openai/gpt-5.6-terra")["calls"])


def test_two_clients_on_claude_go_in_separate_requests() -> None:
    _assert_one_request_per_client(
        _run("two_clients", PROBE_MODEL="anthropic/claude-sonnet-5-5")["calls"]
    )


def test_a_legacy_model_without_a_profile_goes_out_as_today() -> None:
    model = "anthropic/claude-sonnet-4-6"
    now = _run("legacy", PROBE_MODEL=model)["calls"]
    before = _run("legacy", PROBE_MODEL=model, PROBE_NO_PROFILES="1")["calls"]
    assert len(now) == len(before) == 1
    assert now[0]["path"] == before[0]["path"]
    assert now[0]["body"] == before[0]["body"], "byte a byte, como antes de la 065"
    body = now[0]["body"]
    assert "output_config" not in body, "el effort de Claude 5.5 no llega a un heredado"
    assert body.get("thinking", {}).get("type") != "between_tools"
