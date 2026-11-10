"""Entry point: ``nexus-renderer`` (the image's command)."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import uvicorn
from fastapi import FastAPI

from nexus_renderer.app import create_app
from nexus_renderer.browser import PlaywrightRenderer
from nexus_renderer.config import Settings
from nexus_renderer.egress import EgressGuard
from nexus_renderer.proxy import ForwardProxy


def build(env: Mapping[str, str] | None = None) -> tuple[Settings, PlaywrightRenderer, FastAPI]:
    """Wire the pieces without starting any of them."""
    settings = Settings.from_env(env)
    guard = EgressGuard()
    renderer = PlaywrightRenderer(settings=settings, guard=guard, proxy=ForwardProxy(guard))
    return settings, renderer, create_app(settings, renderer)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings, _renderer, app = build()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
        server_header=False,
        proxy_headers=False,
        log_level="info",
    )


__all__ = ["build", "run"]
