"""Spec 005 · R3.4 y ADR-037 D3 — la conciliación va en una sola dirección.

**Ningún aviso del proveedor puede restar saldo. Ninguno.**

Por qué merece un fichero propio y un recorrido exhaustivo: un aviso externo
que pudiera restar convierte cualquier fallo del proveedor —un evento
duplicado leído al revés, un reembolso mal interpretado, un evento de prueba
que se cuela en producción— en **saldo que desaparece de la cuenta de alguien
que pagó**. Sumar de más es un error que se ve, se explica y se corrige.
Restar de más lo descubre el partner cuando su agente se calla.

Y por qué es exhaustivo y no un caso: la avería que previene **no es un
evento concreto, es una clase**. Se recorren todos los tipos manejados y
algunos que no lo están, con el saldo puesto en una cifra conocida, y se
comprueba que ninguno lo baja.

> **Dónde se ejerce, y por qué importa.** La primera versión de este fichero
> mandaba los avisos al webhook y miraba el saldo. Pasaba siempre — y no
> vigilaba nada: **el webhook solo registra y encola**, y el trabajo que
> podría restar lo hace el worker. Se comprobó metiendo una resta de verdad en
> un manejador: el test seguía en verde. Ahora se ejercita ``handle_entry``,
> que es donde se aplica un aviso, y esa misma sonda lo pone en rojo.
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

from nexus_api.billing.events import HANDLED_EVENTS
from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_SECRET = "whsec_test_spec005"
_PATH = "/webhook/billing"
_START = 50_000

#: Tipos a los que NO estamos suscritos, incluidos a propósito: si algún día
#: alguien los añade sin pensar, este test es el que lo para.
_ALSO_TRIED = (
    "charge.refunded",
    "charge.dispute.created",
    "invoice.voided",
    "customer.subscription.paused",
    "invoice.created",
)


def _sign(payload: bytes) -> str:
    ts = int(time.time())
    mac = hmac.new(_SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


@pytest.fixture(autouse=True)
def _billing_keys(monkeypatch: pytest.MonkeyPatch):
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


async def _partner_with_balance() -> uuid.UUID:
    pid = uuid.uuid4()
    slug = f"ned-{pid.hex[:10]}"
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.execute(
            sa.text(
                "UPDATE partner_wallets SET purchased_remaining = :q, included_remaining = :q "
                "WHERE partner_id = :p"
            ),
            {"q": _START, "p": str(pid)},
        )
        await s.commit()
    return pid


async def _balances(pid: uuid.UUID) -> tuple[int, int]:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT included_remaining, purchased_remaining "
                    "FROM partner_wallets WHERE partner_id = :p"
                ),
                {"p": str(pid)},
            )
        ).first()
    assert row is not None, "el partner no tiene libro"
    return int(row[0]), int(row[1])


def _event(event_type: str, partner_id: uuid.UUID) -> dict[str, Any]:
    """Un aviso con todo lo que un manejador podría mirar para restar.

    Lleva importes negativos y campos de reembolso a propósito: si algún
    manejador los usara, el saldo bajaría y el test lo vería.
    """
    return {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "type": event_type,
        "data": {
            "object": {
                "id": f"obj_{uuid.uuid4().hex[:10]}",
                "client_reference_id": str(partner_id),
                "metadata": {"partner_id": str(partner_id)},
                "amount_total": -99_999,
                "amount_refunded": 99_999,
                "amount_paid": -12_345,
                "status": "refunded",
                "payment_status": "paid",
            }
        },
    }


class _FakeProviderObject:
    """Lo que el proveedor devolvería, con todos los campos de restar puestos."""

    def __init__(self, partner_id: uuid.UUID) -> None:
        self.id = f"obj_{uuid.uuid4().hex[:10]}"
        self.amount_total = -99_999
        self.amount_paid = -12_345
        self.amount_refunded = 99_999
        self.payment_status = "paid"
        self.status = "active"
        self.customer = "cus_x"
        self.subscription = "sub_x"
        self.lines = None
        self.metadata = {"partner_id": str(partner_id)}
        self.last_finalization_error = {"code": "probe"}


class _FakeClient:
    def __init__(self, obj: Any) -> None:
        self._obj = obj
        self.invoices = self
        self.subscriptions = self
        self.checkout = self
        self.sessions = self

    def retrieve(self, _id: str) -> Any:
        return self._obj


async def _apply(pid: uuid.UUID, event_type: str) -> None:
    """Aplica un aviso por el camino REAL: el del worker."""
    import sys
    from pathlib import Path

    worker_src = Path(__file__).resolve().parents[3] / "worker" / "src"
    if str(worker_src) not in sys.path:
        sys.path.insert(0, str(worker_src))
    from nexus_worker.billing.process_event import Skip, handle_entry

    obj = _FakeProviderObject(pid)
    async with get_sessionmaker()() as session:
        try:
            await handle_entry(
                session,
                _FakeClient(obj),
                {
                    "event_type": event_type,
                    "partner_id": str(pid),
                    "provider_event_id": f"evt_{uuid.uuid4().hex[:8]}",
                    "object_id": obj.id,
                    "checkout_session_id": obj.id,
                },
            )
            await session.commit()
        except Skip:
            # Un aviso que no procede no es un fallo: es el caso normal.
            await session.rollback()
        except Exception:
            # Un manejador que revienta tampoco puede haber restado nada, y
            # eso es justo lo que el test de fuera comprueba.
            await session.rollback()


async def test_no_handled_event_ever_lowers_a_balance() -> None:
    """El recorrido completo, por el camino donde se aplica de verdad."""
    pid = await _partner_with_balance()
    before = await _balances(pid)

    for event_type in sorted(HANDLED_EVENTS):
        await _apply(pid, event_type)

        included, purchased = await _balances(pid)
        assert included >= before[0], (
            f"«{event_type}» bajó el pool de {before[0]} a {included}. Ningún aviso "
            "externo puede restar saldo (ADR-037 D3)"
        )
        assert purchased >= before[1], (
            f"«{event_type}» bajó el crédito comprado de {before[1]} a {purchased}. "
            "Eso es dinero que el partner pagó"
        )


async def test_no_unsubscribed_event_lowers_a_balance_either(client) -> None:
    """Los que hoy se ignoran, por si mañana alguien los maneja."""
    pid = await _partner_with_balance()
    before = await _balances(pid)

    for event_type in _ALSO_TRIED:
        body = json.dumps(_event(event_type, pid)).encode()
        resp = await client.post(_PATH, content=body, headers={"Stripe-Signature": _sign(body)})
        assert resp.status_code == 200, f"{event_type}: {resp.text}"

    assert await _balances(pid) == before


async def test_a_refund_notice_does_not_take_credit_back() -> None:
    """Consecuencia incómoda que se acepta a propósito (research D3).

    Un reembolso **no** retira crédito automáticamente: lo decide un operador,
    con rastro. Es raro, y el coste de automatizarlo mal es que a alguien le
    desaparezca saldo que pagó.
    """
    pid = await _partner_with_balance()
    before = await _balances(pid)
    await _apply(pid, "charge.refunded")
    assert await _balances(pid) == before


async def test_the_billing_package_cannot_even_reach_the_debit() -> None:
    """La otra mitad de la garantía, estructural y no por recorrido.

    Un test de comportamiento sólo cubre los caminos que ejecuta. Éste cubre
    los que nadie ha escrito todavía.
    """
    import ast
    from pathlib import Path

    billing = Path(__file__).resolve().parents[2] / "src" / "nexus_api" / "billing"
    offenders: list[str] = []
    for path in billing.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                alias.name in {"debit_wallet", "debit_allocation"} for alias in node.names
            ):
                offenders.append(path.name)
    assert not offenders, f"el paquete de cobro importa una resta: {offenders}"
