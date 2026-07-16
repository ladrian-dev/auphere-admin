"""Nexus runtime worker.

Block C — agent runtime with strict tool whitelist + checkpointer scoping.
The worker package houses the LangGraph pipeline, the LiteLLM router, the
in-process tool stubs (full MCP servers ship in block D), and the Redis
Stream consumer that the Meta webhook feeds.

Imports here stay light so ``nexus_api`` (which uses this package only in
tests) does not pay for langgraph/litellm at import time.
"""

import os

# ── litellm connection hygiene (root fix for the classify Timeout storm) ──────
# litellm's aiohttp transport keeps idle keep-alive connections pooled for
# ``AIOHTTP_KEEPALIVE_TIMEOUT`` seconds (litellm default: 120). Anthropic's edge
# closes idle connections well before that, so after a lull between WhatsApp
# turns the FIRST call of the next turn — always ``classify`` — reused a
# server-closed socket: aiohttp raised ``ServerDisconnected``, litellm mapped it
# to ``Timeout`` (failing in ~1ms, long before the 30s budget) and the turn ate
# a wasted retry. Holding the pooled connection for LESS time than the server's
# idle-close window means we always reconnect fresh instead of grabbing a dead
# socket. Set BEFORE any ``import litellm`` (litellm reads this at
# constants-import time; every litellm import in the worker is lazy, so this
# package-init runs first) and via ``setdefault`` so Doppler still overrides.
os.environ.setdefault("AIOHTTP_KEEPALIVE_TIMEOUT", "15")

__all__ = ["__version__"]

__version__ = "0.1.0"
