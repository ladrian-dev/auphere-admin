"""Template resolution must not fan out one Graph API call per recipient.

A campaign sends one HTTP request per recipient, and each one used to
resolve the template live against Meta. 141 recipients meant 141
back-to-back Graph calls, which exhausted the HTTP pool and failed the
New Air batch mid-run. The cache collapses that to one call per WABA per
TTL — while still expiring fast enough that a paused template is caught.
"""

from __future__ import annotations

import pytest
import respx
from nexus_channels.whatsapp_meta.credentials import MetaCredentials
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL

from nexus_api.services import whatsapp_templates as svc

_TEMPLATE_PAYLOAD = {
    "data": [
        {
            "id": "1",
            "name": "newair_instalacion_vencida",
            "language": "es",
            "status": "APPROVED",
            "category": "MARKETING",
            "components": [{"type": "BODY", "text": "Hola {{nombre}} — {{fecha}}"}],
        }
    ]
}


def _creds(waba_id: str) -> MetaCredentials:
    return MetaCredentials(
        bisuat="EAA-token",
        waba_id=waba_id,
        phone_number_id="PN_1",
        business_id="BIZ_1",
        display_phone_number="+56964321907",
        verify_token="v" * 32,
    )


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    svc.invalidate_template_cache()


@pytest.fixture
def _stub_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(_session: object) -> MetaCredentials:
        return _creds("WABA_1")

    monkeypatch.setattr(svc, "require_meta_credentials", fake)


async def test_repeated_sends_hit_meta_once(_stub_creds: None) -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.get("/WABA_1/message_templates").respond(200, json=_TEMPLATE_PAYLOAD)

        for _ in range(20):
            templates, waba = await svc.fetch_templates(session=None)  # type: ignore[arg-type]

        assert waba == "WABA_1"
        assert templates[0].name == "newair_instalacion_vencida"
        assert route.call_count == 1, "one Graph call should serve the whole fan-out"


async def test_cache_expires(_stub_creds: None, monkeypatch: pytest.MonkeyPatch) -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.get("/WABA_1/message_templates").respond(200, json=_TEMPLATE_PAYLOAD)

        clock = [1000.0]
        monkeypatch.setattr(svc.time, "monotonic", lambda: clock[0])

        await svc.fetch_templates(session=None)  # type: ignore[arg-type]
        clock[0] += svc._TEMPLATE_CACHE_TTL_SECONDS + 1
        await svc.fetch_templates(session=None)  # type: ignore[arg-type]

        assert route.call_count == 2


async def test_use_cache_false_always_refetches(_stub_creds: None) -> None:
    """The operator panel must never read a stale approval state."""
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.get("/WABA_1/message_templates").respond(200, json=_TEMPLATE_PAYLOAD)

        await svc.fetch_templates(session=None)  # type: ignore[arg-type]
        await svc.fetch_templates(session=None, use_cache=False)  # type: ignore[arg-type]

        assert route.call_count == 2


async def test_invalidate_drops_only_that_waba(_stub_creds: None) -> None:
    svc._template_cache["WABA_1"] = (9e9, [])
    svc._template_cache["WABA_2"] = (9e9, [])

    svc.invalidate_template_cache("WABA_1")

    assert "WABA_1" not in svc._template_cache
    assert "WABA_2" in svc._template_cache, "one tenant's write must not flush another's"
