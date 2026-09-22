"""Lo que el teammate lee sobre sí mismo — spec 015, Requisito 2.

**El defecto que esto cierra, medido.** El texto compartido con el Companion
afirmaba sin condición «Tienes herramientas de lectura sobre la consola… Y
tienes herramientas de propuesta…». Contando lo que cada combinación de
interruptores entrega de verdad, eso era **falso en tres de las cinco**:

===================  =======  ==========
interruptor          `build`  `consult`
===================  =======  ==========
solo leer                 26          26
**solo publicar**        **2**      **0**
solo gastar                3           0
solo contactar             4           0
leer + escribir           37          26
===================  =======  ==========

Y al revés: ``shell_local`` no aparecía en ninguna de las 89 líneas del prompt,
ni siquiera cuando el teammate tenía máquina.

La descripción sale de ``for_teammate``, no de una lista aparte: que existan dos
formas de contestar «qué tiene este teammate» **es** el defecto.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.services.teammate_catalog import (
    describe_for_teammate,
    permissions_to_tool_names,
)


class _Teammate:
    def __init__(self, permissions: dict[str, Any], *, local_exec: bool = False) -> None:
        self.name = "Sofía"
        self.job = "revisora"
        self.tool_names = permissions_to_tool_names(permissions)
        self.local_exec = local_exec


def _describe(permissions: dict[str, Any], *, mode: str = "build", machine: bool = False) -> str:
    return describe_for_teammate(
        _Teammate(permissions, local_exec=machine), mode=mode, machine_present=machine
    )


# ── lo que tiene ────────────────────────────────────────────────────────


def test_a_teammate_that_can_only_publish_is_not_told_it_can_read() -> None:
    """El caso que más duele: dos herramientas y un prompt que prometía 26."""
    texto = _describe({"publish": True})

    assert "publicar" in texto
    assert "leer el estado de la consola" not in texto.split("No puedes:")[0]
    assert "No puedes:" in texto
    assert "«Leer»" in texto, "tiene que decir QUÉ daría las lecturas, no solo que faltan"


def test_what_is_missing_says_what_would_give_it() -> None:
    texto = _describe({"read": True})

    assert "«Publicar»" in texto
    assert "«Gastar»" in texto
    assert "«Invitar y pedir ayuda»" in texto


def test_the_machine_is_named_when_it_is_there() -> None:
    """Hoy no se nombra nunca, ni cuando la tiene."""
    con = _describe({"read": True, "write": True}, machine=True)
    sin = _describe({"read": True, "write": True}, machine=False)

    assert "ejecutar programas en la máquina" in con
    assert "ejecutar programas en la máquina" not in sin


def test_the_machine_is_not_offered_as_a_switch() -> None:
    """Mandar a alguien a «activar un interruptor» que no existe es peor que callar."""
    sin = _describe({"read": True})

    assert "vincular una máquina" in sin
    assert "interruptor" not in sin.split("ejecutar en una máquina")[1].split(")")[0]


# ── el caso de cero herramientas, que existe ────────────────────────────


def test_zero_tools_is_said_out_loud_and_has_a_way_out() -> None:
    """Publicar-en-consulta entrega **cero**, y hoy el teammate se calla.

    La ``<regla_madre>`` del prompt compartido le ordena no afirmar lo que no ha
    leído. A un teammate sin lecturas eso es callarse del todo, sin que sepa por
    qué. La salida vive aquí —en el bloque por teammate— y no en el prefijo,
    porque el prefijo es compartido y esto le pasa solo a algunos.
    """
    texto = _describe({"publish": True}, mode="consult")

    assert "NO tienes ninguna herramienta" in texto
    assert "no te quedes callado" in texto.lower()


def test_without_reads_it_is_told_not_to_assert_and_why() -> None:
    texto = _describe({"publish": True})

    assert "Sin lecturas no puedes comprobar nada" in texto


# ── la única fuente ─────────────────────────────────────────────────────


@pytest.mark.parametrize("mode", ["build", "consult"])
@pytest.mark.parametrize(
    "permissions",
    [
        {"read": True},
        {"publish": True},
        {"spend": True},
        {"contact": True},
        {"read": True, "write": True},
    ],
)
def test_the_description_never_claims_a_family_it_does_not_have(
    permissions: dict[str, Any], mode: str
) -> None:
    """Lo afirmado y lo entregado, comparados sobre el mismo objeto."""
    from nexus_api.services.teammate_catalog import for_teammate

    teammate = _Teammate(permissions)
    entregadas = set(for_teammate(teammate, mode=mode, machine_present=False))
    texto = describe_for_teammate(teammate, mode=mode, machine_present=False)

    puede = texto.split("No puedes:")[0]
    from nexus_api.services.teammate_catalog import _FAMILY_NAMES

    for key, nombres in _FAMILY_NAMES.items():
        tiene = bool(entregadas & nombres)
        etiqueta = {
            "read": "leer el estado de la consola",
            "write": "preparar cambios",
            "publish": "publicar una versión",
            "spend": "mover consumo",
            "contact": "invitar a alguien",
        }[key]
        assert (etiqueta in puede) is tiene, (
            f"{key}: el texto dice {etiqueta in puede} y el catálogo dice {tiene}"
        )
