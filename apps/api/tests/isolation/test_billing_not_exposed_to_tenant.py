"""Spec 005 · garantía 1 — nada del cobro llega a un cliente final.

Las entidades de esta spec son **del partner o de plataforma**. Ninguna lleva
``tenant_id``, así que no hay superficie por la que un cliente final las
alcance — pero eso hay que comprobarlo, no suponerlo: la forma habitual de que
un dato se escape no es una consulta mal escrita, es una columna añadida meses
después «para poder filtrar».
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

_BILLING_TABLES = ("membership_tiers", "partner_subscriptions", "billing_events")


async def test_no_billing_table_carries_a_tenant_id() -> None:
    async with get_sessionmaker()() as s:
        rows = (
            await s.execute(
                sa.text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE column_name = 'tenant_id' AND table_name = ANY(:t)"
                ),
                {"t": list(_BILLING_TABLES)},
            )
        ).all()
        assert not rows, (
            f"estas tablas de cobro llevan tenant_id: {[r[0] for r in rows]}. "
            "Si el cobro empieza a hablar de tenants, un cliente final acaba "
            "viendo lo que su agencia paga"
        )


async def test_no_tenant_facing_route_mentions_a_billing_table() -> None:
    """El otro lado de lo mismo: el esquema no basta si la ruta lo expone."""
    from nexus_api.main import app

    offenders: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not (path.startswith("/v1/embed") or path.startswith("/v1/widget")):
            continue
        endpoint = getattr(route, "endpoint", None)
        source = getattr(endpoint, "__doc__", "") or ""
        module = getattr(endpoint, "__module__", "")
        if "billing" in module or any(t in source for t in _BILLING_TABLES):
            offenders.append(path)
    assert not offenders, f"rutas de cliente final que tocan el cobro: {offenders}"


async def test_billing_events_is_platform_level_without_rls() -> None:
    """Y esto es a propósito, no un olvido.

    ``billing_events`` no lleva RLS porque **no es de nadie**: una fila puede
    no tener partner resuelto, y el rastro de un aviso de dinero de una cuenta
    desconocida es justo el que hay que poder leer. Lo que la protege es que
    ninguna ruta de partner ni de tenant la expone.
    """
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                sa.text("SELECT relrowsecurity FROM pg_class WHERE relname = 'billing_events'")
            )
        ).first()
        assert row is not None
        assert row[0] is False, (
            "billing_events tiene RLS: o se documenta por qué columna filtra, o "
            "sobra — una política que nadie puede satisfacer deja la tabla muda"
        )
