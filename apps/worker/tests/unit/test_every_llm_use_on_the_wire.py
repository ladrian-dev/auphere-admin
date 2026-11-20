"""Spec 065, T009 (requisitos 4.12 y 3.2): cada uso de LiteLLM sale con el mapa fijo.

Fijar el mapa de modelos de LiteLLM (research.md §D13) cambia la conducta de **todos** los
usos, no solo la respuesta del agente: con el mapa local que trae LiteLLM 1.83.14 y sin
nuestras entradas, cualquier ``tool_choice`` hacia GPT-5.6 se rechaza antes de salir y el
razonamiento de Haiku 5.5 también. Por eso aquí hay un caso por cada uso de
:func:`nexus_worker.platform_models.default_models`, con el modelo que resuelve hoy ese uso
y la forma de petición que manda su código, hasta un servidor local que hace de OpenAI y de
Anthropic. Un uso nuevo en el registro sin su caso aquí también falla.

Corre en un subproceso porque LiteLLM lee ``LITELLM_LOCAL_MODEL_COST_MAP`` al importarse, y
ese subproceso **no** fija la variable: la tiene que fijar la puerta de LiteLLM
(``nexus_api.core.litellm_map``), como en producción.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import cache
from typing import Any

import pytest

SCRIPT = r"""
import asyncio, json, os, threading, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

calls = []


def label_enum(body):
    for tool in body.get("tools") or []:
        enum = (tool.get("input_schema") or {}).get("properties", {}).get("label", {}).get("enum")
        if enum:
            return enum
    fmt = body.get("response_format") or {}
    return ((fmt.get("json_schema") or {}).get("schema") or {}).get("properties", {}).get("label", {}).get("enum")


class Provider(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        raw_body = self.rfile.read(int(self.headers["content-length"]))
        if "/audio/transcriptions" in self.path:
            calls.append({"path": self.path, "body": {}})
            out = {"text": "hola", "duration": 1.0, "language": "es", "task": "transcribe"}
        else:
            body = json.loads(raw_body)
            calls.append({"path": self.path, "body": body})
            enum = label_enum(body)
            if "/messages" in self.path:
                if enum and body.get("tool_choice", {}).get("type") == "tool":
                    content = [{"type": "tool_use", "id": "toolu_1", "name": body["tools"][0]["name"],
                                "input": {"label": enum[0]}}]
                    stop = "tool_use"
                else:
                    content, stop = [{"type": "text", "text": "ok"}], "end_turn"
                out = {"id": "m", "type": "message", "role": "assistant", "model": body["model"],
                       "content": content, "stop_reason": stop, "stop_sequence": None,
                       "usage": {"input_tokens": 10, "output_tokens": 2}}
            else:
                fmt = (body.get("response_format") or {}).get("type")
                text = json.dumps({"label": enum[0]}) if enum else ("{}" if fmt == "json_object" else "ok")
                out = {"id": "c", "object": "chat.completion", "created": 1, "model": body["model"],
                       "choices": [{"index": 0, "finish_reason": "stop",
                                    "message": {"role": "assistant", "content": text}}],
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

from nexus_api.core.litellm_map import litellm_module
from nexus_api.core.llm_proxy import apply_litellm_proxy_kwargs
from nexus_worker.platform_models import default_models
from nexus_worker.runtime.companion.prompt import thinking_extra
from nexus_worker.runtime.llm import LiteLLMProvider, LLMRouter

TENANT = uuid.uuid4()
TOOLS = [{"type": "function", "function": {"name": "reservas_slots", "description": "Huecos libres",
          "parameters": {"type": "object", "properties": {"dia": {"type": "string"}}}}}]
CHAT = [{"role": "system", "content": "Eres un asistente."}, {"role": "user", "content": "hola"}]


def provider():
    return LiteLLMProvider(context_management=None)


async def tools(model):
    await provider().acomplete_with_tools(tenant_id=TENANT, role="respond", model=model,
                                          messages=CHAT, tools=TOOLS)


async def closure(model):
    # El cierre del turno (pipeline): las mismas herramientas y ``tool_choice: none``.
    await provider().acomplete_with_tools(tenant_id=TENANT, role="respond", model=model,
                                          messages=CHAT, tools=TOOLS, extra={"tool_choice": "none"})


async def companion(model):
    # El cierre del Companion: razonamiento, esfuerzo y ``tool_choice: none``.
    await provider().acomplete_with_tools(tenant_id=TENANT, role="respond", model=model,
                                          messages=CHAT, tools=TOOLS,
                                          extra=thinking_extra("low", tool_choice="none"))


async def label(model):
    router = LLMRouter(provider=provider(), classify_model=model, respond_model=model,
                       fallback_model="", classify_fallback_model="", retry_backoff_s=0)
    await router.classify(tenant_id=TENANT, messages=CHAT, models=(model,), labels=("info", "book"))


async def json_object(model):
    await provider().acomplete(tenant_id=TENANT, role="respond", model=model, messages=CHAT,
                               extra={"response_format": {"type": "json_object"}})


async def plain(model):
    await provider().acomplete(tenant_id=TENANT, role="respond", model=model, messages=CHAT)


async def direct(model):
    # La mejora de prompts y el juez de las evaluaciones llaman a LiteLLM sin el proveedor.
    kwargs = apply_litellm_proxy_kwargs({
        "model": model,
        "messages": [{"role": "system", "content": [{"type": "text", "text": "Juzga.",
                                                      "cache_control": {"type": "ephemeral"}}]},
                     {"role": "user", "content": "hola"}],
        "max_tokens": 400,
        "metadata": {"role": "eval_judge"},
    })
    await litellm_module().acompletion(**kwargs)


async def vision(model):
    pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    await litellm_module().acompletion(**apply_litellm_proxy_kwargs({
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Describe la imagen."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + pixel}}]}],
    }))


async def transcription(model):
    import io
    audio = io.BytesIO(b"\x00" * 64)
    audio.name = "audio.ogg"
    await litellm_module().atranscription(**apply_litellm_proxy_kwargs({
        "model": model, "file": audio, "response_format": "verbose_json"}))


SHAPES = {"tools": tools, "closure": closure, "companion": companion, "label": label,
          "json_object": json_object, "plain": plain, "direct": direct, "vision": vision,
          "transcription": transcription}
USE_SHAPES = json.loads(os.environ["PROBE_USE_SHAPES"])


async def main():
    # Spec 065 (T056): las reservas de la otra familia son usos mientras estén habilitadas;
    # aquí, las seis, para que cada una tenga su caso.
    from nexus_api.core import respond_catalog
    from nexus_api.core.respond_profiles import PROFILES

    respond_catalog.refresh_from_rows(
        [{"model_id": m, "status": "active", "offer_label": m, "price_input_per_mtok": 1,
          "respond_enabled_at": "2026-11-20"} for m in PROFILES]
        + [{"model_id": m, "status": "active", "offer_label": None, "price_input_per_mtok": 1,
            "respond_enabled_at": None}
           for m in respond_catalog.BOOT_HOP_MODEL_IDS if m not in PROFILES]
    )
    models = default_models()
    results = {}
    for use, shapes in USE_SHAPES.items():
        model = models.get(use)
        if model is None:
            continue
        for shape in shapes:
            before = len(calls)
            try:
                await SHAPES[shape](model)
                error = None
            except Exception as exc:  # noqa: BLE001 — the test names it
                error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}"
            results[f"{use}:{shape}"] = {"model": model, "error": error, "calls": calls[before:]}
    print("RESULT" + json.dumps({"uses": sorted(models), "results": results,
                                 "map_pinned": os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP")}))


asyncio.run(main())
"""

#: La forma (o formas) de petición que manda cada uso de ``default_models()``.
USE_SHAPES: dict[str, list[str]] = {
    # El turno del agente: las herramientas y el cierre con ``tool_choice: none``.
    "respond": ["tools", "closure"],
    "respond_fallback": ["tools", "closure"],
    # Spec 065: la reserva de la otra familia de cada modelo y el modelo de los agentes sin
    # elección también responden el turno.
    "respond_fallback_openai": ["tools", "closure"],
    "respond_fallback_anthropic": ["tools", "closure"],
    "agent_default": ["tools", "closure"],
    "qa_respond": ["tools", "closure"],
    "console_fallback": ["tools"],
    "partner_default": ["tools"],
    # El clasificador, el freno de reservas y la reserva del clasificador: una etiqueta.
    "classify": ["label"],
    "qa_classify": ["label"],
    "booking_brake": ["label"],
    "classify_fallback": ["label"],
    "outcome_grader": ["plain"],
    # El constructor y la lectura de fuentes piden JSON; el resto, texto.
    "build": ["json_object"],
    "extract": ["json_object", "plain"],
    "read_source": ["json_object", "plain"],
    "sector": ["label", "plain"],
    "simulation": ["plain"],
    "customer_sim": ["plain"],
    "judge": ["plain", "json_object"],
    # La API.
    "companion": ["companion"],
    "improve": ["direct"],
    "vision": ["vision"],
    "transcribe": ["transcription"],
    "knowledge_embedding": [],
    # Las evaluaciones del panel.
    "evals_classify": ["label"],
    "evals_respond": ["tools"],
    "evals_fallback": ["tools", "label"],
    "evals_judge": ["direct"],
    "evals_companion": ["companion"],
}


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
    env["PROBE_USE_SHAPES"] = json.dumps(USE_SHAPES)
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, env=env, timeout=300
    )
    assert done.returncode == 0, done.stderr[-3000:]
    line = next(x for x in done.stdout.splitlines() if x.startswith("RESULT"))
    out: dict[str, Any] = json.loads(line[len("RESULT") :])
    return out


def _case(use: str, shape: str) -> dict[str, Any]:
    result = _run()["results"].get(f"{use}:{shape}")
    if result is None:
        pytest.fail(f"{use} no resuelve ningún modelo en este proceso")
    assert result["error"] is None, f"{use} con {result['model']}: {result['error']}"
    assert result["calls"], f"{use} no llegó al proveedor"
    call: dict[str, Any] = result["calls"][-1]
    if str(result["model"]).startswith("openai/") and shape != "transcription":
        # Sin desvío a ``/responses``: el turno, el cierre y el Companion van por Chat
        # Completions (research.md §D8.1; T014).
        assert call["path"].endswith("/chat/completions"), call["path"]
    return call


def test_the_map_is_pinned_by_the_litellm_gate_not_by_the_caller() -> None:
    assert _run()["map_pinned"] == "True"


def test_every_use_of_the_registry_has_its_case_here() -> None:
    missing = set(_run()["uses"]) - set(USE_SHAPES)
    assert not missing, f"usos sin caso en el cable: {sorted(missing)}"


@pytest.mark.parametrize(
    ("use", "shape"),
    [(use, shape) for use, shapes in USE_SHAPES.items() for shape in shapes],
)
def test_each_use_reaches_the_provider_with_the_map_pinned(use: str, shape: str) -> None:
    call = _case(use, shape)
    body = call["body"]
    path = call["path"]
    if shape in {"tools", "closure", "companion"}:
        assert body.get("tools"), "las herramientas no llegaron"
        if path.endswith("/chat/completions"):
            assert "thinking" not in body and "output_config" not in body, (
                "parámetros de Anthropic hacia OpenAI"
            )
            assert body.get("reasoning_effort") == "none", "GPT-5.6 con herramientas va sin razonar"
    if shape in {"closure", "companion"}:
        if path.endswith("/chat/completions"):
            assert body.get("tool_choice") == "none"
        else:
            assert body.get("tool_choice") == {"type": "none"}
    if shape == "label":
        if path.endswith("/messages"):
            assert body["tool_choice"]["type"] == "tool"
        else:
            assert body["response_format"]["type"] == "json_schema"
    if shape == "json_object":
        assert path.endswith("/chat/completions")
        assert body["response_format"] == {"type": "json_object"}
    if shape == "vision":
        assert any(
            isinstance(part, dict) and part.get("type") in {"image", "image_url"}
            for message in body["messages"]
            for part in (message.get("content") if isinstance(message.get("content"), list) else [])
        )
    if shape == "transcription":
        assert path.endswith("/audio/transcriptions")
