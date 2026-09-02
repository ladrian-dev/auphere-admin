"""Local catalogue client — same contract as the Amigable Venta client.

Serves rows from ``local_catalog_products`` (one row per SKU, scoped to a
tenant by RLS) instead of an HTTP API. The returned dicts have the SAME
keys the Amigable API returns, so the ``inventory.*`` tools cannot tell the
two backends apart — which is the whole point: swapping the source is an
operator action, not a code change.

**Search is deliberately identical to the upstream API's**, quirks included:

- matches ``nombre`` and ``sku`` only — never ``categoria`` or ``tipo``;
- case- and accent-insensitive, substring-based;
- capped at the same :data:`RESULT_CAP` rows, reporting ``truncated`` the
  same way.

Mirroring the cap on a database that could return everything looks
gratuitous until the swap happens: if the local backend answered more
generously, the agent's behaviour would change the day the real API came
back, and the demo would stop matching production.

Accent-insensitivity is precomputed, not computed at query time: the
loader stores a folded ``search_text`` column, so matching is a plain
``LIKE`` and needs no ``unaccent`` extension.
"""

from __future__ import annotations

import unicodedata
import uuid
from typing import Any

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from sqlalchemy import text

log = structlog.get_logger(__name__)

# Same cap as the Amigable Venta API. See the module docstring.
RESULT_CAP = 1000


def fold(value: str) -> str:
    """Lowercase and strip accents. Must match the loader's folding exactly,
    or stored rows become unsearchable."""
    decomposed = unicodedata.normalize("NFD", value or "")
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.casefold().strip()


class LocalCatalogClient:
    """Read-only view over one tenant's imported catalogue."""

    def __init__(self, tenant_id: uuid.UUID) -> None:
        self._tenant_id = tenant_id

    async def search_products(self, query: str) -> tuple[list[dict[str, Any]], bool]:
        """Search the catalogue by product name or SKU.

        Returns ``(rows, truncated)`` in the Amigable Venta row shape.
        """
        term = fold(query or "")
        if not term:
            # The upstream API answers 422 for an empty q; the tools never
            # send one (the schema enforces min_length=1), so an empty term
            # here means a caller bug, not user input.
            msg = 'el parametro "q" es obligatorio para buscar productos'
            raise ValueError(msg)

        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, self._tenant_id):
            result = await session.execute(
                text(
                    """
                    SELECT sku, nombre, categoria, tipo,
                           precio_usd, stock_actual, stock_minimo
                    FROM local_catalog_products
                    WHERE tenant_id = :tenant_id
                      AND search_text LIKE :pattern
                    ORDER BY nombre, sku
                    LIMIT :cap
                    """
                ),
                {
                    "tenant_id": str(self._tenant_id),
                    "pattern": f"%{term}%",
                    "cap": RESULT_CAP,
                },
            )
            rows = result.mappings().all()

        out: list[dict[str, Any]] = [
            {
                "sku": r["sku"],
                "nombre": r["nombre"],
                "categoria": r["categoria"],
                "tipo": r["tipo"],
                "precio_usd": float(r["precio_usd"] or 0),
                "stock_actual": int(r["stock_actual"] or 0),
                "stock_minimo": int(r["stock_minimo"] or 0),
            }
            for r in rows
        ]
        return out, len(out) >= RESULT_CAP

    async def decrement_stock(self, sku: str, cantidad: int) -> dict[str, Any]:
        """Descuenta ``cantidad`` unidades de un SKU — la VENTA SIMULADA de la demo.

        Solo el backend local soporta esto: escribe en ``local_catalog_products``,
        la tabla propia de Nexus. NO es una venta real en un POS; el API de
        Amigable Venta es de solo lectura y por eso la tool que llama aquí
        rechaza ese backend antes de llegar a este método.

        El descuento es atómico y RLS-scoped: el ``UPDATE`` lleva la guardia
        ``stock_actual >= :n`` en el mismo statement, así que dos ventas
        concurrentes nunca dejan el stock por debajo de cero (la segunda no
        afecta filas y se reporta como ``stock_insuficiente``).

        Stock insuficiente o SKU inexistente son RESULTADOS, no errores: se
        devuelven en el dict. Solo se lanza por argumentos inválidos.
        """
        sku_norm = (sku or "").strip()
        if not sku_norm:
            raise ValueError("sku es obligatorio")
        if cantidad < 1:
            raise ValueError("cantidad debe ser >= 1")

        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, self._tenant_id):
            updated = (
                (
                    await session.execute(
                        text(
                            """
                        UPDATE local_catalog_products
                           SET stock_actual = stock_actual - :n,
                               updated_at = now()
                         WHERE tenant_id = :tenant_id
                           AND sku = :sku
                           AND stock_actual >= :n
                        RETURNING nombre, precio_usd, stock_actual
                        """
                        ),
                        {"tenant_id": str(self._tenant_id), "sku": sku_norm, "n": cantidad},
                    )
                )
                .mappings()
                .first()
            )

            if updated is not None:
                # tenant_scoped_session hace commit al salir limpio del bloque.
                new_stock = int(updated["stock_actual"] or 0)
                return {
                    "encontrado": True,
                    "vendido": True,
                    "sku": sku_norm,
                    "nombre": updated["nombre"],
                    "precio_usd": float(updated["precio_usd"] or 0),
                    "stock_anterior": new_stock + cantidad,
                    "stock_actual": new_stock,
                    "motivo": None,
                }

            # No se descontó: distinguir "no existe" de "no alcanza el stock".
            current = (
                (
                    await session.execute(
                        text(
                            """
                        SELECT nombre, precio_usd, stock_actual
                          FROM local_catalog_products
                         WHERE tenant_id = :tenant_id AND sku = :sku
                        """
                        ),
                        {"tenant_id": str(self._tenant_id), "sku": sku_norm},
                    )
                )
                .mappings()
                .first()
            )

            if current is None:
                return {
                    "encontrado": False,
                    "vendido": False,
                    "sku": sku_norm,
                    "nombre": None,
                    "precio_usd": None,
                    "stock_anterior": None,
                    "stock_actual": None,
                    "motivo": "sku_no_encontrado",
                }
            stock = int(current["stock_actual"] or 0)
            return {
                "encontrado": True,
                "vendido": False,
                "sku": sku_norm,
                "nombre": current["nombre"],
                "precio_usd": float(current["precio_usd"] or 0),
                "stock_anterior": stock,
                "stock_actual": stock,
                "motivo": "stock_insuficiente",
            }
