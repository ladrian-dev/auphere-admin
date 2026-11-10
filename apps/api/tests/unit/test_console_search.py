"""Spec 047, T008 — ⌘K: qué pantallas y qué acciones ve cada persona (requisito 47.2).

Las pantallas y las acciones de ``GET /console/search`` viajan como **claves**;
los textos son de la consola. Aquí se fija el filtro, que es el mismo que el de
la navegación de hoy (``apps/console/src/components/shell/nav.ts``): el módulo
que Auphere dio al partner (spec 032) **y** el permiso del rol de la persona.
Una acción que la persona no puede hacer no aparece (§V).
"""

from __future__ import annotations

import pytest

from nexus_api.api.console.search import (
    ACTIONS,
    SCREENS,
    allowed_actions,
    allowed_screens,
    search_needle,
)
from nexus_api.core.console_auth import PERMISSIONS
from nexus_api.db.models import PARTNER_MODULES

ALL = tuple(PARTNER_MODULES)


def _keys(hits: list[object]) -> list[str]:
    return [h.key for h in hits]  # type: ignore[attr-defined]


def test_the_screens_and_their_addresses() -> None:
    assert [(s.key, s.href) for s in SCREENS] == [
        ("home", "/"),
        ("clients", "/clients"),
        ("usage", "/usage"),
        ("audit", "/audit"),
        ("knowledge", "/knowledge"),
        ("workstation", "/workstation"),
        ("team", "/team"),
        ("billing", "/billing"),
        ("keys", "/keys"),
        ("notifications", "/notifications"),
    ]


def test_the_actions_and_their_addresses() -> None:
    assert [(a.key, a.href) for a in ACTIONS] == [
        ("new_client", "/clients/new"),
        ("invite_member", "/team?invite=1"),
        ("new_api_key", "/keys?new=1"),
    ]


def test_every_permission_named_is_a_real_one() -> None:
    for entry in (*SCREENS, *ACTIONS):
        assert entry.permission is None or entry.permission in PERMISSIONS
        assert entry.module is None or entry.module in PARTNER_MODULES


def test_an_owner_with_the_whole_console_sees_everything() -> None:
    assert _keys(allowed_screens("owner", ALL)) == [s.key for s in SCREENS]
    assert _keys(allowed_actions("owner", ALL)) == ["new_client", "invite_member", "new_api_key"]


@pytest.mark.parametrize(
    ("role", "screens", "actions"),
    [
        (
            "admin",
            [
                "home",
                "clients",
                "usage",
                "audit",
                "knowledge",
                "workstation",
                "team",
                "keys",
                "notifications",
            ],
            ["new_client", "invite_member", "new_api_key"],
        ),
        (
            "builder",
            [
                "home",
                "clients",
                "usage",
                "knowledge",
                "workstation",
                "team",
                "keys",
                "notifications",
            ],
            ["new_client"],
        ),
        (
            "analyst",
            [
                "home",
                "clients",
                "usage",
                "audit",
                "knowledge",
                "workstation",
                "team",
                "notifications",
            ],
            [],
        ),
        ("billing", ["home", "usage", "team", "billing", "notifications"], []),
    ],
)
def test_each_role_sees_only_what_it_may_open_and_do(
    role: str, screens: list[str], actions: list[str]
) -> None:
    assert _keys(allowed_screens(role, ALL)) == screens
    assert _keys(allowed_actions(role, ALL)) == actions


def test_a_module_auphere_did_not_give_hides_its_screen_and_its_actions() -> None:
    modules = tuple(m for m in ALL if m not in ("team", "keys", "panel"))
    screens = _keys(allowed_screens("owner", modules))
    assert "team" not in screens
    assert "keys" not in screens
    assert "home" not in screens
    assert _keys(allowed_actions("owner", modules)) == ["new_client"]


def test_notifications_are_always_there() -> None:
    # The bell is not a module (spec 032): every member reaches it.
    for role in ("owner", "admin", "builder", "analyst", "billing"):
        assert "notifications" in _keys(allowed_screens(role, ()))


@pytest.mark.parametrize(
    ("q", "needle"),
    [("  Recep ", "Recep"), ("", None), ("   ", None), (None, None)],
)
def test_the_needle_is_the_trimmed_query(q: str | None, needle: str | None) -> None:
    assert search_needle(q) == needle
