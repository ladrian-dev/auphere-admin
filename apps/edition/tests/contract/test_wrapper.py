"""El envoltorio del harness — Requisitos 5.1 y 5.2.

Es T001 llevado a producto. Aquel spike demostró en máquina sucia que el flag deja el
catálogo con solo las herramientas de Crew y que los cuatro servidores ajenos ni
siquiera arrancan sus procesos; esto fija esa forma para que no se pierda en un
comentario.

El *por qué* funciona está medido y merece quedar escrito: el SDK serializa los
``mcpServers`` que Crew envía en ``session/new`` a ``--mcp-config``, así que
``--strict-mcp-config`` restringe **a** ese conjunto en vez de vaciarlo.
"""

from __future__ import annotations

from auphere_edition.wrapper import (
    STRICT_FLAG,
    foreign_servers,
    render_wrapper_script,
    wrapper_argv,
)


def test_the_strict_flag_is_prepended_to_the_real_binary():
    argv = wrapper_argv("/usr/local/bin/claude", ["--mcp-config", "{}", "--verbose"])
    assert argv[0] == "/usr/local/bin/claude"
    assert argv[1] == STRICT_FLAG
    assert argv[2:] == ["--mcp-config", "{}", "--verbose"]


def test_the_flag_is_never_duplicated():
    """El SDK sabe empujarlo por su cuenta; dos veces no aporta y confunde el log."""
    argv = wrapper_argv("/bin/claude", [STRICT_FLAG, "--verbose"])
    assert argv.count(STRICT_FLAG) == 1


def test_the_script_execs_the_real_binary():
    script = render_wrapper_script("/usr/local/bin/claude")
    assert "exec" in script
    assert "/usr/local/bin/claude" in script
    assert STRICT_FLAG in script


def test_the_script_refuses_to_point_at_itself():
    """Un envoltorio que se llama a sí mismo es una bomba de recursión silenciosa."""
    import pytest

    with pytest.raises(ValueError):
        render_wrapper_script("/opt/auphere/bin/claude-strict", wrapper_path="/opt/auphere/bin/claude-strict")


# ── R5.2: dejar constancia del intento ─────────────────────────────────


def test_foreign_servers_are_named_so_the_attempt_is_recorded():
    """No basta con no exponerlas: hay que poder decir qué se intentó colar."""
    config = {"mcpServers": {"chrome-devtools": {}, "playwright": {}, "higgsfield": {}}}
    assert foreign_servers(config) == ["chrome-devtools", "higgsfield", "playwright"]


def test_a_clean_machine_records_nothing():
    assert foreign_servers({}) == []
    assert foreign_servers({"mcpServers": {}}) == []


def test_a_malformed_config_is_not_an_excuse_to_crash():
    """El fichero es del partner: puede tener cualquier cosa dentro."""
    assert foreign_servers({"mcpServers": "esto no es un objeto"}) == []
    assert foreign_servers(None) == []
