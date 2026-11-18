"""Spec 063, requisito 3.1 — el modo JSON del constructor llega al proveedor.

Con el ``LiteLLMProvider`` real hasta un servidor local que hace de OpenAI, y con el
mapa de modelos que trae LiteLLM (``LITELLM_LOCAL_MODEL_COST_MAP``): una prueba que
sustituye el transporte no ve los parámetros que LiteLLM rechaza antes de salir
(memoria del 2026-11-05). Corre aparte porque LiteLLM lee esa variable al importarse.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPT = r"""
import asyncio, json, os, threading, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

calls = []


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        calls.append(body)
        out = {"id": "c", "object": "chat.completion", "created": 1, "model": body["model"],
               "choices": [{"index": 0, "finish_reason": "length",
                            "message": {"role": "assistant", "content": "{\"voice\": {}"}}],
               "usage": {"prompt_tokens": 10, "completion_tokens": 7, "total_tokens": 17}}
        raw = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


server = HTTPServer(("127.0.0.1", 0), Provider)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
os.environ.update({"OPENAI_API_BASE": base + "/v1", "OPENAI_BASE_URL": base + "/v1",
                   "OPENAI_API_KEY": "k"})

from nexus_worker.jobs.handlers.agent_draft import JSON_MODE
from nexus_worker.runtime.llm import LiteLLMProvider, supports_json_object


async def main():
    provider = LiteLLMProvider(context_management=None, timeout_s=30, max_retries=0)
    out = await provider.acomplete_detailed(
        tenant_id=uuid.uuid4(), role="build", model="openai/gpt-5.6-sol",
        messages=[{"role": "user", "content": "Devuelve el borrador en JSON"}], extra=dict(JSON_MODE))
    supports = {m: supports_json_object(m) for m in
                ("openai/gpt-5.6-sol", "anthropic/claude-sonnet-5-5", "anthropic/claude-haiku-5-5",
                 "nadie/un-modelo-que-no-existe")}
    print("RESULT" + json.dumps({"calls": calls, "finish": out.finish_reason,
                                 "tokens": out.output_tokens, "supports": supports}))


asyncio.run(main())
"""


def _run() -> dict[str, Any]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"LITELLM_PROXY_API_BASE", "LITELLM_PROXY_VIRTUAL_KEYS"}
    }
    env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    line = next(x for x in done.stdout.splitlines() if x.startswith("RESULT"))
    out: dict[str, Any] = json.loads(line[len("RESULT") :])
    return out


def test_the_build_call_asks_the_provider_for_json() -> None:
    out = _run()
    (body,) = out["calls"]
    assert body["response_format"] == {"type": "json_object"}
    assert out["finish"] == "length" and out["tokens"] == 7
    assert out["supports"]["openai/gpt-5.6-sol"] is True
    assert out["supports"]["anthropic/claude-sonnet-5-5"] is True
    assert out["supports"]["anthropic/claude-haiku-5-5"] is True
    assert out["supports"]["nadie/un-modelo-que-no-existe"] is False
