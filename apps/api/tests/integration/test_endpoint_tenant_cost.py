"""Coste por tenant / mes / versión de agente (WP-22, mitad backend).

Integración y no unit porque lo que hay que probar es la consulta contra
la tabla real: ``usage_records`` está particionada por mes y tiene RLS
ENABLE + FORCE, y las dos cosas pueden hacer que el endpoint devuelva
cero sin dar ningún error.

El test que más importa es el de las filas sin precio. ``SUM(cost_usd)``
ignora los NULL, así que un mes medido pero sin valorar devuelve una
cifra pequeña y perfectamente creíble. Si el panel de margen se construye
sobre eso, el error no se descubre nunca: sale un margen mejor del real y
nadie tiene motivo para dudar de él.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa

from nexus_api.api.admin.cost import _first_of_month_n_back
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Tenant,
    TenantPlan,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _tenant_with_agent(db_session) -> tuple[uuid.UUID, uuid.UUID, int]:
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Coste",
            slug=f"cost-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()
    config = AgentConfig(
        tenant_id=tenant_id,
        version=7,
        status=AgentConfigStatus.ACTIVE,
        system_prompt_rendered="Eres un asistente de prueba.",
        channels=[],
        tools=[],
        policies={},
        created_by="test",
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    return tenant_id, config.id, config.version


async def _usage(
    tenant_id: uuid.UUID,
    agent_config_id: uuid.UUID | None,
    *,
    cost: str | None,
    occurred_at: datetime,
    meter: str = "llm.input_tokens",
) -> None:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        # No se confía en las particiones que dejó la 0064: en una base
        # recién migrada el mes de hace cuatro puede no existir y el
        # INSERT fallaría con "no partition of relation found" — un rojo
        # que aparecería solo en CI y solo algunos meses.
        #
        # Solo se crea si falta: ``ensure_month_partition`` re-aplica
        # ALTER sobre la partición existente y eso exige ser su dueño, que
        # el rol de test no es.
        month = occurred_at.date().replace(day=1)
        name = f"usage_records_y{month.year}m{month.month:02d}"
        exists = await session.scalar(
            sa.text("SELECT 1 FROM pg_class WHERE relname = :n"), {"n": name}
        )
        if not exists:
            await session.execute(
                sa.text("SELECT ensure_month_partition('usage_records', :m)"),
                {"m": month},
            )
        await session.execute(
            sa.text(
                """
                INSERT INTO usage_records
                    (tenant_id, occurred_at, meter, quantity, billable_qty,
                     cost_usd, model, agent_config_id, idempotency_key)
                VALUES (:t, :at, :meter, 1000, 1000,
                        CAST(:cost AS numeric), 'anthropic/claude-sonnet-4-6',
                        :acid, :idem)
                """
            ),
            {
                "t": str(tenant_id),
                "at": occurred_at,
                "meter": meter,
                "cost": cost,
                "acid": str(agent_config_id) if agent_config_id else None,
                "idem": uuid.uuid4().hex,
            },
        )
        await session.commit()


async def test_cost_is_grouped_by_month_and_agent_version(
    client, admin_headers, db_session
) -> None:
    tenant_id, config_id, version = await _tenant_with_agent(db_session)
    now = datetime.now(UTC)
    await _usage(tenant_id, config_id, cost="0.02000000", occurred_at=now)
    await _usage(tenant_id, config_id, cost="0.01000000", occurred_at=now)

    r = await client.get(f"/admin/tenants/{tenant_id}/cost", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_cost_usd"] == pytest.approx(0.03)
    assert body["total_records"] == 2
    assert body["complete"] is True
    bucket = body["buckets"][0]
    assert bucket["month"] == now.strftime("%Y-%m")
    assert bucket["agent_config_id"] == str(config_id)
    # La versión es la etiqueta que el panel enseña — el criterio de salida
    # de la Fase 2 habla de "por versión de agente", no por uuid.
    assert bucket["agent_config_version"] == version


async def test_unpriced_rows_are_counted_and_flag_the_total_as_incomplete(
    client, admin_headers, db_session
) -> None:
    """El fallo que este endpoint existe para no cometer: SUM ignora los
    NULL y devolvería 0,02 como si fuera el coste del mes."""
    tenant_id, config_id, _ = await _tenant_with_agent(db_session)
    now = datetime.now(UTC)
    await _usage(tenant_id, config_id, cost="0.02000000", occurred_at=now)
    await _usage(tenant_id, config_id, cost=None, occurred_at=now)
    await _usage(tenant_id, config_id, cost=None, occurred_at=now)

    body = (await client.get(f"/admin/tenants/{tenant_id}/cost", headers=admin_headers)).json()

    assert body["total_cost_usd"] == pytest.approx(0.02)
    assert body["total_records"] == 3
    assert body["total_unpriced_records"] == 2
    assert body["complete"] is False
    assert body["buckets"][0]["unpriced_records"] == 2


async def test_the_window_starts_on_the_first_of_the_month_and_crosses_years() -> None:
    """Aritmética pura, y por eso mismo el sitio donde vive el error de
    uno: ``months=1`` tiene que ser el mes EN CURSO (no el anterior) y una
    ventana pedida en enero tiene que retroceder de año.

    No se prueba insertando consumo antiguo: ``usage_records`` está
    particionada y en una base recién migrada solo existen las particiones
    del mes actual y el siguiente — el rol de test no puede crear las
    demás, así que un test así sería verde aquí y rojo en CI.
    """
    assert _first_of_month_n_back(1, today=date(2026, 8, 11)) == date(2026, 8, 1)
    assert _first_of_month_n_back(6, today=date(2026, 8, 11)) == date(2026, 3, 1)
    assert _first_of_month_n_back(6, today=date(2026, 1, 15)) == date(2025, 8, 1)
    # Diciembre es donde falla el ``% 12`` mal escrito: el mes 12 tiene que
    # seguir siendo diciembre y no caer al 0.
    assert _first_of_month_n_back(1, today=date(2026, 12, 31)) == date(2026, 12, 1)


async def test_the_months_parameter_reaches_the_query(client, admin_headers, db_session) -> None:
    """El cableado del parámetro. Sin esto, ``months`` podría quedarse sin
    usar y el informe devolvería siempre la ventana por defecto sin que
    ninguna aserción de importes lo notase."""
    tenant_id, _, _ = await _tenant_with_agent(db_session)
    for months in (1, 6, 24):
        body = (
            await client.get(
                f"/admin/tenants/{tenant_id}/cost?months={months}", headers=admin_headers
            )
        ).json()
        assert body["since"] == _first_of_month_n_back(months).isoformat()

    # Fuera de rango: 0 no significa nada y 25 invita a barrer la tabla
    # entera de un cliente antiguo desde el panel.
    assert (
        await client.get(f"/admin/tenants/{tenant_id}/cost?months=0", headers=admin_headers)
    ).status_code == 422
    assert (
        await client.get(f"/admin/tenants/{tenant_id}/cost?months=25", headers=admin_headers)
    ).status_code == 422


async def test_another_tenants_usage_is_not_visible(client, admin_headers, db_session) -> None:
    """Control de aislamiento. La consulta no lleva ``WHERE tenant_id`` a
    propósito — si la RLS dejara de aplicar, el panel de margen de un
    cliente mostraría el gasto de otro y la suma seguiría pareciendo
    razonable."""
    mine, my_config, _ = await _tenant_with_agent(db_session)
    theirs, their_config, _ = await _tenant_with_agent(db_session)
    now = datetime.now(UTC)
    await _usage(mine, my_config, cost="0.01000000", occurred_at=now)
    await _usage(theirs, their_config, cost="7.00000000", occurred_at=now)

    body = (await client.get(f"/admin/tenants/{mine}/cost", headers=admin_headers)).json()
    assert body["total_cost_usd"] == pytest.approx(0.01)
    assert body["total_records"] == 1


async def test_usage_without_an_agent_config_still_shows_up(
    client, admin_headers, db_session
) -> None:
    """El consumo de evals y del QA Playground no lleva ``agent_config_id``.
    Dejarlo fuera del informe escondería coste real del cliente."""
    tenant_id, _, _ = await _tenant_with_agent(db_session)
    await _usage(tenant_id, None, cost="0.30000000", occurred_at=datetime.now(UTC))

    body = (await client.get(f"/admin/tenants/{tenant_id}/cost", headers=admin_headers)).json()
    assert body["total_cost_usd"] == pytest.approx(0.30)
    assert body["buckets"][0]["agent_config_id"] is None


async def test_a_tenant_without_usage_reports_zero_and_complete(
    client, admin_headers, db_session
) -> None:
    tenant_id, _, _ = await _tenant_with_agent(db_session)
    body = (await client.get(f"/admin/tenants/{tenant_id}/cost", headers=admin_headers)).json()
    assert body["buckets"] == []
    assert body["total_cost_usd"] == 0
    assert body["complete"] is True


async def test_the_endpoint_needs_an_admin_token(client, db_session) -> None:
    tenant_id, _, _ = await _tenant_with_agent(db_session)
    r = await client.get(f"/admin/tenants/{tenant_id}/cost")
    assert r.status_code in (401, 403)
