"""Spec 076 — lo que usan las tres historias: ajustes y la conversación del turno.

- La medición está cerrada por defecto: ni lista ni apertura general.
- La lista de tenants se lee del entorno y una errata se rechaza al arrancar.
- La conversación del turno viaja en un ``ContextVar`` al lado del cliente, para
  que las herramientas sepan de qué número viene un resultado sin preguntarlo.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from nexus_api.config import Settings
from nexus_api.core.tenant_context import conversation_context, get_current_conversation


def test_measurement_is_closed_by_default() -> None:
    s = Settings()
    assert s.ad_measurement_tenant_ids == frozenset()
    assert s.ad_measurement_general_availability is False
    assert s.meta_capi_test_event_code is None
    assert s.meta_config_id_wa_events_test_cloud_api is None
    assert s.meta_config_id_wa_events_test_coexistence is None


def test_measurement_tenants_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setenv("NEXUS_AD_MEASUREMENT_TENANTS", f" {a}, {b} ,")
    assert Settings().ad_measurement_tenant_ids == frozenset({a, b})


def test_measurement_tenants_refuse_a_typo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_AD_MEASUREMENT_TENANTS", "auphere")
    with pytest.raises(ValidationError):
        Settings()


def test_worker_settings_defaults() -> None:
    from nexus_worker.config import WorkerSettings

    w = WorkerSettings()
    assert w.retention_ad_click_days == 90
    assert w.conversion_dispatch_tick_seconds == 60.0


def test_conversation_context_inside_and_outside() -> None:
    assert get_current_conversation() is None
    cid = uuid.uuid4()
    with conversation_context(cid):
        assert get_current_conversation() == cid
        with conversation_context(None):
            assert get_current_conversation() is None
        assert get_current_conversation() == cid
    assert get_current_conversation() is None
