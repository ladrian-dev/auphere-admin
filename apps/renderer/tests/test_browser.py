"""The Playwright layer, with Playwright replaced by fakes (no Chromium here).

What these pin down: Chromium is launched through the proxy with the loopback
bypass removed, every context blocks service workers and downloads, popups
are closed, dialogs dismissed, file choosers swallowed, and a render answers
``final_url``/``status``/``html`` inside the time and size budget — or a
closed error code, never a traceback.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from playwright.async_api import Error as PlaywrightError

from nexus_renderer.browser import (
    SKIPPED_RESOURCE_TYPES,
    PlaywrightRenderer,
    RenderError,
    chromium_args,
    strip_active_content,
)
from nexus_renderer.config import Settings
from nexus_renderer.egress import EgressGuard
from nexus_renderer.proxy import REFUSED_HEADER

PUBLIC_IP = "93.184.215.14"
TOKEN = "t" * 40

# ── fakes ─────────────────────────────────────────────────────────────────


class FakeResponse:
    def __init__(self, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {"content-type": "text/html"}


class FakePage:
    def __init__(self, behaviour: dict[str, Any]) -> None:
        self.behaviour = behaviour
        self.handlers: dict[str, Callable[[Any], Any]] = {}
        self.url = "about:blank"
        self.goto_calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def on(self, event: str, handler: Callable[[Any], Any]) -> None:
        self.handlers[event] = handler

    async def goto(self, url: str, **kwargs: Any) -> FakeResponse | None:
        self.goto_calls.append((url, kwargs))
        delay = self.behaviour.get("goto_delay")
        if delay:
            await asyncio.sleep(delay)
        error = self.behaviour.get("goto_error")
        if error is not None:
            raise error
        self.url = self.behaviour.get("final_url", url)
        response: FakeResponse | None = self.behaviour.get("response", FakeResponse())
        return response

    async def wait_for_load_state(self, state: str, **kwargs: Any) -> None:
        self.behaviour.setdefault("load_states", []).append(state)

    async def content(self) -> str:
        html: str = self.behaviour.get("html", "<html><body><p>Hola</p></body></html>")
        return html

    async def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, behaviour: dict[str, Any]) -> None:
        self.behaviour = behaviour
        self.handlers: dict[str, Callable[[Any], Any]] = {}
        self.routes: list[tuple[str, Callable[[Any], Awaitable[None]]]] = []
        self.pages: list[FakePage] = []
        self.closed = False

    def on(self, event: str, handler: Callable[[Any], Any]) -> None:
        self.handlers[event] = handler

    async def route(self, pattern: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        self.routes.append((pattern, handler))

    async def new_page(self) -> FakePage:
        page = FakePage(self.behaviour)
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, behaviour: dict[str, Any]) -> None:
        self.behaviour = behaviour
        self.contexts: list[tuple[dict[str, Any], FakeContext]] = []
        self.connected = True
        self.closed = False

    async def new_context(self, **kwargs: Any) -> FakeContext:
        context = FakeContext(self.behaviour)
        self.contexts.append((kwargs, context))
        return context

    def is_connected(self) -> bool:
        return self.connected

    async def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, behaviour: dict[str, Any]) -> None:
        self.behaviour = behaviour
        self.launches: list[dict[str, Any]] = []
        self.browsers: list[FakeBrowser] = []

    async def launch(self, **kwargs: Any) -> FakeBrowser:
        self.launches.append(kwargs)
        browser = FakeBrowser(self.behaviour)
        self.browsers.append(browser)
        return browser


class FakePlaywright:
    def __init__(self, behaviour: dict[str, Any]) -> None:
        self.chromium = FakeChromium(behaviour)
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FakeProxy:
    url = "http://127.0.0.1:41234"

    def __init__(self) -> None:
        self.started = False
        self.closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True


def guard() -> EgressGuard:
    async def resolve(host: str) -> list[str]:
        table = {"shop.example": [PUBLIC_IP], "intranet.example": ["10.0.0.9"]}
        if host not in table:
            raise OSError("unknown")
        return table[host]

    return EgressGuard(resolve)


async def make_renderer(
    behaviour: dict[str, Any] | None = None, **settings: Any
) -> tuple[PlaywrightRenderer, FakePlaywright, FakeProxy]:
    playwright = FakePlaywright(behaviour if behaviour is not None else {})
    proxy = FakeProxy()

    async def start_playwright() -> Any:
        return playwright

    renderer = PlaywrightRenderer(
        settings=Settings(token=TOKEN, **settings),
        guard=guard(),
        proxy=proxy,  # type: ignore[arg-type]
        start_playwright=start_playwright,
    )
    await renderer.start()
    return renderer, playwright, proxy


def only_context(playwright: FakePlaywright) -> tuple[dict[str, Any], FakeContext]:
    [browser] = playwright.chromium.browsers
    [entry] = browser.contexts
    return entry


# ── launch ────────────────────────────────────────────────────────────────


async def test_chromium_goes_through_the_proxy_with_loopback_proxied() -> None:
    renderer, playwright, proxy = await make_renderer()
    assert proxy.started
    [launch] = playwright.chromium.launches
    args = launch["args"]
    assert f"--proxy-server={proxy.url}" in args
    # Without this Chromium connects DIRECTLY to localhost and link-local
    # (169.254.169.254, 169.254.170.2): its implicit bypass rules.
    assert "--proxy-bypass-list=<-loopback>" in args
    assert "--disable-quic" in args
    assert "--force-webrtc-ip-handling-policy=disable_non_proxied_udp" in args
    assert launch["headless"] is True
    assert "proxy" not in launch  # one source of truth: the switches above
    await renderer.close()
    assert proxy.closed and playwright.stopped


def test_chromium_args_have_no_bypass_beyond_loopback_removal() -> None:
    args = chromium_args("http://127.0.0.1:1")
    bypass = [a for a in args if a.startswith("--proxy-bypass-list=")]
    assert bypass == ["--proxy-bypass-list=<-loopback>"]
    assert not any(a.startswith("--no-proxy-server") for a in args)


# ── one render ────────────────────────────────────────────────────────────


async def test_render_returns_final_url_status_and_html() -> None:
    behaviour: dict[str, Any] = {
        "final_url": "https://shop.example/es/",
        "response": FakeResponse(200),
        "html": "<html><head><title>Barbería</title></head><body><p>Corte 15 €</p></body></html>",
    }
    renderer, playwright, _ = await make_renderer(behaviour)
    result = await renderer.render("https://shop.example/")
    assert result.final_url == "https://shop.example/es/"
    assert result.status == 200
    assert "Corte 15 €" in result.html

    options, context = only_context(playwright)
    assert options["service_workers"] == "block"
    assert options["accept_downloads"] is False
    assert options["java_script_enabled"] is True
    assert options["user_agent"].startswith("NexusReader/")
    assert context.closed, "one context per request, always closed"
    [page] = context.pages
    [(url, kwargs)] = page.goto_calls
    assert url == "https://shop.example/"
    assert 0 < kwargs["timeout"] <= 20_000
    await renderer.close()


async def test_page_handlers_neutralise_dialogs_popups_downloads_and_file_choosers() -> None:
    renderer, playwright, _ = await make_renderer()
    await renderer.render("https://shop.example/")
    _, context = only_context(playwright)
    [page] = context.pages

    class Dialog:
        dismissed = False

        async def dismiss(self) -> None:
            self.dismissed = True

    dialog = Dialog()
    await page.handlers["dialog"](dialog)
    assert dialog.dismissed

    class Download:
        cancelled = False

        async def cancel(self) -> None:
            self.cancelled = True

    download = Download()
    await page.handlers["download"](download)
    assert download.cancelled

    class FileChooser:
        touched = False

        async def set_files(self, *_args: object) -> None:  # pragma: no cover - must not run
            self.touched = True

    chooser = FileChooser()
    result = page.handlers["filechooser"](chooser)
    if asyncio.iscoroutine(result):
        await result
    assert not chooser.touched

    popup = FakePage({})
    await context.handlers["page"](popup)
    assert popup.closed
    await context.handlers["page"](page)
    assert not page.closed, "the page being rendered is not a popup"
    await renderer.close()


@pytest.mark.parametrize(
    ("resource_type", "url", "aborted"),
    [
        ("document", "https://shop.example/", False),
        ("script", "https://cdn.example/app.js", False),
        ("xhr", "https://shop.example/api/menu", False),
        ("stylesheet", "https://shop.example/a.css", False),
        ("image", "https://shop.example/logo.png", True),
        ("media", "https://shop.example/intro.mp4", True),
        ("font", "https://fonts.example/a.woff2", True),
        ("other", "ftp://shop.example/x", True),
        ("document", "file:///etc/passwd", True),
    ],
)
async def test_route_skips_heavy_and_non_web_requests(
    resource_type: str, url: str, aborted: bool
) -> None:
    renderer, playwright, _ = await make_renderer()
    await renderer.render("https://shop.example/")
    _, context = only_context(playwright)
    [(pattern, handler)] = context.routes
    assert pattern == "**/*"

    class Request:
        def __init__(self) -> None:
            self.resource_type = resource_type
            self.url = url

    class Route:
        def __init__(self) -> None:
            self.request = Request()
            self.outcome = ""

        async def abort(self, *_args: object) -> None:
            self.outcome = "abort"

        async def continue_(self) -> None:
            self.outcome = "continue"

    route = Route()
    await handler(route)
    assert route.outcome == ("abort" if aborted else "continue")
    assert {"image", "media", "font"} <= SKIPPED_RESOURCE_TYPES
    await renderer.close()


# ── refusals and failures ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://shop.example/", "bad_url"),
        ("file:///etc/passwd", "bad_url"),
        ("javascript:alert(1)", "bad_url"),
        ("https://user:pw@shop.example/", "bad_url"),
        ("https:///nohost", "bad_url"),
        ("https://shop.example:99999/", "bad_url"),
        ("https://" + "a" * 2100 + ".example/", "bad_url"),
        ("http://127.0.0.1/", "forbidden_address"),
        ("http://169.254.169.254/latest/meta-data/", "forbidden_address"),
        ("http://[::1]/", "forbidden_address"),
        ("https://intranet.example/", "forbidden_address"),
        ("https://shop.example:8443/", "forbidden_address"),
        ("https://nowhere.example/", "unreachable"),
    ],
)
async def test_bad_or_forbidden_targets_never_open_a_page(url: str, code: str) -> None:
    renderer, playwright, _ = await make_renderer()
    with pytest.raises(RenderError) as exc:
        await renderer.render(url)
    assert exc.value.code == code
    [browser] = playwright.chromium.browsers
    assert browser.contexts == []
    await renderer.close()


async def test_proxy_refusal_of_the_main_document_is_forbidden() -> None:
    """A redirect to a private address reaches the proxy, which answers 403
    with its marker header; the render reports it as such, not as a page."""
    behaviour = {
        "final_url": "http://10.0.0.1/admin",
        "response": FakeResponse(403, {REFUSED_HEADER.lower(): "address"}),
    }
    renderer, playwright, _ = await make_renderer(behaviour)
    with pytest.raises(RenderError) as exc:
        await renderer.render("http://shop.example/")
    assert exc.value.code == "forbidden_address"
    _, context = only_context(playwright)
    assert context.closed
    await renderer.close()


async def test_navigation_error_is_unreachable_and_closes_the_context() -> None:
    behaviour = {"goto_error": PlaywrightError("net::ERR_TUNNEL_CONNECTION_FAILED")}
    renderer, playwright, _ = await make_renderer(behaviour)
    with pytest.raises(RenderError) as exc:
        await renderer.render("https://shop.example/")
    assert exc.value.code == "unreachable"
    _, context = only_context(playwright)
    assert context.closed
    await renderer.close()


async def test_total_budget_is_enforced() -> None:
    renderer, playwright, _ = await make_renderer({"goto_delay": 2}, total_timeout_s=0.1)
    with pytest.raises(RenderError) as exc:
        await renderer.render("https://shop.example/")
    assert exc.value.code == "timeout"
    _, context = only_context(playwright)
    assert context.closed
    await renderer.close()


async def test_final_url_outside_the_web_is_unreachable() -> None:
    renderer, _, _ = await make_renderer({"final_url": "chrome-error://chromewebdata/"})
    with pytest.raises(RenderError) as exc:
        await renderer.render("https://shop.example/")
    assert exc.value.code == "unreachable"
    await renderer.close()


async def test_html_over_the_cap_is_too_large() -> None:
    big = "<html><body>" + "<p>texto</p>" * 300_000 + "</body></html>"  # ~3.6 MB
    renderer, _, _ = await make_renderer({"html": big})
    with pytest.raises(RenderError) as exc:
        await renderer.render("https://shop.example/")
    assert exc.value.code == "too_large"
    await renderer.close()


async def test_scripts_do_not_count_against_the_cap() -> None:
    """A page whose weight is its JavaScript bundle still fits: scripts and
    styles are dropped before measuring, JSON-LD is kept (requirement 59.1)."""
    bundle = "<script>" + "x" * 3_000_000 + "</script>"
    html = f"<html><head>{bundle}</head><body><p>Abierto de 9 a 20</p></body></html>"
    renderer, _, _ = await make_renderer({"html": html})
    result = await renderer.render("https://shop.example/")
    assert "Abierto de 9 a 20" in result.html
    assert len(result.html.encode()) < 2 * 1024 * 1024
    await renderer.close()


async def test_status_is_zero_without_a_response() -> None:
    renderer, _, _ = await make_renderer({"response": None})
    result = await renderer.render("https://shop.example/")
    assert result.status == 0
    await renderer.close()


async def test_disconnected_browser_is_relaunched() -> None:
    renderer, playwright, _ = await make_renderer()
    playwright.chromium.browsers[0].connected = False
    await renderer.render("https://shop.example/")
    assert len(playwright.chromium.launches) == 2
    assert playwright.chromium.browsers[1].contexts
    await renderer.close()


# ── the markup the reader receives ──────────────────────────────────────────


def test_strip_active_content_keeps_json_ld_and_text() -> None:
    html = (
        "<html><head>"
        '<script src="/app.js"></script>'
        "<script>window.__STATE__ = {}</script>"
        '<script type="module">import x from "y"</script>'
        '<script type="application/ld+json">{"@type": "HairSalon", "name": "Cultor"}</script>'
        "<style>body { color: red }</style>"
        "</head><body><h1>Cultor</h1><SCRIPT>evil()</SCRIPT ></body></html>"
    )
    cleaned = strip_active_content(html)
    assert '"@type": "HairSalon"' in cleaned
    assert "application/ld+json" in cleaned
    assert "<h1>Cultor</h1>" in cleaned
    for gone in ("app.js", "__STATE__", "import x", "color: red", "evil()"):
        assert gone not in cleaned
