"""Garantía 2 — la lista blanca de la superficie 3a es exhaustiva y por tenant.

Sigue el mismo reparto que ``test_2_tool_whitelist_contract``: aquí se fija el
**contrato de datos** en el que se apoyará el runtime, y la comprobación del catálogo
en vivo llega con la US4 (tareas T019-T022), que es quien construye el servidor MCP y
el envoltorio. Lo que se puede comprobar hoy se comprueba hoy.

**Un punto abierto, escrito aquí para que no se pierda.** El Requisito 5.4 dice que
el catálogo del teammate lo configura únicamente Auphere y que el partner no puede
añadir herramientas «ni desde su máquina ni desde la consola». Hoy
``console/agents.py`` **sí** deja al partner fijar ``tools`` — pero de *su agente de
cliente final*, que no es el teammate. Si la US4 sirviera el catálogo del teammate
desde ese mismo campo, R5.4 quedaría incumplido. La US4 tiene que elegir
explícitamente de dónde sale el catálogo del teammate, y este comentario es el
recordatorio de que es una elección y no un detalle.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from nexus_api.core.console_auth import PERMISSIONS, permissions_for
from nexus_api.db.models import LocalExecutable

from .conftest import set_tenant

pytestmark = [pytest.mark.isolation]


@pytest.mark.asyncio
async def test_the_allowlist_starts_empty_for_a_new_tenant(db_session, tenants_ab):
    """No hay ejecutables por defecto. Un default global sería el "global" que §I prohíbe."""
    await set_tenant(db_session, tenants_ab["a"])
    count = (await db_session.execute(select(func.count()).select_from(LocalExecutable))).scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_an_archived_executable_is_no_longer_active(db_session, tenants_ab):
    """Borrar no existe: se archiva, y lo archivado deja de contar como permitido."""
    from datetime import UTC, datetime

    row = LocalExecutable(
        id=uuid.uuid4(), tenant_id=tenants_ab["a"], executable="make", added_by="tester"
    )
    db_session.add(row)
    await db_session.commit()

    await set_tenant(db_session, tenants_ab["a"])
    active = (
        (
            await db_session.execute(
                select(LocalExecutable).where(LocalExecutable.removed_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    assert [r.executable for r in active] == ["make"]

    row.removed_at = datetime.now(UTC)
    await db_session.flush()
    active = (
        (
            await db_session.execute(
                select(LocalExecutable).where(LocalExecutable.removed_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    assert active == []


def test_writing_the_allowlist_is_not_a_configuration_role():
    """Añadir un ejecutable es una decisión de seguridad (Requisito 2.1).

    Si el rol que configura el día a día pudiera ampliarla, la lista blanca dejaría de
    ser una garantía: lo que no se puede aprobar en caliente tampoco debería poder
    añadirlo quien toca la configuración.
    """
    assert "workstation:write" in PERMISSIONS
    assert "workstation:write" not in permissions_for("builder")
    assert "workstation:write" not in permissions_for("analyst")
    assert "workstation:read" in permissions_for("builder")


def test_reading_and_writing_are_separate_permissions():
    assert PERMISSIONS["workstation:write"] < PERMISSIONS["workstation:read"]
