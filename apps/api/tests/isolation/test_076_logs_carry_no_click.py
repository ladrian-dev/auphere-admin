"""Garantía 6 — los logs del envío a Meta llevan el tenant y nunca a la persona.

Spec 076, requisito 6.7. Se capturan los logs de guardar un clic, encolar,
enviar, reintentar, fallar y descartar, y se comprueba que:

- todos llevan ``tenant_id``;
- ninguno contiene el ``ctwa_clid``, el teléfono, el teléfono normalizado ni su
  SHA-256.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
import sqlalchemy as sa
import structlog
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL, MetaClient
from nexus_worker.conversions.dispatcher import drain_tenant
from nexus_worker.runtime.dispatcher import accept_inbound

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import ChannelAdMeasurement, Reservation
from nexus_api.services.ad_conversion_dispatch import Outcome, Outgoing
from nexus_api.services.ad_conversions import enqueue_for_booking

from ..integration.test_076_conversion_dispatch import PHONE, _click, _event, _world

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

CLID = "SECRET-CLICK-7f3a"
SECRETS = (CLID, PHONE, hashlib.sha256(PHONE.encode()).hexdigest())
OURS = ("ad_referral.", "ad_conversion.", "ad_measurement.")
#: Lo que el recorrido tiene que haber registrado: si un paso deja de escribir
#: su log, esta prueba no puede quedarse en verde sin mirarlo.
EXPECTED = {
    "ad_referral.stored",
    "ad_conversion.enqueued",
    "ad_conversion.sent",
    "ad_conversion.failed",
    "ad_conversion.retry",
    "ad_conversion.discarded",
}


def _check(logs: list[dict[str, Any]]) -> None:
    mine = [e for e in logs if str(e.get("event", "")).startswith(OURS)]
    assert {e["event"] for e in mine} >= EXPECTED, sorted({e["event"] for e in mine})
    for entry in mine:
        assert entry.get("tenant_id"), entry
        text = json.dumps(entry, default=str)
        for secret in SECRETS:
            assert secret not in text, (secret, entry["event"])


async def test_the_whole_flow_logs_no_person(db_session) -> None:
    w = await _world(db_session)
    with structlog.testing.capture_logs() as logs:
        # Guardar el clic (worker) con un mensaje que trae el anuncio.
        from tests.integration._turn_world import World

        world = World(
            tenant_id=w["tenant"],
            channel_id=w["channel"],
            agent_id=uuid.uuid4(),
            provider_identifier="x",
        )
        accepted = await accept_inbound(
            world.event(
                "Vi su anuncio", user=PHONE, referral={"source_type": "ad", "ctwa_clid": CLID}
            )
        )
        # Encolar una reserva del agente en esa conversación.
        sm = get_sessionmaker()
        async with sm() as s, tenant_scoped_session(s, w["tenant"]):
            res = Reservation(
                tenant_id=w["tenant"],
                mode="capacity",
                status="confirmed",
                starts_at=datetime.now(UTC) + timedelta(days=1),
                ends_at=datetime.now(UTC) + timedelta(days=1, hours=1),
                origin="agent",
                channel="whatsapp",
                created_by_kind="agent",
                price_minor=100,
                currency="CLP",
                customer_id=w["ana"],
                conversation_id=accepted.conversation_id,
            )
            s.add(res)
            await s.flush()
            await enqueue_for_booking(s, res)
            await s.commit()

        async def ok(out: Outgoing) -> Outcome:
            return Outcome("sent")

        await drain_tenant(w["tenant"], send=ok)
        # Un fallo, un reintento y un descarte.
        await _event(w, source="r-fail")
        await drain_tenant(w["tenant"], send=lambda o: _const(Outcome("failed", "meta_100")))
        await _event(w, source="r-retry")
        await drain_tenant(w["tenant"], send=lambda o: _const(Outcome("retry", "meta_transient")))
        async with sm() as s, tenant_scoped_session(s, w["tenant"]):
            await s.execute(sa.update(ChannelAdMeasurement).values(enabled=False))
            await s.commit()
        await _event(w, source="r-off")
        await drain_tenant(w["tenant"], send=ok)
    _check(logs)


async def _const(outcome: Outcome) -> Outcome:
    return outcome


async def test_the_real_send_to_meta_logs_no_person_and_no_token(db_session, monkeypatch) -> None:
    """Por el envío de verdad (``deliver`` y el cliente de Meta), con un error de
    Meta que repite el clic y el teléfono en su mensaje: ningún log lleva el
    clic, el teléfono, su hash ni el token del número."""
    token = "TOKEN-SECRET-9f2"
    w = await _world(db_session, token=token, dataset="DS-ECHO")
    ref = await _click(w, clid=CLID)
    await _event(w, referral=ref, source="r-echo")
    await _event(w, source="r-hash")
    monkeypatch.setattr(
        "nexus_worker.conversions.dispatcher._client",
        lambda: MetaClient("app-secret", max_retries=1),
    )
    echo = {
        "error": {
            "message": f"Invalid parameter: ctwa_clid {CLID} ph {SECRETS[2]} phone {PHONE}",
            "type": "OAuthException",
            "code": 100,
        }
    }
    with (
        structlog.testing.capture_logs() as logs,
        respx.mock(base_url=META_GRAPH_BASE_URL) as mock,
    ):
        route = mock.post("/DS-ECHO/events").mock(return_value=httpx.Response(400, json=echo))
        await drain_tenant(w["tenant"])
    assert route.call_count == 2
    events = {e.get("event") for e in logs}
    assert "ad_conversion.failed" in events, sorted(map(str, events))
    for entry in logs:
        text = json.dumps(entry, default=str)
        for secret in (*SECRETS, token):
            assert secret not in text, (secret, entry.get("event"))
