"""LLM-facing inventory tools (``inventory.*``).

Read-only access to a tenant's product catalogue and stock so the warehouse
agent can answer what exists, how many units there are, at what price, and
which variants a product has.

**Two interchangeable backends, one contract.** The tools never know which
one answered:

- ``amigable_venta`` — the Amigable Venta POS REST API (api_key connector).
- ``catalogo_local`` — a catalogue in Postgres, imported from a spreadsheet.

``_resolve_backend`` picks per tenant: the Amigable connector wins whenever
it is connected, and the imported catalogue answers otherwise. So the day
the upstream API has data again, an operator installs that connector and it
takes over — no code change, no prompt change, no new agent version.

The local backend is deliberately **not** modelled as a connector. There is
nothing to authenticate to (the rows live in our own database, tenant-scoped
by RLS), and the four ``auth_kind`` values are pinned by a CHECK constraint
on a shared table — widening that enum for a temporary bridge would outlive
the bridge. Presence of rows is the signal instead.

Credential resolution for the Amigable backend mirrors the Amigable Cobro
server: read ``tenant_connectors.credentials_ref`` (slug ``amigable_venta``),
fetch the ``tenant_credentials`` row, decrypt the payload to ``{"token"}``,
take the optional ``base_url`` from ``endpoint_meta``. The local backend
needs no credentials — the rows are already tenant-scoped by RLS.

**The grouping is the whole point of this module.** The catalogue stores
each variant as its own row and repeats the product name: "Ibuprofeno" is
four SKUs priced $1.35 to $4.19 with independent stock. Handing those rows
to the model raw produces answers like "tienes Ibuprofeno a 1.35" — true of
one SKU and wrong about the product. Every tool here groups by name first
and reports the aggregate plus the spread.
"""

from __future__ import annotations

import json
import unicodedata
import uuid
from typing import Any, ClassVar

import structlog
from nexus_api.core.tenant_context import require_current_tenant, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Connector,
    TenantConnector,
    TenantConnectorStatus,
    TenantCredentials,
)
from sqlalchemy import select
from sqlalchemy import text as sa_text

from nexus_mcp.base import ToolBase, ToolError
from nexus_mcp.servers.amigable_venta.client import DEFAULT_BASE_URL, AmigableVentaClient
from nexus_mcp.servers.catalogo_local.client import LocalCatalogClient
from nexus_mcp.servers.inventory.schemas import (
    CheckStockInput,
    CheckStockOutput,
    GetProductInput,
    GetProductOutput,
    LowStockInput,
    LowStockOutput,
    ProductGroup,
    ProductVariant,
    SearchProductsInput,
    SearchProductsOutput,
)

log = structlog.get_logger(__name__)

_AMIGABLE_VENTA_SLUG = "amigable_venta"

_LIVE_STATUSES = (
    TenantConnectorStatus.CONNECTED.value,
    TenantConnectorStatus.PARTIAL.value,
)

# Any backend must expose ``async search_products(query) -> (rows, truncated)``
# with rows in the Amigable Venta shape.
CatalogBackend = AmigableVentaClient | LocalCatalogClient


# ── backend resolution ───────────────────────────────────────────────────


class InventoryNotConfigured(ToolError):
    """No catalogue connector installed for this tenant. Surfaced as a clean
    "connector not connected" message, not a stack trace."""


async def _amigable_is_connected(tenant_id: uuid.UUID) -> bool:
    """Whether this tenant has a live Amigable Venta install."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = (
            await session.execute(
                select(Connector.slug)
                .join(TenantConnector, TenantConnector.connector_id == Connector.id)
                .where(
                    TenantConnector.tenant_id == tenant_id,
                    Connector.slug == _AMIGABLE_VENTA_SLUG,
                    TenantConnector.status.in_(_LIVE_STATUSES),
                )
            )
        ).first()
    return row is not None


async def _has_local_catalog(tenant_id: uuid.UUID) -> bool:
    """Whether this tenant has an imported catalogue with at least one row."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = (
            await session.execute(
                sa_text(
                    "SELECT 1 FROM local_catalog_products "
                    "WHERE tenant_id = :tenant_id LIMIT 1"
                ),
                {"tenant_id": str(tenant_id)},
            )
        ).first()
    return row is not None


async def _load_amigable_venta_client(tenant_id: uuid.UUID) -> AmigableVentaClient:
    """Resolve the active Amigable Venta connector for ``tenant_id``."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = (
            await session.execute(
                select(TenantConnector, Connector)
                .join(Connector, Connector.id == TenantConnector.connector_id)
                .where(
                    TenantConnector.tenant_id == tenant_id,
                    Connector.slug == _AMIGABLE_VENTA_SLUG,
                    TenantConnector.status.in_(_LIVE_STATUSES),
                )
            )
        ).first()
        if row is None:
            raise InventoryNotConfigured(
                "Amigable Venta connector is not connected for this tenant"
            )
        tc: TenantConnector = row[0]
        cred_ref: dict[str, Any] = tc.credentials_ref or {}
        tenant_credentials_id_raw = cred_ref.get("tenant_credentials_id")
        endpoint_meta = cred_ref.get("endpoint_meta") or {}
        base_url = endpoint_meta.get("base_url") or DEFAULT_BASE_URL
        if not tenant_credentials_id_raw:
            raise InventoryNotConfigured(
                "Amigable Venta credentials_ref missing tenant_credentials_id"
            )
        try:
            tenant_credentials_id = uuid.UUID(str(tenant_credentials_id_raw))
        except ValueError as exc:
            raise InventoryNotConfigured(
                "Amigable Venta credentials_ref.tenant_credentials_id is not a UUID: "
                f"{tenant_credentials_id_raw!r}"
            ) from exc

        creds_row = await session.get(TenantCredentials, tenant_credentials_id)
        if creds_row is None:
            raise InventoryNotConfigured(
                f"tenant_credentials row {tenant_credentials_id} not found"
            )
        try:
            payload = json.loads(bytes(creds_row.encrypted_payload).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise InventoryNotConfigured(
                f"Amigable Venta credentials payload is not valid JSON: {exc}"
            ) from exc

    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise InventoryNotConfigured("Amigable Venta credentials payload missing 'token'")
    return AmigableVentaClient(token=token, base_url=base_url)


async def _resolve_backend(tenant_id: uuid.UUID) -> CatalogBackend:
    """Pick the catalogue backend for ``tenant_id``. Amigable wins."""
    if await _amigable_is_connected(tenant_id):
        return await _load_amigable_venta_client(tenant_id)
    if await _has_local_catalog(tenant_id):
        return LocalCatalogClient(tenant_id)
    raise InventoryNotConfigured(
        "this tenant has no catalogue: connect the Amigable Venta connector "
        "or import a catalogue into local_catalog_products"
    )


# ── test hook ────────────────────────────────────────────────────────────


_client_override: CatalogBackend | None = None


def set_test_client(client: CatalogBackend | None) -> None:
    """Bypass credential resolution. Test-only."""
    global _client_override
    _client_override = client


async def _resolve_client(tenant_id: uuid.UUID) -> CatalogBackend:
    if _client_override is not None:
        return _client_override
    return await _resolve_backend(tenant_id)


# ── shaping ──────────────────────────────────────────────────────────────


def _fold(text: str) -> str:
    """Lowercase and strip accents so 'Acetaminofén' == 'acetaminofen'."""
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.casefold().strip()


def _to_variant(raw: dict[str, Any]) -> ProductVariant:
    stock = int(raw.get("stock_actual") or 0)
    minimo = int(raw.get("stock_minimo") or 0)
    return ProductVariant(
        sku=str(raw.get("sku") or ""),
        nombre=str(raw.get("nombre") or ""),
        categoria=raw.get("categoria"),
        precio_usd=round(float(raw.get("precio_usd") or 0), 2),
        stock_actual=stock,
        stock_minimo=minimo,
        bajo_minimo=stock <= minimo,
        agotado=stock == 0,
    )


def _group_by_name(variants: list[ProductVariant]) -> list[ProductGroup]:
    """Collapse variants into one entry per product name.

    Grouping key is the folded name, so accent/case drift in the source
    data does not split a product in two. The reported name is the first
    spelling seen.
    """
    buckets: dict[str, list[ProductVariant]] = {}
    for v in variants:
        buckets.setdefault(_fold(v.nombre), []).append(v)

    groups: list[ProductGroup] = []
    for members in buckets.values():
        prices = [m.precio_usd for m in members]
        groups.append(
            ProductGroup(
                nombre=members[0].nombre,
                categoria=members[0].categoria,
                variantes=len(members),
                stock_total=sum(m.stock_actual for m in members),
                precio_min=min(prices),
                precio_max=max(prices),
                variantes_bajo_minimo=sum(1 for m in members if m.bajo_minimo),
                skus=[m.sku for m in members],
            )
        )
    return groups


def _best_group(
    variants: list[ProductVariant], query: str
) -> tuple[list[ProductVariant], list[str], bool]:
    """Pick the product the query most likely meant.

    Returns ``(members, other_names, ambiguous)``. An exact SKU match wins
    outright — asking for FARM-00001 is unambiguous by construction. Then
    exact folded name, then the shortest name containing the query (the
    shortest is the base product: "Ibuprofeno" over "Ibuprofeno Gel
    tópico"), then whatever came back first.
    """
    if not variants:
        return [], [], False

    folded_query = _fold(query)

    for v in variants:
        if _fold(v.sku) == folded_query:
            members = [m for m in variants if _fold(m.nombre) == _fold(v.nombre)]
            others = _other_names(variants, v.nombre)
            return members, others, False

    buckets: dict[str, list[ProductVariant]] = {}
    for v in variants:
        buckets.setdefault(_fold(v.nombre), []).append(v)

    chosen_key: str | None = None
    if folded_query in buckets:
        chosen_key = folded_query
    else:
        containing = [k for k in buckets if folded_query in k]
        if containing:
            chosen_key = min(containing, key=len)
        else:
            chosen_key = next(iter(buckets))

    members = buckets[chosen_key]
    others = _other_names(variants, members[0].nombre)
    return members, others, len(buckets) > 1


def _other_names(variants: list[ProductVariant], chosen: str) -> list[str]:
    seen: list[str] = []
    chosen_folded = _fold(chosen)
    for v in variants:
        if _fold(v.nombre) == chosen_folded:
            continue
        if v.nombre not in seen:
            seen.append(v.nombre)
        if len(seen) >= 8:
            break
    return seen


# ── tools ────────────────────────────────────────────────────────────────


class _InventoryTool(ToolBase):
    """Shared client resolution for every inventory.* tool.

    Every tool here is a read-only lookup: no side effect to block, so the
    QA Playground (dry_run) executes them for real. Reading stock is
    idempotent and is exactly what the operator needs to preview.
    """

    side_effects: ClassVar[tuple[str, ...]] = ()

    async def _client(self) -> CatalogBackend:
        return await _resolve_client(require_current_tenant())


class SearchProducts(_InventoryTool):
    name = "inventory.search_products"
    description = (
        "Busca productos del inventario por NOMBRE o SKU y los devuelve AGRUPADOS "
        "por producto, con cuántas variantes tiene cada uno, el stock sumado y el "
        "rango de precios. Úsala para '¿tenemos X?', '¿qué jarabes hay?' o para "
        "ubicar un producto antes de pedir su detalle. No busca por categoría ni "
        "por tipo. Si truncado=true hay coincidencias que no se ven: pide un "
        "término más específico en vez de afirmar que eso es todo."
    )
    input_model = SearchProductsInput
    output_model = SearchProductsOutput

    async def run(self, payload: SearchProductsInput) -> SearchProductsOutput:  # type: ignore[override]
        client = await self._client()
        rows, truncated = await client.search_products(payload.query)
        variants = [_to_variant(r) for r in rows]
        groups = _group_by_name(variants)
        groups.sort(key=lambda g: (-g.stock_total, g.nombre))
        return SearchProductsOutput(
            query=payload.query,
            productos_encontrados=len(groups),
            variantes_encontradas=len(variants),
            devueltos=min(len(groups), payload.limit),
            truncado=truncated,
            items=groups[: payload.limit],
        )


class GetProduct(_InventoryTool):
    name = "inventory.get_product"
    description = (
        "Devuelve el detalle COMPLETO de un producto: todas sus variantes con SKU, "
        "precio, stock y umbral de reposición. Úsala cuando pregunten por las "
        "variantes, las presentaciones o los precios de un producto concreto. "
        "Acepta nombre o SKU. Si ambiguo=true, la búsqueda coincidió con varios "
        "productos: di cuál elegiste y ofrece otros_candidatos antes de dar el "
        "dato por bueno."
    )
    input_model = GetProductInput
    output_model = GetProductOutput

    async def run(self, payload: GetProductInput) -> GetProductOutput:  # type: ignore[override]
        client = await self._client()
        rows, _truncated = await client.search_products(payload.query)
        variants = [_to_variant(r) for r in rows]
        members, others, ambiguous = _best_group(variants, payload.query)
        if not members:
            return GetProductOutput(encontrado=False, query=payload.query)
        members.sort(key=lambda m: m.precio_usd)
        prices = [m.precio_usd for m in members]
        return GetProductOutput(
            encontrado=True,
            query=payload.query,
            nombre=members[0].nombre,
            categoria=members[0].categoria,
            variantes=len(members),
            stock_total=sum(m.stock_actual for m in members),
            precio_min=min(prices),
            precio_max=max(prices),
            ambiguo=ambiguous,
            otros_candidatos=others,
            detalle=members,
        )


class CheckStock(_InventoryTool):
    name = "inventory.check_stock"
    description = (
        "Valida cuántas unidades hay de un producto, sumando todas sus variantes y "
        "desglosando por SKU. Úsala para '¿cuántos X tenemos?', '¿queda X?' o "
        "'¿hay que reponer X?'. Acepta nombre o SKU. Responde con el total y "
        "señala las variantes agotadas o por debajo de su mínimo."
    )
    input_model = CheckStockInput
    output_model = CheckStockOutput

    async def run(self, payload: CheckStockInput) -> CheckStockOutput:  # type: ignore[override]
        client = await self._client()
        rows, _truncated = await client.search_products(payload.query)
        variants = [_to_variant(r) for r in rows]
        members, _others, _ambiguous = _best_group(variants, payload.query)
        if not members:
            return CheckStockOutput(encontrado=False, query=payload.query)
        members.sort(key=lambda m: -m.stock_actual)
        total = sum(m.stock_actual for m in members)
        return CheckStockOutput(
            encontrado=True,
            query=payload.query,
            nombre=members[0].nombre,
            stock_total=total,
            hay_stock=total > 0,
            variantes=len(members),
            variantes_agotadas=sum(1 for m in members if m.agotado),
            variantes_bajo_minimo=sum(1 for m in members if m.bajo_minimo),
            detalle=members,
        )


class LowStock(_InventoryTool):
    name = "inventory.low_stock"
    description = (
        "Lista las variantes que hay que REPONER dentro de una familia de "
        "productos: las que están en o por debajo de su stock mínimo, las más "
        "críticas primero. Requiere un término de búsqueda porque el API no "
        "permite recorrer el catálogo entero, solo buscar. Si truncado=true la "
        "revisión no cubrió todo: acota el término."
    )
    input_model = LowStockInput
    output_model = LowStockOutput

    async def run(self, payload: LowStockInput) -> LowStockOutput:  # type: ignore[override]
        client = await self._client()
        rows, truncated = await client.search_products(payload.query)
        variants = [_to_variant(r) for r in rows]
        flagged = [v for v in variants if v.bajo_minimo]
        if not payload.incluir_agotados:
            flagged = [v for v in flagged if not v.agotado]
        # Most critical first: how far below the threshold, then how few
        # units are left. A SKU 30 units under its minimum outranks one
        # sitting exactly on it.
        flagged.sort(key=lambda v: (v.stock_actual - v.stock_minimo, v.stock_actual))
        return LowStockOutput(
            query=payload.query,
            revisadas=len(variants),
            bajo_minimo=sum(1 for v in variants if v.bajo_minimo),
            agotadas=sum(1 for v in variants if v.agotado),
            devueltas=min(len(flagged), payload.limit),
            truncado=truncated,
            items=flagged[: payload.limit],
        )


INVENTORY_TOOLS: tuple[type[ToolBase], ...] = (
    SearchProducts,
    GetProduct,
    CheckStock,
    LowStock,
)


def build_inventory_tools() -> list[ToolBase]:
    return [cls() for cls in INVENTORY_TOOLS]


__all__ = [
    "INVENTORY_TOOLS",
    "InventoryNotConfigured",
    "build_inventory_tools",
    "set_test_client",
]
