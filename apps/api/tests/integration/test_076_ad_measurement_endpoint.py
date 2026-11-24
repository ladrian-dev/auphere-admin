"""Spec 076, requisitos 4.1 a 4.8, 7.2 y 7.4 — activar la medición de un número.

``GET /console/clients/{ref}/channels/{id}`` trae el bloque ``ad_measurement``
solo si el número la admite (tenant en la lista o apertura general; WhatsApp de
Meta; no en coexistencia por ahora). ``PUT …/ad-measurement``:

- sin ``confirm_data_sharing`` → 422 ``confirm_required``;
- el token del número sin ``whatsapp_business_manage_events`` → 409
  ``reauthorize`` y no se activa;
- activar → crea u obtiene el conjunto de datos, lo guarda, nombra a quien lo
  activó y deja la auditoría con la confirmación;
- un fallo de Meta → 502 ``meta_unavailable`` y nada activado;
- desactivar → los pendientes del número se descartan.

Meta se sustituye por un doble: nada sale a la red.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.credentials import ChannelCredentialsRepository, MetaCredentials
from nexus_channels.whatsapp_meta.exceptions import MetaTransientError

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AdConversionEvent,
    AuditLog,
    Channel,
    ChannelAdMeasurement,
    ChannelStatus,
    ChannelType,
    Customer,
)
from nexus_api.services import ad_measurement

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SCOPE = "whatsapp_business_manage_events"


class FakeMeta:
    def __init__(self, *, scopes: set[str] | None = None, fail: bool = False) -> None:
        self.scopes = scopes if scopes is not None else {SCOPE, "whatsapp_business_messaging"}
        self.fail = fail
        self.datasets: list[str] = []

    async def token_scopes(self, *, input_token: str, app_id: str) -> set[str]:
        assert input_token == "TOKEN-OF-THE-NUMBER"
        return self.scopes

    async def ensure_dataset(self, *, waba_id: str, access_token: str) -> str:
        if self.fail:
            raise MetaTransientError("down", status_code=503)
        self.datasets.append(waba_id)
        return "DS-777"

    async def close(self) -> None:
        return None


@pytest.fixture
def meta(monkeypatch: pytest.MonkeyPatch) -> FakeMeta:
    fake = FakeMeta()
    monkeypatch.setattr(ad_measurement, "meta_client", lambda: fake)
    return fake


@pytest.fixture
def listed(monkeypatch: pytest.MonkeyPatch, console_world: dict[str, Any]) -> None:
    monkeypatch.setattr(
        get_settings(), "ad_measurement_tenants", str(console_world["a"]["tenant_id"])
    )


async def _number(
    tenant_id: uuid.UUID, *, mode: str = "cloud_api", kind: ChannelType = ChannelType.WHATSAPP
) -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        ch = Channel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            type=kind,
            provider="meta",
            provider_identifier=f"+5699{uuid.uuid4().int % 10**7:07d}",
            status=ChannelStatus.ACTIVE,
            config={"phone_number_id": "PN1", "waba_id": "WABA1", "mode": mode},
        )
        s.add(ch)
        await s.flush()
        await ChannelCredentialsRepository(s).upsert(
            ch.id,
            MetaCredentials(
                bisuat="TOKEN-OF-THE-NUMBER",
                waba_id="WABA1",
                phone_number_id="PN1",
                business_id="BIZ",
                display_phone_number=ch.provider_identifier,
                verify_token="v",
                mode=mode,  # type: ignore[arg-type]
            ),
        )
        await s.commit()
        return ch.id


def _url(w: dict[str, Any], channel: uuid.UUID, tail: str = "") -> str:
    return f"/console/clients/{w['ref']}/channels/{channel}{tail}"


async def _put(client: Any, w: dict[str, Any], channel: uuid.UUID, **body: Any) -> Any:
    return await client.put(_url(w, channel, "/ad-measurement"), json=body, headers=w["headers"]())


async def _row(tenant_id: uuid.UUID, channel: uuid.UUID) -> ChannelAdMeasurement | None:
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, tenant_id):
        row = (
            await s.execute(
                sa.select(ChannelAdMeasurement).where(ChannelAdMeasurement.channel_id == channel)
            )
        ).scalar_one_or_none()
        if row is not None:
            s.expunge(row)
        return row


async def test_not_offered_without_the_list(client, console_world, meta) -> None:
    w = console_world["a"]
    ch = await _number(w["tenant_id"])
    page = await client.get(_url(w, ch), headers=w["headers"]())
    assert page.status_code == 200, page.text
    assert page.json().get("ad_measurement") is None
    r = await _put(client, w, ch, enabled=True, confirm_data_sharing=True)
    assert r.status_code == 404


async def test_not_offered_in_coexistence(client, console_world, meta, listed) -> None:
    w = console_world["a"]
    ch = await _number(w["tenant_id"], mode="coexistence")
    assert (await client.get(_url(w, ch), headers=w["headers"]())).json().get(
        "ad_measurement"
    ) is None
    assert (await _put(client, w, ch, enabled=True, confirm_data_sharing=True)).status_code == 404


async def test_offered_and_off_by_default(client, console_world, meta, listed) -> None:
    w = console_world["a"]
    ch = await _number(w["tenant_id"])
    block = (await client.get(_url(w, ch), headers=w["headers"]())).json()["ad_measurement"]
    assert block["state"] == "off" and block["enabled"] is False
    assert block["dataset_linked"] is False and block["sent_7d"] == 0
    assert block["reconnect_config_id"] == get_settings().meta_config_id_wa_cloud_api


async def test_the_test_config_is_used_when_set(
    client, console_world, meta, listed, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "meta_config_id_wa_events_test_cloud_api", "TEST-CFG")
    w = console_world["a"]
    ch = await _number(w["tenant_id"])
    block = (await client.get(_url(w, ch), headers=w["headers"]())).json()["ad_measurement"]
    assert block["reconnect_config_id"] == "TEST-CFG"


async def test_confirmation_is_required(client, console_world, meta, listed) -> None:
    w = console_world["a"]
    ch = await _number(w["tenant_id"])
    r = await _put(client, w, ch, enabled=True, confirm_data_sharing=False)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "confirm_required"
    assert await _row(w["tenant_id"], ch) is None


async def test_missing_permission_asks_to_reconnect(client, console_world, meta, listed) -> None:
    meta.scopes = {"whatsapp_business_messaging"}
    w = console_world["a"]
    ch = await _number(w["tenant_id"])
    r = await _put(client, w, ch, enabled=True, confirm_data_sharing=True)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "reauthorize"
    row = await _row(w["tenant_id"], ch)
    assert row is None or row.enabled is False
    block = (await client.get(_url(w, ch), headers=w["headers"]())).json()["ad_measurement"]
    assert block["state"] == "reauthorize" and block["enabled"] is False


async def test_enabling_links_the_dataset_and_audits(client, console_world, meta, listed) -> None:
    w = console_world["a"]
    ch = await _number(w["tenant_id"])
    r = await _put(client, w, ch, enabled=True, confirm_data_sharing=True)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "on" and r.json()["enabled"] is True
    assert r.json()["dataset_linked"] is True
    assert meta.datasets == ["WABA1"]
    row = await _row(w["tenant_id"], ch)
    assert row is not None and row.enabled and row.meta_dataset_id == "DS-777"
    assert row.enabled_by and row.enabled_at is not None
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant_id"]):
        audit = (
            await s.execute(
                sa.select(AuditLog).where(
                    AuditLog.action == "console.channel.ad_measurement",
                    AuditLog.target == f"channel:{ch}",
                )
            )
        ).scalar_one()
    assert audit.after_json["enabled"] is True
    assert audit.after_json["confirm_data_sharing"] is True
    assert audit.after_json["meta_dataset_id"] == "DS-777"


async def test_meta_down_enables_nothing(client, console_world, meta, listed) -> None:
    meta.fail = True
    w = console_world["a"]
    ch = await _number(w["tenant_id"])
    r = await _put(client, w, ch, enabled=True, confirm_data_sharing=True)
    assert r.status_code == 502 and r.json()["detail"]["code"] == "meta_unavailable"
    row = await _row(w["tenant_id"], ch)
    assert row is None or row.enabled is False


async def test_disabling_discards_what_is_pending(client, console_world, meta, listed) -> None:
    w = console_world["a"]
    ch = await _number(w["tenant_id"])
    assert (await _put(client, w, ch, enabled=True, confirm_data_sharing=True)).status_code == 200
    sm = get_sessionmaker()
    async with sm() as s, tenant_scoped_session(s, w["tenant_id"]):
        ana = Customer(tenant_id=w["tenant_id"], identifier="56911110000", preferences={})
        s.add(ana)
        await s.flush()
        s.add(
            AdConversionEvent(
                tenant_id=w["tenant_id"],
                channel_id=ch,
                customer_id=ana.id,
                source_kind="reservation",
                source_id="r1",
                event_name="Purchase",
                event_id="reservation:r1:Purchase",
                event_time=datetime.now(UTC),
                value_minor=100,
                currency="CLP",
            )
        )
        await s.commit()
    r = await _put(client, w, ch, enabled=False, confirm_data_sharing=False)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "off"
    async with sm() as s, tenant_scoped_session(s, w["tenant_id"]):
        statuses = (await s.execute(sa.select(AdConversionEvent.status))).scalars().all()
    assert list(statuses) == ["discarded"]
    row = await _row(w["tenant_id"], ch)
    assert row is not None and row.disabled_by and row.disabled_at is not None


async def test_an_analyst_cannot_switch_it(client, db_session, console_world, meta, listed) -> None:
    from tests.conftest import add_console_member

    w = console_world["a"]
    ch = await _number(w["tenant_id"])
    analyst = await add_console_member(db_session, partner_id=w["partner_id"], role="analyst")
    r = await client.put(
        _url(w, ch, "/ad-measurement"),
        json={"enabled": True, "confirm_data_sharing": True},
        headers=analyst["headers"](),
    )
    assert r.status_code == 403
