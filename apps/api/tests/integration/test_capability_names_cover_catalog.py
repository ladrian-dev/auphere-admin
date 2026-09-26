"""Spec 017 (R5.1): el mapa de nombres cubre **todo** el catálogo sembrado.

El catálogo de herramientas no vive en un fichero: se siembra por
migraciones, y hoy son 48. Este test lee la base, que es la única fuente que
no se desfasa, y exige que cada herramienta tenga su nombre de negocio.

Así, el día que una migración añada una herramienta, esto se pone rojo y
alguien tiene que decidir cómo se llama en la pantalla — en vez de que un
partner se encuentre `orders.cancel` y tenga que adivinar.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.api.console.capability_names import CAPABILITY_NAMES

pytestmark = pytest.mark.asyncio


async def test_every_seeded_tool_has_a_business_name(db_session) -> None:
    names = (await db_session.execute(sa.text("SELECT name FROM tool_catalog"))).scalars().all()
    assert names, "el catálogo está vacío: la siembra no corrió"

    sin_nombre = sorted(n for n in names if ("tool", n) not in CAPABILITY_NAMES)
    assert not sin_nombre, (
        "estas herramientas se le enseñarían al partner con su nombre técnico: "
        + ", ".join(sin_nombre)
    )


# Deliberadamente NO se comprueba lo contrario —que el mapa no nombre nada
# que falte en la base—, porque el catálogo no es uno solo: las migraciones
# siembran unas herramientas y `scripts/seed_connectors.py` otras, así que un
# entorno con menos herramientas es normal, no un error. Una entrada de más
# es copy sin usar; una de menos es un partner leyendo `orders.cancel`.
