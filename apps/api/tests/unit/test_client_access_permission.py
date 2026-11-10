"""Spec 056, T007 — quién abre la consola a su cliente (requisito 3.2, D4).

``client_access:manage`` lo tienen owner y admin, y nadie más: encender la
consola del cliente e invitar a sus personas da a alguien de fuera del partner
la Bandeja del cliente (el riesgo que el owner aceptó en D3). El builder hace
agentes y canales, no da acceso; por eso no vale ``clients:write``.

La copia de la consola (``apps/console/src/lib/permissions.ts``) la vigila
``apps/console/src/lib/__tests__/permissions.test.ts``.
"""

from __future__ import annotations

from nexus_api.core.console_auth import PERMISSIONS, permissions_for


def test_only_owner_and_admin_manage_the_client_access() -> None:
    assert PERMISSIONS["client_access:manage"] == frozenset({"owner", "admin"})
    assert "client_access:manage" in permissions_for("owner")
    assert "client_access:manage" in permissions_for("admin")
    for role in ("builder", "analyst", "billing"):
        assert "client_access:manage" not in permissions_for(role)


def test_it_is_not_the_same_door_as_editing_clients() -> None:
    # El builder edita clientes y agentes, pero no da acceso a la consola (D4).
    assert "builder" in PERMISSIONS["clients:write"]
    assert PERMISSIONS["client_access:manage"] < PERMISSIONS["clients:write"]
