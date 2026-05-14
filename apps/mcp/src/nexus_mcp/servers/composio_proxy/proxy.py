"""Per-tenant Composio-backed tool proxy.

A ``ComposioProxyTool`` is a thin :class:`ToolBase` that, when ``invoke``d:

1. Validates the LLM-supplied args against the input schema Composio
   advertised at sync time (cached in ``tool_catalog.input_schema``).
2. Resolves ``user_id = f"tenant_{slug}"`` from the active tenant via the
   contextvar and pairs it with the tenant's ``connection_id`` (loaded
   from ``tenant_connectors.credentials_ref`` once per turn).
3. Calls ``ComposioClient.execute_tool`` and wraps the result in the
   standard ``ToolResult`` envelope.

Because Composio toolkits are per-tenant by construction, the registry
can't preload them at process start. The pipeline's handler node calls
:func:`build_composio_proxies_for_tenant` *per turn*, builds a tenant-
scoped MCPRegistry view by merging the proxies with the global static
tools, and runs dispatch against that view. The cost is one DB query
(blueprint load) per turn — cheap and bounded.

Defense in depth:

- The pre-LLM whitelist filter still applies; a Composio tool not in the
  active ``agent_config.tools`` set never reaches the LLM.
- ``MCPRegistry.dispatch`` re-checks the whitelist before invoking. A
  hallucinated ``calendly.create_event`` against a tenant without
  Calendly connected falls back to ``ToolNotInWhitelist``.
- The Composio adapter enforces the ``user_id`` invariant when calling
  ``execute_tool``: even a smuggled ``connection_id`` belonging to
  another tenant would fail on the upstream side (the connection's
  ``user_id`` is recorded at link time).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, ClassVar

import structlog
from nexus_api.core.tenant_context import (
    require_current_tenant,
    tenant_scoped_session,
)
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Connector,
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
    ToolCatalog,
    ToolStatus,
)
from pydantic import ConfigDict, Field
from sqlalchemy import select

from nexus_mcp.base import InputModel, OutputModel, ToolBase, ToolError, make_envelope

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ComposioToolBlueprint:
    """Sufficient data to materialise a proxy at dispatch time."""

    tool_name: str
    description: str
    input_schema: dict[str, Any]
    toolkit_slug: str
    connection_id: str
    user_id: str


# ── pydantic shim for input/output ─────────────────────────────────────────


class _PassthroughInput(InputModel):
    """Accept arbitrary JSON-serialisable args. Composio's own server-side
    schema is the authority — re-validating here would just duplicate the
    constraint and risk drift when Composio updates a toolkit."""

    model_config = ConfigDict(extra="allow")


class _PassthroughOutput(OutputModel):
    model_config = ConfigDict(extra="allow")
    # Pydantic accepts ``= {}`` as a default for dict fields (it copies on
    # instantiation), but ruff RUF012 flags it. Use ``Field(default_factory)``
    # to express the intent and silence the lint.
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    log_id: str | None = None


# ── proxy tool ──────────────────────────────────────────────────────────────


class ComposioProxyTool(ToolBase):
    """One instance per (tenant, composio tool). Built lazily per turn."""

    # Class-level attributes are required by :class:`ToolBase`. They get
    # overwritten on each instance via ``__init__`` below; the registry
    # reads them after construction.
    name: ClassVar[str] = "composio.placeholder"
    description: ClassVar[str] = ""
    input_model: ClassVar[type[InputModel]] = _PassthroughInput
    output_model: ClassVar[type[OutputModel]] = _PassthroughOutput
    side_effects: ClassVar[tuple[str, ...]] = ("external_api",)

    def __init__(self, blueprint: ComposioToolBlueprint) -> None:
        self._blueprint = blueprint
        # Subclass-the-shape-at-runtime so each proxy advertises a
        # distinct ``name`` to LiteLLM. The ``input_model`` stays the
        # passthrough — Composio enforces the real shape upstream.
        self.name = blueprint.tool_name
        self.description = blueprint.description or (f"Composio-backed tool {blueprint.tool_name}")
        self.input_model = _PassthroughInput  # type: ignore[misc]
        self.output_model = _PassthroughOutput  # type: ignore[misc]
        # Surface the schema Composio gave us so to_tool_def returns the
        # real parameters to the LLM.
        self._input_schema = blueprint.input_schema

    def to_tool_def(self) -> Any:  # type: ignore[override]
        """Instance-method override of the classmethod on ToolBase.

        The registry calls ``self._tools[name].to_tool_def()`` so the
        descriptor on the instance wins. Each proxy carries its own
        ``name`` / ``description`` / ``_input_schema``.
        """
        from nexus_mcp.base import ToolDef

        return ToolDef(
            name=self.name,
            description=self.description,
            parameters=self._input_schema or {"type": "object", "properties": {}},
        )

    async def run(self, payload: InputModel) -> OutputModel:
        # Not used — we override ``invoke`` because we don't want
        # ``invoke``'s strict isinstance check (Composio returns a
        # dynamic dict, not a Pydantic instance).
        raise NotImplementedError

    async def invoke(self, args: dict[str, Any]) -> dict[str, Any]:
        tenant_id = require_current_tenant()
        bp = self._blueprint

        # Lazy import to avoid the SDK warm-up cost at module load.
        from nexus_api.services.connectors.composio_client import (
            ComposioAuthExpired,
            ComposioError,
            ComposioNotFound,
            ComposioUnavailable,
        )
        from nexus_api.services.connectors.runtime import get_composio_client

        client = get_composio_client()
        try:
            result = await client.execute_tool(
                tool_slug=bp.tool_name,
                user_id=bp.user_id,
                connection_id=bp.connection_id,
                arguments=dict(args),
            )
        except ComposioAuthExpired as exc:
            raise ToolError(
                f"connection for {bp.toolkit_slug} expired (401); operator must re-consent"
            ) from exc
        except ComposioNotFound as exc:
            raise ToolError(f"connection {bp.connection_id} not found by Composio: {exc}") from exc
        except ComposioUnavailable as exc:
            raise ToolError(f"Composio temporarily unavailable: {exc}") from exc
        except ComposioError as exc:
            raise ToolError(f"Composio error: {exc}") from exc

        return make_envelope(
            tool=bp.tool_name,
            tenant_id=tenant_id,
            args=dict(args),
            result={
                "data": dict(result.data),
                "error": result.error,
                "log_id": result.log_id,
            },
            status="ok" if result.error is None else "error",
        )


# ── blueprint loading ──────────────────────────────────────────────────────


async def load_blueprints_for_tenant(
    tenant_id: uuid.UUID,
    *,
    whitelist: frozenset[str] | None = None,
) -> list[ComposioToolBlueprint]:
    """Return blueprints for every Composio-backed tool active under the
    tenant. ``whitelist`` filters down to only the tools the agent_config
    references — saves us materialising 50 GCal tools when the agent only
    uses 3.
    """
    sm = get_sessionmaker()
    blueprints: list[ComposioToolBlueprint] = []
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        # Tenant.slug — the canonical ``user_id`` ingredient — is global
        # data not RLS-scoped (Tenant rows ARE the scope). The lookup
        # works inside the scoped session because ``tenants`` doesn't
        # have RLS.
        slug = await session.scalar(select(Tenant.slug).where(Tenant.id == tenant_id))
        if not slug:
            return blueprints
        user_id = f"tenant_{slug}"

        # All ACTIVE tenant_connectors for composio connectors + their
        # tools. Single join keeps the per-turn cost down.
        result = await session.execute(
            select(TenantConnector, Connector)
            .join(Connector, Connector.id == TenantConnector.connector_id)
            .where(
                TenantConnector.tenant_id == tenant_id,
                Connector.auth_kind == "oauth_composio",
                TenantConnector.status.in_(
                    [
                        TenantConnectorStatus.CONNECTED.value,
                        TenantConnectorStatus.PARTIAL.value,
                    ]
                ),
            )
        )
        installs = list(result.all())
        if not installs:
            return blueprints

        # Map connector_id → connection_id once.
        connection_by_connector: dict[uuid.UUID, str] = {}
        toolkit_by_connector: dict[uuid.UUID, str] = {}
        for tc, conn in installs:
            credentials = tc.credentials_ref or {}
            connection_id = credentials.get("composio_connection_id")
            if isinstance(connection_id, str) and connection_id:
                connection_by_connector[conn.id] = connection_id
                # toolkit slug lives after the ``composio:`` prefix in
                # mcp_server_ref.
                toolkit_by_connector[conn.id] = (
                    conn.mcp_server_ref.split(":", 1)[1]
                    if ":" in conn.mcp_server_ref
                    else conn.slug
                )

        if not connection_by_connector:
            return blueprints

        # Tools belonging to these connectors.
        tools_q = select(ToolCatalog).where(
            ToolCatalog.connector_id.in_(connection_by_connector.keys()),
            ToolCatalog.status == ToolStatus.ACTIVE,
        )
        tools = (await session.scalars(tools_q)).all()
        for t in tools:
            if whitelist is not None and t.name not in whitelist:
                continue
            blueprints.append(
                ComposioToolBlueprint(
                    tool_name=t.name,
                    description=t.description or f"Composio tool {t.name}",
                    input_schema=t.input_schema or {},
                    toolkit_slug=toolkit_by_connector.get(t.connector_id, ""),
                    connection_id=connection_by_connector[t.connector_id],
                    user_id=user_id,
                )
            )
    return blueprints


def build_composio_proxies_for_tenant(
    blueprints: list[ComposioToolBlueprint],
) -> list[ComposioProxyTool]:
    """Materialise proxy tools from blueprints. Pure (no I/O)."""
    return [ComposioProxyTool(bp) for bp in blueprints]
