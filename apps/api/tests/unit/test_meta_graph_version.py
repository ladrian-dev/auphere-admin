"""Spec 050, requirement 3.5 — one Graph API version, taken from settings.

Meta retires a Graph version two years after it ships (v21.0 dies on
2027-01-21). The server and the browsers speak the same one, read from
``meta_graph_api_version``; nothing pins another by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_VERSION, MetaClient

from nexus_api.config import Settings

REPO = Path(__file__).resolve().parents[4]
SOURCES = [
    REPO / "apps" / "api" / "src",
    REPO / "apps" / "worker" / "src",
    REPO / "apps" / "channels" / "src",
    REPO / "apps" / "mcp" / "src",
    REPO / "apps" / "console" / "src",
    REPO / "apps" / "admin" / "src",
]
VERSION = re.compile(r"""["'/]v(2\d)\.0\b""")
#: Where versions are named on purpose: the setting and its expiry table.
ALLOWED = {REPO / "apps" / "api" / "src" / "nexus_api" / "config.py"}


def test_the_default_is_v26() -> None:
    assert Settings.model_fields["meta_graph_api_version"].default == "v26.0"
    assert META_GRAPH_VERSION == "v26.0"


@pytest.mark.asyncio
async def test_the_client_calls_the_version_it_is_given() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"id": "PN"})

    client = MetaClient("secret", version="v27.0", transport=httpx.MockTransport(handler))
    await client.get_phone_number(phone_number_id="PN", access_token="T")
    default = MetaClient("secret", transport=httpx.MockTransport(handler))
    await default.get_phone_number(phone_number_id="PN", access_token="T")
    assert seen[0].startswith("/v27.0/") and seen[1].startswith("/v26.0/")


def test_no_other_version_is_written_by_hand() -> None:
    offenders: list[str] = []
    for root in SOURCES:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or "__tests__" in path.parts:
                continue
            if "node_modules" in path.parts or path.name.endswith((".test.ts", ".test.tsx")):
                continue
            if path in ALLOWED:
                continue
            for n, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                for m in VERSION.finditer(line):
                    if m.group(1) != "26":
                        offenders.append(f"{path.relative_to(REPO)}:{n}: {line.strip()[:90]}")
    assert offenders == []


# ── 3.6: the operator hears about an expiring version ───────────────────────


def test_the_notice_starts_sixty_days_before_expiry() -> None:
    from datetime import date

    from nexus_api.config import graph_version_notice

    assert graph_version_notice("v22.0", date(2027, 3, 20)) is None  # 61 days left
    assert graph_version_notice("v22.0", date(2027, 3, 21)) == (date(2027, 5, 20), 60)
    assert graph_version_notice("v22.0", date(2027, 6, 1)) == (date(2027, 5, 20), -12)
    # A version without a published date has more than two years left.
    assert graph_version_notice("v26.0", date(2028, 12, 1)) is None


def test_the_health_cron_warns_once_a_day(monkeypatch) -> None:
    from datetime import date

    from nexus_worker.streams import whatsapp_health_cron as cron

    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        cron.log, "error", lambda event, **kw: events.append({"event": event, **kw})
    )
    monkeypatch.setattr(cron, "get_settings", lambda: Settings(meta_graph_api_version="v22.0"))

    day = date(2027, 5, 1)
    warned = cron.warn_if_graph_version_expiring(None, today=day)
    warned = cron.warn_if_graph_version_expiring(warned, today=day)
    assert warned == day
    assert events == [
        {
            "event": "meta.graph_version_expiring",
            "version": "v22.0",
            "expires_on": "2027-05-20",
            "days_left": 19,
        }
    ]
    assert cron.warn_if_graph_version_expiring(None, today=date(2027, 1, 1)) is None


@pytest.mark.asyncio
async def test_the_status_page_learns_the_version(client, admin_headers) -> None:
    r = await client.get("/admin/instance", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta_graph_version"] == "v26.0"
    assert body["meta_graph_expires_on"] is None and body["meta_graph_days_left"] is None
