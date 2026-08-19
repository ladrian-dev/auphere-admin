#!/usr/bin/env python
"""Las cinco razones del §17, sobre la base (CO-08, §11 de CONTRACT-V2).

Es la mitad *consultable* de las métricas del piloto. La otra mitad son los
contadores de ``core/otel_metrics.py``, que existen porque hay hechos —un
turno sin respaldo, una verificación en rojo— que solo se conocen en el
instante en que pasan y no dejan fila.

**No hay endpoint de métricas** (§11): esto se corre a mano, una vez, al
cerrar el piloto o cuando alguien pregunta. Un panel público sería una
superficie nueva de la consola para responder una pregunta que se hace tres
veces al mes.

Uso::

    cd apps/api
    uv run python scripts/companion_pilot_metrics.py --days 30
    uv run python scripts/companion_pilot_metrics.py --days 30 --by-partner

La razón que MANDA es la primera que se imprime: **confirmaciones canceladas
por debajo del 15 %**. Un Companion que propone cosas que la gente cancela es
peor que no tener Companion, porque enseña a desconfiar de él.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

#: Objetivos del §17. Se imprimen junto al valor para que el número tenga
#: contra qué compararse sin abrir el documento.
TARGETS: dict[str, str] = {
    "hitl_cancelled_ratio": "< 15 % — LA QUE MANDA",
    "task_completed_ratio": "> 50 %",
    "verify_failed_ratio": "< 3 %",
    "cost_per_completed_usd": "< 0,40 $",
}

# ``companion.actions`` lleva RLS por principal, así que estas consultas se
# corren con el dueño de la base (el mismo que aplica las migraciones), no
# con ``nexus_app``. Es una lectura de operador sobre la plataforma entera,
# no una lectura de partner — y por eso vive en un script y no en la API.

_CANCELLED = """
SELECT
  count(*) FILTER (WHERE status = 'cancelled')                       AS cancelled,
  count(*) FILTER (WHERE status <> 'proposed' OR proposed_at < now()) AS proposed,
  count(*) FILTER (WHERE status = 'applied')                          AS applied
FROM companion.actions
WHERE proposed_at >= now() - make_interval(days => :days)
"""

_THREADS = """
SELECT count(*) AS threads
FROM companion.threads
WHERE created_at >= now() - make_interval(days => :days)
"""

_RUNS = """
SELECT
  count(*)                                        AS runs,
  count(*) FILTER (WHERE status = 'paused')       AS paused,
  coalesce(sum(coalesce(input_tokens, 0) + coalesce(output_tokens, 0)), 0) AS tokens
FROM companion.runs
WHERE started_at >= now() - make_interval(days => :days)
"""

# ``usage_records`` tiene FORCE ROW LEVEL SECURITY por tenant y en Aurora el
# dueño de la tabla no es superusuario, así que esta consulta puede devolver
# cero incluso habiendo filas. Cuando pase, el script lo dice ("sin datos")
# en vez de imprimir 0,00 $ — un cero falso se lee como "es gratis".
_COST = """
SELECT coalesce(sum(cost_usd), 0) AS cost_usd, count(*) AS records
FROM usage_records
WHERE source = 'companion'
  AND occurred_at >= now() - make_interval(days => :days)
"""

_TICKETS = """
SELECT payload->>'topic' AS topic, count(*) AS n
FROM console_notifications
WHERE kind IN ('support.ticket_opened', 'support.capability_requested')
  AND created_at >= now() - make_interval(days => :days)
GROUP BY 1
ORDER BY n DESC, 1
LIMIT 20
"""


def _ratio(num: float, den: float) -> str:
    if den <= 0:
        # Sin denominador NO se imprime un 0 %: un cero falso se lee como
        # "va perfecto" y es exactamente lo contrario de lo que sabemos.
        return "sin datos"
    return f"{num * 100.0 / den:.1f} %  ({num:.0f}/{den:.0f})"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument(
        "--by-partner",
        action="store_true",
        help="Añade el desglose de tickets por asunto (§25.2).",
    )
    args = parser.parse_args()

    url = os.environ.get("NEXUS_DATABASE_URL")
    if not url:
        raise SystemExit("NEXUS_DATABASE_URL no está puesto.")
    engine = create_async_engine(url)
    params = {"days": args.days}
    try:
        async with engine.connect() as conn:
            actions = (await conn.execute(sa.text(_CANCELLED), params)).mappings().one()
            threads = (await conn.execute(sa.text(_THREADS), params)).mappings().one()
            runs = (await conn.execute(sa.text(_RUNS), params)).mappings().one()
            cost = (await conn.execute(sa.text(_COST), params)).mappings().one()
            tickets: list[Any] = (
                (await conn.execute(sa.text(_TICKETS), params)).mappings().all()
                if args.by_partner
                else []
            )
    finally:
        await engine.dispose()

    applied = float(actions["applied"])
    print(f"\nCompanion · últimos {args.days} días\n" + "─" * 52)
    print(
        f"  confirmaciones canceladas   {_ratio(float(actions['cancelled']), float(actions['proposed']))}"
        f"\n      objetivo: {TARGETS['hitl_cancelled_ratio']}"
    )
    print(
        f"  tareas completadas/hilos    {_ratio(applied, float(threads['threads']))}"
        f"\n      objetivo: {TARGETS['task_completed_ratio']}"
    )
    print(f"  hilos abiertos              {threads['threads']}")
    print(f"  runs                        {runs['runs']}  (pausados por tope: {runs['paused']})")
    print(f"  tokens del Companion        {runs['tokens']:,}")
    if applied > 0 and float(cost["cost_usd"]) > 0:
        print(
            f"  coste por trabajo hecho     {float(cost['cost_usd']) / applied:.3f} $"
            f"\n      objetivo: {TARGETS['cost_per_completed_usd']}"
        )
    else:
        # Un hilo del Companion SIN cliente no deja fila en ``usage_records``
        # (esa tabla exige ``tenant_id``), así que un coste vacío puede ser
        # simplemente que todo el uso fue sin cliente. Se dice, en vez de
        # imprimir un cero que parecería gratis.
        print("  coste por trabajo hecho     sin datos de usage_records en la ventana")
    print(
        "\n  Las razones de 'afirmaciones sin respaldo' y 'fallos de verificación'\n"
        "  no salen de aquí: no dejan fila. Están en los contadores\n"
        "  companion.turn.* y companion.verify.* de core/otel_metrics.py."
    )
    if tickets:
        print("\n  Tickets por asunto (§25.2)\n" + "  " + "─" * 30)
        for row in tickets:
            print(f"    {row['n']:>4}  {row['topic']}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
