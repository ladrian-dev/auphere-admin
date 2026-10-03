"""Modelos de las herramientas del catálogo de Meta (spec 022)."""

from __future__ import annotations

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel


class SearchProductsInput(InputModel):
    query: str = Field(
        default="",
        max_length=120,
        description="Texto a buscar en el nombre del producto. Vacío devuelve los primeros.",
    )
    limit: int = Field(default=5, ge=1, le=10, description="Cuántos devolver, como máximo 10.")


class GetProductInput(InputModel):
    retailer_id: str = Field(
        min_length=1,
        max_length=120,
        description="El identificador del producto en el catálogo (retailer_id), tal como lo devolvió la búsqueda.",
    )


class CatalogProduct(OutputModel):
    retailer_id: str = Field(
        description="Identificador del producto en el catálogo. Es el que se pasa en `products` para mandar la tarjeta."
    )
    name: str = Field(description="Nombre del producto.")
    price: str | None = Field(
        default=None, description="Precio tal como lo enseña el catálogo (con moneda)."
    )
    currency: str | None = Field(default=None, description="Moneda del precio.")
    availability: str | None = Field(
        default=None, description="`in stock`, `out of stock` u otro estado del catálogo."
    )
    image_url: str | None = Field(default=None, description="Imagen del producto.")
    description: str | None = Field(
        default=None, description="Descripción del catálogo, recortada."
    )


class SearchProductsOutput(OutputModel):
    query: str
    products: list[CatalogProduct] = Field(description="Los productos encontrados, hasta `limit`.")
    truncated: bool = Field(
        description="True si el catálogo devolvió el máximo pedido: puede haber más."
    )


class GetProductOutput(OutputModel):
    found: bool
    product: CatalogProduct | None = None
