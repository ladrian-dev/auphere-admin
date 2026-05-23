"""Verify Anthropic prompt-cache hits with real traffic.

Fase A — claude-platform-integration §A.4. ``_with_prompt_caching`` was
shipped in 2026-05-22 (Fase 2 E3) but the gate of E3 left open was:
*verify that ``cache_read_input_tokens > 0`` on the second and third
turns when the system prefix exceeds the model's minimum*. This script
closes that gate by driving the LiteLLM provider with the same shape the
runtime uses (system block(s) + cache_control breakpoint, plus tools so
context_management is exercised) against a real model.

Usage:

    ANTHROPIC_API_KEY=sk-ant-... \\
      uv run python apps/worker/scripts/verify_cache_hits.py

Options (env vars):

- ``NEXUS_CACHE_VERIFY_MODEL`` — model id (default
  ``anthropic/claude-haiku-4-5``; Haiku needs ≥ 4096 tokens of prefix to
  cache, the script pads to comfortably clear that minimum).
- ``NEXUS_CACHE_VERIFY_TURNS`` — number of turns to drive (default 3).
- ``NEXUS_CACHE_VERIFY_PAUSE_S`` — seconds between turns (default 5).
  Anthropic's ephemeral cache lasts ~5 minutes; any wait below that
  must still hit. We default to 5s — fast feedback without risking the
  TTL.

The script logs each turn's ``cache_creation_input_tokens`` and
``cache_read_input_tokens`` and exits non-zero if turn 2 reports
``cache_read_input_tokens == 0`` (which would mean caching is silently
broken — see roadmap E3 acceptance).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

from nexus_worker.runtime.llm import (
    DEFAULT_CONTEXT_MANAGEMENT,
    LiteLLMProvider,
)

# Padding string repeated to push the cached prefix above Haiku's 4096-token
# minimum without inventing meaningful content. Each repetition ≈ 50 tokens
# in cl100k_base; 100 repetitions ≈ 5000 tokens, comfortably above the
# minimum so the cache reliably engages.
_PAD = (
    "Sample knowledge graph fact about the operator's catalogue: "
    "services, opening hours, location, pricing rules. "
)


def _build_system_prefix() -> str:
    """Build a system prefix that comfortably exceeds Haiku 4.5's 4096-token
    cache minimum so the run does not silently hit the no-cache fallback."""
    return (
        "You are a test agent for verifying Anthropic prompt caching. "
        "Answer in a single short sentence.\n\n"
        + (_PAD * 100)
    )


async def _run(*, model: str, turns: int, pause_s: float) -> int:
    """Drive ``turns`` identical calls against ``model`` and report cache
    usage. Returns 0 on success, non-zero on cache-miss in turn 2+."""
    provider = LiteLLMProvider(context_management=DEFAULT_CONTEXT_MANAGEMENT)
    tenant_id = uuid.uuid4()
    system_prefix = _build_system_prefix()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "noop",
                "description": "test tool, never call",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        }
    ]
    messages = [
        {"role": "system", "content": system_prefix},
        {"role": "user", "content": "Say 'ok' and stop."},
    ]

    failed = False
    for turn in range(1, turns + 1):
        # ``_raw_complete`` is the internal that returns the full provider
        # response (with usage). We call it directly so we can read the
        # cache_*_input_tokens fields.
        response = await provider._raw_complete(
            tenant_id=tenant_id,
            role="cache-verify",
            model=model,
            messages=messages,
            tools=tools,
        )
        usage = (response.get("usage") or {}) if isinstance(response, dict) else {}
        # LiteLLM normalises Anthropic's usage block; both names appear.
        cache_creation = (
            usage.get("cache_creation_input_tokens")
            or usage.get("prompt_cache_creation_input_tokens")
            or 0
        )
        cache_read = (
            usage.get("cache_read_input_tokens")
            or usage.get("prompt_cache_read_input_tokens")
            or 0
        )
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        print(
            f"turn {turn}: input_tokens={input_tokens} "
            f"cache_creation={cache_creation} cache_read={cache_read}"
        )
        if turn >= 2 and cache_read == 0:
            print(
                f"FAIL: turn {turn} reported cache_read_input_tokens=0 — "
                "the cache breakpoint is not engaging on warm prefix",
                file=sys.stderr,
            )
            failed = True
        if turn < turns:
            await asyncio.sleep(pause_s)

    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=os.getenv("NEXUS_CACHE_VERIFY_MODEL", "anthropic/claude-haiku-4-5"),
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=int(os.getenv("NEXUS_CACHE_VERIFY_TURNS", "3")),
    )
    parser.add_argument(
        "--pause-s",
        type=float,
        default=float(os.getenv("NEXUS_CACHE_VERIFY_PAUSE_S", "5")),
    )
    args = parser.parse_args()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 2
    return asyncio.run(_run(model=args.model, turns=args.turns, pause_s=args.pause_s))


if __name__ == "__main__":
    raise SystemExit(main())
