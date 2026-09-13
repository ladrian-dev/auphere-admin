"""Spec 005 · T117 — la costura entre el webhook y el worker.

El webhook **registra y encola**; el worker **aplica**. Cada mitad tenía su
test y la unión no tenía ninguno, así que el 2026-09-13, configurando staging y
producción, se vio que `nexus:billing:events` no tenía consumidor: `handle_entry`
existía, estaba probado, y no lo arrancaba nadie. El aviso llegaba, se guardaba,
se encolaba y ahí moría. El producto **cobraba sin entregar** y las 115 tareas de
la spec estaban en verde, porque cada pieza se había probado por separado.

Por eso este test **no llama a `handle_entry`**. Llama a `drain_once`, que es el
bucle que lee el stream: es lo único que comprueba que el cable está puesto.
Llamar al manejador a mano es exactamente lo que ocultó la avería —la misma
lección que la cabecera de `test_no_external_debit.py` ya había aprendido un
nivel más abajo.

Si alguien vuelve a dejar el consumidor sin declarar, este test se pone rojo
donde importa: en el saldo que el partner pagó y no recibió.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SECRET = "whsec_test_t117"
_PATH = "/webhook/billing"
_STREAM = "nexus:billing:events"
#: 30 $ en céntimos. Positivo y por encima de cero, que es una de las tres
#: puertas de ``apply_credit_purchase``.
_CENTS = 3_000


def _worker_on_path() -> None:
    """El worker no es dependencia de ``apps/api``; el camino real vive ahí."""
    worker_src = Path(__file__).resolve().parents[3] / "worker" / "src"
    if str(worker_src) not in sys.path:
        sys.path.insert(0, str(worker_src))


def _sign(payload: bytes) -> str:
    ts = int(time.time())
    mac = hmac.new(_SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


@pytest.fixture(autouse=True)
def _billing_keys(monkeypatch: pytest.MonkeyPatch) -> Any:
    from nexus_api.config import get_settings

    monkeypatch.setenv("NEXUS_BILLING_API_KEY", "sk_test_t117")
    monkeypatch.setenv("NEXUS_BILLING_PUBLIC_KEY", "pk_test_t117")
    monkeypatch.setenv("NEXUS_BILLING_WEBHOOK_SECRET", _SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def client() -> Any:
    from nexus_api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _partner() -> uuid.UUID:
    pid = uuid.uuid4()
    slug = f"t117-{pid.hex[:10]}"
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.commit()
    return pid


async def _purchased(pid: uuid.UUID) -> int:
    async with get_sessionmaker()() as s:
        value = await s.scalar(
            sa.text("SELECT purchased_remaining FROM partner_wallets WHERE partner_id = :p"),
            {"p": str(pid)},
        )
    assert value is not None, "el partner no tiene libro"
    return int(value)


async def _event_status(provider_event_id: str) -> str | None:
    async with get_sessionmaker()() as s:
        return await s.scalar(
            sa.text("SELECT status FROM billing_events WHERE provider_event_id = :e"),
            {"e": provider_event_id},
        )


def _notice(*, partner_id: uuid.UUID | None, session_id: str) -> dict[str, Any]:
    """Una compra de crédito confirmada, tal y como la manda el proveedor."""
    obj: dict[str, Any] = {
        "id": session_id,
        "object": "checkout.session",
        "amount_total": _CENTS,
        "payment_status": "paid",
        "mode": "payment",
        "metadata": {},
    }
    if partner_id is not None:
        obj["client_reference_id"] = str(partner_id)
    return {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "type": "checkout.session.completed",
        "data": {"object": obj},
    }


class _FakeCheckout:
    """Lo que el proveedor devuelve al recuperar la sesión por su id."""

    def __init__(self, session_id: str) -> None:
        self.id = session_id
        self.amount_total = _CENTS
        self.payment_status = "paid"
        self.mode = "payment"
        self.customer = "cus_t117"
        self.subscription = None
        self.metadata: dict[str, str] = {}


class _FakeClient:
    def __init__(self, obj: Any) -> None:
        self._obj = obj
        self.checkout = self
        self.sessions = self
        self.invoices = self
        self.subscriptions = self

    def retrieve(self, _id: str) -> Any:
        return self._obj


async def _post(client: Any, notice: dict[str, Any]) -> Any:
    body = json.dumps(notice).encode()
    return await client.post(
        _PATH,
        content=body,
        headers={"Stripe-Signature": _sign(body), "Content-Type": "application/json"},
    )


async def _drain(redis: Any, session_id: str) -> int:
    """Corre el bucle de verdad. **No** llama a ``handle_entry``."""
    _worker_on_path()
    from nexus_worker.billing.process_event import drain_once

    return await drain_once(
        redis,
        get_sessionmaker(),
        _FakeClient(_FakeCheckout(session_id)),
        consumer_name="t117",
    )


async def test_a_confirmed_purchase_reaches_the_book_through_the_stream(
    client: Any, fake_redis: Any
) -> None:
    """El camino entero: aviso firmado → stream → consumidor → saldo."""
    pid = await _partner()
    before = await _purchased(pid)
    session_id = f"cs_test_{uuid.uuid4().hex[:12]}"
    notice = _notice(partner_id=pid, session_id=session_id)

    response = await _post(client, notice)
    assert response.status_code == 200, response.text
    # El webhook responde deprisa y deja el trabajo para después (Requisito 4.3).
    assert response.json() == {"status": "queued"}

    # La entrada tiene que estar ahí: si el webhook no encolara, el consumidor
    # no tendría nada que leer y este test pasaría por el motivo equivocado.
    assert await fake_redis.xlen(_STREAM) == 1, "el webhook no encoló el aviso"

    attended = await _drain(fake_redis, session_id)
    assert attended == 1, "el consumidor no leyó la entrada del stream"

    after = await _purchased(pid)
    assert after > before, (
        f"el saldo comprado no subió ({before} → {after}). El aviso llegó, se "
        "encoló y no se aplicó: es la avería del 2026-09-13"
    )
    assert await _event_status(notice["id"]) == "processed"


async def test_an_orphan_notice_ends_failed_and_moves_no_balance(
    client: Any, fake_redis: Any
) -> None:
    """Un aviso que no es nuestro se guarda y se marca, no se aplica.

    Importa más de lo que parece: la cuenta del proveedor puede alojar otro
    negocio —en producción lo hace—, así que llegarán compras ajenas. El destino
    correcto es ``failed`` con rastro, y **ningún** saldo movido.
    """
    pid = await _partner()
    before = await _purchased(pid)
    session_id = f"cs_test_{uuid.uuid4().hex[:12]}"
    notice = _notice(partner_id=None, session_id=session_id)

    response = await _post(client, notice)
    assert response.status_code == 200, response.text

    attended = await _drain(fake_redis, session_id)
    assert attended == 1

    assert await _event_status(notice["id"]) == "failed"
    assert await _purchased(pid) == before, "un aviso huérfano movió un saldo"


async def test_the_same_purchase_credits_once(client: Any, fake_redis: Any) -> None:
    """Dos avisos distintos para la misma sesión acreditan una vez (3.3).

    ``checkout.session.completed`` y ``async_payment_succeeded`` llegan los dos
    para la misma compra, y la restricción única del id del aviso no los atrapa
    porque son avisos distintos. El ancla es el id de la sesión.
    """
    pid = await _partner()
    session_id = f"cs_test_{uuid.uuid4().hex[:12]}"

    first = _notice(partner_id=pid, session_id=session_id)
    await _post(client, first)
    await _drain(fake_redis, session_id)
    once = await _purchased(pid)

    second = _notice(partner_id=pid, session_id=session_id)
    second["type"] = "checkout.session.async_payment_succeeded"
    await _post(client, second)
    await _drain(fake_redis, session_id)

    assert await _purchased(pid) == once, "la segunda confirmación acreditó otra vez"
    assert await _event_status(second["id"]) == "ignored"
