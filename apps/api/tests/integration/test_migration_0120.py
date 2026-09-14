"""Spec 007 · los tres pesos por carril en el catálogo (migración 0120).

Integración y no unidad por lo mismo que la 0116: lo que se comprueba es el
**esquema real**. Los ``CHECK``, la escala de la columna y las filas sembradas
sólo existen en Postgres; un test de unidad sobre el modelo SQLAlchemy diría que
todo está bien contra una base que no tiene ninguna de las tres cosas.

Lo que más se vigila aquí es lo que **no** se ve: que ampliar la resolución de
``NUMERIC(6,3)`` a ``NUMERIC(12,6)`` **no mueva por su cuenta** un peso que ya
cabía (R2.5). Esto corre sobre una base con tres clientes con tráfico, y un
cambio de escala que redondea de más es exactamente la clase de defecto que
nadie mira hasta que cuadra una factura.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

#: El objetivo y el suelo viven en el contrato, no en el test.
TARGET = Decimal("2.2")
FLOOR = Decimal("1.50")
SELL_USD_PER_MILLION = Decimal(10)

_LANES = (
    ("quota_weight_input", "price_input_per_mtok"),
    ("quota_weight_cache_read", "price_cache_read_per_mtok"),
    ("quota_weight_output", "price_output_per_mtok"),
)


async def _columns(conn: sa.ext.asyncio.AsyncConnection, table: str) -> dict[str, dict]:
    rows = (
        await conn.execute(
            sa.text(
                """
                SELECT column_name, data_type, is_nullable,
                       numeric_precision, numeric_scale
                  FROM information_schema.columns
                 WHERE table_name = :t
                """
            ),
            {"t": table},
        )
    ).mappings()
    return {r["column_name"]: dict(r) for r in rows}


async def test_the_three_lane_columns_exist_with_the_price_scale() -> None:
    """R1.1, R2.4 — tres columnas, y con la MISMA escala que las tarifas.

    El peso *es* una tarifa reescalada. Con tres decimales, el carril de caché
    de ``openai/gpt-5.6-luna`` vale 0,0044 y se guardaría como 0,004 — 2,00x en
    vez de 2,20x. Sigue sobre el suelo, pero el siguiente modelo más barato
    puede no estarlo.
    """
    async with get_sessionmaker()() as s:
        cols = await _columns(await s.connection(), "model_profiles")
        for weight_col, price_col in _LANES:
            assert weight_col in cols, f"falta la columna {weight_col}"
            assert cols[weight_col]["is_nullable"] == "YES"
            assert (
                cols[weight_col]["numeric_precision"],
                cols[weight_col]["numeric_scale"],
            ) == (
                cols[price_col]["numeric_precision"],
                cols[price_col]["numeric_scale"],
            ), f"{weight_col} no tiene la escala de {price_col}"


async def test_quota_weight_survives_the_migration() -> None:
    """La columna vieja NO se borra aquí: el ``downgrade()`` tiene que poder
    devolver los datos (patrón de la 0115 con ``companion_monthly_token_cap``).
    La elimina una migración posterior, cuando el despliegue lleve un ciclo."""
    async with get_sessionmaker()() as s:
        cols = await _columns(await s.connection(), "model_profiles")
        assert "quota_weight" in cols, "quota_weight no puede desaparecer en esta migración"


async def test_every_servable_model_is_seeded_from_its_own_price() -> None:
    """R1.2 — el peso sembrado es ``2,2 x precio_del_carril / 10``.

    Se comprueba **contra la tarifa de la propia fila**, no contra una lista
    escrita en el test: una lista pasa en verde el día que alguien añade un
    modelo y no la actualiza, que es justo el fallo que hay que impedir.
    """
    async with get_sessionmaker()() as s:
        rows = (
            (
                await s.execute(
                    sa.text(
                        "SELECT model_id, price_input_per_mtok, price_cache_read_per_mtok,"
                        "       price_output_per_mtok, quota_weight_input,"
                        "       quota_weight_cache_read, quota_weight_output, quota_weight"
                        "  FROM model_profiles"
                    )
                )
            )
            .mappings()
            .all()
        )
        assert rows, "el catálogo está vacío: el test pasaría por vacío"

        servable = [r for r in rows if r["quota_weight"] is not None]
        assert servable, "ningún modelo tenía peso antes: no hay nada que migrar"

        for row in servable:
            for weight_col, price_col in _LANES:
                price, weight = row[price_col], row[weight_col]
                assert price is not None, f"{row['model_id']}: sin tarifa en {price_col}"
                assert weight is not None, f"{row['model_id']}: sin peso en {weight_col}"
                expected = (TARGET * Decimal(price) / SELL_USD_PER_MILLION).quantize(
                    Decimal(1).scaleb(-6)
                )
                assert Decimal(weight) == expected, (
                    f"{row['model_id']}.{weight_col}: {weight} != {expected}"
                )


async def test_widening_the_scale_did_not_move_a_weight_that_already_fitted() -> None:
    """R2.5 — ampliar la resolución no puede cambiar por su cuenta lo que nadie
    decidió cambiar.

    Todo peso cuyo valor exacto ya cabía en tres decimales tiene que valer lo
    mismo con seis. El caso que lo hace no trivial es el contrario —la caché de
    luna, 0,0044, que NO cabía— y ése tiene que haber ganado precisión.
    """
    async with get_sessionmaker()() as s:
        rows = (
            (
                await s.execute(
                    sa.text(
                        "SELECT model_id, price_cache_read_per_mtok, quota_weight_cache_read"
                        "  FROM model_profiles WHERE quota_weight IS NOT NULL"
                    )
                )
            )
            .mappings()
            .all()
        )
        assert rows

        checked = 0
        for row in rows:
            exact = TARGET * Decimal(row["price_cache_read_per_mtok"]) / SELL_USD_PER_MILLION
            stored = Decimal(row["quota_weight_cache_read"])
            if exact == exact.quantize(Decimal("0.001")):
                assert stored == exact, (
                    f"{row['model_id']}: cabía en 3 decimales y se movió ({stored} != {exact})"
                )
                checked += 1
        assert checked, "ningún peso cabía en 3 decimales: el test pasó por vacío"


async def test_a_model_outside_the_llm_quota_lane_keeps_working_without_weights() -> None:
    """R1.7 — ``openai/whisper-1`` se mide por minutos, no pasa por la cuota, y
    **sigue en el catálogo** con los tres pesos a NULL. No es «peso 1»."""
    async with get_sessionmaker()() as s:
        row = (
            (
                await s.execute(
                    sa.text(
                        "SELECT quota_weight, quota_weight_input, quota_weight_cache_read,"
                        "       quota_weight_output, price_per_minute"
                        "  FROM model_profiles WHERE model_id = 'openai/whisper-1'"
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        assert row is not None, "whisper-1 desapareció del catálogo"
        assert row["quota_weight"] is None
        for col in ("quota_weight_input", "quota_weight_cache_read", "quota_weight_output"):
            assert row[col] is None, f"whisper-1 no debe tener {col}"


async def test_the_three_or_none_check_refuses_a_half_weighted_model() -> None:
    """R1.1, R1.6 — un modelo con dos pesos y uno nulo no es «medio servible»:
    es un error de configuración, y el esquema lo rechaza."""
    async with get_sessionmaker()() as s:
        with pytest.raises(IntegrityError):
            async with s.begin():
                await s.execute(
                    sa.text(
                        "INSERT INTO model_profiles"
                        " (provider, model_id, display_name, quota_weight_input,"
                        "  quota_weight_cache_read, quota_weight_output)"
                        " VALUES ('test', 'test/half-weighted', 'Half', 0.5, 0.05, NULL)"
                    )
                )


async def test_a_non_positive_weight_is_refused() -> None:
    """R1.1 — mismo criterio que el ``CHECK`` que ``quota_weight`` ya tenía."""
    async with get_sessionmaker()() as s:
        with pytest.raises(IntegrityError):
            async with s.begin():
                await s.execute(
                    sa.text(
                        "INSERT INTO model_profiles"
                        " (provider, model_id, display_name, quota_weight_input,"
                        "  quota_weight_cache_read, quota_weight_output)"
                        " VALUES ('test', 'test/zero-weight', 'Zero', 0, 0.05, 1.0)"
                    )
                )
