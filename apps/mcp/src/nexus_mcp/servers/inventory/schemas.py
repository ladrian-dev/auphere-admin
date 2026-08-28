"""Pydantic input/output models for the Amigable Venta (inventory.*) tools.

Input models validate the LLM's arguments; output models are the strict
shape the tool must return (the LLM sees ``model_json_schema()``).

Two shaping decisions worth knowing before editing:

1. **Scalars come FIRST in every output model.** The worker truncates tool
   JSON at 8_000 chars (``_TOOL_RESULT_CHAR_CAP``); if the item list led,
   the totals would never reach the model on a fat catalogue search.

2. **``precio_costo`` is deliberately NOT exposed.** The upstream API
   returns it on every row, but cost price is the one field in this
   catalogue that must never reach a customer-facing turn. Adding it is a
   one-line change the day someone asks for margin — leaking it back out
   of a transcript is not.
"""

from __future__ import annotations

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class ProductVariant(OutputModel):
    """One concrete SKU. In this catalogue several SKUs share a name and
    differ in price and stock — that is what "variante" means here."""

    sku: str = Field(description="Código SKU único de esta variante.")
    nombre: str = Field(description="Nombre del producto.")
    categoria: str | None = Field(default=None, description="Categoría del producto.")
    precio_usd: float = Field(description="Precio de venta en USD de ESTA variante.")
    stock_actual: int = Field(description="Unidades disponibles de ESTA variante.")
    stock_minimo: int = Field(description="Umbral de reposición de ESTA variante.")
    bajo_minimo: bool = Field(description="True si stock_actual <= stock_minimo (toca reponer).")
    agotado: bool = Field(description="True si stock_actual es 0.")


class ProductGroup(OutputModel):
    """Un producto agrupado por nombre, con todas sus variantes sumadas."""

    nombre: str = Field(description="Nombre del producto.")
    categoria: str | None = Field(default=None, description="Categoría del producto.")
    variantes: int = Field(description="Cuántos SKUs distintos existen con este nombre.")
    stock_total: int = Field(description="Suma de unidades de todas las variantes.")
    precio_min: float = Field(description="Precio más bajo entre las variantes (USD).")
    precio_max: float = Field(description="Precio más alto entre las variantes (USD).")
    variantes_bajo_minimo: int = Field(
        description="Cuántas variantes están en o por debajo de su stock mínimo."
    )
    skus: list[str] = Field(description="SKUs de las variantes, para consultar el detalle.")


# ── inventory.search_products ────────────────────────────────────────────


class SearchProductsInput(InputModel):
    query: str = Field(
        min_length=1,
        description=(
            "Texto a buscar en el NOMBRE o el SKU del producto (ej. 'ibuprofeno', "
            "'jarabe', 'FARM-00001'). No busca por categoría ni por tipo. "
            "Ignora mayúsculas y tildes y busca por coincidencia parcial."
        ),
    )
    limit: int = Field(
        default=12,
        ge=1,
        le=50,
        description="Máximo de productos (agrupados por nombre) a devolver.",
    )


class SearchProductsOutput(OutputModel):
    query: str = Field(description="Término buscado.")
    productos_encontrados: int = Field(
        description="Productos distintos (por nombre) que coinciden, antes de aplicar limit."
    )
    variantes_encontradas: int = Field(description="Filas/SKUs totales que coinciden.")
    devueltos: int = Field(description="Productos incluidos en items (tras aplicar limit).")
    truncado: bool = Field(
        description=(
            "True si el API llegó a su tope de 1000 filas y hay coincidencias que "
            "NO se ven. Si es True, NO afirmes que la lista está completa: pide "
            "un término de búsqueda más específico."
        )
    )
    items: list[ProductGroup] = Field(description="Productos agrupados, mayor stock primero.")


# ── inventory.get_product ────────────────────────────────────────────────


class GetProductInput(InputModel):
    query: str = Field(
        min_length=1,
        description=(
            "Nombre exacto o aproximado del producto, o su SKU. Devuelve TODAS "
            "las variantes del producto que mejor coincida."
        ),
    )


class GetProductOutput(OutputModel):
    encontrado: bool = Field(description="False si no coincidió ningún producto.")
    query: str = Field(description="Término buscado.")
    nombre: str | None = Field(default=None, description="Nombre del producto resuelto.")
    categoria: str | None = Field(default=None, description="Categoría del producto.")
    variantes: int = Field(default=0, description="Número de SKUs de este producto.")
    stock_total: int = Field(default=0, description="Unidades sumando todas las variantes.")
    precio_min: float = Field(default=0.0, description="Precio más bajo (USD).")
    precio_max: float = Field(default=0.0, description="Precio más alto (USD).")
    ambiguo: bool = Field(
        default=False,
        description=(
            "True si la búsqueda coincidió con varios productos distintos y se "
            "resolvió el más parecido. Confirma con el usuario antes de dar el dato "
            "por bueno y ofrécele otros_candidatos."
        ),
    )
    otros_candidatos: list[str] = Field(
        default_factory=list,
        description="Otros nombres de producto que también coincidieron (máx. 8).",
    )
    detalle: list[ProductVariant] = Field(
        default_factory=list, description="Todas las variantes, de menor a mayor precio."
    )


# ── inventory.check_stock ────────────────────────────────────────────────


class CheckStockInput(InputModel):
    query: str = Field(
        min_length=1, description="Nombre o SKU del producto cuyo stock se quiere validar."
    )


class CheckStockOutput(OutputModel):
    encontrado: bool = Field(description="False si no coincidió ningún producto.")
    query: str = Field(description="Término buscado.")
    nombre: str | None = Field(default=None, description="Producto resuelto.")
    stock_total: int = Field(default=0, description="Unidades disponibles en total.")
    hay_stock: bool = Field(default=False, description="True si stock_total > 0.")
    variantes: int = Field(default=0, description="SKUs distintos de este producto.")
    variantes_agotadas: int = Field(default=0, description="SKUs con 0 unidades.")
    variantes_bajo_minimo: int = Field(
        default=0, description="SKUs en o por debajo de su stock mínimo."
    )
    detalle: list[ProductVariant] = Field(
        default_factory=list, description="Stock por SKU, de mayor a menor."
    )


# ── inventory.low_stock ──────────────────────────────────────────────────


class LowStockInput(InputModel):
    query: str = Field(
        min_length=1,
        description=(
            "Familia de productos a revisar por NOMBRE o SKU (ej. 'jarabe', "
            "'ibuprofeno', 'FARM-002'). Es obligatorio: el API no permite listar "
            "el catálogo completo, solo buscar."
        ),
    )
    limit: int = Field(default=20, ge=1, le=50, description="Máximo de variantes a devolver.")
    incluir_agotados: bool = Field(
        default=True, description="Si false, omite las variantes con 0 unidades."
    )


class LowStockOutput(OutputModel):
    query: str = Field(description="Término buscado.")
    revisadas: int = Field(description="Variantes que se revisaron.")
    bajo_minimo: int = Field(description="Variantes en o por debajo de su stock mínimo.")
    agotadas: int = Field(description="Variantes con 0 unidades.")
    devueltas: int = Field(description="Variantes incluidas en items (tras aplicar limit).")
    truncado: bool = Field(
        description=(
            "True si el API llegó a su tope de 1000 filas. Si es True, la revisión "
            "NO cubrió todo: acota la búsqueda."
        )
    )
    items: list[ProductVariant] = Field(
        description="Variantes a reponer, las más críticas primero."
    )
