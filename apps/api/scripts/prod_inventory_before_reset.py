"""Qué hay ahí dentro, antes de borrar nada. **Solo lee.**

Escrito el 2026-09-20 para vaciar el entorno de teammates y rehacer el alta
desde cero. Borrar sin mirar es cómo se pierde lo que no se sabía que había, y
aquí hay dos cosas concretas que mirar antes:

1. **Si algún tenant tiene citas.** Es la pregunta H3 que quedó abierta el
   2026-09-19: el fallo de `booking.*` dejaba leer citas de otros clientes
   dentro del mismo negocio. Si hay filas, hubo datos personales expuestos y
   corre un plazo de notificación; si hay cero, era latente. **Borrar primero
   destruye la única forma de responderlo.**
2. **Si hay suscripciones de Stripe vivas.** Borrar filas de la base **no**
   cancela nada en Stripe: la suscripción sigue cobrando contra una cuenta que
   ya no existe.

Uso::

    cd apps/api && uv run python scripts/prod_inventory_before_reset.py

No escribe. No borra. No pide confirmación porque no hace falta.
"""

from __future__ import annotations

import asyncio

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

QUERIES: tuple[tuple[str, str], ...] = (
    (
        "Personas que entran a la consola",
        "select id, email, display_name, created_at from console_auth.principals order by created_at",
    ),
    (
        "Partners",
        "select p.id, p.slug, p.name, p.created_at, "
        "(select count(*) from partner_memberships m where m.partner_id = p.id) as personas "
        "from partners p order by p.created_at",
    ),
    (
        "Clientes finales, y de quién son",
        "select t.id, t.slug, t.name, t.status, pt.partner_id "
        "from tenants t left join partner_tenants pt on pt.tenant_id = t.id "
        "order by t.created_at",
    ),
    (
        "H3 · CITAS POR CLIENTE — la pregunta que hay que responder antes de borrar",
        "select t.slug, count(a.id) as citas, min(a.created_at) as primera, "
        "max(a.created_at) as ultima "
        "from tenants t left join appointments a on a.tenant_id = t.id "
        "group by t.slug order by citas desc",
    ),
    (
        "Conversaciones y mensajes reales de clientes finales",
        "select t.slug, count(distinct c.id) as conversaciones, count(m.id) as mensajes "
        "from tenants t left join conversations c on c.tenant_id = t.id "
        "left join messages m on m.conversation_id = c.id group by t.slug order by mensajes desc",
    ),
    (
        "Stripe · suscripciones que seguirían cobrando tras borrar",
        "select partner_id, tier_code, state, current_period_end "
        "from partner_subscriptions order by created_at",
    ),
    (
        "Facturación — es lo que bloquea el borrado (FK RESTRICT)",
        "select partner_id, tenant_id, period_year, period_month, status "
        "from invoices order by period_year, period_month",
    ),
    (
        "Teammates, máquinas y trabajo en la máquina",
        "select (select count(*) from teammates) as teammates, "
        "(select count(*) from partner_devices) as maquinas, "
        "(select count(*) from local_executions) as ejecuciones",
    ),
)


async def main() -> int:
    from nexus_api.config import get_settings

    engine = create_async_engine(get_settings().database_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        for title, sql in QUERIES:
            print(f"\n{'─' * 72}\n{title}\n{'─' * 72}")
            try:
                rows = (await session.execute(sa.text(sql))).all()
            except Exception as exc:
                # El rollback NO es opcional: en Postgres, un error dentro de
                # una transacción la aborta entera y **todo lo que viniera
                # después saldría vacío**. Un inventario que se calla la mitad
                # es peor que ninguno, porque se parece a «no hay nada».
                await session.rollback()
                print(f"  ⚠ no se pudo leer: {type(exc).__name__}: {str(exc).splitlines()[0]}")
                continue
            if not rows:
                print("  (nada)")
                continue
            for r in rows:
                print("  " + " · ".join(str(v) for v in r))
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
