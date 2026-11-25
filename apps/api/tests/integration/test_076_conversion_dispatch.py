"""Spec 076, requisitos 5.3, 5.9 y 6.1 a 6.5 — el despachador que envía a Meta.

``drain_tenant`` reserva los eventos pendientes del tenant (con plazo), los
envía **fuera** de la transacción, uno por petición, y anota el resultado. El
envío a Meta se sustituye por un doble que registra lo que recibe.

- cuerpo con clic ``{whatsapp_business_account_id, ctwa_clid}``; sin clic,
  ``{…, whatsapp_phone_number_id, ph}`` con el SHA-256 del teléfono;
- un evento de más de 6 d 23 h no sale (``too_old``);
- transitorio → reintento con espera; token o permiso → ``failed`` y la
  medición del número pide volver a conectar; otro error → ``failed``;
- la medición apagada o una baja nueva al enviar → ``discarded``;
- una cancelación espera a que su original sea final;
- el conjunto de datos y el token son los de la medición y las credenciales del
  tenant del evento.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.credentials import ChannelCredentialsRepository, MetaCredentials
from nexus_worker.conversions.dispatcher import drain_tenant

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AdConversionEvent,
    Channel,
    ChannelAdMeasurement,
    ChannelStatus,
    ChannelType,
    Customer,
    CustomerAdReferral,
    Tenant,
    TenantPlan,
    TenantStatus,
    WhatsAppOptOut,
)
from nexus_api.services.ad_conversion_dispatch import Outcome, Outgoing

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PHONE = "56911112222"


class FakeMeta:
    """Lo que Meta recibe, y lo que responde por evento."""

    def __init__(self, outcome: Outcome | None = None) -> None:
        self.sent: list[Outgoing] = []
        self.outcome = outcome or Outcome("sent")

    async def __call__(self, out: Outgoing) -> Outcome:
        self.sent.append(out)
        return self.outcome


async def _world(
    db_session: Any, *, token: str = "TOKEN-A", dataset: str = "DS-A"
) -> dict[str, Any]:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name="T",
            slug=f"cv-{tid.hex[:10]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
        )
    )
    await db_session.commit()
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tid):
        ch = Channel(
            id=uuid.uuid4(),
            tenant_id=tid,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+5699{uuid.uuid4().int % 10**7:07d}",
            status=ChannelStatus.ACTIVE,
            config={"phone_number_id": f"PN-{token}", "waba_id": f"WABA-{token}"},
        )
        s.add(ch)
        await s.flush()
        await ChannelCredentialsRepository(s).upsert(
            ch.id,
            MetaCredentials(
                bisuat=token,
                waba_id=f"WABA-{token}",
                phone_number_id=f"PN-{token}",
                business_id="B",
                display_phone_number=ch.provider_identifier,
                verify_token="v",
            ),
        )
        s.add(
            ChannelAdMeasurement(
                tenant_id=tid, channel_id=ch.id, enabled=True, meta_dataset_id=dataset
            )
        )
        ana = Customer(tenant_id=tid, identifier=PHONE, phone=PHONE, preferences={})
        s.add(ana)
        await s.commit()
        return {"tenant": tid, "channel": ch.id, "ana": ana.id, "token": token, "dataset": dataset}


async def _click(w: dict[str, Any], clid: str | None = "CLICK") -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        ref = CustomerAdReferral(
            tenant_id=w["tenant"],
            customer_id=w["ana"],
            channel_id=w["channel"],
            provider_message_id=f"wamid.{uuid.uuid4().hex}",
            source_type="ad",
            source_id="A",
            ctwa_clid=clid,
            clicked_at=datetime.now(UTC) - timedelta(hours=1),
        )
        s.add(ref)
        await s.commit()
        return ref.id


async def _event(
    w: dict[str, Any],
    *,
    name: str = "Purchase",
    referral: uuid.UUID | None = None,
    age: timedelta = timedelta(minutes=5),
    cancels: uuid.UUID | None = None,
    status: str = "pending",
    source: str = "r1",
) -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        ev = AdConversionEvent(
            tenant_id=w["tenant"],
            channel_id=w["channel"],
            customer_id=w["ana"],
            referral_id=referral,
            cancels_event_id=cancels,
            source_kind="reservation",
            source_id=source,
            event_name=name,
            event_id=f"reservation:{source}:{name}",
            event_time=datetime.now(UTC) - age,
            value_minor=15000 if name != "LeadSubmitted" else None,
            currency="CLP" if name != "LeadSubmitted" else None,
            status=status,
        )
        s.add(ev)
        await s.commit()
        return ev.id


async def _get(w: dict[str, Any], event: uuid.UUID) -> AdConversionEvent:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        row = await s.get(AdConversionEvent, event)
        assert row is not None
        s.expunge(row)
        return row


async def _measurement(w: dict[str, Any]) -> ChannelAdMeasurement:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        row = (
            await s.execute(
                sa.select(ChannelAdMeasurement).where(
                    ChannelAdMeasurement.channel_id == w["channel"]
                )
            )
        ).scalar_one()
        s.expunge(row)
        return row


async def test_with_a_click(db_session) -> None:
    w = await _world(db_session)
    ref = await _click(w)
    ev = await _event(w, referral=ref)
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    (out,) = meta.sent
    assert out.dataset_id == w["dataset"] and out.access_token == w["token"]
    body = out.event
    assert body["event_name"] == "Purchase" and body["event_id"] == "reservation:r1:Purchase"
    assert body["action_source"] == "business_messaging" and body["messaging_channel"] == "whatsapp"
    assert body["user_data"] == {
        "whatsapp_business_account_id": "WABA-TOKEN-A",
        "ctwa_clid": "CLICK",
    }
    assert body["custom_data"] == {"currency": "CLP", "value": 15000}
    row = await _get(w, ev)
    assert row.status == "sent" and row.sent_at is not None and row.attempts == 1


async def test_without_a_click_goes_with_the_hashed_phone(db_session) -> None:
    w = await _world(db_session)
    await _event(w, name="LeadSubmitted")
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    (out,) = meta.sent
    assert out.event["user_data"] == {
        "whatsapp_business_account_id": "WABA-TOKEN-A",
        "whatsapp_phone_number_id": "PN-TOKEN-A",
        "ph": [hashlib.sha256(PHONE.encode()).hexdigest()],
    }
    assert "custom_data" not in out.event


async def test_a_click_whose_id_was_cleared_falls_back_to_the_phone(db_session) -> None:
    w = await _world(db_session)
    ref = await _click(w, clid=None)
    await _event(w, referral=ref)
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    assert "ph" in meta.sent[0].event["user_data"]


async def test_too_old_never_leaves(db_session) -> None:
    w = await _world(db_session)
    ev = await _event(w, age=timedelta(days=7))
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    assert meta.sent == []
    row = await _get(w, ev)
    assert (row.status, row.last_error_code) == ("failed", "too_old")


async def test_a_transient_error_waits_and_retries(db_session) -> None:
    w = await _world(db_session)
    ev = await _event(w)
    await drain_tenant(w["tenant"], send=FakeMeta(Outcome("retry", "meta_transient")))
    row = await _get(w, ev)
    assert row.status == "pending" and row.attempts == 1
    assert row.next_attempt_at > datetime.now(UTC) + timedelta(seconds=30)
    assert row.lease_until is None


async def test_the_sixth_transient_error_gives_up(db_session) -> None:
    w = await _world(db_session)
    ev = await _event(w)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        await s.execute(
            sa.update(AdConversionEvent).where(AdConversionEvent.id == ev).values(attempts=5)
        )
        await s.commit()
    await drain_tenant(w["tenant"], send=FakeMeta(Outcome("retry", "meta_transient")))
    row = await _get(w, ev)
    assert (row.status, row.last_error_code) == ("failed", "meta_transient")


async def test_token_or_permission_asks_to_reconnect(db_session) -> None:
    w = await _world(db_session)
    ev = await _event(w)
    await drain_tenant(w["tenant"], send=FakeMeta(Outcome("failed", "reauthorize")))
    row = await _get(w, ev)
    assert (row.status, row.last_error_code) == ("failed", "reauthorize")
    m = await _measurement(w)
    assert m.last_error_code == "reauthorize" and m.last_error_at is not None


async def test_another_error_fails_with_its_code(db_session) -> None:
    w = await _world(db_session)
    ev = await _event(w)
    await drain_tenant(w["tenant"], send=FakeMeta(Outcome("failed", "meta_100")))
    assert (await _get(w, ev)).last_error_code == "meta_100"
    assert (await _measurement(w)).last_error_code == "meta_100"


async def test_a_success_clears_the_numbers_error(db_session) -> None:
    w = await _world(db_session)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        await s.execute(
            sa.update(ChannelAdMeasurement)
            .where(ChannelAdMeasurement.channel_id == w["channel"])
            .values(last_error_code="meta_100", last_error_at=datetime.now(UTC))
        )
        await s.commit()
    await _event(w)
    await drain_tenant(w["tenant"], send=FakeMeta())
    assert (await _measurement(w)).last_error_code is None


async def test_measurement_off_at_send_discards(db_session) -> None:
    w = await _world(db_session)
    ev = await _event(w)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        await s.execute(
            sa.update(ChannelAdMeasurement)
            .where(ChannelAdMeasurement.channel_id == w["channel"])
            .values(enabled=False)
        )
        await s.commit()
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    assert meta.sent == [] and (await _get(w, ev)).status == "discarded"


async def test_an_opt_out_at_send_discards(db_session) -> None:
    w = await _world(db_session)
    ev = await _event(w)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        s.add(
            WhatsAppOptOut(
                tenant_id=w["tenant"],
                channel_id=w["channel"],
                customer_id=w["ana"],
                recipient_phone=PHONE,
                scope="marketing",
                source="keyword",
                reason="keyword_stop",
                opted_out_at=datetime.now(UTC),
            )
        )
        await s.commit()
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    assert meta.sent == [] and (await _get(w, ev)).status == "discarded"


async def test_a_cancellation_waits_for_its_original(db_session) -> None:
    w = await _world(db_session)
    original = await _event(w, status="pending")
    cancel = await _event(w, name="OrderCanceled", cancels=original)
    # El original todavía no ha salido: solo sale el original.
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    assert [o.event["event_name"] for o in meta.sent] == ["Purchase"]
    row = await _get(w, cancel)
    assert row.status == "pending" and row.attempts == 0
    # En la pasada siguiente, con el original enviado, sale la cancelación.
    meta2 = FakeMeta()
    await drain_tenant(w["tenant"], send=meta2)
    assert [o.event["event_name"] for o in meta2.sent] == ["OrderCanceled"]
    assert (await _get(w, cancel)).status == "sent"


async def test_a_cancellation_of_something_meta_never_got_is_discarded(db_session) -> None:
    w = await _world(db_session)
    original = await _event(w, status="failed")
    cancel = await _event(w, name="OrderCanceled", cancels=original)
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    assert meta.sent == [] and (await _get(w, cancel)).status == "discarded"


async def test_the_test_event_code_travels_only_when_set(db_session, monkeypatch) -> None:
    w = await _world(db_session)
    await _event(w)
    monkeypatch.setattr(get_settings(), "meta_capi_test_event_code", "TEST42")
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    assert meta.sent[0].test_event_code == "TEST42"


async def test_a_lease_stops_a_second_drain(db_session) -> None:
    w = await _world(db_session)
    ev = await _event(w)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        await s.execute(
            sa.update(AdConversionEvent)
            .where(AdConversionEvent.id == ev)
            .values(lease_until=datetime.now(UTC) + timedelta(minutes=1))
        )
        await s.commit()
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    assert meta.sent == []


async def test_without_click_or_phone_it_fails_and_the_number_says_so(db_session) -> None:
    """Requisito 6.3: un evento sin clic ni teléfono no sale, y el número lo dice."""
    w = await _world(db_session)
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant"]):
        nobody = Customer(tenant_id=w["tenant"], identifier="sin-telefono", preferences={})
        s.add(nobody)
        await s.flush()
        ev = AdConversionEvent(
            tenant_id=w["tenant"],
            channel_id=w["channel"],
            customer_id=nobody.id,
            source_kind="reservation",
            source_id="r-nobody",
            event_name="Purchase",
            event_id="reservation:r-nobody:Purchase",
            event_time=datetime.now(UTC),
            value_minor=100,
            currency="CLP",
            status="pending",
        )
        s.add(ev)
        await s.commit()
        ev_id = ev.id
    meta = FakeMeta()
    await drain_tenant(w["tenant"], send=meta)
    assert meta.sent == []
    row = await _get(w, ev_id)
    assert (row.status, row.last_error_code) == ("failed", "no_identity")
    assert (await _measurement(w)).last_error_code == "no_identity"
