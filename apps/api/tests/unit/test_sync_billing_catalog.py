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


# ── El webhook y el portal, que también se crean por API ─────────────────────


class FakeWebhooks:
    def __init__(self, existing: list | None = None) -> None:
        self.items = list(existing or [])
        self.created: list[dict[str, Any]] = []

    def list(self, params: dict[str, Any] | None = None) -> Any:
        return type("R", (), {"data": list(self.items)})()

    def create(self, params: dict[str, Any]) -> Any:
        self.created.append(params)
        made = Obj({"id": f"we_{len(self.items)}", "secret": "whsec_fake", **params})
        self.items.append(made)
        return made


class FakePortal:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.configurations = self

    def list(self, params: dict[str, Any] | None = None) -> Any:
        return type("R", (), {"data": []})()

    def create(self, params: dict[str, Any]) -> Any:
        self.created.append(params)
        return Obj({"id": "bpc_1", **params})


class FullClient(FakeClient):
    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self.webhook_endpoints = FakeWebhooks(kw.get("webhooks"))
        self.billing_portal = FakePortal()


async def test_the_webhook_subscribes_to_exactly_what_the_api_handles() -> None:
    """La lista del script y la del código **no pueden divergir**.

    Si el script pide un evento que la API no maneja, se registra ruido. Si
    falta uno que sí maneja, el manejador nunca se entera — y en esta spec eso
    significa cobros que no se aplican.
    """
    mod = _load()
    from nexus_api.billing.events import HANDLED_EVENTS

    assert set(mod.WEBHOOK_EVENTS) == set(HANDLED_EVENTS), (
        "la lista de eventos del script se desincronizó de HANDLED_EVENTS"
    )


async def test_invoice_created_is_not_in_the_script_either() -> None:
    """La mina de las 72 horas, vigilada también desde aquí.

    Es el sitio donde más fácil se cuela: alguien configurando el webhook en
    el panel marca «todos los eventos» y el castigo llega tres días después.
    """
    mod = _load()
    assert "invoice.created" not in mod.WEBHOOK_EVENTS


async def test_creating_the_webhook_is_idempotent_by_url() -> None:
    mod = _load()
    client = FullClient()
    first = mod.ensure_webhook(client, url="https://api.example/webhook/billing", dry_run=False)
    assert first is not None and first.startswith("whsec_")
    again = mod.ensure_webhook(client, url="https://api.example/webhook/billing", dry_run=False)
    assert again is None, "la segunda pasada creó un segundo endpoint"
    assert len(client.webhook_endpoints.created) == 1


async def test_the_portal_lets_the_partner_do_the_three_things() -> None:
    """Cambiar tarjeta, ver facturas y darse de baja. Nada más.

    Dejar que el portal cambie de plan sería una segunda vía de hacerlo, sin
    pasar por nuestros topes: alguien podría bajar a un nivel con menos plazas
    de las que usa, y el 409 que lo impide vive en nuestra API.
    """
    mod = _load()
    client = FullClient()
    mod.ensure_portal(client, return_url="https://console.example/billing", dry_run=False)
    features = client.billing_portal.created[0]["features"]
    assert features["payment_method_update"]["enabled"] is True
    assert features["invoice_history"]["enabled"] is True
    assert features["subscription_cancel"]["enabled"] is True
    assert features["subscription_update"]["enabled"] is False, (
        "el portal permite cambiar de plan: eso saltaría los topes de nivel"
    )


async def test_the_portal_cancels_at_period_end() -> None:
    """Nadie pierde la semana que ya pagó."""
    mod = _load()
    client = FullClient()
    mod.ensure_portal(client, return_url="https://console.example/billing", dry_run=False)
    cancel = client.billing_portal.created[0]["features"]["subscription_cancel"]
    assert cancel["mode"] == "at_period_end"
    assert cancel["proration_behavior"] == "none"


async def test_dry_run_creates_neither() -> None:
    mod = _load()
    client = FullClient()
    mod.ensure_webhook(client, url="https://api.example/webhook/billing", dry_run=True)
    mod.ensure_portal(client, return_url="https://console.example/billing", dry_run=True)
    assert client.webhook_endpoints.created == []
    assert client.billing_portal.created == []


# ── Los dos entornos, y la guardia que impide cruzarlos ──────────────────────


async def test_both_environments_are_declared() -> None:
    mod = _load()
    assert set(mod.ENVIRONMENTS) == {"staging", "prod"}


async def test_each_environment_points_at_its_own_hosts() -> None:
    """Staging y producción no comparten ni webhook ni consola."""
    mod = _load()
    staging, prod = mod.ENVIRONMENTS["staging"], mod.ENVIRONMENTS["prod"]
    assert staging["webhook_url"] != prod["webhook_url"]
    assert staging["console_url"] != prod["console_url"]
    assert "staging" in staging["webhook_url"]
    assert "staging" not in prod["webhook_url"]


async def test_a_test_key_may_not_configure_production() -> None:
    """La mitad inofensiva del cruce, y aun así se para.

    Registraría el webhook de pruebas contra el dominio de producción: los
    pagos reales no llegarían a ninguna parte y nadie se enteraría hasta
    cuadrar ingresos.
    """
    mod = _load()
    with pytest.raises(mod.EnvironmentMismatch):
        mod.check_key_matches_environment("sk_test_abc", "prod")


async def test_a_live_key_may_not_configure_staging() -> None:
    """**La mitad cara.**

    Apuntaría el webhook de producción a staging: los cobros reales llegarían
    al entorno de pruebas, donde se aplicarían contra una base de datos que no
    es la de los clientes. Dinero cobrado que no acredita a nadie.
    """
    mod = _load()
    with pytest.raises(mod.EnvironmentMismatch):
        mod.check_key_matches_environment("sk_live_abc", "staging")


async def test_the_right_pairings_pass() -> None:
    mod = _load()
    mod.check_key_matches_environment("sk_test_abc", "staging")
    mod.check_key_matches_environment("sk_live_abc", "prod")


async def test_an_unrecognisable_key_is_refused() -> None:
    """Una clave restringida o mal pegada no se adivina."""
    mod = _load()
    with pytest.raises(mod.EnvironmentMismatch):
        mod.check_key_matches_environment("pk_test_abc", "staging")
    with pytest.raises(mod.EnvironmentMismatch):
        mod.check_key_matches_environment("", "staging")


async def test_the_price_ids_are_per_environment_and_the_script_says_so() -> None:
    """Modo test y modo live son catálogos DISTINTOS dentro de la misma cuenta.

    Los ``stripe_price_id`` de staging no sirven en producción. Es la clase de
    detalle que se descubre en el peor momento, así que el script lo dice al
    imprimir los UPDATE.
    """
    mod = _load()
    assert "staging" in mod.PRICE_ID_WARNING or "entorno" in mod.PRICE_ID_WARNING


# ── La línea de órdenes, que es por donde se usa de verdad ───────────────────
#
# Estos tests existen porque faltaban: la guardia de entorno estaba escrita y
# probada, el CLI no la llamaba, y todo estaba en verde. Probar la función y no
# la puerta por la que se entra deja exactamente ese hueco.


async def test_the_cli_refuses_a_live_key_against_staging(monkeypatch, capsys) -> None:
    """El cruce caro, por la puerta real."""
    mod = _load()
    monkeypatch.setenv("BILLING_API_KEY", "sk_live_falsa")
    code = mod.main(["--env", "staging", "--dry-run"])
    assert code == 2
    assert "prod" in capsys.readouterr().err


async def test_the_cli_refuses_a_test_key_against_prod(monkeypatch, capsys) -> None:
    mod = _load()
    monkeypatch.setenv("BILLING_API_KEY", "sk_test_falsa")
    assert mod.main(["--env", "prod", "--dry-run"]) == 2


async def test_the_cli_requires_an_environment(monkeypatch) -> None:
    """Sin ``--env`` no se adivina: equivocarse de entorno es lo caro."""
    mod = _load()
    monkeypatch.setenv("BILLING_API_KEY", "sk_test_falsa")
    with pytest.raises(SystemExit):
        mod.main(["--dry-run"])


async def test_the_cli_refuses_without_a_key(monkeypatch, capsys) -> None:
    mod = _load()
    monkeypatch.delenv("BILLING_API_KEY", raising=False)
    monkeypatch.delenv("NEXUS_BILLING_API_KEY", raising=False)
    assert mod.main(["--env", "staging", "--dry-run"]) == 2
    assert "la clave la pones tú" in capsys.readouterr().err
