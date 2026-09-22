"""Lo prometido y lo entregado no pueden separarse — spec 015, Requisito 4.

**Vive en `tests/isolation/` aunque no toque RLS**, y la razón es la misma por
la que está `test_33_teammate_catalog_is_subset.py` un paso más abajo: es la
costura del principio «la whitelist de herramientas es exhaustiva» —garantía
2—. Aquel vigila que el catálogo del teammate sea un subconjunto; éste vigila
que **lo que se le cuenta al teammate sea ese catálogo y no otro**.

**Por qué NO busca nombres de herramienta citados en el texto.** Era la forma
obvia y **se comprobó que da cero hallazgos**: el texto compartido cita tres
nombres —`console.apply`, `console.list_clients`, `console.propose_pack`— y los
tres existen. Un barrido así habría nacido en verde vigilando nada, que es
exactamente lo que le pasó al de la spec 012 hasta que se corrigió para buscar
la ruta compartida en vez de los símbolos de un lado.

Lo que sí caza, escrito antes que el diseño:

===============================================  ======
cambio futuro                                    mitad
===============================================  ======
añadir una herramienta sin describirla            (b)
mover una herramienta de familia                  (b)
añadir un interruptor sin ampliar el mapa         (b)
devolver prosa incondicional al prefijo           (a)
===============================================  ======
"""

from __future__ import annotations

import itertools
import re
from typing import Any

import pytest

from nexus_api.services.teammate_catalog import (
    _DESCRIBED_NAMES,
    _FAMILIES,
    _FAMILY_NAMES,
    MACHINE_TOOL,
    describe_for_teammate,
    for_teammate,
    permissions_to_tool_names,
)

pytestmark = [pytest.mark.isolation]

SWITCHES = ("read", "write", "publish", "spend", "contact")
MODES = ("build", "consult")


# ── mitad (a): el prefijo compartido no promete capacidades ─────────────

#: Formas de **afirmar** que se tiene algo. **Es un suelo, no un techo**: quien
#: invente una nueva y la meta en el prefijo la añade aquí, y el comentario
#: existe para que no la borre en su lugar.
#:
#: El ``(?<!No )`` no es cosmético y se ganó en la primera ejecución: sin él,
#: la puerta señalaba «**No** tienes acceso a las conversaciones de los clientes
#: finales», que es una **guarda** y no una promesa. Un test que empuja a
#: borrar una guarda para ponerse verde es peor que no tener test.
_AFIRMACIONES = (
    r"(?<!No )[Tt]ienes herramientas",
    r"(?<!No )[Tt]ienes acceso a",
    r"(?<!no )[Pp]uedes consultar el estado",
    r"(?<!No )[Dd]ispones de herramientas",
)


def test_the_shared_prefix_promises_no_capabilities() -> None:
    """Lo que el teammate puede hacer se lo dice **su** bloque, no el común.

    El prefijo es idéntico para todos los teammates y para el Companion. Toda
    afirmación de capacidad que viva aquí es falsa para alguien: hoy lo era
    para tres de las cinco combinaciones de interruptores.
    """
    from nexus_worker.runtime.companion.prompt import SYSTEM_PROMPT

    encontradas = [p for p in _AFIRMACIONES if re.search(p, SYSTEM_PROMPT)]

    assert not encontradas, (
        f"el prefijo compartido vuelve a prometer capacidades: {encontradas}. "
        "Lo que un teammate puede hacer depende de sus interruptores, de su modo "
        "y de si tiene máquina — el texto común no puede saberlo."
    )


def test_what_is_forbidden_for_everyone_stays_in_the_prefix() -> None:
    """La otra cara, y por eso este test existe: **no se vació el bloque**.

    Lo que nadie puede hacer nunca —borrar clientes, facturación, claves, la
    revelación de IA— sí es verdad para todos y no depende de ningún
    interruptor. Retirarlo «de paso» sería quitar una guarda creyendo que se
    quita una promesa.
    """
    from nexus_worker.runtime.companion.prompt import SYSTEM_PROMPT

    for guarda in ("borrar clientes", "facturación", "claves de API", "revelación de IA"):
        assert guarda in SYSTEM_PROMPT, f"desapareció del prefijo una prohibición global: {guarda}"


# ── mitad (b): lo descrito es lo entregado, en las 128 combinaciones ─────


class _Teammate:
    def __init__(self, perms: dict[str, bool], *, local_exec: bool) -> None:
        self.name = "X"
        self.job = "y"
        self.tool_names = permissions_to_tool_names(perms)
        self.local_exec = local_exec


def _combinaciones() -> list[tuple[dict[str, bool], str, bool]]:
    salida = []
    for bits in itertools.product((False, True), repeat=len(SWITCHES)):
        perms = dict(zip(SWITCHES, bits, strict=True))
        for mode, machine in itertools.product(MODES, (False, True)):
            salida.append((perms, mode, machine))
    return salida


COMBINACIONES = _combinaciones()


def test_the_sweep_actually_sweeps_the_whole_space() -> None:
    """2 elevado a 5 interruptores, por 2 modos, por 2 de máquina. Enteras."""
    assert len(COMBINACIONES) == 128


@pytest.mark.parametrize(("perms", "mode", "machine"), COMBINACIONES)
def test_the_description_matches_the_catalogue(
    perms: dict[str, bool], mode: str, machine: bool
) -> None:
    """Lo descrito y lo entregado, familia por familia, sobre el mismo objeto."""
    teammate: Any = _Teammate(perms, local_exec=machine)
    entregadas = set(for_teammate(teammate, mode=mode, machine_present=machine))
    texto = describe_for_teammate(teammate, mode=mode, machine_present=machine)
    puede = texto.split("No puedes:")[0]

    for key, etiqueta, _how in _FAMILIES:
        tiene = bool(entregadas & _FAMILY_NAMES[key])
        dicho = etiqueta in puede
        assert dicho == tiene, (
            f"familia {key!r} con perms={perms} mode={mode} machine={machine}: "
            f"el texto dice {dicho} y el catálogo entrega {tiene}"
        )

    tiene_maquina = MACHINE_TOOL in entregadas
    assert ("en la máquina de tu persona" in puede) == tiene_maquina


def test_every_tool_delivered_falls_into_a_described_family() -> None:
    """Si alguien añade una herramienta al catálogo y no la describe, cae aquí.

    Es el cambio que ocurrió de verdad el 2026-09-20 con ``shell_local``: entró
    en el catálogo y nadie revisó el prompt. Pasó inadvertido hasta que alguien
    fue a buscarlo.
    """
    # Se lee del módulo, no se reconstruye aquí: reconstruirlo sería una
    # segunda fuente, y entonces la puerta podría estar de acuerdo consigo
    # misma mientras el código dice otra cosa.
    cubiertas = set(_DESCRIBED_NAMES)

    todas: set[str] = set()
    for perms, mode, machine in COMBINACIONES:
        teammate: Any = _Teammate(perms, local_exec=machine)
        todas |= set(for_teammate(teammate, mode=mode, machine_present=machine))

    huerfanas = sorted(todas - cubiertas)
    assert not huerfanas, (
        f"estas herramientas se entregan y ninguna familia las describe: {huerfanas}. "
        "Amplía `_FAMILIES` y `_FAMILY_NAMES` en `services/teammate_catalog.py`."
    )


def test_each_family_is_exactly_what_its_switch_delivers() -> None:
    """El ancla independiente, y **la puerta no la tenía**.

    Lo destapó T024, que exige romperla a propósito: al mover una herramienta
    de familia, la puerta **pasaba en verde**. La razón es que sus dos mitades
    leían el mismo ``_FAMILY_NAMES`` —la descripción y la comprobación—, así
    que estaba de acuerdo consigo misma mientras el catálogo decía otra cosa.
    Un test que solo se compara consigo mismo no vigila nada; es la misma
    lección que la spec 012 pagó con un barrido que buscaba símbolos de un lado.

    El ancla es ``permissions_to_tool_names``, que es **quien decide de verdad**
    qué da cada interruptor. Lo que una familia describe tiene que ser
    exactamente lo que su interruptor entrega — ni una más, ni una menos.
    """
    from nexus_api.services.teammate_catalog import _APPLY_NAMES

    for switch in SWITCHES:
        entrega = set(permissions_to_tool_names({switch: True})) - _APPLY_NAMES
        describe = set(_FAMILY_NAMES[switch])

        assert entrega == describe, (
            f"el interruptor {switch!r} entrega {sorted(entrega - describe)} que su "
            f"familia no describe, y describe {sorted(describe - entrega)} que no "
            "entrega. Alguien movió una herramienta de familia sin mover su "
            "descripción."
        )


def test_every_switch_has_a_readable_name() -> None:
    """Un interruptor nuevo sin etiqueta produce una descripción sin nombre."""
    descritos = {key for key, _, _ in _FAMILIES}

    assert descritos == set(SWITCHES), (
        f"interruptores sin describir: {set(SWITCHES) - descritos}; "
        f"descritos que ya no existen: {descritos - set(SWITCHES)}"
    )
