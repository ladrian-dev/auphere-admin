"""The HTTP surface: ``POST /render`` behind a bearer token, ``GET /health``."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexus_renderer import app as app_module
from nexus_renderer.app import create_app
from nexus_renderer.browser import RenderError, RenderResult
from nexus_renderer.config import ConfigError, Settings

TOKEN = "s" * 48
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeRenderer:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls: list[str] = []
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def render(self, url: str) -> RenderResult:
        self.calls.append(url)
        if self.error:
            raise RenderError(self.error)
        return RenderResult(final_url=url + "es/", status=200, html="<p>Hola</p>")


def client_for(renderer: FakeRenderer) -> TestClient:
    return TestClient(create_app(Settings(token=TOKEN), renderer))


def test_health_needs_no_token() -> None:
    renderer = FakeRenderer()
    with client_for(renderer) as client:
        assert renderer.started
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert renderer.closed


def test_render_with_the_token() -> None:
    renderer = FakeRenderer()
    with client_for(renderer) as client:
        response = client.post("/render", json={"url": "https://shop.example/"}, headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {
        "final_url": "https://shop.example/es/",
        "status": 200,
        "html": "<p>Hola</p>",
    }
    assert renderer.calls == ["https://shop.example/"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": f"Bearer {TOKEN[:-1]}"},
        {"Authorization": f"Bearer {TOKEN}x"},
        {"Authorization": "Bearer wrong"},
        {"X-Token": TOKEN},
    ],
)
def test_render_without_the_right_token_is_401(headers: dict[str, str]) -> None:
    renderer = FakeRenderer()
    with client_for(renderer) as client:
        response = client.post("/render", json={"url": "https://shop.example/"}, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert renderer.calls == []


def test_token_is_checked_before_the_body() -> None:
    """A caller without the token learns nothing about the body schema."""
    renderer = FakeRenderer()
    with client_for(renderer) as client:
        response = client.post("/render", content=b"not json")
    assert response.status_code == 401


def test_token_comparison_is_constant_time(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[bytes, bytes]] = []
    real = app_module.hmac.compare_digest

    def spy(a: Any, b: Any) -> bool:
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(app_module.hmac, "compare_digest", spy)
    with client_for(FakeRenderer()) as client:
        client.post("/render", json={"url": "https://shop.example/"}, headers=AUTH)
    assert seen == [(TOKEN.encode(), TOKEN.encode())]


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"{}",
        b'{"url": 5}',
        b'{"url": ""}',
        b'{"url": "https://shop.example/", "extra": true}',
        b'{"url": "https://shop.example/' + b"a" * 2100 + b'"}',
        b"[]",
    ],
)
def test_bad_body_is_400(body: bytes) -> None:
    renderer = FakeRenderer()
    with client_for(renderer) as client:
        response = client.post(
            "/render", content=body, headers={**AUTH, "Content-Type": "application/json"}
        )
    assert response.status_code == 400
    assert response.json() == {"error": "bad_request"}
    assert renderer.calls == []


def test_oversized_body_is_413() -> None:
    renderer = FakeRenderer()
    with client_for(renderer) as client:
        response = client.post(
            "/render",
            content=b'{"url": "https://shop.example/", "pad": "' + b"x" * 20_000 + b'"}',
            headers={**AUTH, "Content-Type": "application/json"},
        )
    assert response.status_code == 413
    assert renderer.calls == []


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("bad_url", 400),
        ("forbidden_address", 422),
        ("too_large", 413),
        ("unreachable", 502),
        ("timeout", 504),
    ],
)
def test_render_errors_map_to_closed_codes(code: str, status: int) -> None:
    with client_for(FakeRenderer(error=code)) as client:
        response = client.post("/render", json={"url": "https://shop.example/"}, headers=AUTH)
    assert response.status_code == status
    assert response.json() == {"error": code}


def test_no_docs_or_schema_routes() -> None:
    with client_for(FakeRenderer()) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404


# ── configuration ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "env", [{}, {"NEXUS_RENDERER_TOKEN": ""}, {"NEXUS_RENDERER_TOKEN": "short"}]
)
def test_refuses_to_start_without_a_strong_token(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_settings_from_env() -> None:
    settings = Settings.from_env(
        {
            "NEXUS_RENDERER_TOKEN": f"  {TOKEN}  ",
            "NEXUS_RENDERER_PORT": "9000",
            "NEXUS_RENDERER_MAX_CONCURRENCY": "3",
        }
    )
    assert settings.token == TOKEN
    assert settings.port == 9000
    assert settings.max_concurrency == 3
    # The spec's budget is not configurable from the environment.
    assert settings.total_timeout_s == 20.0
    assert settings.max_html_bytes == 2 * 1024 * 1024


@pytest.mark.parametrize(
    "env",
    [
        {"NEXUS_RENDERER_PORT": "http"},
        {"NEXUS_RENDERER_PORT": "0"},
        {"NEXUS_RENDERER_MAX_CONCURRENCY": "0"},
        {"NEXUS_RENDERER_MAX_CONCURRENCY": "100"},
    ],
)
def test_bad_numbers_refuse_to_start(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env({"NEXUS_RENDERER_TOKEN": TOKEN, **env})


def test_build_app_wires_the_real_pieces_without_starting_them() -> None:
    from nexus_renderer.browser import PlaywrightRenderer
    from nexus_renderer.main import build

    settings, renderer, app = build({"NEXUS_RENDERER_TOKEN": TOKEN})
    assert settings.token == TOKEN
    assert isinstance(renderer, PlaywrightRenderer)
    assert app.title == "nexus-renderer"
