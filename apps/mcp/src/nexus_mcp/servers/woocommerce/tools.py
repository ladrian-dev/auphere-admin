"""LLM-facing WooCommerce tools.

Lifecycle of a tool call:

1. ``MCPRegistry.dispatch`` asserts tenant context + whitelist, then
   calls ``tool.invoke(args)``.
2. ``ToolBase.invoke`` validates args against the Pydantic input model
   and re-asserts ``require_current_tenant``.
3. The tool's ``run`` method loads the tenant's WooCommerce credentials
   (one DB read per turn — could be cached later, intentionally NOT
   cached now to keep the tenant boundary obvious), constructs a fresh
   ``WooCommerceClient``, and calls the relevant WooCommerce endpoint.
4. The vendor response is reshaped into the tool's Pydantic output
   model. Descriptions are HTML-stripped and truncated; ``meta_data``
   is dropped entirely.

Credential resolution lives in ``_load_woocommerce_client`` so it's
the single place to change if we add caching or a secret-rotation
path later. The function reads ``tenant_connectors.credentials_ref``,
fetches the ``tenant_credentials`` row by id, decrypts the Fernet
payload, and returns a ready ``WooCommerceClient``.
"""

from __future__ import annotations

import html
import json
import re
import uuid
from typing import Any, ClassVar

import structlog
from nexus_api.core.tenant_context import (
    require_current_tenant,
    tenant_scoped_session,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Connector,
    TenantConnector,
    TenantConnectorStatus,
    TenantCredentials,
)
from sqlalchemy import select

from nexus_mcp.base import ToolBase, ToolError
from nexus_mcp.servers.woocommerce.client import WooCommerceClient
from nexus_mcp.servers.woocommerce.errors import (
    WooCommerceAuthError,
    WooCommerceNotFound,
)
from nexus_mcp.servers.woocommerce.schemas import (
    AddOrderNoteInput,
    AddOrderNoteOutput,
    AddressInput,
    AddressOutput,
    AttributeCompact,
    Category,
    CategoryRef,
    CreateOrderInput,
    CreateOrderOutput,
    Customer,
    GetCustomerInput,
    GetCustomerOutput,
    GetOrderInput,
    GetOrderOutput,
    GetProductInput,
    GetProductOutput,
    ImageRef,
    LineItemOutput,
    ListCategoriesInput,
    ListCategoriesOutput,
    ListCustomersInput,
    ListCustomersOutput,
    ListOrdersInput,
    ListOrdersOutput,
    ListProductsInput,
    ListProductsOutput,
    ListProductVariationsInput,
    ListProductVariationsOutput,
    OrderDetail,
    OrderNote,
    OrderSummary,
    ProductDetail,
    ProductSummary,
    ProductVariation,
    UpdateOrderInput,
    UpdateOrderOutput,
    UpdateOrderStatusInput,
    UpdateOrderStatusOutput,
)

log = structlog.get_logger(__name__)

_WOOCOMMERCE_SLUG = "woocommerce"
_DESCRIPTION_MAX = 500


# ── credential resolution ────────────────────────────────────────────────


class WooCommerceNotConfigured(ToolError):
    """No active ``tenant_connectors`` row for WooCommerce. The pipeline
    will surface this as a clean "connector not connected" message
    rather than a stack trace."""


async def _load_woocommerce_client(tenant_id: uuid.UUID) -> WooCommerceClient:
    """Resolve the active WooCommerce install for ``tenant_id`` and
    return a ready client.

    Raises ``WooCommerceNotConfigured`` if no install exists or its
    status excludes it from active use.
    """
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        row = (
            await session.execute(
                select(TenantConnector, Connector)
                .join(Connector, Connector.id == TenantConnector.connector_id)
                .where(
                    TenantConnector.tenant_id == tenant_id,
                    Connector.slug == _WOOCOMMERCE_SLUG,
                    TenantConnector.status.in_(
                        [
                            TenantConnectorStatus.CONNECTED.value,
                            TenantConnectorStatus.PARTIAL.value,
                        ]
                    ),
                )
            )
        ).first()
        if row is None:
            raise WooCommerceNotConfigured("WooCommerce connector is not connected for this tenant")
        tc: TenantConnector = row[0]
        cred_ref: dict[str, Any] = tc.credentials_ref or {}
        tenant_credentials_id_raw = cred_ref.get("tenant_credentials_id")
        endpoint_meta = cred_ref.get("endpoint_meta") or {}
        store_url = endpoint_meta.get("store_url")
        if not (tenant_credentials_id_raw and store_url):
            raise WooCommerceNotConfigured(
                "WooCommerce credentials_ref missing tenant_credentials_id or "
                "endpoint_meta.store_url"
            )
        try:
            tenant_credentials_id = uuid.UUID(str(tenant_credentials_id_raw))
        except ValueError as exc:
            raise WooCommerceNotConfigured(
                f"WooCommerce credentials_ref.tenant_credentials_id is not a UUID: "
                f"{tenant_credentials_id_raw!r}"
            ) from exc

        creds_row = await session.get(TenantCredentials, tenant_credentials_id)
        if creds_row is None:
            raise WooCommerceNotConfigured(
                f"tenant_credentials row {tenant_credentials_id} not found"
            )
        if creds_row.needs_reauth:
            raise WooCommerceAuthError(
                "WooCommerce credentials flagged for reauth", status_code=401
            )
        try:
            payload = json.loads(bytes(creds_row.encrypted_payload).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise WooCommerceNotConfigured(
                f"WooCommerce credentials payload is not valid JSON: {exc}"
            ) from exc

    consumer_key = payload.get("consumer_key")
    consumer_secret = payload.get("consumer_secret")
    if not (isinstance(consumer_key, str) and isinstance(consumer_secret, str)):
        raise WooCommerceNotConfigured(
            "WooCommerce credentials payload missing consumer_key / consumer_secret"
        )
    return WooCommerceClient(
        store_url=store_url,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
    )


# ── test hook ────────────────────────────────────────────────────────────


_client_override: WooCommerceClient | None = None


def set_test_client(client: WooCommerceClient | None) -> None:
    """Bypass credential resolution. Test-only — call from a fixture
    and reset to None at teardown. Never used in production."""
    global _client_override
    _client_override = client


async def _resolve_client(tenant_id: uuid.UUID) -> WooCommerceClient:
    if _client_override is not None:
        return _client_override
    return await _load_woocommerce_client(tenant_id)


_WC_POST_ID_RE = re.compile(r"^wc_post_id_(\d+)$")


async def _resolve_retailer_id(
    client: WooCommerceClient, retailer_id: str
) -> tuple[int | None, int | None]:
    """Map a Meta catalog ``retailer_id`` back to a WooCommerce
    ``(product_id, variation_id)``.

    The Facebook-for-WooCommerce plugin sets each catalog item's
    retailer_id to the product SKU when present, else ``wc_post_id_{id}``.
    A native WhatsApp cart returns those retailer_ids, so to create the
    WooCommerce order we reverse the mapping:

    - ``wc_post_id_{N}`` → ``product_id = N``
    - otherwise treat it as a SKU and look the product up.

    Raises ``ToolError`` when it can't be resolved so the order isn't
    silently created with the wrong items.
    """
    rid = retailer_id.strip()
    m = _WC_POST_ID_RE.match(rid)
    if m:
        return int(m.group(1)), None
    items, _meta = await client.list_paginated(
        "/products", page=1, per_page=1, extra_params={"sku": rid}
    )
    if items:
        return int(items[0]["id"]), None
    raise ToolError(
        f"could not resolve catalog retailer_id {retailer_id!r} to a "
        "WooCommerce product (unknown SKU)"
    )


# ── shared shaping helpers ───────────────────────────────────────────────


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(raw: Any) -> str | None:
    """Strip HTML tags + decode entities + truncate. WooCommerce stores
    descriptions as raw WP HTML; the LLM doesn't benefit from inline
    ``<strong>`` markup, and the long ones blow up context."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = html.unescape(_HTML_TAG_RE.sub("", raw)).strip()
    if not text:
        return None
    if len(text) > _DESCRIPTION_MAX:
        text = text[: _DESCRIPTION_MAX - 1].rstrip() + "…"
    return text


def _first_image(images_raw: Any) -> ImageRef | None:
    if not isinstance(images_raw, list) or not images_raw:
        return None
    first = images_raw[0]
    if not isinstance(first, dict):
        return None
    src = first.get("src")
    if not isinstance(src, str) or not src:
        return None
    return ImageRef(src=src)


def _category_refs(categories_raw: Any) -> list[CategoryRef]:
    out: list[CategoryRef] = []
    if not isinstance(categories_raw, list):
        return out
    for c in categories_raw:
        if not isinstance(c, dict):
            continue
        try:
            out.append(
                CategoryRef(
                    id=int(c["id"]),
                    name=str(c["name"]),
                    slug=str(c.get("slug", "")),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _attributes(attributes_raw: Any) -> list[AttributeCompact]:
    out: list[AttributeCompact] = []
    if not isinstance(attributes_raw, list):
        return out
    for a in attributes_raw:
        if not isinstance(a, dict):
            continue
        try:
            out.append(
                AttributeCompact(
                    id=a.get("id") if isinstance(a.get("id"), int) else None,
                    name=str(a.get("name", "")),
                    slug=a.get("slug") if isinstance(a.get("slug"), str) else None,
                    options=[str(o) for o in (a.get("options") or []) if isinstance(o, str)],
                    option=(str(a["option"]) if isinstance(a.get("option"), str) else None),
                    variation=bool(a.get("variation", False)),
                )
            )
        except (TypeError, ValueError):
            continue
    return out


def _product_summary(p: dict[str, Any]) -> ProductSummary:
    return ProductSummary(
        id=int(p["id"]),
        name=str(p.get("name", "")),
        slug=str(p.get("slug", "")),
        sku=p.get("sku") or None,
        type=p.get("type", "simple"),
        status=p.get("status", "publish"),
        price=str(p.get("price", "")),
        regular_price=p.get("regular_price") or None,
        sale_price=p.get("sale_price") or None,
        stock_status=p.get("stock_status", "instock"),
        stock_quantity=(
            int(p["stock_quantity"]) if isinstance(p.get("stock_quantity"), int) else None
        ),
        permalink=p.get("permalink") or None,
        image=_first_image(p.get("images")),
        categories=_category_refs(p.get("categories")),
    )


def _product_detail(p: dict[str, Any]) -> ProductDetail:
    return ProductDetail(
        id=int(p["id"]),
        name=str(p.get("name", "")),
        slug=str(p.get("slug", "")),
        sku=p.get("sku") or None,
        type=p.get("type", "simple"),
        status=p.get("status", "publish"),
        short_description=_clean_text(p.get("short_description")),
        description=_clean_text(p.get("description")),
        price=str(p.get("price", "")),
        regular_price=p.get("regular_price") or None,
        sale_price=p.get("sale_price") or None,
        on_sale=bool(p.get("on_sale", False)),
        stock_status=p.get("stock_status", "instock"),
        stock_quantity=(
            int(p["stock_quantity"]) if isinstance(p.get("stock_quantity"), int) else None
        ),
        manage_stock=bool(p.get("manage_stock", False)),
        permalink=p.get("permalink") or None,
        image=_first_image(p.get("images")),
        categories=_category_refs(p.get("categories")),
        attributes=_attributes(p.get("attributes")),
        variations=[int(v) for v in (p.get("variations") or []) if isinstance(v, int)],
    )


def _variation(v: dict[str, Any]) -> ProductVariation:
    image = None
    raw_image = v.get("image")
    if isinstance(raw_image, dict):
        src = raw_image.get("src")
        if isinstance(src, str) and src:
            image = ImageRef(src=src)
    return ProductVariation(
        id=int(v["id"]),
        sku=v.get("sku") or None,
        price=str(v.get("price", "")),
        regular_price=v.get("regular_price") or None,
        sale_price=v.get("sale_price") or None,
        on_sale=bool(v.get("on_sale", False)),
        stock_status=v.get("stock_status", "instock"),
        stock_quantity=(
            int(v["stock_quantity"]) if isinstance(v.get("stock_quantity"), int) else None
        ),
        image=image,
        attributes=_attributes(v.get("attributes")),
    )


def _address_out(raw: Any) -> AddressOutput:
    if not isinstance(raw, dict):
        return AddressOutput()
    return AddressOutput(
        first_name=raw.get("first_name") or None,
        last_name=raw.get("last_name") or None,
        company=raw.get("company") or None,
        address_1=raw.get("address_1") or None,
        address_2=raw.get("address_2") or None,
        city=raw.get("city") or None,
        state=raw.get("state") or None,
        postcode=raw.get("postcode") or None,
        country=raw.get("country") or None,
        email=raw.get("email") or None,
        phone=raw.get("phone") or None,
    )


def _line_items(items_raw: Any) -> list[LineItemOutput]:
    out: list[LineItemOutput] = []
    if not isinstance(items_raw, list):
        return out
    for li in items_raw:
        if not isinstance(li, dict):
            continue
        try:
            out.append(
                LineItemOutput(
                    id=int(li["id"]),
                    name=str(li.get("name", "")),
                    product_id=int(li["product_id"]),
                    variation_id=(
                        int(li["variation_id"])
                        if isinstance(li.get("variation_id"), int) and li["variation_id"]
                        else None
                    ),
                    sku=li.get("sku") or None,
                    quantity=int(li.get("quantity", 1)),
                    price=str(li.get("price", "")),
                    subtotal=str(li.get("subtotal", "")),
                    total=str(li.get("total", "")),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _order_summary(o: dict[str, Any]) -> OrderSummary:
    return OrderSummary(
        id=int(o["id"]),
        number=str(o.get("number", o.get("id", ""))),
        status=o.get("status", "pending"),
        currency=str(o.get("currency", "")),
        date_created=o.get("date_created") or None,
        total=str(o.get("total", "")),
        customer_id=int(o.get("customer_id", 0)),
        customer_note=o.get("customer_note") or None,
        payment_method=o.get("payment_method") or None,
        payment_method_title=o.get("payment_method_title") or None,
    )


def _order_detail(o: dict[str, Any]) -> OrderDetail:
    return OrderDetail(
        id=int(o["id"]),
        number=str(o.get("number", o.get("id", ""))),
        status=o.get("status", "pending"),
        currency=str(o.get("currency", "")),
        date_created=o.get("date_created") or None,
        date_modified=o.get("date_modified") or None,
        date_paid=o.get("date_paid") or None,
        total=str(o.get("total", "")),
        subtotal=o.get("subtotal") or None,
        total_tax=o.get("total_tax") or None,
        shipping_total=o.get("shipping_total") or None,
        discount_total=o.get("discount_total") or None,
        customer_id=int(o.get("customer_id", 0)),
        customer_note=o.get("customer_note") or None,
        billing=_address_out(o.get("billing")),
        shipping=_address_out(o.get("shipping")),
        payment_method=o.get("payment_method") or None,
        payment_method_title=o.get("payment_method_title") or None,
        transaction_id=o.get("transaction_id") or None,
        payment_url=o.get("payment_url") or None,
        line_items=_line_items(o.get("line_items")),
    )


def _customer(c: dict[str, Any]) -> Customer:
    billing = c.get("billing") if isinstance(c.get("billing"), dict) else {}
    return Customer(
        id=int(c["id"]),
        email=str(c.get("email", "")),
        first_name=c.get("first_name") or None,
        last_name=c.get("last_name") or None,
        username=c.get("username") or None,
        role=c.get("role") or None,
        billing_phone=billing.get("phone") if isinstance(billing, dict) else None,
        date_created=c.get("date_created") or None,
    )


def _address_to_payload(addr: AddressInput | None) -> dict[str, Any] | None:
    if addr is None:
        return None
    # WooCommerce expects an empty string rather than null for unset
    # address fields. Convert here so the LLM-supplied None doesn't
    # cause a 400 on patch semantics.
    return {k: ("" if v is None else v) for k, v in addr.model_dump(mode="json").items()}


# ── base class ───────────────────────────────────────────────────────────


class _WooTool(ToolBase):
    """Pulls the client resolution boilerplate out of every tool."""

    side_effects: ClassVar[tuple[str, ...]] = ("external_api",)

    async def _client(self) -> WooCommerceClient:
        return await _resolve_client(require_current_tenant())


# ── read-only tools ──────────────────────────────────────────────────────


class ListProducts(_WooTool):
    name = "woocommerce.list_products"
    description = (
        "List products in the connected WooCommerce store. Supports filtering by "
        "search term, category slug, product type (simple/variable), status, "
        "stock status and an attribute pair (e.g. attribute='pa_color' + "
        "attribute_term='azul' to list every product with the colour 'azul'). "
        "Paginated — inspect total_count and has_more to decide whether to "
        "request a follow-up page."
    )
    input_model = ListProductsInput
    output_model = ListProductsOutput

    async def run(self, payload: ListProductsInput) -> ListProductsOutput:  # type: ignore[override]
        client = await self._client()
        params: dict[str, Any] = {
            "search": payload.search,
            "category": payload.category,
            "type": payload.type,
            "status": payload.status,
            "stock_status": payload.stock_status,
            "attribute": payload.attribute,
            "attribute_term": payload.attribute_term,
        }
        items_raw, meta = await client.list_paginated(
            "/products",
            page=payload.page,
            per_page=payload.per_page,
            extra_params=params,
        )
        return ListProductsOutput(
            items=[_product_summary(p) for p in items_raw],
            page=meta.page,
            per_page=meta.per_page,
            total_count=meta.total_count,
            total_pages=meta.total_pages,
            has_more=meta.has_more,
        )


class GetProduct(_WooTool):
    name = "woocommerce.get_product"
    description = (
        "Fetch one product by id OR by sku. Returns the full product including "
        "attributes (with all available options) and the list of variation ids. "
        "Use woocommerce.list_product_variations to expand variations."
    )
    input_model = GetProductInput
    output_model = GetProductOutput

    async def run(self, payload: GetProductInput) -> GetProductOutput:  # type: ignore[override]
        if (payload.id is None) == (payload.sku is None):
            raise ToolError(
                "GetProduct requires exactly one of id or sku (got "
                f"id={payload.id!r}, sku={payload.sku!r})"
            )
        client = await self._client()
        if payload.id is not None:
            data = await client.get_resource(f"/products/{payload.id}")
        else:
            # WooCommerce lookup by sku uses the list endpoint with the
            # sku query param. It returns an array (0 or 1 item).
            items, _meta = await client.list_paginated(
                "/products", page=1, per_page=1, extra_params={"sku": payload.sku}
            )
            if not items:
                raise WooCommerceNotFound(f"no product with sku={payload.sku!r}", status_code=404)
            data = items[0]
        return GetProductOutput(product=_product_detail(data))


class ListProductVariations(_WooTool):
    name = "woocommerce.list_product_variations"
    description = (
        "List variations of a variable product (e.g. all (size, colour) "
        "combinations of a duvet cover). Returns each variation's id, sku, "
        "price, stock status, image and resolved attribute values. The agent "
        "needs the variation id (not the parent product id) when creating an "
        "order for a specific variation."
    )
    input_model = ListProductVariationsInput
    output_model = ListProductVariationsOutput

    async def run(  # type: ignore[override]
        self, payload: ListProductVariationsInput
    ) -> ListProductVariationsOutput:
        client = await self._client()
        items_raw, meta = await client.list_paginated(
            f"/products/{payload.product_id}/variations",
            page=payload.page,
            per_page=payload.per_page,
        )
        return ListProductVariationsOutput(
            items=[_variation(v) for v in items_raw],
            page=meta.page,
            per_page=meta.per_page,
            total_count=meta.total_count,
            total_pages=meta.total_pages,
            has_more=meta.has_more,
        )


class ListCategories(_WooTool):
    name = "woocommerce.list_categories"
    description = (
        "List product categories. Useful to discover the slug to pass back into "
        "list_products' category filter."
    )
    input_model = ListCategoriesInput
    output_model = ListCategoriesOutput

    async def run(self, payload: ListCategoriesInput) -> ListCategoriesOutput:  # type: ignore[override]
        client = await self._client()
        items_raw, meta = await client.list_paginated(
            "/products/categories",
            page=payload.page,
            per_page=payload.per_page,
            extra_params={
                "search": payload.search,
                "parent": payload.parent,
            },
        )
        items = [
            Category(
                id=int(c["id"]),
                name=str(c.get("name", "")),
                slug=str(c.get("slug", "")),
                parent=int(c.get("parent", 0)),
                description=_clean_text(c.get("description")),
                count=int(c.get("count", 0)),
            )
            for c in items_raw
            if isinstance(c.get("id"), int)
        ]
        return ListCategoriesOutput(
            items=items,
            page=meta.page,
            per_page=meta.per_page,
            total_count=meta.total_count,
            total_pages=meta.total_pages,
            has_more=meta.has_more,
        )


class ListOrders(_WooTool):
    name = "woocommerce.list_orders"
    description = (
        "List orders. Filter by status, customer id, creation date range and "
        "free-text search (customer name / order number). Returns a compact "
        "view per order; call woocommerce.get_order for full details including "
        "line items, billing/shipping address and totals."
    )
    input_model = ListOrdersInput
    output_model = ListOrdersOutput

    async def run(self, payload: ListOrdersInput) -> ListOrdersOutput:  # type: ignore[override]
        client = await self._client()
        items_raw, meta = await client.list_paginated(
            "/orders",
            page=payload.page,
            per_page=payload.per_page,
            extra_params={
                "status": payload.status,
                "customer": payload.customer,
                "after": payload.after,
                "before": payload.before,
                "search": payload.search,
            },
        )
        return ListOrdersOutput(
            items=[_order_summary(o) for o in items_raw],
            page=meta.page,
            per_page=meta.per_page,
            total_count=meta.total_count,
            total_pages=meta.total_pages,
            has_more=meta.has_more,
        )


class GetOrder(_WooTool):
    name = "woocommerce.get_order"
    description = (
        "Fetch one order by id. Returns full details including every line "
        "item (with product_id, variation_id, sku, quantity, totals), the "
        "billing and shipping addresses, and payment metadata."
    )
    input_model = GetOrderInput
    output_model = GetOrderOutput

    async def run(self, payload: GetOrderInput) -> GetOrderOutput:  # type: ignore[override]
        client = await self._client()
        data = await client.get_resource(f"/orders/{payload.id}")
        return GetOrderOutput(order=_order_detail(data))


class ListCustomers(_WooTool):
    name = "woocommerce.list_customers"
    description = (
        "Search customers by email or display name. Returns a compact view; "
        "call woocommerce.get_customer for the full record including billing "
        "phone."
    )
    input_model = ListCustomersInput
    output_model = ListCustomersOutput

    async def run(self, payload: ListCustomersInput) -> ListCustomersOutput:  # type: ignore[override]
        client = await self._client()
        items_raw, meta = await client.list_paginated(
            "/customers",
            page=payload.page,
            per_page=payload.per_page,
            extra_params={
                "search": payload.search,
                "email": payload.email,
            },
        )
        return ListCustomersOutput(
            items=[_customer(c) for c in items_raw],
            page=meta.page,
            per_page=meta.per_page,
            total_count=meta.total_count,
            total_pages=meta.total_pages,
            has_more=meta.has_more,
        )


class GetCustomer(_WooTool):
    name = "woocommerce.get_customer"
    description = "Fetch one customer by id OR by email. Exactly one is required."
    input_model = GetCustomerInput
    output_model = GetCustomerOutput

    async def run(self, payload: GetCustomerInput) -> GetCustomerOutput:  # type: ignore[override]
        if (payload.id is None) == (payload.email is None):
            raise ToolError(
                "GetCustomer requires exactly one of id or email "
                f"(got id={payload.id!r}, email={payload.email!r})"
            )
        client = await self._client()
        if payload.id is not None:
            data = await client.get_resource(f"/customers/{payload.id}")
        else:
            items, _meta = await client.list_paginated(
                "/customers",
                page=1,
                per_page=1,
                extra_params={"email": payload.email},
            )
            if not items:
                raise WooCommerceNotFound(
                    f"no customer with email={payload.email!r}", status_code=404
                )
            data = items[0]
        return GetCustomerOutput(customer=_customer(data))


# ── destructive tools ────────────────────────────────────────────────────


class CreateOrder(_WooTool):
    name = "woocommerce.create_order"
    description = (
        "Create a new order. Each line item must reference a product_id, a "
        "variation_id (for variable products), or both — the variation_id "
        "wins when both are supplied. Status defaults to 'pending' so the "
        "operator can review; call update_order_status to move it forward "
        "once payment is confirmed."
    )
    input_model = CreateOrderInput
    output_model = CreateOrderOutput
    side_effects: ClassVar[tuple[str, ...]] = ("external_api", "mutates_db")

    async def run(self, payload: CreateOrderInput) -> CreateOrderOutput:  # type: ignore[override]
        client = await self._client()
        line_items_payload: list[dict[str, Any]] = []
        for li in payload.line_items:
            product_id = li.product_id
            variation_id = li.variation_id
            # Native-cart items arrive as Meta catalog retailer_ids. Resolve
            # them to WooCommerce ids server-side (deterministic; not via the
            # LLM) so the same cart the customer built maps to real products.
            if product_id is None and variation_id is None and li.retailer_id:
                product_id, variation_id = await _resolve_retailer_id(client, li.retailer_id)
            if product_id is None and variation_id is None:
                raise ToolError(
                    "every line_item must include product_id, variation_id, or a "
                    "resolvable retailer_id"
                )
            item: dict[str, Any] = {"quantity": li.quantity}
            if product_id is not None:
                item["product_id"] = product_id
            if variation_id is not None:
                item["variation_id"] = variation_id
            if li.subtotal is not None:
                item["subtotal"] = li.subtotal
            line_items_payload.append(item)

        body: dict[str, Any] = {
            "line_items": line_items_payload,
            "status": payload.status,
        }
        if payload.customer_id is not None:
            body["customer_id"] = payload.customer_id
        billing = _address_to_payload(payload.billing)
        if billing:
            body["billing"] = billing
        shipping = _address_to_payload(payload.shipping)
        if shipping:
            body["shipping"] = shipping
        if payload.payment_method:
            body["payment_method"] = payload.payment_method
        if payload.payment_method_title:
            body["payment_method_title"] = payload.payment_method_title
        if payload.customer_note:
            body["customer_note"] = payload.customer_note
        if payload.meta_data:
            body["meta_data"] = payload.meta_data

        data = await client.post_resource("/orders", payload=body)
        log.info(
            "woocommerce.order_created",
            order_id=data.get("id"),
            status=data.get("status"),
            line_items=len(line_items_payload),
        )
        return CreateOrderOutput(order=_order_detail(data))


class UpdateOrderStatus(_WooTool):
    name = "woocommerce.update_order_status"
    description = (
        "Move an existing order to a different status (pending, processing, "
        "on-hold, completed, cancelled, refunded, failed). Returns the "
        "previous and new status for audit."
    )
    input_model = UpdateOrderStatusInput
    output_model = UpdateOrderStatusOutput
    side_effects: ClassVar[tuple[str, ...]] = ("external_api", "mutates_db")

    async def run(  # type: ignore[override]
        self, payload: UpdateOrderStatusInput
    ) -> UpdateOrderStatusOutput:
        client = await self._client()
        # Read first so we can report previous_status. One extra round
        # trip but worth it for the audit signal.
        before = await client.get_resource(f"/orders/{payload.id}")
        previous_status = before.get("status", "pending")
        after = await client.put_resource(
            f"/orders/{payload.id}", payload={"status": payload.status}
        )
        log.info(
            "woocommerce.order_status_changed",
            order_id=payload.id,
            previous_status=previous_status,
            new_status=after.get("status"),
        )
        return UpdateOrderStatusOutput(
            id=int(after["id"]),
            previous_status=previous_status,
            status=after.get("status", payload.status),
            date_modified=after.get("date_modified") or None,
        )


class UpdateOrder(_WooTool):
    name = "woocommerce.update_order"
    description = (
        "Update a restricted set of fields on an existing order: billing / "
        "shipping address, customer note, payment method. Status changes go "
        "through update_order_status (separate tool for clearer audit)."
    )
    input_model = UpdateOrderInput
    output_model = UpdateOrderOutput
    side_effects: ClassVar[tuple[str, ...]] = ("external_api", "mutates_db")

    async def run(self, payload: UpdateOrderInput) -> UpdateOrderOutput:  # type: ignore[override]
        client = await self._client()
        body: dict[str, Any] = {}
        billing = _address_to_payload(payload.billing)
        if billing is not None:
            body["billing"] = billing
        shipping = _address_to_payload(payload.shipping)
        if shipping is not None:
            body["shipping"] = shipping
        if payload.customer_note is not None:
            body["customer_note"] = payload.customer_note
        if payload.payment_method is not None:
            body["payment_method"] = payload.payment_method
        if payload.payment_method_title is not None:
            body["payment_method_title"] = payload.payment_method_title
        if not body:
            raise ToolError("update_order requires at least one field to change")
        data = await client.put_resource(f"/orders/{payload.id}", payload=body)
        log.info("woocommerce.order_updated", order_id=payload.id, fields=list(body.keys()))
        return UpdateOrderOutput(order=_order_detail(data))


class AddOrderNote(_WooTool):
    name = "woocommerce.add_order_note"
    description = (
        "Add a note to an order. If customer_note=True the note is emailed "
        "to the customer; otherwise it stays internal (visible in WP-Admin "
        "only)."
    )
    input_model = AddOrderNoteInput
    output_model = AddOrderNoteOutput
    side_effects: ClassVar[tuple[str, ...]] = ("external_api", "mutates_db")

    async def run(self, payload: AddOrderNoteInput) -> AddOrderNoteOutput:  # type: ignore[override]
        client = await self._client()
        data = await client.post_resource(
            f"/orders/{payload.order_id}/notes",
            payload={
                "note": payload.note,
                "customer_note": payload.customer_note,
            },
        )
        log.info(
            "woocommerce.order_note_added",
            order_id=payload.order_id,
            note_id=data.get("id"),
            customer_visible=payload.customer_note,
        )
        return AddOrderNoteOutput(
            note=OrderNote(
                id=int(data["id"]),
                author=data.get("author") or None,
                date_created=data.get("date_created") or None,
                note=str(data.get("note", payload.note)),
                customer_note=bool(data.get("customer_note", payload.customer_note)),
            )
        )


# ── tool collection ─────────────────────────────────────────────────────


# Order matters only for stable schema-snapshot diffs; alphabetical
# inside each kind (read-only / destructive) keeps PRs reviewable.
WOOCOMMERCE_TOOLS: tuple[type[ToolBase], ...] = (
    # read-only
    GetCustomer,
    GetOrder,
    GetProduct,
    ListCategories,
    ListCustomers,
    ListOrders,
    ListProductVariations,
    ListProducts,
    # destructive
    AddOrderNote,
    CreateOrder,
    UpdateOrder,
    UpdateOrderStatus,
)


def build_woocommerce_tools() -> list[ToolBase]:
    """Materialise tool instances. The MCP registry calls this once at
    process startup from ``build_default_registry``."""
    return [cls() for cls in WOOCOMMERCE_TOOLS]


__all__ = [
    "WOOCOMMERCE_TOOLS",
    "AddOrderNote",
    "CreateOrder",
    "GetCustomer",
    "GetOrder",
    "GetProduct",
    "ListCategories",
    "ListCustomers",
    "ListOrders",
    "ListProductVariations",
    "ListProducts",
    "UpdateOrder",
    "UpdateOrderStatus",
    "WooCommerceNotConfigured",
    "build_woocommerce_tools",
    "set_test_client",
]
