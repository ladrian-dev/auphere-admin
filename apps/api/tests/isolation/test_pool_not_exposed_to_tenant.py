"""Spec 004 · puerta de aislamiento — el cliente final no ve nada de esto.

R4.6 / D6. La respuesta esperada es «nada», y el punto de este fichero es que
eso se **pruebe** en vez de afirmarse.

Estructuralmente ya es difícil que se filtre: el libro, el pool y los topes
viven en tablas **de partner o de plataforma** —``partner_wallets``,
``usage_ledger``, ``partner_allocations``, ``partners``, ``model_profiles``— y
ninguna lleva ``tenant_id``. No hay que quitarle un permiso a nadie: es que no
hay puerta.

Lo que este test guarda es que nadie abra una. Copia el patrón estructural que
CP-21 ya usa sobre el esquema OpenAPI para el contenido de conversación.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

#: Nombres que delatan una fuga del plano económico al plano de cliente final.
FORBIDDEN = (
    "weekly_pool_tokens",
    "included_remaining",
    "purchased_remaining",
    "quota_weight",
    # Spec 007 — los tres pesos por carril. Se añaden aquí el mismo día que
    # existen: una lista de nombres prohibidos que se actualiza «luego» es una
    # lista que protege el esquema de hace seis meses.
    "quota_weight_input",
    "quota_weight_cache_read",
    "quota_weight_output",
    "pool_size",
    "included_percent_used",
    "companion_monthly_token_cap",
    "price_input_per_mtok",
    "price_output_per_mtok",
)

#: Prefijos de ruta orientados a cliente final o a su plano de datos.
TENANT_FACING = ("/webhook", "/v1/embed")


def _paths_of(schema: dict, prefixes: tuple[str, ...]) -> list[str]:
    return [p for p in schema.get("paths", {}) if p.startswith(prefixes)]


async def test_no_tenant_facing_endpoint_names_the_economic_plane(client) -> None:
    res = await client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()

    paths = _paths_of(schema, TENANT_FACING)
    assert paths, "no se encontró ninguna ruta de cliente final: el test no prueba nada"

    import json

    for path in paths:
        blob = json.dumps(schema["paths"][path])
        for name in FORBIDDEN:
            assert name not in blob, (
                f"{path} menciona «{name}». El pool, el saldo y los precios son del "
                "plano del PARTNER; un endpoint de cliente final no puede nombrarlos"
            )


async def test_the_forbidden_scan_actually_catches_a_leak() -> None:
    """Que la lista vigile, y no sólo que exista.

    El caso de arriba pasa tanto si ningún endpoint nombra el plano económico
    como si el barrido estuviera roto —un ``json.dumps`` sobre el objeto
    equivocado, un prefijo que ya no casa— y las dos cosas se ven igual desde
    fuera: verde. Esto le da un esquema sintético que **sí** filtra y comprueba
    que lo encuentra.

    Se añade con la spec 007, al descubrir que el test del suelo pasaba en verde
    con el invariante roto porque miraba donde no era.
    """
    import json

    leaky = {"paths": {"/webhook/x": {"get": {"responses": {"200": {"quota_weight_output": 1}}}}}}
    paths = _paths_of(leaky, TENANT_FACING)
    assert paths == ["/webhook/x"], "el barrido no encuentra ni la ruta"
    blob = json.dumps(leaky["paths"]["/webhook/x"])
    assert any(name in blob for name in FORBIDDEN), (
        "la lista FORBIDDEN no detecta una fuga evidente: el caso de al lado "
        "estaría pasando por vacío"
    )


async def test_the_economic_tables_have_no_tenant_column(db_session) -> None:
    """La razón por la que no hay puerta, comprobada y no supuesta."""
    import sqlalchemy as sa

    for table in ("partner_wallets", "partners", "model_profiles"):
        cols = {
            r[0]
            for r in (
                await db_session.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
                    ),
                    {"t": table},
                )
            ).all()
        }
        assert "tenant_id" not in cols, (
            f"{table} ganó un tenant_id: eso abre una superficie por la que el plano "
            "económico del partner puede alcanzar a un cliente final"
        )


async def test_the_ledger_keeps_its_tenant_only_as_attribution(db_session) -> None:
    """``usage_ledger`` sí tiene ``tenant_id``, y es correcto: sirve para saber
    a qué cliente se imputó un débito. Lo que no puede es dejar de tener
    ``partner_id``, que es por donde la RLS lo alcanza."""
    import sqlalchemy as sa

    cols = {
        r[0]
        for r in (
            await db_session.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'usage_ledger'"
                )
            )
        ).all()
    }
    assert "partner_id" in cols
    assert "tenant_id" in cols
