"""Composio v3 SDK adapter — `link()` / tools / webhook verify.

Why an adapter and not direct SDK use:

- The runtime must always pass ``user_id = f"tenant_{tenant.slug}"`` so the
  Composio entity-isolation guarantee holds. A thin Protocol + concrete
  impl makes that enforced at one place and gives tests a swappable fake.
- Composio is still migrating v2→v3 (deadline 2026-07-03 for ``initiate()``
  retirement). The adapter pins us to ``connected_accounts.link()`` and
  ``tools.get()``/``tools.execute()`` from day one.
- An outage in Composio (~36h precedent Apr 28-30 2026) must degrade
  predictably: every call wrapped here can raise ``ComposioUnavailable``,
  and callers translate that to ``connector_temporarily_unavailable`` for
  the LLM.

The SDK import is lazy so test environments without the package can still
load the module and use ``FakeComposioClient``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


class ComposioError(RuntimeError):
    """Generic upstream error talking to Composio."""


class ComposioUnavailable(ComposioError):
    """Composio API is down / timing out / 5xx — degrade gracefully."""


class ComposioAuthExpired(ComposioError):
    """A 401/403 came back from Composio. Caller must flip ``needs_reauth``."""


class ComposioNotFound(ComposioError):
    """connection_id or toolkit unknown to Composio."""


class ComposioAuthConfigMissing(ComposioError):
    """No auth_config registered in Composio for the requested toolkit.

    Raised when the operator forgot to create the auth_config in the Composio
    dashboard before initiating consent. The error message tells them exactly
    which toolkit to register.
    """


class ComposioAuthConfigAmbiguous(ComposioError):
    """Multiple auth_configs exist for the same toolkit in this project.

    Phase 1 expects exactly one auth_config per toolkit. If we hit this, the
    operator must label one as "default" (Phase 4+ feature) or remove the
    duplicates from the dashboard.
    """


@dataclass(frozen=True)
class AuthConfigSummary:
    """One auth_config row from ``composio.auth_configs.list()``.

    Composio's dashboard surfaces these as cards (see operator screenshot).
    The platform uses them to build the dynamic part of the connector
    catalog — every auth_config the operator registered becomes a
    connectable toolkit in Nexus without a deploy. Fields are tolerant
    to v3 SDK shape differences across minor versions; the dashboard
    metadata (icon, vendor, category) is best-effort and may be empty.
    """

    auth_config_id: str
    toolkit_slug: str
    display_name: str
    auth_scheme: str  # "OAUTH2", "API_KEY", etc.
    vendor: str | None = None
    category: str | None = None
    icon_url: str | None = None
    docs_url: str | None = None


@dataclass(frozen=True)
class ConnectionRequest:
    """Result of ``composio.connected_accounts.link()``."""

    connection_id: str
    redirect_url: str


@dataclass(frozen=True)
class ConnectedAccount:
    """A connection in Composio terms."""

    connection_id: str
    user_id: str
    toolkit_slug: str
    status: str  # "ACTIVE" | "EXPIRED" | "FAILED" | etc.
    granted_scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ComposioTool:
    """One tool descriptor from ``composio.tools.get()``.

    The annotations (read_only / destructive) come either from the
    upstream MCP descriptor (if Composio passes them through) or from a
    per-slug override map in the seed YAML. See ``tools_sync.py`` for
    the resolution.
    """

    slug: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    scopes: list[str] = field(default_factory=list)
    raw_tags: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolExecution:
    """Result of ``composio.tools.execute()``."""

    data: dict[str, Any]
    error: str | None
    log_id: str | None


class ComposioClientProtocol(abc.ABC):
    """Surface the rest of the codebase depends on. Two implementations:
    ``LiveComposioClient`` (real SDK) and ``FakeComposioClient`` (tests).
    """

    @abc.abstractmethod
    async def find_auth_config_id(self, toolkit: str) -> str:
        """Resolve the auth_config_id for a toolkit from Composio itself.

        Replaces the prior pattern of pegando auth_config_ids in Doppler.
        Composio is the source of truth — the operator creates auth_configs
        in the dashboard and they become discoverable here. Raises
        ``ConfigNotFound`` if the toolkit has no auth_config in this project.
        """

    @abc.abstractmethod
    async def list_auth_configs(self) -> list[AuthConfigSummary]:
        """Enumerate every auth_config registered in this Composio project.

        Used by the catalog endpoint to derive the dynamic part of the
        connector list — toolkits that became available the moment the
        operator added them in the dashboard, no redeploy required.

        Returns an empty list if Composio has no auth_configs yet. Raises
        ``ComposioUnavailable`` for transport / 5xx errors so the caller
        can degrade to "show only the custom seeds".
        """

    @abc.abstractmethod
    async def link_account(
        self,
        *,
        user_id: str,
        auth_config_id: str,
        callback_url: str | None = None,
    ) -> ConnectionRequest: ...

    @abc.abstractmethod
    async def get_account(self, connection_id: str) -> ConnectedAccount: ...

    @abc.abstractmethod
    async def revoke_account(self, connection_id: str) -> None: ...

    @abc.abstractmethod
    async def list_tools(
        self, *, user_id: str, toolkit: str, limit: int | None = None
    ) -> list[ComposioTool]: ...

    @abc.abstractmethod
    async def execute_tool(
        self,
        *,
        tool_slug: str,
        user_id: str,
        connection_id: str,
        arguments: dict[str, Any],
    ) -> ToolExecution: ...


# ── live impl ───────────────────────────────────────────────────────────────


class LiveComposioClient(ComposioClientProtocol):
    """Wrapper over the official ``composio`` Python SDK v3."""

    def __init__(self, *, api_key: str) -> None:
        if not api_key:
            msg = "Composio API key is empty — set NEXUS_COMPOSIO_API_KEY"
            raise ValueError(msg)
        try:
            # Lazy import so tests without the package still load this module.
            from composio import Composio
        except ImportError as exc:  # pragma: no cover — runtime check
            msg = (
                "composio SDK not installed; add `composio>=0.8` to deps "
                "before using LiveComposioClient"
            )
            raise RuntimeError(msg) from exc
        self._client = Composio(api_key=api_key)

    async def list_auth_configs(self) -> list[AuthConfigSummary]:
        try:
            response = await _maybe_async(self._client.auth_configs.list)
        except Exception as exc:
            raise _translate_composio_error(exc) from exc
        items = getattr(response, "items", None) or getattr(response, "data", None) or []
        out: list[AuthConfigSummary] = []
        for it in items:
            toolkit_obj = getattr(it, "toolkit", None)
            toolkit_slug = (
                str(getattr(toolkit_obj, "slug", "") or getattr(it, "toolkit_slug", ""))
                .strip()
                .lower()
            )
            if not toolkit_slug:
                # auth_config without a toolkit binding is an SDK
                # anomaly — skip rather than crash the entire catalog.
                continue
            display_name = str(
                getattr(toolkit_obj, "name", "") or getattr(it, "name", "") or toolkit_slug.title()
            )
            scheme = str(getattr(it, "auth_scheme", None) or getattr(it, "scheme", "OAUTH2"))
            vendor = (
                getattr(toolkit_obj, "vendor", None)
                or getattr(toolkit_obj, "provider_name", None)
                or None
            )
            category_obj = getattr(toolkit_obj, "category", None) or getattr(
                toolkit_obj, "categories", None
            )
            category: str | None
            if isinstance(category_obj, list) and category_obj:
                category = str(category_obj[0])
            elif category_obj:
                category = str(category_obj)
            else:
                category = None
            out.append(
                AuthConfigSummary(
                    auth_config_id=str(it.id),
                    toolkit_slug=toolkit_slug,
                    display_name=display_name,
                    auth_scheme=scheme.upper(),
                    vendor=str(vendor) if vendor else None,
                    category=category,
                    icon_url=getattr(toolkit_obj, "logo_url", None)
                    or getattr(toolkit_obj, "icon_url", None),
                    docs_url=getattr(toolkit_obj, "docs_url", None),
                )
            )
        return out

    async def find_auth_config_id(self, toolkit: str) -> str:
        try:
            response = await _maybe_async(self._client.auth_configs.list, toolkit=toolkit)
        except Exception as exc:
            raise _translate_composio_error(exc) from exc
        # Composio v3 returns a paginated response with ``items`` (or ``data``
        # depending on SDK minor version). Be tolerant of either.
        items = getattr(response, "items", None) or getattr(response, "data", None) or []
        if not items:
            msg = (
                f"no auth_config registered in Composio for toolkit "
                f"{toolkit!r}; create one in the dashboard "
                "(Auth Configs → + Add → select toolkit)"
            )
            raise ComposioAuthConfigMissing(msg)
        if len(items) > 1:
            ids = [str(getattr(i, "id", "?")) for i in items]
            msg = (
                f"multiple auth_configs ({len(items)}) for toolkit {toolkit!r}: "
                f"{ids}. Phase 1 expects exactly one. Remove duplicates from "
                "the Composio dashboard or label one as default (Phase 4+)."
            )
            raise ComposioAuthConfigAmbiguous(msg)
        ac_id: str = str(items[0].id)
        return ac_id

    async def link_account(
        self,
        *,
        user_id: str,
        auth_config_id: str,
        callback_url: str | None = None,
    ) -> ConnectionRequest:
        try:
            kwargs: dict[str, Any] = {
                "user_id": user_id,
                "auth_config_id": auth_config_id,
            }
            if callback_url:
                kwargs["callback_url"] = callback_url
            req = await _maybe_async(self._client.connected_accounts.link, **kwargs)
        except Exception as exc:
            raise _translate_composio_error(exc) from exc
        return ConnectionRequest(
            connection_id=str(req.id),
            redirect_url=str(req.redirect_url),
        )

    async def get_account(self, connection_id: str) -> ConnectedAccount:
        try:
            acc = await _maybe_async(self._client.connected_accounts.get, connection_id)
        except Exception as exc:
            raise _translate_composio_error(exc) from exc
        return ConnectedAccount(
            connection_id=str(acc.id),
            user_id=str(getattr(acc, "user_id", "")),
            toolkit_slug=str(getattr(acc, "toolkit", "")),
            status=str(getattr(acc, "status", "UNKNOWN")),
            granted_scopes=list(getattr(acc, "scopes", []) or []),
        )

    async def revoke_account(self, connection_id: str) -> None:
        try:
            await _maybe_async(self._client.connected_accounts.delete, connection_id)
        except Exception as exc:
            raise _translate_composio_error(exc) from exc

    async def list_tools(
        self, *, user_id: str, toolkit: str, limit: int | None = None
    ) -> list[ComposioTool]:
        try:
            kwargs: dict[str, Any] = {
                "user_id": user_id,
                "toolkits": [toolkit],
            }
            if limit:
                kwargs["limit"] = limit
            tools = await _maybe_async(self._client.tools.get, **kwargs)
        except Exception as exc:
            raise _translate_composio_error(exc) from exc
        out: list[ComposioTool] = []
        for t in tools:
            out.append(
                ComposioTool(
                    slug=str(getattr(t, "name", getattr(t, "slug", ""))),
                    description=str(getattr(t, "description", "")),
                    input_schema=dict(
                        getattr(t, "parameters", getattr(t, "input_schema", {})) or {}
                    ),
                    output_schema=dict(getattr(t, "output_schema", {}) or {}),
                    scopes=list(getattr(t, "scopes", []) or []),
                    raw_tags=dict(getattr(t, "tags", {}) or {}),
                )
            )
        return out

    async def execute_tool(
        self,
        *,
        tool_slug: str,
        user_id: str,
        connection_id: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        try:
            result = await _maybe_async(
                self._client.tools.execute,
                tool_slug,
                user_id=user_id,
                connected_account_id=connection_id,
                arguments=arguments,
            )
        except Exception as exc:
            raise _translate_composio_error(exc) from exc
        return ToolExecution(
            data=dict(getattr(result, "data", {}) or {}),
            error=getattr(result, "error", None),
            log_id=getattr(result, "log_id", None),
        )


async def _maybe_async(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call a Composio SDK method; await if it returned a coroutine."""
    import inspect

    res = fn(*args, **kwargs)
    if inspect.isawaitable(res):
        return await res
    return res


def _translate_composio_error(exc: Exception) -> Exception:
    """Map opaque SDK errors onto our typed hierarchy.

    The SDK exposes HTTP status on raised exceptions (varies by version);
    we duck-type via getattr and fall back to ComposioError.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status in {401, 403}:
        return ComposioAuthExpired(str(exc))
    if status == 404:
        return ComposioNotFound(str(exc))
    if isinstance(status, int) and status >= 500:
        return ComposioUnavailable(str(exc))
    if "timeout" in str(exc).lower() or "connection" in str(exc).lower():
        return ComposioUnavailable(str(exc))
    return ComposioError(str(exc))


# ── webhook signature verification (Svix-style; documented by Composio) ─────


def verify_composio_webhook(
    *,
    webhook_id: str,
    webhook_timestamp: str,
    body: str,
    signature_header: str,
    secret: str,
) -> None:
    """Verify a Composio webhook signature. Raises on mismatch.

    Composio uses the Standard Webhooks scheme (Svix-style):
        signing_string = f"{webhook_id}.{webhook_timestamp}.{body}"
        signature = base64(HMAC-SHA256(secret, signing_string))
        header value = "v1,<base64>"

    Headers used: ``webhook-id`` / ``webhook-timestamp`` / ``webhook-signature``.
    """
    import base64
    import hashlib
    import hmac
    import time

    if not secret:
        msg = "composio webhook secret is empty"
        raise ValueError(msg)
    if not (webhook_id and webhook_timestamp and signature_header):
        msg = "composio webhook headers missing"
        raise ValueError(msg)
    # Replay window: 5 minutes (Composio default).
    try:
        ts = int(webhook_timestamp)
    except ValueError as exc:
        msg = f"webhook-timestamp not an int: {webhook_timestamp!r}"
        raise ValueError(msg) from exc
    now = int(time.time())
    if abs(now - ts) > 300:
        msg = f"composio webhook timestamp out of window (Δ={now - ts}s)"
        raise ValueError(msg)
    signing_string = f"{webhook_id}.{webhook_timestamp}.{body}"
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), signing_string.encode("utf-8"), hashlib.sha256).digest()
    ).decode("ascii")
    # Header is "v1,<base64>" or just "<base64>".
    received = signature_header.split(",", 1)[1] if "," in signature_header else signature_header
    if not hmac.compare_digest(expected, received):
        msg = "composio webhook signature mismatch"
        raise ValueError(msg)


# ── fake client for tests ───────────────────────────────────────────────────


@dataclass
class _FakeConnection:
    connection_id: str
    user_id: str
    toolkit: str
    status: str
    granted_scopes: list[str]
    auth_config_id: str
    redirect_url: str


class FakeComposioClient(ComposioClientProtocol):
    """In-memory ComposioClientProtocol for tests + dev environments.

    Drives the runtime end-to-end without a Composio account. Each method
    records its call so tests can assert that the right user_id was sent.
    """

    def __init__(self) -> None:
        self._connections: dict[str, _FakeConnection] = {}
        self._tools_by_toolkit: dict[str, list[ComposioTool]] = {}
        self._auth_configs_by_toolkit: dict[str, list[str]] = {}
        self._auth_config_metadata: dict[str, AuthConfigSummary] = {}
        self._execute_log: list[dict[str, Any]] = []
        self._next_id = 1
        self.simulate_unavailable: bool = False
        self.simulate_auth_expired_for: set[str] = set()

    # control surface used by tests ------------------------------------------

    def register_tools(self, toolkit: str, tools: list[ComposioTool]) -> None:
        self._tools_by_toolkit[toolkit.lower()] = list(tools)

    def register_auth_config(
        self,
        toolkit: str,
        auth_config_id: str,
        *,
        display_name: str | None = None,
        auth_scheme: str = "OAUTH2",
        vendor: str | None = None,
        category: str | None = None,
        icon_url: str | None = None,
    ) -> None:
        """Pretend the operator created an auth_config in the Composio dashboard
        for this toolkit. Tests that exercise the consent flow need to call
        this — otherwise ``find_auth_config_id`` raises ComposioAuthConfigMissing
        (which mirrors real-world behaviour: forgetting to register the
        auth_config = consent flow fails fast).

        Optional metadata flows into ``list_auth_configs()`` so tests that
        cover the dynamic catalog can assert on the projected fields.
        """
        slug = toolkit.lower()
        self._auth_configs_by_toolkit.setdefault(slug, []).append(auth_config_id)
        self._auth_config_metadata[auth_config_id] = AuthConfigSummary(
            auth_config_id=auth_config_id,
            toolkit_slug=slug,
            display_name=display_name or slug.title(),
            auth_scheme=auth_scheme.upper(),
            vendor=vendor,
            category=category,
            icon_url=icon_url,
        )

    def force_connect(
        self,
        *,
        connection_id: str,
        user_id: str,
        toolkit: str,
        status: str = "ACTIVE",
        scopes: list[str] | None = None,
    ) -> _FakeConnection:
        """Skip the OAuth dance; pretend the user already consented."""
        conn = _FakeConnection(
            connection_id=connection_id,
            user_id=user_id,
            toolkit=toolkit.lower(),
            status=status,
            granted_scopes=list(scopes or []),
            auth_config_id="ac_fake",
            redirect_url="https://fake.composio/auth/" + connection_id,
        )
        self._connections[connection_id] = conn
        return conn

    @property
    def execute_log(self) -> list[dict[str, Any]]:
        return list(self._execute_log)

    # ComposioClientProtocol --------------------------------------------------

    async def list_auth_configs(self) -> list[AuthConfigSummary]:
        if self.simulate_unavailable:
            raise ComposioUnavailable("fake: composio down")
        out: list[AuthConfigSummary] = []
        for slug, ids in self._auth_configs_by_toolkit.items():
            for ac_id in ids:
                cached = self._auth_config_metadata.get(ac_id)
                if cached is not None:
                    out.append(cached)
                else:
                    out.append(
                        AuthConfigSummary(
                            auth_config_id=ac_id,
                            toolkit_slug=slug,
                            display_name=slug.title(),
                            auth_scheme="OAUTH2",
                        )
                    )
        return out

    async def find_auth_config_id(self, toolkit: str) -> str:
        if self.simulate_unavailable:
            raise ComposioUnavailable("fake: composio down")
        configs = self._auth_configs_by_toolkit.get(toolkit.lower(), [])
        if not configs:
            raise ComposioAuthConfigMissing(
                f"fake: no auth_config registered for toolkit {toolkit!r}"
            )
        if len(configs) > 1:
            raise ComposioAuthConfigAmbiguous(
                f"fake: {len(configs)} auth_configs for toolkit {toolkit!r}: {configs}"
            )
        return configs[0]

    async def link_account(
        self,
        *,
        user_id: str,
        auth_config_id: str,
        callback_url: str | None = None,
    ) -> ConnectionRequest:
        if self.simulate_unavailable:
            raise ComposioUnavailable("fake: composio down")
        connection_id = f"conn_fake_{self._next_id:04d}"
        self._next_id += 1
        # Toolkit is derived from auth_config_id convention in real Composio;
        # for the fake we infer it lazily on first list_tools call.
        conn = _FakeConnection(
            connection_id=connection_id,
            user_id=user_id,
            toolkit="",  # filled when caller invokes list_tools
            status="PENDING",
            granted_scopes=[],
            auth_config_id=auth_config_id,
            redirect_url=f"https://fake.composio/auth/{connection_id}?cb={callback_url or ''}",
        )
        self._connections[connection_id] = conn
        return ConnectionRequest(connection_id=connection_id, redirect_url=conn.redirect_url)

    async def get_account(self, connection_id: str) -> ConnectedAccount:
        if self.simulate_unavailable:
            raise ComposioUnavailable("fake: composio down")
        if connection_id in self.simulate_auth_expired_for:
            raise ComposioAuthExpired(f"fake: 401 for {connection_id}")
        conn = self._connections.get(connection_id)
        if conn is None:
            raise ComposioNotFound(f"fake: no connection {connection_id}")
        return ConnectedAccount(
            connection_id=conn.connection_id,
            user_id=conn.user_id,
            toolkit_slug=conn.toolkit,
            status=conn.status,
            granted_scopes=list(conn.granted_scopes),
        )

    async def revoke_account(self, connection_id: str) -> None:
        if self.simulate_unavailable:
            raise ComposioUnavailable("fake: composio down")
        self._connections.pop(connection_id, None)

    async def list_tools(
        self, *, user_id: str, toolkit: str, limit: int | None = None
    ) -> list[ComposioTool]:
        if self.simulate_unavailable:
            raise ComposioUnavailable("fake: composio down")
        tools = self._tools_by_toolkit.get(toolkit.lower(), [])
        return list(tools[:limit]) if limit else list(tools)

    async def execute_tool(
        self,
        *,
        tool_slug: str,
        user_id: str,
        connection_id: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        if self.simulate_unavailable:
            raise ComposioUnavailable("fake: composio down")
        if connection_id in self.simulate_auth_expired_for:
            raise ComposioAuthExpired(f"fake: 401 for {connection_id}")
        conn = self._connections.get(connection_id)
        if conn is None:
            raise ComposioNotFound(f"fake: no connection {connection_id}")
        # Critical isolation guard for tests — fake client matches the
        # real client invariant: user_id passed must equal the connection's
        # user_id. A test that smuggles tenant A's user_id with tenant B's
        # connection_id would fail loudly here.
        if conn.user_id != user_id:
            raise ComposioError(
                f"fake: user_id mismatch (connection.user_id={conn.user_id} vs requested={user_id})"
            )
        self._execute_log.append(
            {
                "tool_slug": tool_slug,
                "user_id": user_id,
                "connection_id": connection_id,
                "arguments": dict(arguments),
            }
        )
        return ToolExecution(
            data={"ok": True, "echo": dict(arguments)},
            error=None,
            log_id=f"log_fake_{len(self._execute_log)}",
        )


__all__ = [
    "AuthConfigSummary",
    "ComposioAuthConfigAmbiguous",
    "ComposioAuthConfigMissing",
    "ComposioAuthExpired",
    "ComposioClientProtocol",
    "ComposioError",
    "ComposioNotFound",
    "ComposioTool",
    "ComposioUnavailable",
    "ConnectedAccount",
    "ConnectionRequest",
    "FakeComposioClient",
    "LiveComposioClient",
    "ToolExecution",
    "verify_composio_webhook",
]
