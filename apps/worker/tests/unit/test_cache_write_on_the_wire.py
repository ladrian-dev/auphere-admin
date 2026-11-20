"""Spec 065, T044 (requisitos 5.5 y 5.6): la escritura en caché, fijada en el cable.

Antes de cobrar la escritura en su carril hay que saber dos cosas de LiteLLM, la versión
del lock y con la puerta de ``nexus_api.core.litellm_map`` (mapa fijo y nuestras entradas):

1. **Anthropic.** Su respuesta trae ``input_tokens`` (lo fresco), ``cache_read_input_tokens``
   y ``cache_creation_input_tokens``. ¿El ``prompt_tokens`` que devuelve LiteLLM suma las dos
   cachés? Si no las sumara, «prompt - lectura - escritura» restaría dos veces lo escrito.
2. **GPT-5.6.** OpenAI cobra lo escrito a 1,25 veces la entrada y lo cuenta en
   ``usage.prompt_tokens_details.cache_write_tokens``. ¿Lo deja pasar LiteLLM, y el colector
   lo apunta como ``llm.cache_write``? Hasta la 065, Sol salía siempre con escritura 0
   (research.md §D14, «Hallazgo»).

Medido el 2026-11-20 con 1.83.14 (el lock) y, en un entorno aparte, con 1.83.0: las dos
versiones dan lo mismo, en la respuesta entera y en el streaming.

Las llamadas van por ``LiteLLMProvider`` real (``acomplete`` y ``astream_complete``, el
camino del copiloto) dentro de un ``usage_turn``, hasta un servidor local que hace de
Anthropic y de OpenAI. Sin coste y sin red. Corre en un subproceso porque LiteLLM lee
``LITELLM_LOCAL_MODEL_COST_MAP`` al importarse.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import cache
from typing import Any

import pytest

#: Lo que manda el proveedor en cada llamada. Fresco 100, leído 5.000, escrito 3.000.
FRESH, READ, WRITTEN, OUTPUT = 100, 5_000, 3_000, 20
#: OpenAI cuenta lo leído y lo escrito dentro de ``prompt_tokens``.
OPENAI_PROMPT = FRESH + READ + WRITTEN

SCRIPT = r"""
import asyncio, json, os, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FRESH, READ, WRITTEN, OUTPUT = 100, 5000, 3000, 20
ANTHROPIC_USAGE = {"input_tokens": FRESH, "output_tokens": OUTPUT,
                   "cache_creation_input_tokens": WRITTEN, "cache_read_input_tokens": READ}
OPENAI_USAGE = {"prompt_tokens": FRESH + READ + WRITTEN, "completion_tokens": OUTPUT,
                "total_tokens": FRESH + READ + WRITTEN + OUTPUT,
                "prompt_tokens_details": {"cached_tokens": READ, "cache_write_tokens": WRITTEN}}


def anthropic_stream(model):
    events = [
        {"type": "message_start", "message": {
            "id": "m", "type": "message", "role": "assistant", "model": model, "content": [],
            "stop_reason": None, "stop_sequence": None,
            "usage": {**ANTHROPIC_USAGE, "output_tokens": 1}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ok"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": OUTPUT}},
        {"type": "message_stop"},
    ]
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def openai_stream(model):
    base = {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": model}
    events = [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"},
                              "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {**base, "choices": [], "usage": OPENAI_USAGE},
    ]
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        anthropic = "/messages" in self.path
        if body.get("stream"):
            raw = (anthropic_stream if anthropic else openai_stream)(body["model"]).encode()
            kind = "text/event-stream"
        elif anthropic:
            raw = json.dumps({"id": "m", "type": "message", "role": "assistant",
                              "model": body["model"], "content": [{"type": "text", "text": "ok"}],
                              "stop_reason": "end_turn", "stop_sequence": None,
                              "usage": ANTHROPIC_USAGE}).encode()
            kind = "application/json"
        else:
            raw = json.dumps({"id": "c", "object": "chat.completion", "created": 1,
                              "model": body["model"],
                              "choices": [{"index": 0, "finish_reason": "stop",
                                           "message": {"role": "assistant", "content": "ok"}}],
                              "usage": OPENAI_USAGE}).encode()
            kind = "application/json"
        self.send_response(200)
        self.send_header("content-type", kind)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{server.server_port}"
os.environ.update({"ANTHROPIC_API_BASE": base, "ANTHROPIC_API_KEY": "k",
                   "OPENAI_API_BASE": base + "/v1", "OPENAI_BASE_URL": base + "/v1",
                   "OPENAI_API_KEY": "k"})

from nexus_api.core.litellm_map import litellm_module
import nexus_worker.metering.collector as collector
from nexus_worker.metering.consumer import rows_from_entry
from nexus_worker.runtime.llm import LiteLLMProvider

litellm = litellm_module()
published = []


async def capture(scope):
    # Lo que ``_publish`` mandaría al stream, sin Redis.
    published.append({"tenant_id": str(scope.tenant_id), "turn_id": scope.turn_id,
                      "source": scope.source,
                      "events": json.dumps([e.as_dict() for e in scope.events])})


collector._publish = capture
TENANT = uuid.UUID(int=65)
CHAT = [{"role": "user", "content": "hola"}]


async def one(model, stream):
    published.clear()
    raw_usage = None
    async with collector.usage_turn(tenant_id=TENANT, turn_id="turn-1"):
        provider = LiteLLMProvider(context_management=None)
        if stream:
            async for kind, _text in provider.astream_complete(
                    tenant_id=TENANT, role="respond", model=model, messages=CHAT):
                pass
            raw = await litellm.acompletion(model=model, messages=CHAT, stream=True,
                                            stream_options={"include_usage": True})
            async for chunk in raw:
                if getattr(chunk, "usage", None):
                    raw_usage = chunk.usage.model_dump()
        else:
            await provider.acomplete(tenant_id=TENANT, role="respond", model=model, messages=CHAT)
            raw_usage = (await litellm.acompletion(model=model, messages=CHAT)).usage.model_dump()
    # Lo de fuera del proveedor (la segunda llamada, para leer el ``usage`` en bruto) no
    # está dentro de ninguna medida: solo cuenta lo que pasó por ``LiteLLMProvider``.
    entry = published[0]
    events = json.loads(entry["events"])
    _tenant, rows = rows_from_entry(entry)
    return {
        "usage": raw_usage,
        "meters": {e["meter"]: e["quantity"] for e in events if e["idempotency_key"].startswith("turn-1:1:")},
        "rows": {r["meter"]: {"quantity": r["quantity"], "billable_qty": r["billable_qty"]}
                 for r in rows if r["idempotency_key"].startswith("turn-1:1:")},
    }


async def main():
    out = {}
    for model in ("anthropic/claude-sonnet-5-5", "openai/gpt-5.6-sol"):
        for stream in (False, True):
            out[f"{model}|{'stream' if stream else 'buffered'}"] = await one(model, stream)
    out["version"] = __import__("importlib.metadata").metadata.version("litellm")
    print("RESULT" + json.dumps(out))


asyncio.run(main())
"""


@cache
def _probe() -> dict[str, Any]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "LITELLM_PROXY_API_BASE",
            "LITELLM_PROXY_VIRTUAL_KEYS",
            "LITELLM_LOCAL_MODEL_COST_MAP",
            "NEXUS_USAGE_REQUIRE_TASK",
        }
    }
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=180
    )
    assert done.returncode == 0, done.stderr[-3000:]
    line = next(x for x in done.stdout.splitlines() if x.startswith("RESULT"))
    out: dict[str, Any] = json.loads(line[len("RESULT") :])
    return out


MODES = ("buffered", "stream")


def test_it_runs_on_the_locked_litellm() -> None:
    assert _probe()["version"] == "1.83.14"


@pytest.mark.parametrize("mode", MODES)
def test_anthropic_prompt_tokens_already_include_both_caches(mode: str) -> None:
    """La pregunta 1: 8.100 = 100 frescos + 5.000 leídos + 3.000 escritos. «prompt - lectura -
    escritura» deja lo fresco, sin restar nada dos veces."""
    usage = _probe()[f"anthropic/claude-sonnet-5-5|{mode}"]["usage"]
    assert usage["prompt_tokens"] == FRESH + READ + WRITTEN
    assert usage["cache_read_input_tokens"] == READ
    assert usage["cache_creation_input_tokens"] == WRITTEN


@pytest.mark.parametrize("mode", MODES)
def test_gpt56_cache_write_tokens_pass_through_litellm(mode: str) -> None:
    """La pregunta 2, primera mitad: LiteLLM deja ``cache_write_tokens`` donde OpenAI lo pone,
    y no lo copia a ``cache_creation_input_tokens``."""
    usage = _probe()[f"openai/gpt-5.6-sol|{mode}"]["usage"]
    assert usage["prompt_tokens"] == OPENAI_PROMPT
    assert usage["prompt_tokens_details"]["cached_tokens"] == READ
    assert usage["prompt_tokens_details"]["cache_write_tokens"] == WRITTEN
    assert not usage.get("cache_creation_input_tokens")


@pytest.mark.parametrize("model", ["anthropic/claude-sonnet-5-5", "openai/gpt-5.6-sol"])
@pytest.mark.parametrize("mode", MODES)
def test_the_collector_records_the_write_once(model: str, mode: str) -> None:
    """La pregunta 2, segunda mitad: lo escrito llega al medidor como ``llm.cache_write``, en
    las dos familias y una sola vez (Anthropic no se cuenta además desde
    ``prompt_tokens_details``)."""
    meters = _probe()[f"{model}|{mode}"]["meters"]
    assert meters == {
        "llm.input_tokens": FRESH + READ + WRITTEN,
        "llm.output_tokens": OUTPUT,
        "llm.cache_read": READ,
        "llm.cache_write": WRITTEN,
    }


@pytest.mark.parametrize("model", ["anthropic/claude-sonnet-5-5", "openai/gpt-5.6-sol"])
def test_the_native_breakdown_takes_the_write_out_of_the_input(model: str) -> None:
    """El consumidor, antes de los pesos: la entrada es lo fresco y la escritura va en su fila."""
    rows = _probe()[f"{model}|buffered"]["rows"]
    assert rows["llm.input_tokens"]["billable_qty"] == FRESH
    assert rows["llm.cache_read"]["billable_qty"] == READ
    assert rows["llm.cache_write"]["billable_qty"] == WRITTEN
    assert rows["llm.output_tokens"]["billable_qty"] == OUTPUT
