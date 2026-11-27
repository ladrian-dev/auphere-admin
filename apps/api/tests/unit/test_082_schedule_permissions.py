"""Quién puede poner a un agente a gastar solo — spec 082, T011 (requisito 11).

Una rutina es una instrucción para un agente, así que leer y escribir rutinas
van con los mismos roles que leer y escribir agentes. Son permisos aparte y no
un alias de ``agents:*`` para poder separarlos más adelante sin migración, que
es como se hace en esta casa: añadir un permiso es añadir una fila.

La copia de la consola (``apps/console/src/lib/permissions.ts``) la vigila
``apps/console/src/lib/__tests__/permissions.test.ts``.
"""

from __future__ import annotations

from nexus_api.core.console_auth import PERMISSIONS, permissions_for


def test_reading_routines_goes_with_reading_agents() -> None:
    assert PERMISSIONS["schedules:read"] == PERMISSIONS["agents:read"]
    for role in ("owner", "admin", "builder", "analyst"):
        assert "schedules:read" in permissions_for(role)
    assert "schedules:read" not in permissions_for("billing")


def test_writing_routines_goes_with_writing_agents() -> None:
    assert PERMISSIONS["schedules:write"] == PERMISSIONS["agents:write"]
    for role in ("owner", "admin", "builder"):
        assert "schedules:write" in permissions_for(role)
    for role in ("analyst", "billing"):
        assert "schedules:write" not in permissions_for(role)


def test_they_are_their_own_permissions_not_an_alias() -> None:
    """Si un día una rutina deja de ser cosa del builder, se cambia una fila."""
    assert "schedules:read" in PERMISSIONS
    assert "schedules:write" in PERMISSIONS
