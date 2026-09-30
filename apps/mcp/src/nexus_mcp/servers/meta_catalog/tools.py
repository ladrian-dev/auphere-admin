"""Las herramientas del catálogo de Meta (spec 022, Historia 3).

Solo lectura. Resuelven **qué catálogo** y **con qué token** en el servidor,
por el canal de la conversación; el modelo nunca ve ni uno ni otro
(constitución III). Sin catálogo enlazado, la herramienta lo dice con un
error que el agente puede leer, no con una lista vacía que parezca «no hay
productos».
"""

from __future__ import annotations

import html
import re
import uuid
from typing import Any, ClassVar

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import (
    get_current_customer,
    require_current_tenant,
    tenant_scoped_session,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, ChannelStatus, ChannelType, Conversation
from nexus_api.services.meta_signup_service import build_meta_client as _build_meta_client
from nexus_channels.whatsapp_meta.credentials import (
    ChannelCredentialsRepository,
    MetaCredentialsRepository,
)
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from nexus_channels.whatsapp_meta.meta_client import MetaClient

from nexus_mcp.base import ToolBase, ToolError

from .schemas import (
    CatalogProduct,
    GetProductInput,
    GetProductOutput,
    SearchProductsInput,
    SearchProductsOutput,
)

log = structlog.get_logger(__name__)

_TAGS = re.compile(r"<[^>]+>")


def build_meta_client() -> MetaClient:
    """Costura para los tests: se sustituye por un Meta simulado."""
    return _build_meta_client()


async def resolve_channel_catalog(
    tenant_id: uuid.UUID, customer_id: uuid.UUID | None
) -> tuple[str, str] | None:
    """``(catalog_id, token)`` del canal por el que atiende esta conversación.

    Primero el canal de la última conversación del cliente del turno; si no
    hay cliente (turno de operador, Playground), el primer número vivo del
    negocio con catálogo. ``None`` si ninguno tiene catálogo o credencial.
    """
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        channel: Channel | None = None
        if customer_id is not None:
            channel_id = await session.scalar(
                sa.select(Conversation.channel_id)
                .where(Conversation.customer_id == customer_id)
                .order_by(Conversation.last_inbound_at.desc().nulls_last())
                .limit(1)
            )
            if channel_id is not None:
                channel = await session.get(Channel, channel_id)
        if channel is None or not (channel.config or {}).get("catalog_id"):
            channel = await session.scalar(
                sa.select(Channel)
                .where(
                    Channel.type == ChannelType.WHATSAPP,
                    Channel.status == ChannelStatus.ACTIVE,
                    Channel.config["catalog_id"].astext.isnot(None),
                )
                .order_by(Channel.created_at)
                .limit(1)
            )
        if channel is None:
            return None
        catalog_id = (channel.config or {}).get("catalog_id")
        if not isinstance(catalog_id, str) or not catalog_id:
            return None
        creds = await ChannelCredentialsRepository(session).get(channel.id)
        if creds is None:
            creds = await MetaCredentialsRepository(session).get()
        if creds is None:
            return None
        return catalog_id, creds.bisuat


def _clean(text: object, limit: int = 300) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return None
    plain = html.unescape(_TAGS.sub(" ", text))
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain[:limit] if plain else None


def _to_product(raw: dict[str, Any]) -> CatalogProduct | None:
    rid = raw.get("retailer_id")
    name = raw.get("name")
    if not isinstance(rid, str) or not rid or not isinstance(name, str):
        return None
    return CatalogProduct(
        retailer_id=rid,
        name=name,
        price=str(raw["price"]) if raw.get("price") is not None else None,
        currency=str(raw["currency"]) if raw.get("currency") else None,
        availability=str(raw["availability"]) if raw.get("availability") else None,
        image_url=str(raw["image_url"]) if raw.get("image_url") else None,
        description=_clean(raw.get("description")),
    )


class _CatalogTool(ToolBase):
    side_effects: ClassVar[tuple[str, ...]] = ()

    async def _catalog(self) -> tuple[str, str]:
        found = await resolve_channel_catalog(require_current_tenant(), get_current_customer())
        if found is None:
            raise ToolError(
                "catalog_not_linked: este número no tiene un catálogo de Meta enlazado, "
                "así que no puedes enseñar productos como tarjeta. Dilo con naturalidad."
            )
        return found


class SearchProducts(_CatalogTool):
    name = "catalog.search_products"
    description = (
        "Busca productos en el catálogo de Meta del negocio por nombre y devuelve hasta "
        "10 con su retailer_id, precio y disponibilidad. Úsala antes de mandar una "
        "tarjeta de producto: el retailer_id que devuelve es el que va en `products` "
        "de response.send_interactive. Vacío busca los primeros del catálogo."
    )
    input_model = SearchProductsInput
    output_model = SearchProductsOutput

    async def run(self, payload: SearchProductsInput) -> SearchProductsOutput:  # type: ignore[override]
        catalog_id, token = await self._catalog()
        client = build_meta_client()
        try:
            rows = await client.search_products(
                catalog_id=catalog_id, access_token=token, query=payload.query, limit=payload.limit
            )
        except MetaAPIError as exc:
            log.warning("catalog.search_failed", code=getattr(exc, "code", None), error=str(exc))
            raise ToolError(
                "catalog_unavailable: Meta no respondió al buscar en el catálogo. Inténtalo de nuevo."
            ) from exc
        finally:
            await client.close()
        products = [p for p in (_to_product(r) for r in rows) if p is not None]
        return SearchProductsOutput(
            query=payload.query, products=products, truncated=len(rows) >= payload.limit
        )


class GetProduct(_CatalogTool):
    name = "catalog.get_product"
    description = (
        "Devuelve la ficha de un producto del catálogo de Meta por su retailer_id "
        "(nombre, precio, disponibilidad, imagen y descripción). Úsala para "
        "confirmar precio o disponibilidad antes de mandar su tarjeta."
    )
    input_model = GetProductInput
    output_model = GetProductOutput

    async def run(self, payload: GetProductInput) -> GetProductOutput:  # type: ignore[override]
        catalog_id, token = await self._catalog()
        client = build_meta_client()
        try:
            raw = await client.get_product(
                catalog_id=catalog_id, retailer_id=payload.retailer_id, access_token=token
            )
        except MetaAPIError as exc:
            log.warning("catalog.get_failed", code=getattr(exc, "code", None), error=str(exc))
            raise ToolError(
                "catalog_unavailable: Meta no respondió al leer el catálogo. Inténtalo de nuevo."
            ) from exc
        finally:
            await client.close()
        product = _to_product(raw) if raw else None
        return GetProductOutput(found=product is not None, product=product)


META_CATALOG_TOOLS: tuple[type[ToolBase], ...] = (SearchProducts, GetProduct)

__all__ = [
    "META_CATALOG_TOOLS",
    "GetProduct",
    "SearchProducts",
    "build_meta_client",
    "resolve_channel_catalog",
]
