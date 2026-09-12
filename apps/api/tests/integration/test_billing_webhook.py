"""Spec 005 · el aviso del proveedor: firma, registro, encolar, 200.

R4 entero, y las dos averías silenciosas de research D10.

La secuencia que se comprueba aquí es la de ADR-022 §13-§15 y no admite pasos
intermedios. Lo que más importa de cada una:

* **La firma se verifica antes de mirar el cuerpo.** Un cuerpo que no verifica
  no es contenido dudoso: es contenido que no se lee (§III).
* **El registro va antes de actuar**, con una restricción única. Ahí vive la
  idempotencia — no en el trabajo de fondo, que dos entregas simultáneas se
  saltan.
* **El importe se recupera de la API.** El cuerpo dice *qué pasó*; lo que
  acredita se lee de la fuente. Stripe lo pide porque el cuerpo puede estar
  obsoleto y el principio III lo pide porque lo de fuera es dato.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SECRET = "whsec_test_spec005"
_PATH = "/webhook/billing"


def _sign(payload: bytes, *, secret: str = _SECRET, timestamp: int | None = None) -> str:
    """Cabecera ``Stripe-Signature`` con el esquema v1 documentado."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.".encode() + payload
    mac = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def _event(
    event_type: str = "invoice.paid",
    *,
    event_id: str | None = None,
    partner_id: uuid.UUID | None = None,
    obj: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": event_id or f"evt_{uuid.uuid4().hex[:16]}",
        "type": event_type,
        "data": {"object": obj or {"id": "in_1", "amount_paid": 2000, "status": "paid"}},
    }
    if partner_id is not None:
        body["data"]["object"].setdefault("metadata", {})["partner_id"] = str(partner_id)
    return body


@pytest.fixture(autouse=True)
def _billing_keys(monkeypatch: pytest.MonkeyPatch):
    """Llaves de prueba, y caché de ajustes limpia entre tests."""
    from nexus_api.config import get_settings

    monkeypatch.setenv("NEXUS_BILLING_API_KEY", "sk_test_spec005")
    monkeypatch.setenv("NEXUS_BILLING_PUBLIC_KEY", "pk_test_spec005")
    monkeypatch.setenv("NEXUS_BILLING_WEBHOOK_SECRET", _SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client():
    from nexus_api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _events_for(event_id: str) -> list[dict[str, Any]]:
    async with get_sessionmaker()() as s:
        rows = (
            (
                await s.execute(
                    sa.text(
                        "SELECT provider_event_id, status, partner_id, payload "
                        "FROM billing_events WHERE provider_event_id = :e"
                    ),
                    {"e": event_id},
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]


# ── R4.1 · la firma ───────────────────────────────────────────────────────────


async def test_an_invalid_signature_is_refused_without_reading_the_body(client) -> None:
    body = json.dumps(_event()).encode()
    resp = await client.post(
        _PATH, content=body, headers={"Stripe-Signature": _sign(body, secret="whsec_wrong")}
    )
    assert resp.status_code == 400, resp.text
    assert await _events_for(json.loads(body)["id"]) == [], (
        "un aviso con firma inválida dejó fila: se interpretó antes de verificar"
    )


async def test_a_missing_signature_header_is_refused(client) -> None:
    body = json.dumps(_event()).encode()
    resp = await client.post(_PATH, content=body)
    assert resp.status_code == 400


async def test_a_tampered_body_fails_even_with_a_valid_old_signature(client) -> None:
    """La firma cubre los bytes, no el significado."""
    original = json.dumps(_event()).encode()
    signature = _sign(original)
    tampered = original.replace(b'"amount_paid": 2000', b'"amount_paid": 999999')
    resp = await client.post(_PATH, content=tampered, headers={"Stripe-Signature": signature})
    assert resp.status_code == 400


# ── R4.2 y R4.4 · registrar antes de actuar, e idempotencia ──────────────────


async def test_the_event_is_recorded_before_it_is_acted_on(client) -> None:
    event = _event()
    body = json.dumps(event).encode()
    resp = await client.post(_PATH, content=body, headers={"Stripe-Signature": _sign(body)})
    assert resp.status_code == 200, resp.text
    rows = await _events_for(event["id"])
    assert len(rows) == 1, "el aviso no quedó registrado"
    assert rows[0]["status"] in {"received", "processed", "ignored"}


async def test_five_resends_of_the_same_event_leave_one_row(client) -> None:
    event = _event()
    body = json.dumps(event).encode()
    signature = _sign(body)
    for _ in range(5):
        resp = await client.post(_PATH, content=body, headers={"Stripe-Signature": signature})
        assert resp.status_code == 200, resp.text
    rows = await _events_for(event["id"])
    assert len(rows) == 1, f"cinco reenvíos dejaron {len(rows)} filas: se doblaría un ingreso"


async def test_concurrent_delivery_of_the_same_event_leaves_one_row(client) -> None:
    """Dos entregas a la vez pasan de verdad, y es lo que un SELECT previo no para."""
    import asyncio

    event = _event()
    body = json.dumps(event).encode()
    signature = _sign(body)
    results = await asyncio.gather(
        *(
            client.post(_PATH, content=body, headers={"Stripe-Signature": signature})
            for _ in range(4)
        ),
        return_exceptions=True,
    )
    codes = [r.status_code for r in results if hasattr(r, "status_code")]
    assert codes and all(c == 200 for c in codes), codes
    rows = await _events_for(event["id"])
    assert len(rows) == 1, f"entrega concurrente dejó {len(rows)} filas"


# ── R4.3 · deprisa, y el trabajo aparte ──────────────────────────────────────


async def test_the_webhook_answers_well_under_the_redirect_budget(client) -> None:
    """No es una meta de estilo: el proveedor espera hasta 10 s antes de
    redirigir al cliente a la página de gracias, y una página de gracias que
    tarda diez segundos parece un pago fallido."""
    event = _event()
    body = json.dumps(event).encode()
    started = time.perf_counter()
    resp = await client.post(_PATH, content=body, headers={"Stripe-Signature": _sign(body)})
    elapsed = time.perf_counter() - started
    assert resp.status_code == 200
    assert elapsed < 0.5, f"el webhook tardó {elapsed:.3f}s"


# ── R4.5 · orden y procedencia del dato ──────────────────────────────────────


async def test_an_event_out_of_order_does_not_corrupt_the_state(client) -> None:
    """``subscription.updated`` antes que ``invoice.paid``."""
    pid = uuid.uuid4()
    async with get_sessionmaker()() as s:
        slug = f"ooo-{pid.hex[:8]}"
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.commit()

    for event_type, obj in (
        ("customer.subscription.updated", {"id": "sub_1", "status": "active"}),
        ("invoice.paid", {"id": "in_1", "amount_paid": 2000, "status": "paid"}),
    ):
        event = _event(event_type, partner_id=pid, obj=obj)
        body = json.dumps(event).encode()
        resp = await client.post(_PATH, content=body, headers={"Stripe-Signature": _sign(body)})
        assert resp.status_code == 200, resp.text

    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                sa.text("SELECT state, tier_code FROM partner_subscriptions WHERE partner_id = :p"),
                {"p": str(pid)},
            )
        ).first()
    # Lo que no puede pasar es un estado inventado ni una fila a medias.
    if row is not None:
        from nexus_api.db.models.membership import SUBSCRIPTION_STATES, TIER_CODES

        assert row[0] in SUBSCRIPTION_STATES
        assert row[1] in TIER_CODES


async def test_the_recorded_payload_carries_no_card_data(client) -> None:
    event = _event(
        obj={
            "id": "in_1",
            "amount_paid": 2000,
            "status": "paid",
            "payment_method_details": {"card": {"last4": "4242", "exp_month": 12}},
        }
    )
    body = json.dumps(event).encode()
    resp = await client.post(_PATH, content=body, headers={"Stripe-Signature": _sign(body)})
    assert resp.status_code == 200
    rows = await _events_for(event["id"])
    blob = json.dumps(rows[0]["payload"])
    for needle in ("last4", "4242", "exp_month"):
        assert needle not in blob, f"«{needle}» quedó guardado en billing_events.payload"


# ── V59 y V60 · las dos cosas de research D10 ────────────────────────────────


async def test_a_finalization_failure_is_recorded_and_degrades_nobody(client) -> None:
    """La avería más silenciosa: la suscripción sigue activa y no se cobra.

    No es culpa del partner, así que su estado **no se mueve**. Lo que tiene
    que ocurrir es que quede registrado para que un operador lo vea.
    """
    pid = uuid.uuid4()
    async with get_sessionmaker()() as s:
        slug = f"ff-{pid.hex[:8]}"
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.execute(
            sa.text(
                "INSERT INTO partner_subscriptions (partner_id, tier_code, state) "
                "VALUES (:p, 'pro', 'current')"
            ),
            {"p": str(pid)},
        )
        await s.commit()

    event = _event(
        "invoice.finalization_failed",
        partner_id=pid,
        obj={"id": "in_2", "last_finalization_error": {"code": "tax_location_invalid"}},
    )
    body = json.dumps(event).encode()
    resp = await client.post(_PATH, content=body, headers={"Stripe-Signature": _sign(body)})
    assert resp.status_code == 200

    assert len(await _events_for(event["id"])) == 1, "no quedó registrada la avería"
    async with get_sessionmaker()() as s:
        state = await s.scalar(
            sa.text("SELECT state FROM partner_subscriptions WHERE partner_id = :p"),
            {"p": str(pid)},
        )
    assert state == "current", (
        f"una factura que no finaliza degradó al partner a «{state}». No es culpa "
        "suya: lo que hay que hacer es avisar al operador"
    )


async def test_the_partner_is_resolved_from_the_notice_not_from_the_customer_id(
    client,
) -> None:
    """``client_reference_id`` — lo que mantiene borrable ``stripe_customer_id``."""
    pid = uuid.uuid4()
    async with get_sessionmaker()() as s:
        slug = f"cri-{pid.hex[:8]}"
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.commit()

    event = _event(
        "checkout.session.completed",
        obj={
            "id": f"cs_{uuid.uuid4().hex[:12]}",
            "client_reference_id": str(pid),
            "payment_status": "paid",
            "amount_total": 5000,
            # Sin customer_id a propósito: si el manejador lo necesitara,
            # este test fallaría — y ese es justo el acoplamiento que D5.1 evita.
        },
    )
    body = json.dumps(event).encode()
    resp = await client.post(_PATH, content=body, headers={"Stripe-Signature": _sign(body)})
    assert resp.status_code == 200

    rows = await _events_for(event["id"])
    assert rows, "el aviso no se registró"
    assert str(rows[0]["partner_id"]) == str(pid), (
        "el partner no se resolvió desde el aviso: el manejador depende de "
        "stripe_customer_id, que es lo que rompe la migración de cuenta"
    )
