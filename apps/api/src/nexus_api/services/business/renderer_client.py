"""El cliente del navegador de respaldo — spec 047, T203 (requisito 59.2, research D50).

Cuando una página trae menos texto del que hace falta para leerla, el lector
puede pedírsela ya pintada al servicio ``apps/renderer`` (Chromium detrás de un
proxy que solo deja salir a direcciones públicas por 80/443). Este módulo es lo
único de ese servicio que vive en la API: un ``POST /render`` con token.

**Sin conectar todavía.** Lo conecta al lector la T202; hasta entonces nadie lo
llama.

**Apagado si no está configurado.** Sin ``NEXUS_RENDERER_URL`` (o sin
``NEXUS_RENDERER_TOKEN``), :func:`render` devuelve ``None`` sin hacer nada. Es lo
normal: el servicio está apagado por defecto (``renderer_enabled`` en
Terraform). La configuración se lee con su propio ``BaseSettings`` (prefijo
``NEXUS_RENDERER_``), igual que ``config.Settings``, para no tocar la
configuración común.

**Nunca lanza.** Un fallo del renderer —no responde, tarda más de su tope,
contesta un error o algo que no valida— es ``None`` y una línea de log con el
motivo y el *host*, nunca la URL entera ni el token. El lector sigue con lo que
tenía.

**Las mismas guardas.** La dirección pedida pasa por ``assert_public_url``
antes de salir (una privada ni se envía) y la ``final_url`` que vuelve, también.
El renderer las aplica además en cada conexión que hace la página. El tamaño
(2 MB de HTML) y el tiempo (los 20 s del servicio y un margen) se cortan aquí
otra vez. El ``robots.txt`` es de quien llama, como en ``read_page``: la
dirección de partida y la ``final_url``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final
from urllib.parse import urlsplit

import httpx
import structlog
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus_api.services.knowledge_indexer import IndexingError, assert_public_url

log = structlog.get_logger(__name__)

Guard = Callable[[str], Awaitable[None]]

#: El HTML que se acepta, como mucho (el mismo tope que aplica el servicio).
MAX_HTML_BYTES: Final = 2 * 1024 * 1024
#: La respuesta entera: el JSON escapa comillas, saltos y controles.
MAX_RESPONSE_BYTES: Final = 3 * MAX_HTML_BYTES
#: Los 20 s del servicio más el viaje.
DEFAULT_TIMEOUT_S: Final = 25.0


class RendererSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEXUS_RENDERER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = ""
    token: SecretStr = SecretStr("")
    timeout_s: float = DEFAULT_TIMEOUT_S

    @property
    def enabled(self) -> bool:
        return bool(self.url.strip())


@lru_cache
def get_renderer_settings() -> RendererSettings:
    return RendererSettings()


@dataclass(frozen=True)
class Rendered:
    final_url: str
    status: int
    html: str


class _Failure(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def render(
    url: str,
    *,
    settings: RendererSettings | None = None,
    guard: Guard = assert_public_url,
) -> Rendered | None:
    """``url`` pintada por el navegador de respaldo, o ``None`` si no está
    configurado o no se pudo. No lanza."""
    cfg = settings if settings is not None else get_renderer_settings()
    if not cfg.enabled:
        return None
    token = cfg.token.get_secret_value().strip()
    if not token:
        log.warning("renderer.no_token")
        return None
    host = _host(url)
    try:
        await guard(url)
    except IndexingError:
        log.info("renderer.refused", host=host)
        return None
    try:
        async with asyncio.timeout(cfg.timeout_s):
            raw = await _post(cfg.url, token, url, cfg.timeout_s)
        rendered = _parse(raw)
    except _Failure as exc:
        log.info("renderer.failed", host=host, reason=exc.reason)
        return None
    except (httpx.HTTPError, TimeoutError, OSError) as exc:
        log.info("renderer.failed", host=host, reason=type(exc).__name__)
        return None
    except Exception:
        log.exception("renderer.unexpected", host=host)
        return None
    try:
        await guard(rendered.final_url)
    except IndexingError:
        log.info("renderer.final_url_refused", host=host, final_host=_host(rendered.final_url))
        return None
    return rendered


async def _post(base: str, token: str, url: str, timeout_s: float) -> bytes:
    endpoint = base.strip().rstrip("/") + "/render"
    async with (
        httpx.AsyncClient(timeout=timeout_s, follow_redirects=False, trust_env=False) as http,
        http.stream(
            "POST",
            endpoint,
            json={"url": url},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp,
    ):
        chunks: list[bytes] = []
        total = 0
        async for chunk in resp.aiter_bytes():
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise _Failure("too_large")
            chunks.append(chunk)
        if resp.status_code != 200:
            raise _Failure(f"status_{resp.status_code}:{_error_code(b''.join(chunks))}")
    return b"".join(chunks)


def _error_code(raw: bytes) -> str:
    try:
        data: Any = json.loads(raw[:512])
    except ValueError:
        return "?"
    code = data.get("error") if isinstance(data, dict) else None
    return code if isinstance(code, str) and code.isidentifier() else "?"


def _parse(raw: bytes) -> Rendered:
    try:
        data: Any = json.loads(raw)
    except ValueError as exc:
        raise _Failure("bad_json") from exc
    if not isinstance(data, dict):
        raise _Failure("bad_shape")
    final_url, status, html = data.get("final_url"), data.get("status"), data.get("html")
    if (
        not isinstance(final_url, str)
        or not isinstance(html, str)
        or not isinstance(status, int)
        or isinstance(status, bool)
        or not 0 <= status <= 599
    ):
        raise _Failure("bad_shape")
    parts = urlsplit(final_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise _Failure("bad_final_url")
    if len(html.encode("utf-8", errors="replace")) > MAX_HTML_BYTES:
        raise _Failure("too_large")
    return Rendered(final_url=final_url, status=status, html=html)


def _host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "MAX_HTML_BYTES",
    "MAX_RESPONSE_BYTES",
    "Rendered",
    "RendererSettings",
    "get_renderer_settings",
    "render",
]
