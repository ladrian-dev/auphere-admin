"""CO-05 · probar antes de publicar (§7 y §19.2 de CONTRACT-V2).

Lo que se fija aquí es lo que distingue un aviso honesto de uno que miente:
que ``trial`` tenga **tres** estados y no dos, que el aviso sepa que se probó
la versión activa y no la que se va a publicar, y que la respuesta del agente
borrador no salga por este camino.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.companion.tools.catalog import (
    ALL_TOOLS,
    TOOLS_BY_NAME,
    TRIAL_TOOLS,
    ToolSpec,
)
from nexus_api.companion.tools.playground import MAX_PROBES, TrialRecord, parse_probes
from nexus_api.companion.tools.proposals import _trial_warning

TRIAL_TOOL = "companion.run_playground_turn"


# ── el catálogo ────────────────────────────────────────────────────────


def test_the_trial_tool_is_its_own_class_and_never_asks_permission() -> None:
    """Probar no cambia nada del cliente, así que no pasa por
    ``propose → confirm → apply``. Una prueba que exige confirmación es una
    prueba que nadie hace, y entonces la gente publica sin probar."""
    spec = TOOLS_BY_NAME[TRIAL_TOOL]
    assert spec.tool_class == "trial"
    assert spec.permission_policy == "always_allow"
    assert spec.kind is None
    assert spec.method == "POST"
    assert "/playground/" in spec.path


def test_console_apply_is_still_the_only_write() -> None:
    """La garantía C4 no se toca por añadir una clase nueva."""
    assert [t.name for t in ALL_TOOLS if t.tool_class == "mutates"] == ["console.apply"]


def test_a_trial_tool_cannot_be_declared_always_ask() -> None:
    with pytest.raises(ValueError, match="probar no pide permiso"):
        ToolSpec(
            name="x.trial",
            path="/console/clients/{client_ref}/playground/threads/{thread_id}/runs",
            method="POST",
            label="x",
            description="x",
            tool_class="trial",
            permission_policy="always_ask",
        )


def test_only_a_trial_may_use_a_verb_other_than_get() -> None:
    """Sin esto, la clase nueva sería una puerta trasera de escritura."""
    with pytest.raises(ValueError, match="solo una herramienta 'trial'"):
        ToolSpec(
            name="x.write",
            path="/console/clients",
            method="POST",
            label="x",
            description="x",
            tool_class="read",
        )


def test_the_trial_is_published_only_in_build_mode() -> None:
    from nexus_api.companion.tools.catalog import tool_specs

    consult = {t["function"]["name"] for t in tool_specs(mode="consult")}
    build = {t["function"]["name"] for t in tool_specs(mode="build")}
    assert TRIAL_TOOL not in consult
    assert TRIAL_TOOL in build
    assert len(TRIAL_TOOLS) == 1


# ── los mensajes de prueba ─────────────────────────────────────────────


def test_probes_are_one_per_line_trimmed_and_capped() -> None:
    raw = "  ¿Cuánto cuesta?  \n\n¿Abren domingo?\n" + "\n".join(f"p{i}" for i in range(10))
    probes = parse_probes(raw)
    assert probes[:2] == ["¿Cuánto cuesta?", "¿Abren domingo?"]
    assert len(probes) == MAX_PROBES


def test_no_probes_is_not_a_trial() -> None:
    assert parse_probes("   \n  \n") == []


# ── lo que viaja al navegador ──────────────────────────────────────────


def _record(**kwargs: Any) -> TrialRecord:
    base: dict[str, Any] = {
        "client_ref": "boreal",
        "thread_id": "4d2b",
        "ok": True,
        "tokens": 4210,
        "tested_version": 8,
        "turns": [
            {
                "index": 1,
                "probe": "¿Cuánto cuesta el bótox?",
                "ok": True,
                "latency_ms": 1840,
                "checks": [
                    {"name": "agent_answered", "expected": "true", "actual": "true", "ok": True}
                ],
            }
        ],
    }
    base.update(kwargs)
    return TrialRecord(**base)


def test_the_trial_payload_never_carries_the_agents_reply() -> None:
    """Garantía E9. ``probe`` lo redacta el Companion; la respuesta del agente
    se lee abriendo el hilo de playground, no por aquí."""
    payload = _record().as_payload()

    def keys(node: Any) -> set[str]:
        if isinstance(node, dict):
            return set(node) | {k for v in node.values() for k in keys(v)}
        if isinstance(node, list):
            return {k for item in node for k in keys(item)}
        return set()

    # Por CLAVE y no por subcadena: ``agent_answered`` es el nombre de una
    # comprobación, no el texto del agente, y buscar "answer" en el ``repr``
    # lo marcaría — midiendo otra cosa que la que se quiere garantizar.
    assert (
        keys(payload)
        & {
            "content",
            "text",
            "body",
            "message",
            "messages",
            "answer",
            "reply",
            "transcript",
        }
        == set()
    )
    assert set(payload) == {
        "ran",
        "client_ref",
        "thread_id",
        "ok",
        "tokens",
        "tested_version",
        "turns",
    }
    assert set(payload["turns"][0]) == {"index", "probe", "ok", "latency_ms", "checks"}


def test_the_payload_carries_the_client_ref_so_the_drawer_can_link() -> None:
    """§19.2: sin ``client_ref`` la interfaz no puede construir
    ``/clients/{ref}/playground`` y el enlace del panel no existe."""
    assert _record().as_payload()["client_ref"] == "boreal"


# ── el aviso al publicar ───────────────────────────────────────────────


def test_nobody_tried_anything() -> None:
    assert _trial_warning(None, 8) == {
        "trial_ran": False,
        "trial_ok": None,
        "warning_key": "not_tried",
    }


def test_the_trial_failed() -> None:
    assert _trial_warning(_record(ok=False), 8) == {
        "trial_ran": True,
        "trial_ok": False,
        "warning_key": "trial_failed",
    }


def test_it_was_tried_but_what_ran_was_the_active_version() -> None:
    """El estado honesto por defecto mientras el playground no sepa correr un
    borrador: se probó la v7, se va a publicar la v8. Decir "probado" a secas
    sería una afirmación sin respaldo, que es lo que R1 existe para impedir."""
    assert _trial_warning(_record(tested_version=7), 8) == {
        "trial_ran": True,
        "trial_ok": True,
        "warning_key": "tried_active_only",
    }


def test_it_was_tried_and_what_ran_is_what_gets_published() -> None:
    assert _trial_warning(_record(tested_version=8), 8) == {
        "trial_ran": True,
        "trial_ok": True,
        "warning_key": None,
    }


def test_a_trial_without_a_known_version_still_warns() -> None:
    """No saber qué versión respondió es no poder respaldar la prueba."""
    assert _trial_warning(_record(tested_version=None), 8)["warning_key"] == "tried_active_only"
