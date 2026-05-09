"""``GET /admin/screenshots/:tenant_id/:audit_id`` — proxy that serves the
screenshot a mutating AgendaPro tool captured into ``audit_log``.

Why a proxy instead of a direct asset URL:

- The screenshot URL stored on each audit row uses the ``file://``
  scheme during Phase 1 (LocalDiskScreenshotStore in the AgendaPro
  Node server). Browsers cannot follow ``file://`` from an HTTPS
  origin; even in dev they need a server to read the bytes off disk.
- Phase 1.5 / H swaps the disk store for an R2 store. The R2 URLs
  are time-limited signed URLs we don't want to expose unauthenticated
  on the public internet — the proxy adds the auth gate.
- RLS + the path's tenant_id guard make sure operator A can't read
  screenshots from operator B's tenant by guessing audit ids.

The endpoint returns ``image/png`` bytes when the file is reachable
and a structured JSON 404 with header
``X-Screenshot-Backend: <reason>`` otherwise — the panel renders a
placeholder card in that case ("captura no disponible en este
entorno") instead of broken-image markers.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog

router = APIRouter()
log = structlog.get_logger()


def _no_backend(reason: str) -> Response:
    """404 with a stable header so the panel can pick a friendly fallback."""
    return Response(
        status_code=status.HTTP_404_NOT_FOUND,
        content=f'{{"detail": "screenshot unavailable: {reason}"}}',
        media_type="application/json",
        headers={"X-Screenshot-Backend": reason},
    )


def _safe_local_path(file_url: str, root: Path) -> Path | None:
    """Translate ``file://...`` to a Path within ``root`` (defence against
    ``..`` traversal). Returns ``None`` if the URL is malformed or points
    outside ``root``.
    """
    parsed = urlparse(file_url)
    if parsed.scheme != "file":
        return None
    raw = unquote(parsed.path or "")
    if not raw:
        return None
    candidate = Path(raw).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


@router.get(
    "/screenshots/{tenant_id}/{audit_id}",
    dependencies=[Depends(require_admin_token)],
)
async def get_screenshot(
    tenant_id: uuid.UUID,
    audit_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
) -> Response:
    """Stream the screenshot bytes for an audit row, or 404 with reason."""
    result = await session.execute(
        sa.select(AuditLog).where(AuditLog.id == audit_id, AuditLog.tenant_id == tenant_id)
    )
    audit = result.scalar_one_or_none()
    if audit is None:
        return _no_backend("audit_row_not_found_under_tenant")

    after_raw: Any = audit.after_json or {}
    after: dict[str, Any] = after_raw if isinstance(after_raw, dict) else {}
    url = after.get("screenshot_url")
    if not isinstance(url, str) or not url:
        return _no_backend("no_screenshot_recorded")

    if url.startswith(("https://", "http://")):
        # R2 / signed URL — redirect. The signed-URL semantics already
        # enforce expiry; the panel follows the 302 transparently.
        return RedirectResponse(url, status_code=status.HTTP_302_FOUND)

    if url.startswith("file://"):
        # LocalDiskScreenshotStore writes under the directory configured at
        # the Node server's launch. The default expected path lives under
        # ``./var/screenshots`` relative to the repo root; tests + Railway
        # can override via ``NEXUS_SCREENSHOT_LOCAL_ROOT``.
        root = Path(
            os.environ.get(
                "NEXUS_SCREENSHOT_LOCAL_ROOT",
                str(Path.cwd() / "var" / "screenshots"),
            )
        )
        path = _safe_local_path(url, root)
        if path is None:
            log.warning(
                "screenshots.local_path_outside_root",
                tenant_id=str(tenant_id),
                audit_id=str(audit_id),
                root=str(root),
            )
            return _no_backend("local_disk_path_invalid")
        if not path.exists() or not path.is_file():
            return _no_backend("local_disk_file_missing")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            log.warning(
                "screenshots.local_read_failed",
                error=str(exc),
                tenant_id=str(tenant_id),
                audit_id=str(audit_id),
            )
            return _no_backend("local_disk_read_failed")
        return Response(
            content=payload,
            media_type="image/png",
            headers={
                "Cache-Control": "private, max-age=300",
                "X-Screenshot-Backend": "local-disk",
            },
        )

    # Unknown scheme — the agent recorded a URL we don't know how to
    # serve. Treat as a 404 + log so the operator sees it.
    log.warning(
        "screenshots.unknown_scheme",
        scheme=url.split("://", 1)[0] if "://" in url else "none",
        tenant_id=str(tenant_id),
        audit_id=str(audit_id),
    )
    return _no_backend("unknown_scheme")


__all__ = ["router"]
