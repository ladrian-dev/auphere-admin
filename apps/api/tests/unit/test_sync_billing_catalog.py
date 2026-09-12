"""Spec 005 · el script que crea el catálogo en la cuenta del proveedor.

Lo ejecuta una persona con las claves puestas, contra una cuenta con capacidad
de cobro. Por eso vive en ``scripts/`` y no en ``apps/``: un comando de la API
lo dejaría a un ``POST`` de distancia de crear precios en producción.

Lo que se prueba aquí es **la idempotencia**, que es lo que hace que se pueda
ejecutar dos veces sin duplicar precios — y lo que hace posible recrear el
catálogo entero contra la cuenta nueva el día de la migración.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.asyncio]

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "sync_billing_catalog.py"


def _load() -> Any:
    """Carga el script como módulo.

    Se registra en ``sys.modules`` ANTES de ejecutarlo porque el script define
    un ``@dataclass`` y ``dataclasses`` resuelve las anotaciones buscando el
    módulo por su nombre — sin registrarlo, explota al construir la clase.
    """
    spec = importlib.util.spec_from_file_location("sync_billing_catalog", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_billing_catalog"] = module
    spec.loader.exec_module(module)
    return module


class Obj:
    """Imita un objeto del SDK: atributos Y acceso por clave, como StripeObject."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        for k, v in data.items():
            setattr(self, k, v)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


class FakeProducts:
    def __init__(self, existing: list[dict[str, Any]] | None = None) -> None:
        self.items = list(existing or [])
        self.created: list[dict[str, Any]] = []

    def list(self, params: dict[str, Any] | None = None) -> Any:
        return type("R", (), {"data": list(self.items)})()

    def create(self, params: dict[str, Any]) -> Any:
        self.created.append(params)
        made = Obj({"id": f"prod_{params['metadata']['tier_code']}", **params})
        self.items.append(made)
        return made


class FakePrices:
    def __init__(self, existing: list[dict[str, Any]] | None = None) -> None:
        self.items = list(existing or [])
        self.created: list[dict[str, Any]] = []

    def list(self, params: dict[str, Any] | None = None) -> Any:
        return type("R", (), {"data": list(self.items)})()

    def create(self, params: dict[str, Any]) -> Any:
        self.created.append(params)
        made = Obj({"id": f"price_{len(self.items)}", **params})
        self.items.append(made)
        return made


class FakeClient:
    def __init__(self, **kw: Any) -> None:
        self.products = FakeProducts(kw.get("products"))
        self.prices = FakePrices(kw.get("prices"))


async def test_the_free_tier_is_never_created_upstream() -> None:
    """Free no se factura: no tiene precio y no debe aparecer en la cuenta."""
    mod = _load()
    client = FakeClient()
    plan = mod.plan_catalog(mod.TIERS, client)
    assert all(step.code != "free" for step in plan), [s.code for s in plan]


async def test_running_twice_creates_nothing_the_second_time() -> None:
    """La propiedad entera: idempotente por la clave del NIVEL, no por nombre."""
    mod = _load()
    client = FakeClient()

    first = mod.apply(mod.plan_catalog(mod.TIERS, client), client, dry_run=False)
    assert len(first) == 3, first
    created_once = len(client.prices.created)
    assert created_once == 3

    second = mod.apply(mod.plan_catalog(mod.TIERS, client), client, dry_run=False)
    assert second == [], f"la segunda pasada creó cosas: {second}"
    assert len(client.prices.created) == created_once, "se duplicaron precios"


async def test_dry_run_creates_nothing() -> None:
    mod = _load()
    client = FakeClient()
    mod.apply(mod.plan_catalog(mod.TIERS, client), client, dry_run=True)
    assert client.products.created == []
    assert client.prices.created == []


async def test_every_object_carries_our_tier_code() -> None:
    """Es lo que hace la segunda ejecución idempotente y la migración posible.

    Sin ``metadata.tier_code``, reconocer un precio ya creado dependería de su
    nombre visible — que es texto comercial y cambia.
    """
    mod = _load()
    client = FakeClient()
    mod.apply(mod.plan_catalog(mod.TIERS, client), client, dry_run=False)
    for params in client.products.created:
        assert params["metadata"]["tier_code"] in {"pro", "team", "business"}
    for params in client.prices.created:
        assert params["metadata"]["tier_code"] in {"pro", "team", "business"}


async def test_prices_are_usd_monthly_and_match_the_data_model() -> None:
    mod = _load()
    client = FakeClient()
    mod.apply(mod.plan_catalog(mod.TIERS, client), client, dry_run=False)
    by_tier = {p["metadata"]["tier_code"]: p for p in client.prices.created}
    assert by_tier["pro"]["unit_amount"] == 2000
    assert by_tier["team"]["unit_amount"] == 6000
    assert by_tier["business"]["unit_amount"] == 15000
    for params in client.prices.created:
        assert params["currency"] == "usd"
        assert params["recurring"]["interval"] == "month"
