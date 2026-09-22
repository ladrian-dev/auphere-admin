"""Dónde se corta el caché, y qué cuesta el turno — spec 015, Requisito 3.

**Sin llamar al proveedor, y eso es parte del requisito** (R3.2).
``_with_prompt_caching`` es una función pura de lista a lista, así que dónde
caen los puntos de corte se puede afirmar sobre su salida. Un test que exigiera
una llamada real no se correría nunca y no vigilaría nada.

**Lo que esto defiende, medido.** ``_with_prompt_caching`` fusiona *todos* los
mensajes de sistema iniciales contiguos en uno solo. Con un único punto de corte,
el bloque de identidad del teammate cae **dentro** del prefijo cacheado: como la
identidad varía por teammate, cada uno tendría su propia entrada de caché y los
7 KB compartidos se escribirían **una vez por teammate** en vez de una para
todos.
"""

from __future__ import annotations

import pytest
from nexus_worker.runtime.llm import _with_prompt_caching

pytestmark = pytest.mark.unit

COMPARTIDO = "Eres el Companion de Auphere: " + "x" * 6000
IDENTIDAD = "Eres Sofía, teammate del partner, con el oficio «revisora»."


def _cortes(salida: list[dict]) -> list[int]:
    """Índices de los bloques de la cabecera que llevan `cache_control`."""
    cabecera = salida[0]["content"]
    return [i for i, b in enumerate(cabecera) if "cache_control" in b]


def _turno(*, identidad: str | None, historia: int = 4) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": COMPARTIDO}]
    if identidad:
        msgs.append({"role": "system", "content": identidad})
    msgs += [{"role": "user", "content": f"m{i}"} for i in range(historia)]
    return msgs


# ── dónde caen los cortes ───────────────────────────────────────────────


def test_with_an_identity_there_are_two_breakpoints_in_the_header() -> None:
    salida = _with_prompt_caching(_turno(identidad=IDENTIDAD), split_header=True)
    cabecera = salida[0]["content"]

    assert _cortes(salida) == [0, 1], "corte 1 tras lo compartido, corte 2 tras la identidad"
    assert cabecera[0]["text"] == COMPARTIDO
    assert cabecera[1]["text"] == IDENTIDAD


def test_the_shared_block_is_closed_by_its_own_breakpoint() -> None:
    """Es lo que hace que se escriba **una vez para todos**, no una por teammate."""
    una = _with_prompt_caching(_turno(identidad="Eres Sofía…"), split_header=True)
    otra = _with_prompt_caching(_turno(identidad="Eres Nilo…"), split_header=True)

    assert una[0]["content"][0] == otra[0]["content"][0], (
        "el primer bloque y su corte tienen que ser idénticos entre teammates; "
        "si no, cada uno escribe su propia copia de lo compartido"
    )


def test_without_an_identity_there_is_exactly_one_breakpoint() -> None:
    """Quien habla con el Companion no paga ningún corte de más."""
    salida = _with_prompt_caching(_turno(identidad=None), split_header=True)

    assert _cortes(salida) == [0]


def test_the_mobile_breakpoint_still_works_on_top() -> None:
    """Son tres de los cuatro que admite el proveedor, no cuatro."""
    salida = _with_prompt_caching(_turno(identidad=IDENTIDAD), cache_tail=True, split_header=True)
    cola = salida[-1]["content"]

    assert len(_cortes(salida)) == 2
    assert isinstance(cola, list) and "cache_control" in cola[-1]


# ── R3.3 · qué cuesta de más el turno ───────────────────────────────────


def test_the_turn_grows_by_the_two_blocks_and_nothing_else() -> None:
    """El coste no es «no mucho»: es **exactamente** esos dos bloques.

    Se compara el mismo turno con y sin teammate. Si algún día alguien duplica
    el conocimiento, repite el contexto de página o mete un mensaje de más «ya
    que estamos», este test lo dice — y lo dice en caracteres, no en opinión.
    """
    from nexus_worker.runtime.companion.prompt import build_messages

    entorno = "Fecha y hora actuales…"
    sin = build_messages(history=None, user_message="hola", page_context=None)
    con = build_messages(
        history=None,
        user_message="hola",
        page_context=None,
        identity=IDENTIDAD + " " + entorno,
    )

    assert len(con) == len(sin) + 1, "un mensaje más, ni dos"
    crecimiento = sum(len(str(m["content"])) for m in con) - sum(
        len(str(m["content"])) for m in sin
    )
    assert crecimiento == len(IDENTIDAD + " " + entorno), (
        f"el turno creció {crecimiento} caracteres y los bloques nuevos ocupan "
        f"{len(IDENTIDAD + ' ' + entorno)}: algo más se coló"
    )


def test_off_by_default_nothing_changes_for_the_channel_agent() -> None:
    """El aviso estaba escrito en `llm.py` y me lo salté: el agente de cliente
    y los dos playgrounds comparten este proveedor y son **carga viva**.

    Partir la cabecera para todos habría cambiado el reparto de puntos de corte
    de tres agentes para arreglar un problema del Companion. Su propio test
    —`test_llm_resilience.py::TestPromptCaching`— lo cazó, que es exactamente
    para lo que estaba.
    """
    salida = _with_prompt_caching(_turno(identidad=IDENTIDAD))

    assert _cortes(salida) == [1], "sin pedirlo, un solo corte y en el último bloque"
