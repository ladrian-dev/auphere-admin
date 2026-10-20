"""Spec 031 · R3.1, R3.2 — ``/me.nav``: una sola fuente del orden (tarea T011).

La consola web y la app pintan las pestañas en el orden que dice la API, y la
API lo saca de ``ClientAccess.ordered_modules()``. Ninguna de las dos lo
reescribe; si alguien añade un módulo, el orden se decide aquí y en ningún otro
sitio.
"""

from __future__ import annotations

import itertools
import uuid

import pytest

from nexus_api.db.models import CLIENT_MODULES, ClientAccess


@pytest.mark.parametrize(
    "stored",
    [
        list(p)
        for n in range(1, 4)
        for c in itertools.combinations(CLIENT_MODULES, n)
        for p in itertools.permutations(c)
    ],
)
def test_nav_is_the_bar_order_whatever_the_stored_order(stored: list[str]) -> None:
    access = ClientAccess(tenant_id=uuid.uuid4(), partner_id=uuid.uuid4(), modules=stored)

    nav = access.ordered_modules()

    assert list(nav) == [m for m in CLIENT_MODULES if m in stored]


def test_the_bar_order_is_panel_inbox_usage() -> None:
    assert CLIENT_MODULES == ("panel", "inbox", "usage")
