"""Spec 071, T006 — el worker de «Lo que te necesita» (requisitos 2.3 y 2.4).

- ``build.budget.*`` es un aviso **del partner**: sale sin cliente
  (``external_client_ref`` vacío), no colgado del cliente cuyo uso cruzó el umbral;
- el repaso de cada hora resuelve los avisos de cada partner con la consola nueva.

De punta a punta (con base), el repaso se prueba en la API:
``tests/integration/attention/test_resolve_cleared.py``.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from nexus_worker.metering import consumer
from nexus_worker.streams import wallet_crons


class _Session:
    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    def begin(self) -> _Session:
        return self


async def test_the_build_notice_goes_to_the_partner_without_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partner_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(consumer, "_partner_for", AsyncMock(return_value=partner_id))
    monkeypatch.setattr(consumer, "get_sessionmaker", lambda: _Session)
    monkeypatch.setattr(
        "nexus_api.core.partner_context.apply_partner_to_session", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "nexus_api.services.wallet.build_budget.record",
        AsyncMock(return_value=["build.budget.warning"]),
    )
    emitted: list[dict[str, Any]] = []

    async def _emit(**kw: Any) -> None:
        emitted.append(kw)

    announced = AsyncMock()
    monkeypatch.setattr("nexus_api.services.console_notifications.emit_detached", _emit)
    monkeypatch.setattr("nexus_api.services.channel_config.announce", announced)

    await consumer._record_build_line(tenant_id, [{"line": "build", "cost_usd": "1.0"}])

    announced.assert_not_awaited()
    (notice,) = emitted
    assert notice["partner_id"] == partner_id
    assert notice["kind"] == "build.budget.warning"
    assert notice["severity"] == "warning"
    assert notice.get("external_client_ref") is None
    assert str(tenant_id) not in str(notice), "ni el cliente que cruzó el umbral"
    assert notice["dedupe_key"].startswith(f"build.budget.warning:{partner_id}:")


async def test_the_hourly_pass_resolves_every_new_console_partner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partners = [uuid.uuid4(), uuid.uuid4()]
    monkeypatch.setattr(wallet_crons, "_v2_partners", AsyncMock(return_value=partners))
    seen: list[uuid.UUID] = []

    async def _resolve(partner_id: uuid.UUID, **_: Any) -> int:
        seen.append(partner_id)
        if partner_id == partners[0]:
            raise RuntimeError("uno que falla no para a los demás")
        return 2

    monkeypatch.setattr("nexus_api.services.attention_live.resolve_cleared_detached", _resolve)
    assert await wallet_crons.attention_resolve_tick() == 2
    assert seen == partners


def test_the_pass_runs_every_hour() -> None:
    assert wallet_crons.HOURLY == 3600.0
    assert "run_attention_resolve_cron" in wallet_crons.__all__
