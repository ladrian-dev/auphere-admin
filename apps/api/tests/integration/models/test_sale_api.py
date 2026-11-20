"""Spec 059 (requisitos 3.1 a 3.11; T023) — el precio de venta desde el panel
(``contracts/admin-api.md`` §1, §6 y §7).

- Cada fila trae su bloque ``sale``: coste, peso, venta y multiplicador por carril,
  la propuesta y el estado. El listado trae ``sale_policy``.
- ``PUT …/weights`` guarda los tres pesos con su motivo y no baja del suelo.
- Spec 065 (T046, T047): y el cuarto, la escritura en caché. Sin él se queda el guardado;
  falta si el modelo tiene tarifa de escritura y no lo tiene; no se acepta en un modelo sin
  tarifa de escritura.
- ``PUT /admin/models/sale-policy`` cambia el objetivo y, si se pide, aplica la
  propuesta a todos los modelos con coste, en una transacción.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.runtime import model_resolver

from nexus_api.core import respond_catalog
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog
from nexus_api.metering import sale_policy
from nexus_api.services import model_usage, operator_identity

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

BASE = "/admin/models/deployments"
POLICY = "/admin/models/sale-policy"
TOKENS = "c59s-a/tokens"
MINUTE = "c59s-b/minute"
#: Spec 065: con tarifa de escritura (5,00, la de Sol) y sin su peso guardado.
WRITES = "c59s-c/writes"


async def _insert(
    key: str,
    *,
    price: dict[str, Any],
    weights: tuple[Any, Any, Any],
    write_price: Decimal | None = None,
) -> None:
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "INSERT INTO model_profiles (provider, model_id, display_name, route, status, "
                "capabilities, supports_tools, quota_weight_input, quota_weight_cache_read, "
                "quota_weight_output, price_cache_write_per_mtok) VALUES ('c59s', :k, :k, :k, "
                "'active', CAST(:c AS jsonb), true, :wi, :wc, :wo, :cw)"
            ),
            {
                "k": key,
                "c": json.dumps({"tools": True}),
                "wi": weights[0],
                "wc": weights[1],
                "wo": weights[2],
                "cw": write_price,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_prices (deployment_id, valid_from, input, cache_read, "
                "cache_write, output, audio_minute, source_url) SELECT id, DATE '2026-10-28', "
                ":i, :c, :cw, :o, :m, 'https://example.invalid' FROM model_profiles "
                "WHERE model_id = :k"
            ),
            {"k": key, "cw": write_price, **price},
        )


@pytest_asyncio.fixture(autouse=True)
async def _world() -> AsyncIterator[None]:
    # «Aplicar a todos» reescribe los pesos de TODOS los modelos con coste, también
    # los sembrados por las migraciones, que no se truncan entre pruebas. Sin
    # devolverlos, la siguiente que cobra (test_metering_end_to_end) mide con los
    # pesos de 2,5 y no con los de 2,2.
    async with get_sessionmaker()() as session:
        seeded_weights = [
            dict(row._mapping)
            for row in await session.execute(
                sa.text(
                    "SELECT id, quota_weight_input AS i, quota_weight_cache_read AS c, "
                    "quota_weight_output AS o, quota_weight_cache_write AS w FROM model_profiles"
                )
            )
        ]
    await _insert(
        TOKENS,
        price={"i": Decimal("4"), "c": Decimal("0.4"), "o": Decimal("20"), "m": None},
        weights=(Decimal("0.88"), Decimal("0.088"), Decimal("4.4")),
    )
    await _insert(
        MINUTE,
        price={"i": None, "c": None, "o": None, "m": Decimal("0.006")},
        weights=(None, None, None),
    )
    await _insert(
        WRITES,
        price={"i": Decimal("4"), "c": Decimal("0.4"), "o": Decimal("20"), "m": None},
        weights=(Decimal("0.88"), Decimal("0.088"), Decimal("4.4")),
        write_price=Decimal("5"),
    )
    model_resolver.invalidate_catalog()
    model_usage.invalidate()
    sale_policy.invalidate()
    yield
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(sa.text("DELETE FROM model_profiles WHERE model_id LIKE 'c59s-%'"))
        if seeded_weights:
            await session.execute(
                sa.text(
                    "UPDATE model_profiles SET quota_weight_input = :i, "
                    "quota_weight_cache_read = :c, quota_weight_output = :o, "
                    "quota_weight_cache_write = :w WHERE id = :id"
                ),
                seeded_weights,
            )
        await session.execute(
            sa.text(
                "UPDATE platform_settings SET value = '2.2'::jsonb WHERE key = 'sale_multiplier'"
            )
        )
    from nexus_worker.metering import pricing

    model_resolver.invalidate_catalog()
    respond_catalog.reset()
    model_usage.invalidate()
    sale_policy.invalidate()
    pricing.invalidate()


@pytest_asyncio.fixture
async def ops(db_session, admin_headers) -> dict[str, Any]:
    email = f"ops-c59s-{uuid.uuid4().hex[:8]}@auphere.test"
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session, email=email, password="operator-password-1", display_name="Ops"
        )
    return {"headers": {**admin_headers, "X-Operator-Id": str(op.id)}, "actor": f"operator:{email}"}


async def _listing(client, ops) -> dict[str, Any]:
    r = await client.get(BASE, headers=ops["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def _row(listing: dict[str, Any], key: str) -> dict[str, Any]:
    return next(d for d in listing["items"] if d["deployment"]["id"] == key)


async def test_each_row_shows_cost_sale_and_multiplier(client, ops) -> None:
    listing = await _listing(client, ops)
    assert listing["sale_policy"] == {
        "multiplier": "2.2",
        "floor": "1.50",
        "sell_usd_per_million": "10",
    }
    tokens = _row(listing, TOKENS)["sale"]
    assert tokens["state"] == "on_target"
    assert tokens["lanes"]["output"] == {
        "cost": "20.000000",
        "weight": "4.400000",
        "sale": "44.000000",
        "multiplier": "2.20",
    }
    assert _row(listing, MINUTE)["sale"]["state"] == "per_minute"


async def test_weights_are_saved_with_their_reason_and_audited(client, ops) -> None:
    row = _row(await _listing(client, ops), TOKENS)
    r = await client.put(
        f"{BASE}/{row['uuid']}/weights",
        headers=ops["headers"],
        json={"input": "1.0", "cache_read": "0.1", "output": "5.0", "reason": "subir al 2,5"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sale"]["lanes"]["output"]["multiplier"] == "2.50"
    assert r.json()["sale"]["state"] == "drift", "el objetivo sigue en 2,2"
    async with get_sessionmaker()() as session:
        [audit] = list(
            (
                await session.scalars(
                    sa.select(AuditLog).where(
                        AuditLog.action == "deployment.weights_changed",
                        AuditLog.target == f"deployment:{TOKENS}",
                    )
                )
            ).all()
        )
    assert audit.actor == ops["actor"]
    assert audit.before_json["weights"]["output"] == "4.400000"
    # Spec 065: el cuarto peso no vino y se queda el guardado (nulo: sin tarifa de escritura).
    assert audit.after_json == {
        "weights": {
            "input": "1.000000",
            "cache_read": "0.100000",
            "output": "5.000000",
            "cache_write": None,
        },
        "reason": "subir al 2,5",
    }


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"input": "1", "cache_read": "0.1", "reason": "x"}, "partial_weights"),
        ({"input": "0.88", "cache_read": "0.088", "output": "2.9", "reason": "x"}, "below_floor"),
        (
            {"input": "0.88", "cache_read": "0.088", "output": "4.4", "reason": " "},
            "reason_required",
        ),
    ],
)
async def test_bad_weights_are_refused(client, ops, body, code) -> None:
    row = _row(await _listing(client, ops), TOKENS)
    r = await client.put(f"{BASE}/{row['uuid']}/weights", headers=ops["headers"], json=body)
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == code
    if code == "below_floor":
        assert r.json()["detail"]["lanes"] == ["output"]


async def test_a_per_minute_model_has_no_weights(client, ops) -> None:
    row = _row(await _listing(client, ops), MINUTE)
    r = await client.put(
        f"{BASE}/{row['uuid']}/weights",
        headers=ops["headers"],
        json={"input": "1", "cache_read": "0.1", "output": "5", "reason": "x"},
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "per_minute"


async def test_the_target_changes_and_can_apply_to_all(client, ops) -> None:
    keep = await client.put(
        POLICY,
        headers=ops["headers"],
        json={"multiplier": "2.5", "apply_to_all": False, "reason": "x"},
    )
    assert keep.status_code == 200, keep.text
    assert keep.json()["applied_to"] == []
    listing = await _listing(client, ops)
    assert listing["sale_policy"]["multiplier"] == "2.5"
    assert _row(listing, TOKENS)["sale"]["state"] == "drift", "ningún peso cambió"

    apply = await client.put(
        POLICY,
        headers=ops["headers"],
        json={"multiplier": "2.5", "apply_to_all": True, "reason": "y"},
    )
    assert apply.status_code == 200, apply.text
    assert TOKENS in apply.json()["applied_to"]
    assert MINUTE not in apply.json()["applied_to"]
    listing = await _listing(client, ops)
    assert _row(listing, TOKENS)["sale"]["state"] == "on_target"
    assert _row(listing, TOKENS)["sale"]["lanes"]["output"]["weight"] == "5.000000"
    # Spec 065: también la escritura. Con tarifa, 2,5 x 5,00 / 10 = 1,25; sin ella, 0.
    assert WRITES in apply.json()["applied_to"]
    writes = _row(listing, WRITES)["sale"]
    assert writes["state"] == "on_target"
    assert writes["lanes"]["cache_write"]["weight"] == "1.250000"
    assert writes["lanes"]["cache_write"]["multiplier"] == "2.50"
    assert _row(listing, TOKENS)["sale"]["lanes"]["cache_write"]["weight"] == "0.000000"
    async with get_sessionmaker()() as session:
        changed = await session.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "platform.sale_multiplier_changed")
        )
    assert changed and changed >= 2


async def test_a_target_under_the_floor_is_refused(client, ops) -> None:
    r = await client.put(
        POLICY,
        headers=ops["headers"],
        json={"multiplier": "1.4", "apply_to_all": False, "reason": "x"},
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "below_floor"
    assert (await client.get(POLICY, headers=ops["headers"])).json()["multiplier"] == "2.2"


async def test_the_sale_routes_need_the_operator(client, admin_headers) -> None:
    r = await client.put(
        POLICY,
        headers=admin_headers,
        json={"multiplier": "2.5", "apply_to_all": False, "reason": "x"},
    )
    assert r.status_code in (400, 401, 403, 422)


async def test_saving_weights_forgets_the_meter_catalog_in_this_process(client, ops) -> None:
    """T027, lado de la API: el Companion cobra desde este proceso con el mismo
    catálogo del medidor, así que también lo olvida al guardar."""
    from nexus_worker.metering import pricing

    pricing._cache = {"stale": pricing.ModelPrice(model_id="stale")}
    row = _row(await _listing(client, ops), TOKENS)
    r = await client.put(
        f"{BASE}/{row['uuid']}/weights",
        headers=ops["headers"],
        json={"input": "0.88", "cache_read": "0.088", "output": "4.4", "reason": "igual"},
    )
    assert r.status_code == 200, r.text
    assert pricing._cache is None


async def test_a_write_tariff_needs_its_write_weight(client, ops) -> None:
    """Spec 065: el modelo factura la escritura y no tiene su peso, así que sin él falta
    (el medidor no lo cobraría, ``metering.unweighted_model``)."""
    row = _row(await _listing(client, ops), WRITES)
    assert row["sale"]["state"] == "unweighted"
    three = {"input": "0.88", "cache_read": "0.088", "output": "4.4", "reason": "x"}
    r = await client.put(f"{BASE}/{row['uuid']}/weights", headers=ops["headers"], json=three)
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == {"code": "partial_weights", "lanes": ["cache_write"]}

    # 0,66 sobre 5,00 vende a 1,32x, bajo el suelo.
    low = {**three, "cache_write": "0.66"}
    r = await client.put(f"{BASE}/{row['uuid']}/weights", headers=ops["headers"], json=low)
    assert r.status_code == 422 and r.json()["detail"]["lanes"] == ["cache_write"]

    r = await client.put(
        f"{BASE}/{row['uuid']}/weights",
        headers=ops["headers"],
        json={**three, "cache_write": "1.1", "reason": "la escritura a 2,2"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["sale"]["state"] == "on_target"
    assert r.json()["sale"]["lanes"]["cache_write"] == {
        "cost": "5.000000",
        "weight": "1.100000",
        "sale": "11.000000",
        "multiplier": "2.20",
    }
    # Sin el cuarto, ahora se queda el guardado.
    r = await client.put(f"{BASE}/{row['uuid']}/weights", headers=ops["headers"], json=three)
    assert r.status_code == 200, r.text
    assert r.json()["sale"]["lanes"]["cache_write"]["weight"] == "1.100000"


async def test_a_write_weight_without_a_write_tariff_is_refused(client, ops) -> None:
    """Spec 065: el suelo no lo vería (no hay coste con el que compararlo) y se cobraría algo
    que el proveedor no factura. 0 sí vale: es lo que el medidor cobra sin tarifa."""
    row = _row(await _listing(client, ops), TOKENS)
    body = {"input": "0.88", "cache_read": "0.088", "output": "4.4", "reason": "x"}
    r = await client.put(
        f"{BASE}/{row['uuid']}/weights", headers=ops["headers"], json={**body, "cache_write": "1"}
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_write_tariff"
    r = await client.put(
        f"{BASE}/{row['uuid']}/weights", headers=ops["headers"], json={**body, "cache_write": "0"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["sale"]["lanes"]["cache_write"]["weight"] == "0.000000"
