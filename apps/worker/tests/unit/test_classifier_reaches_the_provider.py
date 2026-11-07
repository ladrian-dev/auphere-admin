"""Requisito 69: Claude Haiku 5.5 clasifica de verdad, y si no, clasifica la reserva.

La llamada va por ``LLMRouter`` y ``LiteLLMProvider`` reales hasta un servidor local que
hace de Anthropic y de OpenAI, con el mapa de modelos que trae LiteLLM. Sin
``allowed_openai_params``, ese mapa no conoce el modelo, LiteLLM rechaza ``thinking`` antes
de salir y clasifica siempre la reserva sin que se note: por eso aquí no se sustituye el
transporte. Corre aparte porque LiteLLM lee ``LITELLM_LOCAL_MODEL_COST_MAP`` al importarse.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from typing import Any

import pytest

from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
from nexus_worker.runtime.pipeline import classification_label

SCRIPT = r"""
import asyncio, json, os, threading, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

calls = []
anthropic_says = os.environ["PROBE_ANTHROPIC"]


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        calls.append({"path": self.path, "body": body})
        if "/messages" in self.path:
            content = [{"type": "text", "text": "book"}] if anthropic_says == "ok" else []
            stop = "end_turn" if anthropic_says == "ok" else "refusal"
            out = {"id": "m", "type": "message", "role": "assistant", "model": body["model"],
                   "content": content, "stop_reason": stop, "stop_sequence": None,
                   "usage": {"input_tokens": 10, "output_tokens": 2}}
        else:
            out = {"id": "c", "object": "chat.completion", "created": 1, "model": body["model"],
                   "choices": [{"index": 0, "finish_reason": "stop",
                                "message": {"role": "assistant", "content": "info"}}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
        raw = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


server = HTTPServer(("127.0.0.1", 0), Provider)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
os.environ.update({"ANTHROPIC_API_BASE": base, "ANTHROPIC_API_KEY": "k",
                   "OPENAI_API_BASE": base + "/v1", "OPENAI_BASE_URL": base + "/v1",
                   "OPENAI_API_KEY": "k"})

from nexus_worker.runtime.llm import LiteLLMProvider, LLMRouter


async def main():
    router = LLMRouter(provider=LiteLLMProvider(context_management=None),
                       classify_model="anthropic/claude-haiku-5-5",
                       respond_model="openai/gpt-5.6-sol", fallback_model="",
                       classify_fallback_model="openai/gpt-5.6-sol", retry_backoff_s=0)
    text = await router.classify(tenant_id=uuid.uuid4(),
                                 messages=[{"role": "system", "content": "Clasifica"},
                                           {"role": "user", "content": "hola"}])
    print("RESULT" + json.dumps({"text": text, "calls": calls}))


asyncio.run(main())
"""


def _run(anthropic_says: str) -> dict[str, Any]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"LITELLM_PROXY_API_BASE", "LITELLM_PROXY_VIRTUAL_KEYS"}
    }
    env.update(LITELLM_LOCAL_MODEL_COST_MAP="True", PROBE_ANTHROPIC=anthropic_says)
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    line = next(x for x in done.stdout.splitlines() if x.startswith("RESULT"))
    out: dict[str, Any] = json.loads(line[len("RESULT") :])
    return out


def test_haiku_is_really_called_with_a_word_and_no_reasoning() -> None:
    out = _run("ok")
    assert out["text"] == "book"
    (call,) = out["calls"]
    assert call["path"].endswith("/messages")
    assert call["body"]["model"] == "claude-haiku-5-5"
    assert call["body"]["max_tokens"] == 32
    assert call["body"]["thinking"] == {"type": "disabled"}
    assert "allowed_openai_params" not in call["body"], "es de LiteLLM, no del proveedor"
    assert "temperature" not in call["body"], "Haiku 5.5 rechaza otros valores"


def test_a_refusal_goes_to_the_fallback_and_not_to_a_turn_without_tools() -> None:
    out = _run("refusal")
    assert out["text"] == "info"
    assert out["calls"][-1]["path"].endswith("/chat/completions")
    assert out["calls"][-1]["body"]["model"] == "gpt-5.6-sol"
    assert "thinking" not in out["calls"][-1]["body"]


async def test_only_the_label_call_is_cut_to_a_word() -> None:
    """El sector y el tipado usan el mismo rol y necesitan más salida."""
    provider = InMemoryProvider()
    provider.responder = lambda call: "info"
    router = LLMRouter(
        provider=provider,
        classify_model="anthropic/claude-haiku-5-5",
        respond_model="t/r",
        fallback_model="",
    )
    await router.classify(tenant_id=uuid.uuid4(), messages=[{"role": "user", "content": "x"}])
    assert provider.calls[-1].extra.get("max_tokens") == 32

    await provider.acomplete(
        tenant_id=uuid.uuid4(),
        role="classify",
        model="anthropic/claude-haiku-5-5",
        messages=[{"role": "user", "content": "x"}],
    )
    assert "max_tokens" not in (provider.calls[-1].extra or {})


async def test_simulations_have_a_fallback_to_classify_and_none_to_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nexus_worker.simulation import runner

    monkeypatch.setattr(runner, "_router_override", None, raising=False)
    router = runner.default_router()
    assert router.fallback_model == ""
    assert router.classify_fallback == router.classify_fallback_model != ""
    assert router.classify_fallback != router.classify_model


@pytest.mark.parametrize(
    ("raw", "label"),
    [("book", "book"), (" Book.\n", "book"), ("**info**", "info"), ("", ""), (None, "")],
)
def test_the_label_survives_how_a_model_writes_it(raw: str | None, label: str) -> None:
    assert classification_label(raw) == label
