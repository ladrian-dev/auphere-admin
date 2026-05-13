"""Meta-prompt for the "Mejorar prompt" utility (Block N).

The structure is inspired by Anthropic's Prompt Improver four-step
pipeline (example identification → structured draft → CoT refinement
→ example enhancement) but adapted to Nexus' bespoke-per-tenant model:
we know the channel, vertical, available tools and tenant identity, so
the improver can reference them concretely instead of suggesting
generic "consider adding examples" boilerplate.

Output contract — the model must respond in XML:

::

    <improved_prompt>
    ...
    </improved_prompt>
    <summary>
    - bullet 1
    - bullet 2
    </summary>

The endpoint parses these two tags. If the model returns malformed XML
the endpoint surfaces a 502 with the raw response so the operator can
retry. We deliberately do NOT auto-retry on parse failure: the operator
should see what came back to decide whether to iterate the meta-prompt
or the input.
"""

from __future__ import annotations

from typing import Final

# Bump this when the system prompt or mode instructions change in a way
# that affects observed behaviour. Recorded on each ImproveResult so
# Langfuse / audit can correlate output quality with meta-prompt
# revisions.
META_PROMPT_VERSION: Final[str] = "n.v1"


# The full set of modes the operator can pick from the UI. ``general``
# is the default — broad improvement following the four-step pipeline.
# Each focused mode below narrows the system prompt to keep edits
# predictable (no surprise expansions when the operator just wants to
# shorten).
SUPPORTED_MODES: Final[tuple[str, ...]] = (
    "general",
    "specific",
    "structure",
    "examples",
    "shorter",
    "edge_cases",
    "english",
)


_MODE_INSTRUCTIONS: Final[dict[str, str]] = {
    "general": (
        "Improve the draft following the four-step pipeline:\n"
        "1. Identify any few-shot examples already embedded — keep them.\n"
        "2. Restructure with clearly named sections using XML-like tags "
        "(<role>, <context>, <tools_policy>, <output_format>, <edge_cases>).\n"
        "3. Add chain-of-thought scaffolding for non-trivial decisions "
        "(when to call which tool, when to escalate to human).\n"
        "4. Anchor every instruction to the <agent_context> below: name "
        "the actual tenant, the actual channel, the actual tools."
    ),
    "specific": (
        "Make the draft MORE SPECIFIC. Replace any generic phrasing with "
        "concrete references to the tenant, the channel, the tools, the "
        "business hours and the language declared in <agent_context>. Do "
        "NOT change the overall structure or length materially — focus on "
        "tightening vague instructions."
    ),
    "structure": (
        "Restructure the draft using clearly named XML-like sections "
        "(<role>, <context>, <tools_policy>, <output_format>, "
        "<edge_cases>, <handoff>). Preserve every instruction; only "
        "reorder and section them. Do NOT add new requirements that the "
        "operator did not ask for."
    ),
    "examples": (
        "Add 2-3 concrete few-shot examples that demonstrate the desired "
        "agent behaviour. Use realistic customer phrasing for the declared "
        "channel and language. The examples MUST reference tools from "
        "<available_tools> — do not invent tool names."
    ),
    "shorter": (
        "Shorten the draft WITHOUT losing instructional intent. Target "
        "≈40% fewer tokens. Remove repetition, redundant courtesy text "
        "and boilerplate. Keep edge-case handling intact — those are "
        "load-bearing. NEVER drop tool-calling rules."
    ),
    "edge_cases": (
        "Strengthen edge-case coverage. For each tool in <available_tools> "
        "and each common conversational pivot (ambiguous date, no "
        "availability, customer in wrong language, off-topic chitchat, "
        "explicit escalation request, abuse, fraud signals) add an "
        "explicit instruction to the prompt under an <edge_cases> "
        "section. Preserve the rest."
    ),
    "english": (
        "Translate the draft to natural English while preserving every "
        "instruction. Keep tool names, tenant name and channel verbatim. "
        "Do not add or remove instructions — translation only."
    ),
}


# NOTE: this template is rendered via plain string replace (not
# ``str.format``) on the two placeholders below — the body deliberately
# contains literal ``{`` characters when discussing prompt syntax with
# the model, and we don't want to chase ``{{ }}`` escapes every time
# someone tweaks the wording.
_SYSTEM_PROMPT_TEMPLATE: Final[str] = """\
You are an expert prompt engineer working inside Nexus, Auphere's
multi-tenant AI agent platform. Each tenant runs a bespoke agent on
WhatsApp (and soon other channels) that takes real actions through a
whitelisted toolset.

Your job: improve the operator's DRAFT_PROMPT below so the agent
performs better in production for THIS specific tenant. Apply the
<agent_context> verbatim — anchor every instruction in the real
tenant, channel, tools, business hours and language declared there.

GENERAL RULES:
- The draft is pre-rendered: it already contains the tenant's data
  inline. Preserve those literal values; never re-introduce
  placeholder syntax (e.g. curly-brace tokens like the ones in the
  YAML seeds).
- The whitelist of tools in <available_tools> is exhaustive. Never
  invent tool names. If the draft mentions a tool not in the
  whitelist, drop or replace that reference.
- The channel constrains output style:
    * whatsapp → short messages, no markdown, sparing emojis, plain
      text only.
    * voice → spoken-style ("decí" / "say"), no markdown, sentences
      under ~15 words.
    * web → markdown OK, longer responses allowed.
- The improvement target is described in <mode_instructions>. Stay
  within that scope.

MODE_INSTRUCTIONS:
__MODE_INSTRUCTIONS__

OUTPUT FORMAT (mandatory):
Respond with exactly two top-level XML blocks, in this order:

<improved_prompt>
... the improved prompt verbatim, ready to paste into the editor ...
</improved_prompt>
<summary>
- bullet describing the most important change
- bullet describing the second
- ... (3 to 6 bullets total)
</summary>

Do not wrap the XML in code fences. Do not add any other commentary.
Do not output the <agent_context> back. The <improved_prompt> block is
the agent's new system prompt, written in the same language as the
draft unless <mode_instructions> overrides that.

Meta-prompt version: __VERSION__.
"""


def _format_context_block(context: dict[str, object]) -> str:
    """Render the user-side ``<agent_context>`` block. We do this with
    plain string concatenation (not jinja, not f-strings on user data)
    because the values could legitimately contain ``{`` characters from
    the operator's draft."""
    lines = ["<agent_context>"]
    for key, value in context.items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, list):
            lines.append(f"  <{key}>")
            for item in value:
                lines.append(f"    - {item}")
            lines.append(f"  </{key}>")
        else:
            lines.append(f"  <{key}>{value}</{key}>")
    lines.append("</agent_context>")
    return "\n".join(lines)


def build_meta_messages(
    *,
    draft_prompt: str,
    mode: str,
    feedback: str | None,
    context: dict[str, object],
) -> list[dict[str, object]]:
    """Build the ``messages`` array for ``litellm.acompletion``.

    The system block uses Anthropic's prompt-caching annotation
    (``cache_control={"type": "ephemeral"}``) so the static meta-prompt
    + the mode instructions hit the 90%-off cache lane after the first
    call. The cache TTL is 5 minutes which lines up with the operator
    iterating on a single agent.
    """
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported mode {mode!r}; supported: {SUPPORTED_MODES}")

    system_text = _SYSTEM_PROMPT_TEMPLATE.replace(
        "__MODE_INSTRUCTIONS__", _MODE_INSTRUCTIONS[mode]
    ).replace("__VERSION__", META_PROMPT_VERSION)

    user_block = _format_context_block(context)
    user_block += f"\n<mode>{mode}</mode>"
    if feedback:
        user_block += f"\n<feedback>{feedback}</feedback>"
    user_block += "\n<draft_prompt>\n" + draft_prompt + "\n</draft_prompt>"

    return [
        {
            "role": "system",
            # LiteLLM accepts Anthropic's structured content with
            # cache_control on individual blocks. The text-block shape
            # is the documented contract for prompt caching.
            "content": [
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
        },
        {
            "role": "user",
            "content": user_block,
        },
    ]
