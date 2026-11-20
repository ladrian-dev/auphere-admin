"""Guardián de F1: el catálogo en código y ``model_profiles`` no divergen.

ADR-036 pone la verdad de los modelos en ``model_profiles``. ``HOP_MODEL_IDS``
es su espejo en código, para no consultar la BD en el camino caliente del hop.
Un espejo que nadie compara deja de ser un espejo: este test es la comparación.

Si falla, alguien sembró una fila y no la reflejó (o al revés). Las dos
direcciones importan:

- un id en la BD y no en el código → ese modelo se puede *elegir* y el hop lo
  rechaza con ``UnknownCatalogModel``, que nadie captura;
- un id en el código y no en la BD → el hop lo acepta y el emisor de consumo
  no sabe valorarlo.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.core.respond_catalog import HOP_MODEL_ID_SET, RESPOND_MODEL_ID_SET

pytestmark = pytest.mark.asyncio


async def test_hop_catalog_equals_active_model_profiles(db_session) -> None:
    rows = await db_session.execute(
        sa.text("SELECT model_id FROM model_profiles WHERE status = 'active'")
    )
    in_db = {row[0] for row in rows}
    assert in_db, "model_profiles vacía: las migraciones de catálogo no corrieron"

    solo_en_bd = in_db - HOP_MODEL_ID_SET
    solo_en_codigo = HOP_MODEL_ID_SET - in_db
    assert not solo_en_bd, (
        f"modelos activos en model_profiles que el hop rechazaría: {sorted(solo_en_bd)}"
    )
    assert not solo_en_codigo, (
        f"modelos en HOP_MODEL_IDS que no existen en model_profiles: {sorted(solo_en_codigo)}"
    )


async def test_la_oferta_es_subconjunto_del_catalogo(db_session) -> None:
    """Lo que la consola deja elegir tiene que poder ejecutarse."""
    rows = await db_session.execute(
        sa.text("SELECT model_id FROM model_profiles WHERE status = 'active'")
    )
    in_db = {row[0] for row in rows}
    assert RESPOND_MODEL_ID_SET <= HOP_MODEL_ID_SET
    assert in_db >= RESPOND_MODEL_ID_SET


async def test_lo_ofrecible_y_lo_ofrecido_salen_de_la_base(db_session) -> None:
    """Spec 065 (T008): la semilla de arranque coincide con lo que dejan las migraciones."""
    from nexus_api.core import respond_catalog
    from nexus_api.core.respond_profiles import profile_for

    rows = (
        await db_session.execute(
            sa.text(
                "SELECT model_id, respond_enabled_at FROM model_profiles "
                "WHERE offer_label IS NOT NULL AND status = 'active'"
            )
        )
    ).all()
    offerable = {r[0] for r in rows if profile_for(r[0]) is not None}
    offered = {r[0] for r in rows if r[0] in offerable and r[1] is not None}
    assert offerable == {m for m, _ in respond_catalog.BOOT_OFFERABLE}
    assert offered == {m for m, _ in respond_catalog.BOOT_OFFER}
    default = await respond_catalog.read_agent_default(db_session)
    assert default == respond_catalog.SOL_MODEL_ID, "al desplegar, Sol (CE-005)"
