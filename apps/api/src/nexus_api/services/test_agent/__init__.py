"""Block O — "Probar agente" sandbox.

Public surface:

- :func:`run_test_turn` — single-turn driver the admin endpoint calls.
  Takes the resolved system prompt, the whitelisted tool definitions
  and the conversation history; returns the assistant text + planned
  tool calls (captured, NEVER executed).

- :class:`TestAgentProvider` — Protocol around the LLM. Production
  resolves to :class:`LiteLLMTestAgentProvider`; tests inject
  :class:`FakeTestAgentProvider` to script outputs without touching
  litellm.

Hard invariants from ADR-014:

- The sandbox NEVER dispatches tools. Even read-only ones. Synthetic
  tool results are fed back to the model so it can produce a final
  text response.
- The sandbox NEVER persists ``conversations``, ``messages`` or
  ``customers`` rows.
- The sandbox uses the SAME model + system prompt + whitelist as
  production.
"""

from __future__ import annotations

from nexus_api.services.test_agent.service import (
    FakeTestAgentProvider,
    LiteLLMTestAgentProvider,
    PlannedToolCall,
    TestAgentError,
    TestAgentProvider,
    TestTurnResult,
    run_test_turn,
)

__all__ = [
    "FakeTestAgentProvider",
    "LiteLLMTestAgentProvider",
    "PlannedToolCall",
    "TestAgentError",
    "TestAgentProvider",
    "TestTurnResult",
    "run_test_turn",
]
