"""Garantía 1 — los eventos de un negocio salen con lo suyo (spec 076, requisito 6.5).

Dos negocios con la medición activa, cada uno con su conjunto de datos y su
token. El despachador, pasando por cada tenant, envía cada evento con el
``meta_dataset_id`` y el token **de su tenant**, y nunca un evento de otro. La
ruta de la medición no acepta un conjunto de datos ni un tenant del llamante.
"""

from __future__ import annotations

from typing import Any

import pytest
from nexus_worker.conversions.dispatcher import drain_tenant

from nexus_api.services.ad_conversion_dispatch import Outcome, Outgoing

from ..integration.test_076_conversion_dispatch import _event, _world

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


class Recorder:
    def __init__(self) -> None:
        self.sent: list[Outgoing] = []

    async def __call__(self, out: Outgoing) -> Outcome:
        self.sent.append(out)
        return Outcome("sent")


async def test_each_tenant_sends_with_its_own_dataset_and_token(db_session) -> None:
    a = await _world(db_session, token="TOKEN-A", dataset="DS-A")
    b = await _world(db_session, token="TOKEN-B", dataset="DS-B")
    await _event(a, source="ra")
    await _event(b, source="rb")

    seen_a = Recorder()
    await drain_tenant(a["tenant"], send=seen_a)
    seen_b = Recorder()
    await drain_tenant(b["tenant"], send=seen_b)

    assert [(o.tenant_id, o.dataset_id, o.access_token) for o in seen_a.sent] == [
        (a["tenant"], "DS-A", "TOKEN-A")
    ]
    assert [(o.tenant_id, o.dataset_id, o.access_token) for o in seen_b.sent] == [
        (b["tenant"], "DS-B", "TOKEN-B")
    ]
    assert seen_a.sent[0].event["event_id"] == "reservation:ra:Purchase"
    assert seen_b.sent[0].event["event_id"] == "reservation:rb:Purchase"


async def test_the_route_takes_no_dataset_or_tenant_from_the_caller(
    client: Any, console_world: dict[str, Any]
) -> None:
    w = console_world["a"]
    for extra in (
        {"meta_dataset_id": "DS-EVIL"},
        {"tenant_id": str(console_world["b"]["tenant_id"])},
    ):
        r = await client.put(
            f"/console/clients/{w['ref']}/channels/00000000-0000-0000-0000-000000000000/ad-measurement",
            json={"enabled": True, "confirm_data_sharing": True, **extra},
            headers=w["headers"](),
        )
        assert r.status_code == 422, r.text
