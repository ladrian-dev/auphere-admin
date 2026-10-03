"""Las herramientas del catálogo de Meta (spec 022, Historia 3).

Meta y la resolución del canal se simulan: lo que se prueba es que la
herramienta resuelve catálogo y token **en el servidor**, que el token nunca
sale, que sin catálogo lo dice, y que el límite se acota.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from nexus_api.core.tenant_context import tenant_context
from nexus_channels.whatsapp_meta.exceptions import MetaTransientError
from pydantic import ValidationError

from nexus_mcp.base import ToolError
from nexus_mcp.servers.meta_catalog import tools as catalog_tools
from nexus_mcp.servers.meta_catalog.tools import GetProduct, SearchProducts

pytestmark = pytest.mark.asyncio

TENANT = uuid.uuid4()
RAMO = {
    "retailer_id": "SKU-RAMO",
    "name": "Ramo de 12 rosas",
    "price": "35 EUR",
    "currency": "EUR",
    "availability": "in stock",
    "image_url": "https://img/ramo.jpg",
    "description": "<p>Rosas &amp; eucalipto</p>",
}
PLANTA = {"retailer_id": "SKU-PLANTA", "name": "Monstera", "price": "22 EUR"}


class _FakeMeta:
    def __init__(self, rows: list[dict[str, Any]], *, fail: bool = False) -> None:
        self.rows = rows
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def search_products(self, **kw: Any) -> list[dict[str, Any]]:
        self.calls.append(("search", kw))
        if self.fail:
            raise MetaTransientError("down", status_code=503)
        return self.rows[: kw["limit"]]

    async def get_product(self, **kw: Any) -> dict[str, Any] | None:
        self.calls.append(("get", kw))
        return next((r for r in self.rows if r["retailer_id"] == kw["retailer_id"]), None)

    async def close(self) -> None:
        pass


def _wire(
    monkeypatch, rows, *, linked: tuple[str, str] | None = ("CAT_1", "EAA-canal"), fail=False
) -> _FakeMeta:
    fake = _FakeMeta(rows, fail=fail)
    monkeypatch.setattr(catalog_tools, "build_meta_client", lambda: fake)

    async def _resolve(_tenant: uuid.UUID, _customer: uuid.UUID | None):
        return linked

    monkeypatch.setattr(catalog_tools, "resolve_channel_catalog", _resolve)
    return fake


async def test_search_uses_the_channels_catalog_and_token_and_never_returns_the_token(
    monkeypatch,
) -> None:
    fake = _wire(monkeypatch, [RAMO, PLANTA])
    with tenant_context(TENANT):
        out = (await SearchProducts().invoke({"query": "ramo", "limit": 5}))["result"]
    assert fake.calls[0][1]["catalog_id"] == "CAT_1"
    assert fake.calls[0][1]["access_token"] == "EAA-canal"
    assert [p["retailer_id"] for p in out["products"]] == ["SKU-RAMO", "SKU-PLANTA"]
    assert out["products"][0]["description"] == "Rosas & eucalipto"
    assert "EAA-canal" not in str(out) and "CAT_1" not in str(out)


async def test_limit_is_capped_at_ten_and_truncated_says_there_may_be_more(monkeypatch) -> None:
    rows = [{"retailer_id": f"SKU-{i}", "name": f"Producto {i}"} for i in range(30)]
    fake = _wire(monkeypatch, rows)
    with tenant_context(TENANT):
        out = (await SearchProducts().invoke({"query": "", "limit": 10}))["result"]
    assert fake.calls[0][1]["limit"] == 10
    assert len(out["products"]) == 10
    assert out["truncated"] is True
    with tenant_context(TENANT), pytest.raises(ValidationError):
        await SearchProducts().invoke({"query": "", "limit": 50})


async def test_without_a_linked_catalog_the_tool_says_so_and_does_not_call_meta(
    monkeypatch,
) -> None:
    fake = _wire(monkeypatch, [RAMO], linked=None)
    with tenant_context(TENANT), pytest.raises(ToolError, match="catalog_not_linked"):
        await SearchProducts().invoke({"query": "ramo"})
    assert fake.calls == []


async def test_get_product_finds_by_retailer_id_and_says_when_it_is_not_there(monkeypatch) -> None:
    _wire(monkeypatch, [RAMO])
    with tenant_context(TENANT):
        found = (await GetProduct().invoke({"retailer_id": "SKU-RAMO"}))["result"]
        missing = (await GetProduct().invoke({"retailer_id": "SKU-NADA"}))["result"]
    assert found["found"] is True
    assert found["product"]["price"] == "35 EUR"
    assert missing["found"] is False and missing["product"] is None


async def test_meta_down_is_a_readable_error(monkeypatch) -> None:
    _wire(monkeypatch, [RAMO], fail=True)
    with tenant_context(TENANT), pytest.raises(ToolError, match="catalog_unavailable"):
        await SearchProducts().invoke({"query": "ramo"})


async def test_the_tool_refuses_an_llm_supplied_tenant_or_token() -> None:
    # Un argumento lo rellena el modelo: el token y el tenant son estado del
    # servidor y ``InputModel`` prohíbe los campos extra.
    with tenant_context(TENANT), pytest.raises(ValidationError):
        await SearchProducts().invoke({"query": "ramo", "access_token": "EAA-x"})


def test_the_tools_are_read_only() -> None:
    assert SearchProducts.side_effects == ()
    assert GetProduct.side_effects == ()
