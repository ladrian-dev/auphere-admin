"""Pydantic schemas for every WooCommerce tool.

Design rules (apply to every schema in this file):

1. ``InputModel`` / ``OutputModel`` already enforce ``extra='forbid'``.
   That keeps the LLM from smuggling junk fields, and keeps our output
   from leaking ``meta_data`` that WooCommerce stores plugin secrets in.
2. List outputs wrap items in :class:`ListEnvelope` (M2 in the plan).
   The LLM needs ``has_more`` and ``total_count`` to avoid claiming
   "there are 3 products" when the store has 300.
3. Resource outputs (single product / order / customer) are a deliberate
   subset of WooCommerce's shape — not a pass-through. Descriptions are
   truncated, ``meta_data`` is dropped, raw HTML is not exposed.
4. Money fields stay as ``str`` because WooCommerce returns decimal-as-
   string. Floats would silently round.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import EmailStr, Field, model_validator

from nexus_mcp.base import InputModel, OutputModel

# ── pagination envelope (M2) ─────────────────────────────────────────────


_TItem = TypeVar("_TItem")


class ListEnvelope(OutputModel, Generic[_TItem]):
    """Wraps every paginated list result.

    ``total_count`` and ``total_pages`` may be ``None`` if the vendor
    did not return the headers (older Woo, custom plugin breaking
    semantics). ``has_more`` is always set; when ``total_pages`` is
    unknown we fall back to ``len(items) == per_page`` heuristics on
    the tool side.
    """

    items: list[_TItem]
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)
    total_count: int | None = None
    total_pages: int | None = None
    has_more: bool


# ── reusable nested types ────────────────────────────────────────────────


class CategoryRef(OutputModel):
    """Minimal category reference embedded in product responses."""

    id: int
    name: str
    slug: str


class AttributeCompact(OutputModel):
    """Compact attribute representation for a product or variation.

    For a *product* (variable type), ``options`` lists every available
    value across all variations. For a *variation*, ``option`` holds
    the single selected value and ``options`` is empty.
    """

    id: int | None = None
    name: str
    slug: str | None = None
    options: list[str] = Field(default_factory=list)
    option: str | None = None
    variation: bool = False


class ImageRef(OutputModel):
    """First image of a product / variation. Only the URL — alt text and
    image IDs are skipped to keep the LLM context small."""

    src: str


class LineItemOutput(OutputModel):
    """Order line item as surfaced by Woo on order read.

    The LLM needs enough to reason about the order: product, variation
    (for variable products), quantity, line totals, and the SKU. Tax
    detail is summarised; refunds are not exposed at this layer (out of
    scope for the agent's job; the operator panel has them)."""

    id: int
    name: str
    product_id: int
    variation_id: int | None = None
    sku: str | None = None
    quantity: int
    price: str
    subtotal: str
    total: str


class AddressOutput(OutputModel):
    """Billing / shipping address as Woo returns it.

    All fields optional because real stores rarely fill them all in
    (especially shipping when the order is digital)."""

    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    postcode: str | None = None
    country: str | None = None
    email: str | None = None
    phone: str | None = None


# ── product (resource) ───────────────────────────────────────────────────


ProductType = Literal["simple", "variable", "grouped", "external"]
ProductStatus = Literal["draft", "pending", "private", "publish"]
StockStatus = Literal["instock", "outofstock", "onbackorder"]


class ProductSummary(OutputModel):
    """Compact product, returned by list endpoints. Just enough to let
    the LLM decide which product to ``get_product`` for detail."""

    id: int
    name: str
    slug: str
    sku: str | None = None
    type: ProductType
    status: ProductStatus
    price: str
    regular_price: str | None = None
    sale_price: str | None = None
    stock_status: StockStatus
    stock_quantity: int | None = None
    permalink: str | None = None
    image: ImageRef | None = None
    categories: list[CategoryRef] = Field(default_factory=list)


class ProductDetail(OutputModel):
    """Full product for a single ``get_product`` call."""

    id: int
    name: str
    slug: str
    sku: str | None = None
    type: ProductType
    status: ProductStatus
    short_description: str | None = Field(
        default=None,
        description="HTML stripped + truncated to 500 chars by the tool layer.",
    )
    description: str | None = Field(
        default=None,
        description="HTML stripped + truncated to 500 chars by the tool layer.",
    )
    price: str
    regular_price: str | None = None
    sale_price: str | None = None
    on_sale: bool = False
    stock_status: StockStatus
    stock_quantity: int | None = None
    manage_stock: bool = False
    permalink: str | None = None
    image: ImageRef | None = None
    categories: list[CategoryRef] = Field(default_factory=list)
    attributes: list[AttributeCompact] = Field(default_factory=list)
    variations: list[int] = Field(
        default_factory=list,
        description="Variation IDs. Empty for non-variable products. "
        "Call woocommerce.list_product_variations to expand.",
    )


# ── product (input + output) ─────────────────────────────────────────────


class ListProductsInput(InputModel):
    """Filters mirror the WooCommerce ``GET /products`` endpoint, but
    only the fields the agent actually uses. Adding more later is a
    schema bump — keep the surface small for now."""

    search: str | None = Field(default=None, max_length=200)
    ids: list[int] | None = Field(
        default=None,
        max_length=100,
        description=(
            "Fetch specific products by WooCommerce id (e.g. the retailer_ids "
            "of a native WhatsApp cart). Returns those products with their "
            "names/prices in one call — use it to resolve cart item names."
        ),
    )
    category: str | None = Field(
        default=None,
        max_length=120,
        description="Category slug or id (string).",
    )
    type: ProductType | None = None
    status: ProductStatus | None = None
    stock_status: StockStatus | None = None
    attribute: str | None = Field(
        default=None,
        max_length=120,
        description="Attribute slug, e.g. 'pa_color' or 'pa_size'. "
        "Must be combined with attribute_term.",
    )
    attribute_term: str | None = Field(
        default=None,
        max_length=120,
        description="Attribute term slug, e.g. 'azul', 'queen'. Must be combined with attribute.",
    )
    page: int = Field(default=1, ge=1, le=1000)
    per_page: int = Field(default=20, ge=1, le=100)


class ListProductsOutput(ListEnvelope[ProductSummary]):
    pass


class GetProductInput(InputModel):
    """Identify a product by id OR sku. Exactly one must be provided."""

    id: int | None = Field(default=None, ge=1)
    sku: str | None = Field(default=None, min_length=1, max_length=200)


class GetProductOutput(OutputModel):
    product: ProductDetail


# ── variations ───────────────────────────────────────────────────────────


class ProductVariation(OutputModel):
    """One variation of a variable product (e.g. 'funda, queen, azul')."""

    id: int
    sku: str | None = None
    price: str
    regular_price: str | None = None
    sale_price: str | None = None
    on_sale: bool = False
    stock_status: StockStatus
    stock_quantity: int | None = None
    image: ImageRef | None = None
    attributes: list[AttributeCompact] = Field(default_factory=list)


class ListProductVariationsInput(InputModel):
    """Variations are scoped to one product — product_id is required."""

    product_id: int = Field(ge=1)
    page: int = Field(default=1, ge=1, le=1000)
    per_page: int = Field(default=50, ge=1, le=100)


class ListProductVariationsOutput(ListEnvelope[ProductVariation]):
    pass


# ── categories ───────────────────────────────────────────────────────────


class Category(OutputModel):
    id: int
    name: str
    slug: str
    parent: int = 0
    description: str | None = None
    count: int = 0


class ListCategoriesInput(InputModel):
    search: str | None = Field(default=None, max_length=200)
    parent: int | None = Field(default=None, ge=0)
    page: int = Field(default=1, ge=1, le=1000)
    per_page: int = Field(default=50, ge=1, le=100)


class ListCategoriesOutput(ListEnvelope[Category]):
    pass


# ── orders (resource) ────────────────────────────────────────────────────


OrderStatus = Literal[
    "pending",
    "processing",
    "on-hold",
    "completed",
    "cancelled",
    "refunded",
    "failed",
    "trash",
]


class OrderSummary(OutputModel):
    """Compact order for list endpoints."""

    id: int
    number: str
    status: OrderStatus
    currency: str
    date_created: str | None = None
    total: str
    customer_id: int = 0
    customer_note: str | None = None
    payment_method: str | None = None
    payment_method_title: str | None = None


class OrderDetail(OutputModel):
    """Full order for a single ``get_order`` call."""

    id: int
    number: str
    status: OrderStatus
    currency: str
    date_created: str | None = None
    date_modified: str | None = None
    date_paid: str | None = None
    total: str
    subtotal: str | None = None
    total_tax: str | None = None
    shipping_total: str | None = None
    discount_total: str | None = None
    customer_id: int = 0
    customer_note: str | None = None
    billing: AddressOutput
    shipping: AddressOutput
    payment_method: str | None = None
    payment_method_title: str | None = None
    transaction_id: str | None = None
    # WooCommerce "pay for order" link — the customer opens it to pay the
    # order with the store's active gateways (e.g. Mercado Pago). Present
    # while the order still needs payment; the agent sends it as the
    # "Pagar ahora" button after creating the order.
    payment_url: str | None = None
    line_items: list[LineItemOutput] = Field(default_factory=list)


# ── orders (input + output) ──────────────────────────────────────────────


class ListOrdersInput(InputModel):
    status: OrderStatus | None = None
    customer: int | None = Field(default=None, ge=0)
    after: str | None = Field(
        default=None,
        description="ISO 8601 — list orders created after this datetime.",
    )
    before: str | None = Field(
        default=None,
        description="ISO 8601 — list orders created before this datetime.",
    )
    search: str | None = Field(default=None, max_length=200)
    page: int = Field(default=1, ge=1, le=1000)
    per_page: int = Field(default=20, ge=1, le=100)


class ListOrdersOutput(ListEnvelope[OrderSummary]):
    pass


class GetOrderInput(InputModel):
    id: int = Field(ge=1)


class GetOrderOutput(OutputModel):
    order: OrderDetail


# ── customers ────────────────────────────────────────────────────────────


class Customer(OutputModel):
    id: int
    email: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    role: str | None = None
    billing_phone: str | None = None
    date_created: str | None = None


class ListCustomersInput(InputModel):
    search: str | None = Field(
        default=None,
        max_length=200,
        description="WooCommerce searches by email and display name.",
    )
    email: str | None = Field(default=None, max_length=200)
    page: int = Field(default=1, ge=1, le=1000)
    per_page: int = Field(default=20, ge=1, le=100)


class ListCustomersOutput(ListEnvelope[Customer]):
    pass


class GetCustomerInput(InputModel):
    """Identify a customer by id OR email. Exactly one must be provided."""

    id: int | None = Field(default=None, ge=1)
    email: EmailStr | None = None


class GetCustomerOutput(OutputModel):
    customer: Customer


# ── destructive: create_order ────────────────────────────────────────────


class AddressInput(InputModel):
    """Billing / shipping address as the agent supplies it on order
    creation. ``email`` and ``phone`` only make sense on billing;
    WooCommerce ignores them on shipping but accepts the same shape."""

    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    company: str | None = Field(default=None, max_length=200)
    address_1: str | None = Field(default=None, max_length=240)
    address_2: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postcode: str | None = Field(default=None, max_length=40)
    country: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code, e.g. 'CL', 'MX'.",
    )
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)


class LineItemInput(InputModel):
    """Order line item on creation.

    Either ``product_id`` (for simple products) or ``variation_id`` (for
    a specific variation of a variable product) must be supplied. When
    both are supplied, WooCommerce uses the variation; we accept the
    pair so the LLM can be explicit, but ``variation_id`` wins."""

    product_id: int | None = Field(default=None, ge=1)
    variation_id: int | None = Field(default=None, ge=1)
    retailer_id: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Meta catalog retailer_id from a native WhatsApp cart "
            "([PEDIDO_WHATSAPP]) — e.g. 'wc_post_id_2782' or a SKU. Resolved "
            "server-side to the WooCommerce product/variation; pass it "
            "verbatim when the id came from a native cart."
        ),
    )
    quantity: int = Field(ge=1, le=10_000)
    # Optional manual price override — Woo honours it when the user
    # role permits it. The LLM should not set this unless explicitly
    # asked by the operator; included so the schema is complete.
    subtotal: str | None = Field(
        default=None,
        max_length=40,
        description="Optional manual line subtotal (string decimal). "
        "Leave unset to let WooCommerce compute from product price.",
    )

    @model_validator(mode="after")
    def _at_least_one_identifier(self) -> LineItemInput:
        if self.product_id is None and self.variation_id is None and not self.retailer_id:
            raise ValueError("line item needs one of product_id / variation_id / retailer_id")
        return self


class CreateOrderInput(InputModel):
    """Create a new order. ``status`` defaults to 'pending' so the
    operator can review before the order ships; the agent flips it to
    'processing' / 'on-hold' via update_order_status once payment is
    confirmed externally."""

    line_items: list[LineItemInput] = Field(min_length=1, max_length=100)
    customer_id: int | None = Field(
        default=None,
        ge=0,
        description="WooCommerce customer id. 0 or null = guest checkout.",
    )
    billing: AddressInput | None = None
    shipping: AddressInput | None = None
    payment_method: str | None = Field(
        default=None,
        max_length=80,
        description="Slug, e.g. 'bacs', 'cod', 'stripe'.",
    )
    payment_method_title: str | None = Field(default=None, max_length=200)
    customer_note: str | None = Field(default=None, max_length=2000)
    status: OrderStatus = Field(
        default="pending",
        description="Default 'pending' so the operator can review.",
    )
    meta_data: list[dict[str, Any]] | None = Field(
        default=None,
        max_length=30,
        description=(
            "Custom order metadata as [{key, value}] pairs. Used to tag the "
            "sales channel, e.g. [{'key':'_auphere_source','value':'whatsapp'}] "
            "so orders created from WhatsApp are identifiable in WooCommerce."
        ),
    )
    # set_paid lives in WooCommerce too but we don't expose it — the
    # agent should not be able to mark an order paid without going
    # through update_order_status, which is the auditable path.


class CreateOrderOutput(OutputModel):
    order: OrderDetail


# ── build_checkout_link (read-only: constructs a URL) ────────────────────


class CheckoutItemInput(InputModel):
    """One product to pre-load into the store checkout cart."""

    product_id: int = Field(ge=1)
    quantity: int = Field(default=1, ge=1, le=10_000)


class BuildCheckoutLinkInput(InputModel):
    """Build a checkout URL that pre-fills the cart and opens the store's
    checkout page (where the customer enters shipping + pays)."""

    items: list[CheckoutItemInput] = Field(min_length=1, max_length=100)


class BuildCheckoutLinkOutput(OutputModel):
    url: str


# ── destructive: update_order_status ─────────────────────────────────────


class UpdateOrderStatusInput(InputModel):
    """Move an order to a new status. The most common destructive call."""

    id: int = Field(ge=1)
    status: OrderStatus


class UpdateOrderStatusOutput(OutputModel):
    id: int
    previous_status: OrderStatus
    status: OrderStatus
    date_modified: str | None = None


# ── destructive: update_order ────────────────────────────────────────────


class UpdateOrderInput(InputModel):
    """Restricted update. Only the fields the agent has a real use case
    for — addresses, customer note, payment method. Status changes go
    through update_order_status (separate audit signal)."""

    id: int = Field(ge=1)
    billing: AddressInput | None = None
    shipping: AddressInput | None = None
    customer_note: str | None = Field(default=None, max_length=2000)
    payment_method: str | None = Field(default=None, max_length=80)
    payment_method_title: str | None = Field(default=None, max_length=200)


class UpdateOrderOutput(OutputModel):
    order: OrderDetail


# ── destructive: add_order_note ──────────────────────────────────────────


class AddOrderNoteInput(InputModel):
    """Add a note to an order. If ``customer_note=True``, the note is
    emailed to the customer; otherwise it's internal-only (visible to
    operator/staff in WP-Admin)."""

    order_id: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=4000)
    customer_note: bool = Field(
        default=False,
        description="True = visible to customer (and emailed). False = internal note only.",
    )


class OrderNote(OutputModel):
    id: int
    author: str | None = None
    date_created: str | None = None
    note: str
    customer_note: bool


class AddOrderNoteOutput(OutputModel):
    note: OrderNote


# Sorted alphabetically (ruff RUF022). Sections (nested / read-only /
# destructive) are visible by name prefix so the grouping is preserved
# implicitly: AddOrderNote*, Address*, etc.
__all__ = [
    "AddOrderNoteInput",
    "AddOrderNoteOutput",
    "AddressInput",
    "AddressOutput",
    "AttributeCompact",
    "Category",
    "CategoryRef",
    "CreateOrderInput",
    "CreateOrderOutput",
    "Customer",
    "GetCustomerInput",
    "GetCustomerOutput",
    "GetOrderInput",
    "GetOrderOutput",
    "GetProductInput",
    "GetProductOutput",
    "ImageRef",
    "LineItemInput",
    "LineItemOutput",
    "ListCategoriesInput",
    "ListCategoriesOutput",
    "ListCustomersInput",
    "ListCustomersOutput",
    "ListEnvelope",
    "ListOrdersInput",
    "ListOrdersOutput",
    "ListProductVariationsInput",
    "ListProductVariationsOutput",
    "ListProductsInput",
    "ListProductsOutput",
    "OrderDetail",
    "OrderNote",
    "OrderStatus",
    "OrderSummary",
    "ProductDetail",
    "ProductStatus",
    "ProductSummary",
    "ProductType",
    "ProductVariation",
    "StockStatus",
    "UpdateOrderInput",
    "UpdateOrderOutput",
    "UpdateOrderStatusInput",
    "UpdateOrderStatusOutput",
]
