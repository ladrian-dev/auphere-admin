"""Nexus runtime worker.

Block C — agent runtime with strict tool whitelist + checkpointer scoping.
The worker package houses the LangGraph pipeline, the LiteLLM router, the
in-process tool stubs (full MCP servers ship in block D), and the Redis
Stream consumer that the YCloud webhook feeds.

Imports here stay light so ``nexus_api`` (which uses this package only in
tests) does not pay for langgraph/litellm at import time.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
