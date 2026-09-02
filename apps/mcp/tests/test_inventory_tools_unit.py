"""Unit tests for the Amigable Venta (inventory.*) MCP tools.

DB-free: tools use the ``set_test_client`` hook to bypass credential
resolution. Each test injects a FakeVentaClient returning canned catalogue
rows shaped exactly like the live API (verified 2026-08-24), including the
trait the whole module exists for: several SKUs sharing one product name
with different prices and stock.

The live seed catalogue has no product at or below its minimum, so the
low-stock path is exercised with synthetic rows here — that is the only
place it can be exercised at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from nexus_api.core.tenant_context import tenant_context

from nexus_mcp.base import ToolError
from nexus_mcp.servers.amigable_venta.client import RESULT_CAP, AmigableVentaClient
from nexus_mcp.servers.catalogo_local.client import LocalCatalogClient
from nexus_mcp.servers.catalogo_local.client import fold as local_fold
from nexus_mcp.servers.inventory import tools as inventory_tools
from nexus_mcp.servers.inventory.schemas import (
    CheckStockInput,
    GetProductInput,
    LowStockInput,
    RegisterSaleInput,
    SearchProductsInput,
)
from nexus_mcp.servers.inventory.tools import (
    INVENTORY_TOOLS,
    CheckStock,
    GetProduct,
    InventoryNotConfigured,
    LowStock,
    RegisterSale,
    SearchProducts,
    _fold,
    _resolve_backend,
    set_test_client,
)

_TENANT = uuid.uuid4()


async def _async_true(_tenant_id: uuid.UUID) -> bool:
    return True


async def _async_false(_tenant_id: uuid.UUID) -> bool:
    return False


def _returning(value: object):
    async def _inner(_tenant_id: uuid.UUID) -> object:
        return value

    return _inner


def _row(
    sku: str,
    nombre: str,
    precio: float,
    stock: int,
    minimo: int = 10,
    categoria: str = "Analgésicos y Antipiréticos",
) -> dict[str, Any]:
    """One catalogue row in the live API's shape."""
    return {
        "id": abs(hash(sku)) % 10_000,
        "nombre": nombre,
        "sku": sku,
        "categoria": categoria,
        "tipo": "Mercancía",
        "precio_usd": precio,
        "precio_costo": round(precio * 0.7, 2),
        "stock_actual": stock,
        "stock_minimo": minimo,
        "image_url": "http://venta-api.amigable.app/storage/products/default.png",
    }


# The four "Ibuprofeno" SKUs are the real ones from the live catalogue.
IBUPROFENO = [
    _row("FARM-00005", "Ibuprofeno", 1.35, 293, 10),
    _row("FARM-00006", "Ibuprofeno", 4.19, 126, 9),
    _row("FARM-00007", "Ibuprofeno", 3.30, 280, 16),
    _row("FARM-00004", "Ibuprofeno", 1.95, 126, 10),
]
IBUPROFENO_GEL = [
    _row("FARM-00899", "Ibuprofeno Gel tópico 50 g - Tubo x 60 g", 8.57, 87, 20),
    _row("FARM-00676", "Ibuprofeno Gel tópico 50 g - Tubo x 60 g", 5.52, 290, 9),
]


class FakeVentaClient(AmigableVentaClient):
    """Bypasses real HTTP. Serves one canned result set."""

    def __init__(self, rows: list[dict[str, Any]], *, truncated: bool = False) -> None:
        # Skip the parent __init__ (no credential validation for a fake).
        self.rows = rows
        self.truncated = truncated
        self.queries: list[str] = []

    async def search_products(  # type: ignore[override]
        self, query: str
    ) -> tuple[list[dict[str, Any]], bool]:
        self.queries.append(query)
        return list(self.rows), self.truncated


@pytest.fixture
def tenant() -> Iterator[uuid.UUID]:
    with tenant_context(_TENANT):
        yield _TENANT


@pytest.fixture(autouse=True)
def _reset_client() -> Iterator[None]:
    yield
    set_test_client(None)


def _use(rows: list[dict[str, Any]], *, truncated: bool = False) -> FakeVentaClient:
    client = FakeVentaClient(rows, truncated=truncated)
    set_test_client(client)
    return client


# ── folding ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Acetaminofén", "acetaminofen"),
        ("ACETAMINOFEN", "acetaminofen"),
        ("  Ibuprofeno  ", "ibuprofeno"),
        ("Ácido acetilsalicílico", "acido acetilsalicilico"),
    ],
)
def test_fold_strips_case_and_accents(raw: str, expected: str) -> None:
    assert _fold(raw) == expected


# ── grouping ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_groups_variants_under_one_product(tenant: uuid.UUID) -> None:
    """Four SKUs named "Ibuprofeno" are ONE product with a price spread —
    not four products. Reporting them raw is what makes an agent answer
    "tienes Ibuprofeno a 1.35" and be wrong about the other three."""
    _use(IBUPROFENO)
    out = await SearchProducts().run(SearchProductsInput(query="ibuprofeno"))

    assert out.productos_encontrados == 1
    assert out.variantes_encontradas == 4
    item = out.items[0]
    assert item.nombre == "Ibuprofeno"
    assert item.variantes == 4
    assert item.stock_total == 293 + 126 + 280 + 126
    assert (item.precio_min, item.precio_max) == (1.35, 4.19)
    assert sorted(item.skus) == ["FARM-00004", "FARM-00005", "FARM-00006", "FARM-00007"]


@pytest.mark.asyncio
async def test_search_groups_across_accent_drift(tenant: uuid.UUID) -> None:
    """Same product spelled with and without an accent must not split."""
    _use([_row("A-1", "Acetaminofén", 1.20, 10), _row("A-2", "Acetaminofen", 1.50, 5)])
    out = await SearchProducts().run(SearchProductsInput(query="acetaminofen"))

    assert out.productos_encontrados == 1
    assert out.items[0].variantes == 2
    assert out.items[0].stock_total == 15


@pytest.mark.asyncio
async def test_search_reports_truncation_at_the_api_cap(tenant: uuid.UUID) -> None:
    """The API caps a query at RESULT_CAP rows with no way to page past
    it. Silently returning a capped list reads as "that's everything"."""
    _use(IBUPROFENO, truncated=True)
    out = await SearchProducts().run(SearchProductsInput(query="a"))
    assert out.truncado is True

    _use(IBUPROFENO, truncated=False)
    out = await SearchProducts().run(SearchProductsInput(query="ibuprofeno"))
    assert out.truncado is False


@pytest.mark.asyncio
async def test_search_limit_caps_items_but_not_the_count(tenant: uuid.UUID) -> None:
    _use(IBUPROFENO + IBUPROFENO_GEL)
    out = await SearchProducts().run(SearchProductsInput(query="ibuprofeno", limit=1))

    assert out.productos_encontrados == 2
    assert out.devueltos == 1
    assert len(out.items) == 1


# ── product resolution ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_product_resolves_exact_sku_without_ambiguity(
    tenant: uuid.UUID,
) -> None:
    _use(IBUPROFENO + IBUPROFENO_GEL)
    out = await GetProduct().run(GetProductInput(query="FARM-00899"))

    assert out.encontrado is True
    assert out.nombre == "Ibuprofeno Gel tópico 50 g - Tubo x 60 g"
    assert out.ambiguo is False


@pytest.mark.asyncio
async def test_get_product_prefers_the_base_product_and_flags_ambiguity(
    tenant: uuid.UUID,
) -> None:
    """ "ibuprofeno" matches the base product and every presentation. The
    shortest name is the base product; the rest are offered, not hidden."""
    _use(IBUPROFENO + IBUPROFENO_GEL)
    out = await GetProduct().run(GetProductInput(query="ibuprofeno"))

    assert out.nombre == "Ibuprofeno"
    assert out.variantes == 4
    assert out.ambiguo is True
    assert "Ibuprofeno Gel tópico 50 g - Tubo x 60 g" in out.otros_candidatos


@pytest.mark.asyncio
async def test_get_product_orders_variants_by_price(tenant: uuid.UUID) -> None:
    _use(IBUPROFENO)
    out = await GetProduct().run(GetProductInput(query="ibuprofeno"))

    assert [v.precio_usd for v in out.detalle] == [1.35, 1.95, 3.30, 4.19]


@pytest.mark.asyncio
async def test_get_product_reports_not_found_instead_of_guessing(
    tenant: uuid.UUID,
) -> None:
    _use([])
    out = await GetProduct().run(GetProductInput(query="zzzznoexiste"))

    assert out.encontrado is False
    assert out.nombre is None
    assert out.detalle == []


# ── stock ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_stock_sums_variants_and_counts_alerts(tenant: uuid.UUID) -> None:
    _use(
        [
            _row("S-1", "Amoxicilina", 2.00, 0, 10),  # agotada
            _row("S-2", "Amoxicilina", 2.50, 8, 10),  # bajo mínimo
            _row("S-3", "Amoxicilina", 3.00, 40, 10),  # sana
        ]
    )
    out = await CheckStock().run(CheckStockInput(query="amoxicilina"))

    assert out.encontrado is True
    assert out.stock_total == 48
    assert out.hay_stock is True
    assert out.variantes == 3
    assert out.variantes_agotadas == 1
    assert out.variantes_bajo_minimo == 2  # 0 <= 10 and 8 <= 10
    assert [v.stock_actual for v in out.detalle] == [40, 8, 0]


@pytest.mark.asyncio
async def test_check_stock_says_no_stock_when_every_variant_is_empty(
    tenant: uuid.UUID,
) -> None:
    _use([_row("S-1", "Amoxicilina", 2.00, 0), _row("S-2", "Amoxicilina", 2.50, 0)])
    out = await CheckStock().run(CheckStockInput(query="amoxicilina"))

    assert out.encontrado is True
    assert out.stock_total == 0
    assert out.hay_stock is False


# ── reposición ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_low_stock_ranks_the_most_critical_first(tenant: uuid.UUID) -> None:
    """Ordering is by distance below the threshold, so a SKU 30 units under
    its minimum outranks one sitting exactly on it."""
    _use(
        [
            _row("L-1", "Jarabe A", 3.00, 9, 10),  # -1
            _row("L-2", "Jarabe B", 3.00, 0, 30),  # -30
            _row("L-3", "Jarabe C", 3.00, 18, 20),  # -2
            _row("L-4", "Jarabe D", 3.00, 500, 20),  # sana, se excluye
        ]
    )
    out = await LowStock().run(LowStockInput(query="jarabe"))

    assert out.revisadas == 4
    assert out.bajo_minimo == 3
    assert out.agotadas == 1
    assert [v.sku for v in out.items] == ["L-2", "L-3", "L-1"]


@pytest.mark.asyncio
async def test_low_stock_can_exclude_sold_out_variants(tenant: uuid.UUID) -> None:
    _use([_row("L-1", "Jarabe A", 3.00, 9, 10), _row("L-2", "Jarabe B", 3.00, 0, 30)])
    out = await LowStock().run(LowStockInput(query="jarabe", incluir_agotados=False))

    assert [v.sku for v in out.items] == ["L-1"]
    assert out.agotadas == 1  # still counted, just not listed


# ── guards ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cost_price_never_reaches_the_model(tenant: uuid.UUID) -> None:
    """The API returns precio_costo on every row. It must not survive into
    a tool result: once it is in the transcript it can be quoted to a
    customer."""
    _use(IBUPROFENO)
    for output in (
        await SearchProducts().run(SearchProductsInput(query="ibuprofeno")),
        await GetProduct().run(GetProductInput(query="ibuprofeno")),
        await CheckStock().run(CheckStockInput(query="ibuprofeno")),
        await LowStock().run(LowStockInput(query="ibuprofeno")),
    ):
        assert "precio_costo" not in output.model_dump_json()


def test_side_effects_split_reads_from_the_sale() -> None:
    """Las cuatro consultas NO tienen side effects (el QA Playground las corre
    en dry_run tal cual). ``inventory.register_sale`` SÍ los declara: eso es
    justo lo que hace que el registry la SALTE en dry_run en vez de descontar
    stock de verdad durante una prueba."""
    for tool_cls in INVENTORY_TOOLS:
        assert tool_cls.name.startswith("inventory.")
    read_only = {SearchProducts, GetProduct, CheckStock, LowStock}
    for tool_cls in read_only:
        assert tool_cls.side_effects == (), tool_cls.name
    assert RegisterSale.side_effects == ("mutates_db",)
    # La única tool con efecto de escritura es la venta.
    writers = [t for t in INVENTORY_TOOLS if t.side_effects]
    assert writers == [RegisterSale]


def test_result_cap_matches_the_documented_api_limit() -> None:
    assert RESULT_CAP == 1000


# ── selección de backend ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_amigable_wins_when_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Con ambas fuentes disponibles manda el POS real: el catálogo importado
    es el puente que sustituye, no una segunda opinión."""
    sentinel = FakeVentaClient([])
    monkeypatch.setattr(inventory_tools, "_amigable_is_connected", _async_true)
    monkeypatch.setattr(inventory_tools, "_has_local_catalog", _async_true)
    monkeypatch.setattr(inventory_tools, "_load_amigable_venta_client", _returning(sentinel))

    assert await _resolve_backend(_TENANT) is sentinel


@pytest.mark.asyncio
async def test_local_catalog_answers_when_amigable_is_not_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inventory_tools, "_amigable_is_connected", _async_false)
    monkeypatch.setattr(inventory_tools, "_has_local_catalog", _async_true)

    backend = await _resolve_backend(_TENANT)
    assert isinstance(backend, LocalCatalogClient)


@pytest.mark.asyncio
async def test_no_catalogue_at_all_is_a_clean_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sin ninguna fuente el fallo es explícito, no una lista vacía que el
    agente presentaría como 'no tenemos ese producto'."""
    monkeypatch.setattr(inventory_tools, "_amigable_is_connected", _async_false)
    monkeypatch.setattr(inventory_tools, "_has_local_catalog", _async_false)

    with pytest.raises(InventoryNotConfigured):
        await _resolve_backend(_TENANT)


@pytest.mark.asyncio
async def test_an_empty_local_catalogue_is_not_a_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La señal es que HAYA filas, no que exista la tabla: un catálogo vacío
    no debe ganarle a un error explícito."""
    monkeypatch.setattr(inventory_tools, "_amigable_is_connected", _async_false)
    monkeypatch.setattr(inventory_tools, "_has_local_catalog", _async_false)

    with pytest.raises(InventoryNotConfigured):
        await _resolve_backend(_TENANT)


def test_local_backend_cap_is_higher_than_the_upstream_api() -> None:
    """El backend local sirve un catálogo propio y grande (una farmacia lleva
    miles de SKUs) y es la fuente de verdad de la demo inventario_v1, así que
    NO está atado al tope de 1000 del API de Amigable: usa uno mayor. Lo que
    de verdad acota lo que ve el modelo es el ``limit`` (≤50) de las tools."""
    from nexus_mcp.servers.catalogo_local.client import RESULT_CAP as LOCAL_CAP

    assert LOCAL_CAP > RESULT_CAP  # RESULT_CAP aquí es el del API de Amigable (1000)
    assert LOCAL_CAP >= 5000


def test_the_two_folds_agree() -> None:
    """El importador escribe ``search_text`` con el fold del cliente local, y
    las tools resuelven nombres con el suyo. Si divergen, un producto con
    tilde queda inbuscable."""
    for raw in ("Acetaminofén", "ÁCIDO ascórbico", "  Ibuprofeno  ", "Niño"):
        assert local_fold(raw) == _fold(raw)


# ── inventory.register_sale (venta simulada) ──────────────────────────────


class FakeLocalClient(LocalCatalogClient):
    """Catálogo local en memoria (sin DB) para probar la venta simulada.

    Replica el contrato de ``decrement_stock``: guardia de stock, distinción
    entre SKU inexistente y stock insuficiente, y el descuento real sobre la
    fila. Deja ver el mapeo que hace la tool (importe, stock restante)."""

    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self._tenant_id = _TENANT
        self._rows = rows  # sku -> {"nombre", "precio_usd", "stock_actual"}
        self.calls: list[tuple[str, int]] = []

    async def decrement_stock(self, sku: str, cantidad: int) -> dict[str, Any]:  # type: ignore[override]
        self.calls.append((sku, cantidad))
        row = self._rows.get(sku)
        if row is None:
            return {
                "encontrado": False,
                "vendido": False,
                "sku": sku,
                "nombre": None,
                "precio_usd": None,
                "stock_anterior": None,
                "stock_actual": None,
                "motivo": "sku_no_encontrado",
            }
        if row["stock_actual"] < cantidad:
            return {
                "encontrado": True,
                "vendido": False,
                "sku": sku,
                "nombre": row["nombre"],
                "precio_usd": row["precio_usd"],
                "stock_anterior": row["stock_actual"],
                "stock_actual": row["stock_actual"],
                "motivo": "stock_insuficiente",
            }
        prev = row["stock_actual"]
        row["stock_actual"] = prev - cantidad
        return {
            "encontrado": True,
            "vendido": True,
            "sku": sku,
            "nombre": row["nombre"],
            "precio_usd": row["precio_usd"],
            "stock_anterior": prev,
            "stock_actual": row["stock_actual"],
            "motivo": None,
        }


def _use_local(rows: dict[str, dict[str, Any]]) -> FakeLocalClient:
    client = FakeLocalClient(rows)
    set_test_client(client)
    return client


@pytest.mark.asyncio
async def test_register_sale_decrements_and_reports(tenant: uuid.UUID) -> None:
    client = _use_local(
        {"FARM-00005": {"nombre": "Ibuprofeno", "precio_usd": 1.35, "stock_actual": 293}}
    )
    out = await RegisterSale().run(RegisterSaleInput(sku="FARM-00005", cantidad=2))
    assert out.vendido is True
    assert out.encontrado is True
    assert out.sku == "FARM-00005"
    assert out.nombre == "Ibuprofeno"
    assert out.cantidad == 2
    assert out.precio_usd == 1.35
    assert out.importe_usd == 2.70  # 1.35 * 2
    assert out.stock_anterior == 293
    assert out.stock_actual == 291
    assert out.motivo is None
    # El stock quedó efectivamente descontado en el backend.
    assert client._rows["FARM-00005"]["stock_actual"] == 291


@pytest.mark.asyncio
async def test_register_sale_insufficient_stock_does_not_sell(tenant: uuid.UUID) -> None:
    _use_local({"FARM-00006": {"nombre": "Ibuprofeno", "precio_usd": 4.19, "stock_actual": 1}})
    out = await RegisterSale().run(RegisterSaleInput(sku="FARM-00006", cantidad=5))
    assert out.vendido is False
    assert out.motivo == "stock_insuficiente"
    assert out.stock_actual == 1  # sin cambios
    assert out.importe_usd is None


@pytest.mark.asyncio
async def test_register_sale_unknown_sku(tenant: uuid.UUID) -> None:
    _use_local({})
    out = await RegisterSale().run(RegisterSaleInput(sku="NO-EXISTE", cantidad=1))
    assert out.vendido is False
    assert out.encontrado is False
    assert out.motivo == "sku_no_encontrado"


@pytest.mark.asyncio
async def test_register_sale_refuses_amigable_backend(tenant: uuid.UUID) -> None:
    """El POS real de Amigable Venta es de solo lectura: no se puede vender
    contra él. La tool debe rechazarlo antes de intentar nada."""
    _use(IBUPROFENO)  # FakeVentaClient (subclase de AmigableVentaClient)
    with pytest.raises(ToolError):
        await RegisterSale().run(RegisterSaleInput(sku="FARM-00005", cantidad=1))
