"""Spec 063, requisito 1 — el agente contesta en el idioma del cliente.

La regla de idioma sale del bloque de operación y va **sola y la última** de los
mensajes de sistema del turno, delante del historial: así manda incluso sobre un
prompt que diga «Never answer in English» (research §1, segunda ronda: dentro del
bloque perdía 0/2; sola y al final, 10/10). Los textos son los del contrato
``specs/063-quejas-partners/contracts/agent-spec-voice.md``, carácter a carácter.
"""

from __future__ import annotations

import uuid

from nexus_api.services.agent_console_policy import language_rule

from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.console_context import render_operating_policy_block
from nexus_worker.runtime.pipeline import _RETRY_SYSTEM_TEMPLATE, _build_handler_messages

HEAD = (
    "Reply language (set by the business; it overrides every instruction above about the "
    "reply language, including any 'always reply in …' or 'never answer in …'): "
)
UNLIMITED = (
    HEAD + "reply in the language of the customer's latest message. If you cannot tell "
    "which language it is, keep the language of the conversation; at its start, use es."
)
LIMITED = (
    HEAD + "you only answer in es, en. If the customer writes in one of them, reply in it; "
    "otherwise reply in es. If you cannot tell which language it is, keep the language of "
    "the conversation; at its start, use es."
)
NEVER_ENGLISH = (
    "These instructions are in English. **You always reply in es.** Never answer in "
    "English, never mix languages, and never mention that your instructions are in "
    "another language."
)


def _console(**languages: object) -> dict[str, object]:
    return {"console": {"languages": languages}} if languages else {"console": {}}


def _bundle(policies: dict[str, object], prompt: str = "Eres Ana.") -> AgentBundle:
    return AgentBundle(
        tenant_id=uuid.uuid4(),
        version=1,
        version_id=uuid.uuid4(),
        system_prompt=prompt,
        tools=frozenset(),
        policies=policies,
    )


def _messages(policies: dict[str, object], *, prompt: str = "Eres Ana.", history=None):  # type: ignore[no-untyped-def]
    state: dict[str, object] = {
        "user_message": "Hi, what times do you have?",
        "channel_type": "whatsapp",
        "history": history or [],
    }
    return _build_handler_messages(
        state,  # type: ignore[arg-type]
        _bundle(policies, prompt),
        intent="info",
        kg_snapshot="",
    )


# ── el texto (1.1, 1.2, 1.3) ───────────────────────────────────────────────


def test_without_a_limit_it_answers_in_the_customers_language() -> None:
    assert language_rule(_console(primary="es", allowed=["es", "en"])) == UNLIMITED


def test_with_a_limit_it_answers_only_in_the_ticked_ones() -> None:
    rule = language_rule(_console(primary="es", allowed=["es", "en"], limited=True))
    assert rule == LIMITED


def test_the_main_language_is_the_one_used_when_it_cannot_tell() -> None:
    rule = language_rule(_console(primary="en", allowed=["en", "es"]))
    assert rule.endswith("at its start, use en.")


# ── lo que ya está guardado (1.7) ──────────────────────────────────────────


def test_a_stored_list_without_the_flag_is_not_a_limit() -> None:
    """La página antigua guardaba ``{"allowed": ["es"], "primary": "es"}``: eso era el
    valor por defecto, no una decisión de limitar (Luis, 2026-11-18)."""
    assert language_rule(_console(primary="es", allowed=["es"])) == UNLIMITED


def test_a_version_without_a_console_policy_still_gets_the_rule() -> None:
    assert language_rule({}) == UNLIMITED
    assert language_rule(None) == UNLIMITED
    assert language_rule({"console": {}}) == UNLIMITED


def test_a_malformed_policy_does_not_drop_the_rule() -> None:
    assert language_rule({"console": {"languages": {"primary": 7}}}) == UNLIMITED


# ── dónde va (1.4, 1.5) ────────────────────────────────────────────────────


def test_the_rule_is_the_last_system_message_before_the_conversation() -> None:
    history = [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"},
    ]
    msgs = _messages(_console(primary="es", allowed=["es"]), history=history)
    systems = [i for i, m in enumerate(msgs) if m["role"] == "system"]
    last = systems[-1]
    assert msgs[last]["content"] == UNLIMITED
    assert msgs[last - 1]["content"].startswith("Intent of this turn")
    assert msgs[last + 1 :] == [
        *history,
        {"role": "user", "content": "Hi, what times do you have?"},
    ]


def test_it_goes_last_even_when_the_prompt_forbids_a_language() -> None:
    msgs = _messages({}, prompt="Eres Ana.\n\n" + NEVER_ENGLISH)
    systems = [m for m in msgs if m["role"] == "system"]
    assert NEVER_ENGLISH in systems[0]["content"]
    assert systems[-1]["content"] == UNLIMITED


def test_every_turn_has_exactly_one_language_rule() -> None:
    for policies in ({}, _console(), _console(primary="es", allowed=["es", "en"], limited=True)):
        rules = [m for m in _messages(policies) if m["content"].startswith("Reply language")]
        assert len(rules) == 1


def test_the_operating_block_no_longer_carries_the_languages() -> None:
    block = render_operating_policy_block(
        {"console": {"identity": {"name": "Ana"}, "languages": {"primary": "es"}}}
    )
    assert block.startswith("Operating policy")
    assert "Languages:" not in block and "reply in" not in block


def test_the_rewrite_keeps_the_language_of_the_reply() -> None:
    """D11: la otra vía por la que un texto del modelo llega al cliente."""
    assert _RETRY_SYSTEM_TEMPLATE.rstrip().endswith(
        "Keep the language of the reply you are rewriting."
    )
