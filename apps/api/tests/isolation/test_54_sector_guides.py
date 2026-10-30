"""Garantías 1 y 5 en las guías del sector (spec 047, enmienda del 2026-10-29, T201;
requisitos 58.4 y 58.5; D47 y D66).

- La guía generada para un cliente es **suya**: otro cliente con la misma etiqueta
  no la recibe; el constructor de ese otro cliente genera la suya.
- Lo que entra a generar una guía es la etiqueta y la guía genérica: nada de la
  ficha de ningún cliente.
- La guía convertida por Auphere vive en una tabla de plataforma **sin**
  ``tenant_id`` ni nada que apunte al cliente del que salió, y ``nexus_app`` solo
  la lee.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.base import get_sessionmaker
from nexus_api.services.builder.guides import generated, resolve

from .conftest import set_tenant

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

SECRET = "Gimnasio Secreto de B, llama al 699 000 111"


async def _as(tenant_id: uuid.UUID, sql: str, **params: object) -> list[object]:
    async with get_sessionmaker()() as session, session.begin():
        await set_tenant(session, tenant_id)
        result = await session.execute(sa.text(sql), params)
        return list(result.all()) if result.returns_rows else []


async def _profile(tenant_id: uuid.UUID, info: str) -> None:
    await _as(
        tenant_id,
        "INSERT INTO business_profiles (tenant_id, niche, info, timezone, sector) VALUES "
        "(:t, 'Gimnasio', :i, 'Europe/Madrid', CAST(:s AS jsonb))",
        t=tenant_id,
        i=info,
        s='{"key": "otro", "label": "Gimnasio", "confidence": 0.9, "source": "niche", '
        '"decided_by": "system"}',
    )


async def test_a_generated_guide_never_reaches_another_client(tenants_ab) -> None:
    a, b = tenants_ab["a"], tenants_ab["b"]
    await _profile(a, "Gimnasio de A")
    await _profile(b, SECRET)
    await _as(
        b,
        "INSERT INTO generated_guides (tenant_id, sector_label, label_key, guide, tests) "
        "VALUES (:t, 'Gimnasio', 'gimnasio', CAST(:g AS jsonb), '[]'::jsonb)",
        t=b,
        g='{"ask": ["' + SECRET + '"], "procedures": [], "risks": [], "tools": []}',
    )
    async with get_sessionmaker()() as session, session.begin():
        await set_tenant(session, a)
        with tenant_context(a):
            found = await resolve.for_client(session)
    assert found is not None and found.source == "missing", "la de B no es de A"
    assert found.guide is None
    text = "\n".join(m["content"] for m in generated.generation_messages(found.label))
    assert "Secreto" not in text and "699" not in text and "Gimnasio de A" not in text


async def test_a_converted_guide_points_at_no_client() -> None:
    async with get_sessionmaker()() as session, session.begin():
        columns = {
            row[0]
            for row in await session.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'sector_guides'"
                )
            )
        }
        grants = {
            row[0]
            for row in await session.execute(
                sa.text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_name = 'sector_guides' AND grantee = 'nexus_app'"
                )
            )
        }
    assert columns and not {c for c in columns if "tenant" in c or "client" in c}
    assert grants == {"SELECT"}, "solo el panel la escribe"


async def test_the_sector_test_catalog_is_only_read_by_the_app() -> None:
    """Spec 047, T217 (revisión de seguridad del 2026-10-30): las pruebas del sector
    (``sector_test_catalog``, de plataforma) entran en la suite de cada cliente del
    sector. La 0187 le dio a ``nexus_app`` escribirlas; desde la 0210 solo las lee,
    como ``sector_guides``: las publica el panel con el rol de la plataforma."""
    async with get_sessionmaker()() as session, session.begin():
        grants = {
            row[0]
            for row in await session.execute(
                sa.text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_name = 'sector_test_catalog' AND grantee = 'nexus_app'"
                )
            )
        }
    assert grants == {"SELECT"}, grants
