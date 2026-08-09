"""Unit tests for the WooCommerce MCP tools.

DB-free: tools use the ``set_test_client`` hook to bypass credential
resolution. Each test injects a FakeWooClient that records calls and
returns canned responses.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from nexus_api.core.tenant_context import tenant_context

from nexus_mcp.http import PaginationMeta
from nexus_mcp.servers.woocommerce.client import WooCommerceClient
from nexus_mcp.servers.woocommerce.errors import (
    WooCommerceAuthError,
    WooCommerceNotFound,
)
from nexus_mcp.servers.woocommerce.tools import (
    WOOCOMMERCE_TOOLS,
    AddOrderNote,
    BuildCheckoutLink,
    CreateOrder,
    GetCustomer,
    GetOrder,
    GetProduct,
    ListCategories,
    ListCustomers,
    ListOrders,
    ListProducts,
    ListProductVariations,
    UpdateOrder,
    UpdateOrderStatus,
    set_test_client,
)

pytestmark = [pytest.mark.unit]


# ── fake client ──────────────────────────────────────────────────────────


class FakeWooClient(WooCommerceClient):
    """Bypasses real HTTP. Records every call so tests can assert
    exact endpoint + params the tools build."""

    def __init__(self) -> None:
        # Skip the parent __init__ — we don't want it validating
        # store_url etc. We're a fake.
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.store_url = "https://barbersupply.cl"
        self.next_list: tuple[list[dict[str, Any]], PaginationMeta] | None = None
        self.next_get: dict[str, Any] | None = None
        self.next_post: dict[str, Any] | None = None
        self.next_put: dict[str, Any] | None = None
        self.raise_on_call: Exception | None = None

    async def list_paginated(  # type: ignore[override]
        self,
        path: str,
        *,
        page: int,
        per_page: int,
        extra_params: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], PaginationMeta]:
        self.calls.append(
            ("list", {"path": path, "page": page, "per_page": per_page, "params": extra_params})
        )
        if self.raise_on_call is not None:
            raise self.raise_on_call
        assert self.next_list is not None, f"unexpected list call to {path}"
        return self.next_list

    async def get_resource(  # type: ignore[override]
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append(("get", {"path": path, "params": params}))
        if self.raise_on_call is not None:
            raise self.raise_on_call
        assert self.next_get is not None, f"unexpected get call to {path}"
        return self.next_get

    async def post_resource(  # type: ignore[override]
        self, path: str, *, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(("post", {"path": path, "payload": payload}))
        if self.raise_on_call is not None:
            raise self.raise_on_call
        assert self.next_post is not None, f"unexpected post call to {path}"
        return self.next_post

    async def put_resource(  # type: ignore[override]
        self, path: str, *, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(("put", {"path": path, "payload": payload}))
        if self.raise_on_call is not None:
            raise self.raise_on_call
        assert self.next_put is not None, f"unexpected put call to {path}"
        return self.next_put


# ── fixtures ─────────────────────────────────────────────────────────────


_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def fake_client() -> FakeWooClient:
    c = FakeWooClient()
    set_test_client(c)
    yield c
    set_test_client(None)


@pytest.fixture
def tenant_ctx():
    with tenant_context(_TENANT):
        yield _TENANT


# ── catalog sanity ───────────────────────────────────────────────────────


def test_catalog_has_thirteen_tools():
    assert len(WOOCOMMERCE_TOOLS) == 13
    names = {cls.name for cls in WOOCOMMERCE_TOOLS}
    assert "woocommerce.list_products" in names
    assert "woocommerce.list_product_variations" in names
    assert "woocommerce.create_order" in names
    assert "woocommerce.update_order_status" in names
    assert "woocommerce.build_checkout_link" in names


def test_destructive_tools_marked_with_mutates_db():
    destructive = {
        "woocommerce.add_order_note",
        "woocommerce.create_order",
        "woocommerce.update_order",
        "woocommerce.update_order_status",
    }
    for cls in WOOCOMMERCE_TOOLS:
        if cls.name in destructive:
            assert "mutates_db" in cls.side_effects, cls.name
        else:
            assert "mutates_db" not in cls.side_effects, cls.name


# ── list_products ────────────────────────────────────────────────────────


async def test_list_products_paginates_and_filters(fake_client, tenant_ctx):
    fake_client.next_list = (
        [
            {
                "id": 7,
                "name": "Funda Queen Azul",
                "slug": "funda-queen-azul",
                "sku": "FQ-AZ",
                "type": "variable",
                "status": "publish",
                "price": "199.00",
                "stock_status": "instock",
                "stock_quantity": 12,
                "images": [{"src": "https://shop.example.com/img/funda.jpg"}],
                "categories": [{"id": 3, "name": "Fundas", "slug": "fundas"}],
            }
        ],
        PaginationMeta(page=1, per_page=20, total_count=300, total_pages=15, has_more=True),
    )

    result = await ListProducts().invoke(
        {
            "search": "funda",
            "type": "variable",
            "attribute": "pa_color",
            "attribute_term": "azul",
            "page": 1,
            "per_page": 20,
        }
    )

    # Tool envelope shape
    assert result["status"] == "ok"
    out = result["result"]
    assert out["page"] == 1
    assert out["per_page"] == 20
    assert out["total_count"] == 300
    assert out["has_more"] is True
    assert len(out["items"]) == 1
    item = out["items"][0]
    assert item["id"] == 7
    assert item["type"] == "variable"
    assert item["categories"][0]["slug"] == "fundas"
    assert item["image"]["src"].startswith("https://")

    # The tool built the right query
    assert len(fake_client.calls) == 1
    kind, payload = fake_client.calls[0]
    assert kind == "list"
    assert payload["path"] == "/products"
    assert payload["params"]["type"] == "variable"
    assert payload["params"]["attribute"] == "pa_color"
    assert payload["params"]["attribute_term"] == "azul"


# ── get_product ──────────────────────────────────────────────────────────


async def test_get_product_strips_html_and_returns_variations(fake_client, tenant_ctx):
    fake_client.next_get = {
        "id": 42,
        "name": "Plumón King",
        "slug": "plumon-king",
        "sku": "PK-1",
        "type": "variable",
        "status": "publish",
        "short_description": "<p>Plumón <strong>120x200</strong> &amp; relleno premium.</p>",
        "description": "<div>" + ("Texto largo. " * 200) + "</div>",
        "price": "299.00",
        "stock_status": "instock",
        "categories": [{"id": 5, "name": "Plumones", "slug": "plumones"}],
        "attributes": [
            {
                "id": 1,
                "name": "Tamaño",
                "slug": "pa_size",
                "options": ["queen", "king"],
                "variation": True,
            },
            {
                "id": 2,
                "name": "Color",
                "slug": "pa_color",
                "options": ["azul", "gris"],
                "variation": True,
            },
        ],
        "variations": [101, 102, 103, 104],
    }

    result = await GetProduct().invoke({"id": 42})
    product = result["result"]["product"]

    assert product["id"] == 42
    assert product["short_description"] == "Plumón 120x200 & relleno premium."
    # description truncated at 500
    assert product["description"] is not None
    assert len(product["description"]) <= 500
    assert product["description"].endswith("…")
    assert product["variations"] == [101, 102, 103, 104]
    assert {a["slug"] for a in product["attributes"]} == {"pa_size", "pa_color"}
    assert fake_client.calls[0] == ("get", {"path": "/products/42", "params": None})


async def test_get_product_by_sku_uses_list_endpoint(fake_client, tenant_ctx):
    fake_client.next_list = (
        [
            {
                "id": 99,
                "name": "Base King",
                "slug": "base-king",
                "sku": "BASE-K",
                "type": "simple",
                "status": "publish",
                "price": "499.00",
                "stock_status": "instock",
            }
        ],
        PaginationMeta(page=1, per_page=1, total_count=1, total_pages=1, has_more=False),
    )
    result = await GetProduct().invoke({"sku": "BASE-K"})
    assert result["result"]["product"]["id"] == 99
    kind, payload = fake_client.calls[0]
    assert kind == "list"
    assert payload["params"]["sku"] == "BASE-K"


async def test_get_product_requires_exactly_one_identifier(fake_client, tenant_ctx):
    with pytest.raises(Exception, match="exactly one"):
        await GetProduct().invoke({"id": 1, "sku": "X"})


# ── list_product_variations ──────────────────────────────────────────────


async def test_list_product_variations_returns_attributes(fake_client, tenant_ctx):
    fake_client.next_list = (
        [
            {
                "id": 101,
                "sku": "PK-Q-AZ",
                "price": "299.00",
                "stock_status": "instock",
                "stock_quantity": 4,
                "image": {"src": "https://shop.example.com/img/v.jpg"},
                "attributes": [
                    {"name": "Tamaño", "option": "queen"},
                    {"name": "Color", "option": "azul"},
                ],
            }
        ],
        PaginationMeta(page=1, per_page=50, total_count=4, total_pages=1, has_more=False),
    )
    result = await ListProductVariations().invoke({"product_id": 42})
    items = result["result"]["items"]
    assert items[0]["id"] == 101
    assert items[0]["sku"] == "PK-Q-AZ"
    options = {a["name"]: a["option"] for a in items[0]["attributes"]}
    assert options == {"Tamaño": "queen", "Color": "azul"}
    assert fake_client.calls[0][1]["path"] == "/products/42/variations"


# ── create_order ─────────────────────────────────────────────────────────


async def test_create_order_with_variation_id(fake_client, tenant_ctx):
    fake_client.next_post = {
        "id": 555,
        "number": "555",
        "status": "pending",
        "currency": "CLP",
        "date_created": "2026-05-18T10:00:00",
        "total": "598.00",
        "customer_id": 9,
        "billing": {"first_name": "Ana", "last_name": "Soto", "email": "ana@example.com"},
        "shipping": {"first_name": "Ana", "last_name": "Soto"},
        "line_items": [
            {
                "id": 1,
                "name": "Plumón King Queen Azul",
                "product_id": 42,
                "variation_id": 101,
                "sku": "PK-Q-AZ",
                "quantity": 2,
                "price": "299.00",
                "subtotal": "598.00",
                "total": "598.00",
            }
        ],
    }
    result = await CreateOrder().invoke(
        {
            "line_items": [{"variation_id": 101, "quantity": 2}],
            "customer_id": 9,
            "billing": {
                "first_name": "Ana",
                "last_name": "Soto",
                "email": "ana@example.com",
                "country": "CL",
                "city": "Santiago",
            },
            "payment_method": "bacs",
        }
    )
    order = result["result"]["order"]
    assert order["id"] == 555
    assert order["line_items"][0]["variation_id"] == 101

    kind, payload = fake_client.calls[0]
    assert kind == "post"
    assert payload["path"] == "/orders"
    assert payload["payload"]["status"] == "pending"
    assert payload["payload"]["line_items"] == [{"quantity": 2, "variation_id": 101}]
    # AddressInput None fields get coerced to empty strings before send
    billing_payload = payload["payload"]["billing"]
    assert billing_payload["first_name"] == "Ana"
    assert billing_payload["address_1"] == ""  # was None in input


async def test_create_order_rejects_line_item_without_product_or_variation(fake_client, tenant_ctx):
    fake_client.next_post = {
        "id": 1,
        "number": "1",
        "status": "pending",
        "currency": "CLP",
        "total": "0",
        "line_items": [],
    }
    with pytest.raises(Exception, match="product_id / variation_id / retailer_id"):
        await CreateOrder().invoke({"line_items": [{"quantity": 1}]})


async def test_build_checkout_link(fake_client, tenant_ctx):
    """Builds a multi-product checkout URL with quantities + the wa=1 flag,
    off the tenant's own store_url (no API call)."""
    result = await BuildCheckoutLink().invoke(
        {"items": [{"product_id": 2836}, {"product_id": 2830, "quantity": 2}]}
    )
    assert result["status"] == "ok"
    assert result["result"]["url"] == (
        "https://barbersupply.cl/finalizar-compra/?add-to-cart=2836,2830:2&wa=1"
    )
    # Pure URL builder — no WooCommerce API call.
    assert fake_client.calls == []


async def test_create_order_resolves_raw_id_retailer(fake_client, tenant_ctx):
    """A native-cart line item whose retailer_id is the raw WooCommerce id
    (the catalog's format) resolves to that product_id with no lookup."""
    fake_client.next_post = {
        "id": 7,
        "number": "7",
        "status": "pending",
        "currency": "CLP",
        "total": "0",
        "line_items": [],
    }
    await CreateOrder().invoke({"line_items": [{"retailer_id": "2836", "quantity": 2}]})
    post = next(c for kind, c in fake_client.calls if kind == "post")
    assert post["payload"]["line_items"] == [{"quantity": 2, "product_id": 2836}]
    # raw numeric id resolves locally — no product lookup needed.
    assert not any(kind == "list" for kind, _ in fake_client.calls)


async def test_create_order_resolves_wc_post_id_retailer(fake_client, tenant_ctx):
    """The ``wc_post_id_{N}`` plugin fallback format resolves to product_id N."""
    fake_client.next_post = {
        "id": 7,
        "number": "7",
        "status": "pending",
        "currency": "CLP",
        "total": "0",
        "line_items": [],
    }
    await CreateOrder().invoke({"line_items": [{"retailer_id": "wc_post_id_2782", "quantity": 2}]})
    post = next(c for kind, c in fake_client.calls if kind == "post")
    assert post["payload"]["line_items"] == [{"quantity": 2, "product_id": 2782}]
    assert not any(kind == "list" for kind, _ in fake_client.calls)


async def test_create_order_resolves_nonnumeric_sku_retailer_via_lookup(fake_client, tenant_ctx):
    """A non-numeric retailer_id (an alphanumeric SKU) is resolved to its
    product_id via a ``/products?sku=`` lookup."""
    fake_client.next_list = (
        [{"id": 2836}],
        PaginationMeta(page=1, per_page=1, total_count=1, total_pages=1, has_more=False),
    )
    fake_client.next_post = {
        "id": 8,
        "number": "8",
        "status": "pending",
        "currency": "CLP",
        "total": "0",
        "line_items": [],
    }
    await CreateOrder().invoke({"line_items": [{"retailer_id": "WAHL-GOLD-6", "quantity": 1}]})
    lookup = next(c for kind, c in fake_client.calls if kind == "list")
    assert lookup["params"] == {"sku": "WAHL-GOLD-6"}
    post = next(c for kind, c in fake_client.calls if kind == "post")
    assert post["payload"]["line_items"] == [{"quantity": 1, "product_id": 2836}]


# ── update_order_status ──────────────────────────────────────────────────


async def test_update_order_status_reports_previous(fake_client, tenant_ctx):
    fake_client.next_get = {"id": 555, "status": "pending"}
    fake_client.next_put = {
        "id": 555,
        "status": "processing",
        "date_modified": "2026-05-18T12:00:00",
    }
    result = await UpdateOrderStatus().invoke({"id": 555, "status": "processing"})
    out = result["result"]
    assert out["previous_status"] == "pending"
    assert out["status"] == "processing"
    # Two calls: GET then PUT.
    kinds = [c[0] for c in fake_client.calls]
    assert kinds == ["get", "put"]
    assert fake_client.calls[1][1]["payload"] == {"status": "processing"}


# ── update_order ─────────────────────────────────────────────────────────


async def test_update_order_requires_field(fake_client, tenant_ctx):
    with pytest.raises(Exception, match="at least one field"):
        await UpdateOrder().invoke({"id": 1})


async def test_update_order_sends_only_provided_fields(fake_client, tenant_ctx):
    fake_client.next_put = {
        "id": 555,
        "number": "555",
        "status": "processing",
        "currency": "CLP",
        "total": "598.00",
        "customer_id": 9,
        "billing": {},
        "shipping": {},
        "line_items": [],
    }
    await UpdateOrder().invoke({"id": 555, "customer_note": "Despachado ya"})
    payload = fake_client.calls[0][1]["payload"]
    assert payload == {"customer_note": "Despachado ya"}


# ── add_order_note ───────────────────────────────────────────────────────


async def test_add_order_note_customer_visible(fake_client, tenant_ctx):
    fake_client.next_post = {
        "id": 7001,
        "author": "system",
        "date_created": "2026-05-18T13:00:00",
        "note": "Tu paquete fue despachado.",
        "customer_note": True,
    }
    result = await AddOrderNote().invoke(
        {"order_id": 555, "note": "Tu paquete fue despachado.", "customer_note": True}
    )
    out = result["result"]["note"]
    assert out["id"] == 7001
    assert out["customer_note"] is True
    assert fake_client.calls[0][1]["path"] == "/orders/555/notes"


# ── list_orders / list_categories / customers ────────────────────────────


async def test_list_orders_filters(fake_client, tenant_ctx):
    fake_client.next_list = (
        [{"id": 1, "number": "1", "status": "processing", "currency": "CLP", "total": "100"}],
        PaginationMeta(page=1, per_page=20, total_count=1, total_pages=1, has_more=False),
    )
    await ListOrders().invoke({"status": "processing", "customer": 9})
    params = fake_client.calls[0][1]["params"]
    assert params["status"] == "processing"
    assert params["customer"] == 9
    # None fields are dropped — the base client does this.
    # The fake just records what the tool passed; sanity-check no
    # surprise extras are present.
    assert "search" in params  # tool always passes the key; base filters None


async def test_list_categories_returns_count(fake_client, tenant_ctx):
    fake_client.next_list = (
        [{"id": 3, "name": "Fundas", "slug": "fundas", "parent": 0, "count": 25}],
        PaginationMeta(page=1, per_page=50, total_count=1, total_pages=1, has_more=False),
    )
    result = await ListCategories().invoke({})
    assert result["result"]["items"][0]["count"] == 25


async def test_list_customers_by_email(fake_client, tenant_ctx):
    fake_client.next_list = (
        [
            {
                "id": 9,
                "email": "ana@example.com",
                "first_name": "Ana",
                "last_name": "Soto",
                "billing": {"phone": "+56911111111"},
            }
        ],
        PaginationMeta(page=1, per_page=20, total_count=1, total_pages=1, has_more=False),
    )
    result = await ListCustomers().invoke({"email": "ana@example.com"})
    item = result["result"]["items"][0]
    assert item["billing_phone"] == "+56911111111"


async def test_get_customer_by_email(fake_client, tenant_ctx):
    fake_client.next_list = (
        [{"id": 9, "email": "ana@example.com", "billing": {"phone": "+56911"}}],
        PaginationMeta(page=1, per_page=1, total_count=1, total_pages=1, has_more=False),
    )
    result = await GetCustomer().invoke({"email": "ana@example.com"})
    assert result["result"]["customer"]["id"] == 9


async def test_get_customer_email_not_found(fake_client, tenant_ctx):
    fake_client.next_list = (
        [],
        PaginationMeta(page=1, per_page=1, total_count=0, total_pages=0, has_more=False),
    )
    with pytest.raises(WooCommerceNotFound):
        await GetCustomer().invoke({"email": "missing@example.com"})


# ── auth error propagation ───────────────────────────────────────────────


async def test_auth_error_surfaces(fake_client, tenant_ctx):
    fake_client.raise_on_call = WooCommerceAuthError("bad creds", status_code=401)
    with pytest.raises(WooCommerceAuthError):
        await ListProducts().invoke({"page": 1, "per_page": 20})


# ── get_order ────────────────────────────────────────────────────────────


async def test_get_order_returns_line_items_with_variation_id(fake_client, tenant_ctx):
    fake_client.next_get = {
        "id": 555,
        "number": "555",
        "status": "completed",
        "currency": "CLP",
        "total": "598.00",
        "customer_id": 9,
        "billing": {},
        "shipping": {},
        "line_items": [
            {
                "id": 1,
                "name": "Plumón Queen Azul",
                "product_id": 42,
                "variation_id": 101,
                "sku": "PK-Q-AZ",
                "quantity": 2,
                "price": "299",
                "subtotal": "598",
                "total": "598",
            }
        ],
    }
    result = await GetOrder().invoke({"id": 555})
    order = result["result"]["order"]
    assert order["line_items"][0]["variation_id"] == 101
