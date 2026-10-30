"""One page per request in a headless Chromium that can only talk through the proxy.

The browser is launched once at start and relaunched if it dies; every request
gets its own context (no cookies, storage or cache shared between requests)
and closes it, whatever happens. Inside the context:

- **No service workers** (``service_workers="block"``): a worker would outlive
  the page and fetch on its own.
- **No downloads** (``accept_downloads=False``), **no file chooser** (the
  ``filechooser`` event is taken and nothing is set), **no popups** (closed as
  they open), **dialogs dismissed**.
- Images, media and fonts are not fetched: the reader wants the text, and they
  are most of the bytes. Anything that is not http(s) is aborted.

The page's address is vetted before the browser sees it; everything the page
does afterwards (redirects, subresources, XHR, WebSockets) goes through
:class:`~nexus_renderer.proxy.ForwardProxy`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, Protocol
from urllib.parse import urlsplit

from playwright.async_api import (
    Browser,
    Dialog,
    Download,
    FileChooser,
    Page,
    Playwright,
    Route,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from nexus_renderer.config import Settings
from nexus_renderer.egress import EgressGuard, Refused
from nexus_renderer.proxy import REFUSED_HEADER

log = logging.getLogger(__name__)

#: What a render can fail with; the API maps each to an HTTP status.
ERROR_CODES: Final = ("bad_url", "forbidden_address", "too_large", "unreachable", "timeout")
MAX_URL_CHARS: Final = 2048
#: Requests the page may not make: the bytes are not text.
SKIPPED_RESOURCE_TYPES: Final = frozenset({"image", "media", "font"})
#: The serialised DOM is refused outright beyond this many times the cap,
#: before spending a regex on it.
_RAW_CEILING_FACTOR: Final = 8


class RenderError(Exception):
    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown render error: {code!r}")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RenderResult:
    final_url: str
    status: int
    html: str


class Proxy(Protocol):
    @property
    def url(self) -> str: ...

    async def start(self) -> None: ...

    async def close(self) -> None: ...


StartPlaywright = Callable[[], Awaitable[Playwright]]


async def _start_playwright() -> Playwright:
    return await async_playwright().start()


def chromium_args(proxy_url: str) -> list[str]:
    """The switches that keep Chromium on the proxy."""
    return [
        f"--proxy-server={proxy_url}",
        # Chromium skips the proxy for localhost, 127/8, [::1] and link-local
        # (169.254/16, fe80::/10) by default. ``<-loopback>`` removes that
        # implicit rule, so those go through the proxy too — and are refused.
        "--proxy-bypass-list=<-loopback>",
        # QUIC is UDP and would not go through an HTTP proxy.
        "--disable-quic",
        # WebRTC may only use UDP through the proxy, i.e. not at all.
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
        # No background traffic of Chromium's own (updates, pings, prefetch).
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-sync",
        "--dns-prefetch-disable",
        "--no-pings",
        # Fargate's /dev/shm is small; Chromium falls back to /tmp.
        "--disable-dev-shm-usage",
    ]


_SCRIPT: Final = re.compile(r"<script\b([^>]*)>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_STYLE: Final = re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL)
_LD_JSON: Final = re.compile(r"""type\s*=\s*["']?application/ld\+json""", re.IGNORECASE)


def strip_active_content(html: str) -> str:
    """The rendered DOM without its scripts and styles — the reader wants the
    text — except JSON-LD, which carries the schema.org data (requirement 59.1)."""

    def keep_json_ld(match: re.Match[str]) -> str:
        return match.group(0) if _LD_JSON.search(match.group(1)) else ""

    return _STYLE.sub("", _SCRIPT.sub(keep_json_ld, html))


def _fit(raw: str, max_bytes: int) -> str:
    if len(raw) > max_bytes * _RAW_CEILING_FACTOR:
        raise RenderError("too_large")
    html = strip_active_content(raw)
    if len(html.encode("utf-8", errors="replace")) > max_bytes:
        raise RenderError("too_large")
    return html


def _check_url(url: str) -> tuple[str, int]:
    if len(url) > MAX_URL_CHARS:
        raise RenderError("bad_url")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise RenderError("bad_url") from exc
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise RenderError("bad_url")
    return parts.hostname, port or (443 if parts.scheme == "https" else 80)


async def _route(route: Route) -> None:
    request = route.request
    if request.resource_type in SKIPPED_RESOURCE_TYPES or not request.url.startswith(
        ("http://", "https://")
    ):
        await route.abort("blockedbyclient")
    else:
        await route.continue_()


async def _dismiss(dialog: Dialog) -> None:
    await dialog.dismiss()


async def _cancel(download: Download) -> None:
    await download.cancel()


def _ignore_file_chooser(_chooser: FileChooser) -> None:
    """Listening is what stops the chooser from opening; nothing is ever set."""


class PlaywrightRenderer:
    def __init__(
        self,
        *,
        settings: Settings,
        guard: EgressGuard,
        proxy: Proxy,
        start_playwright: StartPlaywright = _start_playwright,
    ) -> None:
        self._settings = settings
        self._guard = guard
        self._proxy = proxy
        self._start_playwright = start_playwright
        self._slots = asyncio.Semaphore(settings.max_concurrency)
        self._launch_lock = asyncio.Lock()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        await self._proxy.start()
        self._playwright = await self._start_playwright()
        await self._ensure_browser()

    async def close(self) -> None:
        if self._browser is not None:
            with contextlib.suppress(Exception):
                await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            with contextlib.suppress(Exception):
                await self._playwright.stop()
            self._playwright = None
        await self._proxy.close()

    async def _ensure_browser(self) -> Browser:
        async with self._launch_lock:
            if self._browser is not None and self._browser.is_connected():
                return self._browser
            if self._playwright is None:
                raise RuntimeError("renderer not started")
            if self._browser is not None:
                log.warning("renderer.browser_relaunch")
                with contextlib.suppress(Exception):
                    await self._browser.close()
            self._browser = await self._playwright.chromium.launch(
                headless=True, args=chromium_args(self._proxy.url)
            )
            return self._browser

    async def render(self, url: str) -> RenderResult:
        """Render ``url`` within the budget, or raise :class:`RenderError`."""
        host, port = _check_url(url)
        started = time.monotonic()
        deadline = started + self._settings.total_timeout_s
        try:
            async with asyncio.timeout(self._settings.total_timeout_s):
                try:
                    await self._guard.vet(host, port)
                except Refused as exc:
                    code = {"unresolvable": "unreachable", "bad_host": "bad_url"}.get(
                        exc.reason, "forbidden_address"
                    )
                    raise RenderError(code) from exc
                async with self._slots:
                    result = await self._render(url, deadline)
        except TimeoutError as exc:
            log.info("renderer.render host=%s outcome=timeout", host)
            raise RenderError("timeout") from exc
        except RenderError as exc:
            log.info("renderer.render host=%s outcome=%s", host, exc.code)
            raise
        log.info(
            "renderer.render host=%s outcome=ok status=%s bytes=%s ms=%s",
            host,
            result.status,
            len(result.html),
            int((time.monotonic() - started) * 1000),
        )
        return result

    async def _render(self, url: str, deadline: float) -> RenderResult:
        def ms_left() -> float:
            return max(1.0, (deadline - time.monotonic()) * 1000)

        browser = await self._ensure_browser()
        context = await browser.new_context(
            user_agent=self._settings.user_agent,
            service_workers="block",
            accept_downloads=False,
            java_script_enabled=True,
            ignore_https_errors=False,
            viewport={"width": 1280, "height": 900},
            locale="es-ES",
        )
        try:
            await context.route("**/*", _route)
            page = await context.new_page()

            async def close_popup(other: Page) -> None:
                if other is not page:
                    await other.close()

            context.on("page", close_popup)
            page.on("dialog", _dismiss)
            page.on("download", _cancel)
            page.on("filechooser", _ignore_file_chooser)

            response = await page.goto(url, wait_until="domcontentloaded", timeout=ms_left())
            if response is not None and REFUSED_HEADER.lower() in response.headers:
                raise RenderError("forbidden_address")
            # Let the scripts paint what they fetch; a page that never goes
            # quiet is read as it is when the settle time runs out.
            with contextlib.suppress(PlaywrightError):
                await page.wait_for_load_state(
                    "networkidle",
                    timeout=min(self._settings.settle_timeout_s * 1000, ms_left()),
                )
            final_url = page.url
            if urlsplit(final_url).scheme not in ("http", "https"):
                raise RenderError("unreachable")
            html = _fit(await page.content(), self._settings.max_html_bytes)
            return RenderResult(
                final_url=final_url,
                status=response.status if response is not None else 0,
                html=html,
            )
        except PlaywrightTimeoutError as exc:
            raise RenderError("timeout") from exc
        except PlaywrightError as exc:
            log.info("renderer.navigation_failed error=%s", str(exc).split("\n", 1)[0][:200])
            raise RenderError("unreachable") from exc
        finally:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(context.close(), 5)


__all__ = [
    "ERROR_CODES",
    "MAX_URL_CHARS",
    "SKIPPED_RESOURCE_TYPES",
    "PlaywrightRenderer",
    "Proxy",
    "RenderError",
    "RenderResult",
    "chromium_args",
    "strip_active_content",
]
