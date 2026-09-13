#!/usr/bin/env python3
"""Escribe los ``stripe_price_id`` del catálogo en ``membership_tiers``.

Spec 005 · T021. El script que crea el catálogo —``scripts/sync_billing_catalog.py``
en la raíz— habla con la cuenta del proveedor y **no puede alcanzar la base de
datos**: corre en la máquina de una persona, con las claves, fuera de la VPC. Por
eso imprime los ``UPDATE`` en vez de ejecutarlos. Este script es la otra mitad, y
corre donde sí hay base: dentro del contenedor, igual que ``seed_connectors.py``.

Sin él, ``billing/catalog.py`` resuelve ``code → stripe_price_id`` contra una
columna a ``NULL`` y el checkout no encuentra el precio del nivel.

**Idempotente.** Escribir el mismo id dos veces no hace nada; el script dice qué
filas cambiaron y qué filas ya estaban. Un id distinto del que hay **sí** se
sobreescribe, pero avisando de los dos valores: es la operación legítima cuando
se rehace el catálogo contra otra cuenta.

Los ids de modo test y de modo live son catálogos distintos, y **un id no lleva
escrito de qué modo viene**: no hay nada que este script pueda comprobar para
saberlo. Valida la forma (``price_…``) y el nivel, no la procedencia. Escribir
ids de test en la base de producción es, por tanto, el único error de esta
operación que no se detecta solo — de ahí el aviso al final de cada ejecución.

Uso, dentro del contenedor (lo lanza ``aws ecs run-task`` con override):

    python /app/apps/api/scripts/write_billing_price_ids.py \\
        pro=price_xxx team=price_yyy business=price_zzz

El nivel ``free`` no se acepta: no se cobra, así que no tiene precio arriba
(``sync_billing_catalog.py`` no lo crea) y su columna se queda a ``NULL``.
"""

from __future__ import annotations

import asyncio
import sys

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.base import dispose_engine, get_engine
from nexus_api.logging import configure_logging

configure_logging()
log = structlog.get_logger(__name__)

#: Los tres niveles que se cobran. ``free`` queda fuera a propósito.
BILLABLE = ("pro", "team", "business")


def parse_pairs(argv: list[str]) -> dict[str, str] | None:
    """``["pro=price_x"]`` → ``{"pro": "price_x"}``, o ``None`` si algo no cuadra."""
    pairs: dict[str, str] = {}
    for raw in argv:
        if "=" not in raw:
            log.error("write_price_ids.bad_argument", argument=raw, expected="code=price_id")
            return None
        code, _, price_id = raw.partition("=")
        code, price_id = code.strip(), price_id.strip()
        if code == "free":
            log.error("write_price_ids.free_has_no_price", hint="free no se cobra")
            return None
        if code not in BILLABLE:
            log.error("write_price_ids.unknown_code", code=code, expected=list(BILLABLE))
            return None
        # Un ``prod_`` donde va un ``price_`` es el error de copiar y pegar de
        # esta operación: el producto y el precio son objetos distintos y sólo
        # el segundo sirve para abrir una sesión de pago.
        if not price_id.startswith("price_"):
            log.error("write_price_ids.not_a_price_id", code=code, value=price_id)
            return None
        if code in pairs:
            log.error("write_price_ids.duplicate_code", code=code)
            return None
        pairs[code] = price_id
    return pairs


async def main() -> int:
    pairs = parse_pairs(sys.argv[1:])
    if pairs is None:
        return 2
    if not pairs:
        log.error("write_price_ids.nothing_to_do", usage="code=price_id [code=price_id ...]")
        return 2

    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    written, unchanged, replaced, absent = [], [], [], []
    try:
        async with factory() as session:
            for code, price_id in pairs.items():
                current = (
                    await session.execute(
                        text("SELECT stripe_price_id FROM membership_tiers WHERE code = :code"),
                        {"code": code},
                    )
                ).first()
                if current is None:
                    # La fila la siembra la migración 0116. Si no está, la base
                    # no está en la cabeza y escribir sería peor que parar.
                    absent.append(code)
                    continue
                if current[0] == price_id:
                    unchanged.append(code)
                    continue
                await session.execute(
                    text(
                        "UPDATE membership_tiers SET stripe_price_id = :price_id WHERE code = :code"
                    ),
                    {"price_id": price_id, "code": code},
                )
                if current[0]:
                    replaced.append((code, current[0], price_id))
                else:
                    written.append(code)
            if absent:
                log.error(
                    "write_price_ids.tier_missing",
                    codes=absent,
                    hint="¿está la base en la cabeza de Alembic (0116 o superior)?",
                )
                await session.rollback()
                return 3
            await session.commit()
    finally:
        await dispose_engine()

    for code, before, after in replaced:
        log.warning("write_price_ids.replaced", code=code, before=before, after=after)
    log.info(
        "write_price_ids.done",
        written=written,
        unchanged=unchanged,
        replaced=[c for c, _, _ in replaced],
    )
    print(
        "\nRecuerda: los ids de modo test y de modo live son catálogos distintos. "
        "Estos son los del entorno cuya base acabas de tocar."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
