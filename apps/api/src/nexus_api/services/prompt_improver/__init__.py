"""Block N — "Mejorar prompt" utility.

Public surface:

- :func:`improve_prompt` — the high-level entrypoint the admin endpoint
  calls. Takes the operator's draft + tenant context, returns the
  improved text + a bullet list of changes.

- :class:`PromptImproverProvider` — Protocol the service uses to reach
  the LLM. Production resolves it to :class:`LiteLLMPromptImproverProvider`;
  tests pass :class:`FakePromptImproverProvider` to script outputs.

The meta-prompt that drives the improvement lives in
:mod:`.meta_prompt` so it can be unit-tested in isolation.
"""

from __future__ import annotations

from nexus_api.services.prompt_improver.meta_prompt import (
    META_PROMPT_VERSION,
    SUPPORTED_MODES,
    build_meta_messages,
)
from nexus_api.services.prompt_improver.service import (
    AgentContext,
    FakePromptImproverProvider,
    ImproveResult,
    LiteLLMPromptImproverProvider,
    MalformedResponseError,
    PromptImproverError,
    PromptImproverProvider,
    PromptTooLongError,
    improve_prompt,
)

__all__ = [
    "META_PROMPT_VERSION",
    "SUPPORTED_MODES",
    "AgentContext",
    "FakePromptImproverProvider",
    "ImproveResult",
    "LiteLLMPromptImproverProvider",
    "MalformedResponseError",
    "PromptImproverError",
    "PromptImproverProvider",
    "PromptTooLongError",
    "build_meta_messages",
    "improve_prompt",
]
