"""El validador sin modelo del AgentSpec — spec 047, T078 (requisitos 15.4, 16.1 y 16.6).

Comprueba un documento antes de enseñar una propuesta y otra vez al aplicarla,
sin llamar a ningún modelo:

- **el esquema y sus límites** (Pydantic, ``extra="forbid"``: ninguna clave de
  plataforma cabe), más lo que el esquema no puede decir: las secciones suman
  como mucho 8.000 caracteres, y un texto migrado no crece por encima de
  max(8.000, su longitud migrada);
- **las herramientas**: en el catálogo, permitidas (ni internas, ni retiradas, ni
  de una integración que no se ofrece) y, si necesitan una integración,
  **conectadas** al cliente. Lo que falta por conectar va en
  ``connection_requests``, no en ``tools``;
- **ningún cliente final como argumento** (garantía 8): una herramienta con un
  argumento que elige a una persona no entra en un agente «structured»; en un
  agente de antes («instructions») se deja como estaba, salvo que la proponga
  el constructor;
- **nada de otro cliente**: los servicios y los agentes que cita son del cliente,
  y ningún texto lleva el nombre de otro cliente del partner;
- **el aviso de IA lo decide una persona** (16.6): una propuesta del constructor
  que lo trae decidido se rechaza.

La parte pura es :func:`validate_spec`; :func:`load_context` lee de la base lo
que necesita, con el cliente del contexto (RLS).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Final, Literal

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.services.agent_spec.schema import MAX_INSTRUCTIONS_CHARS, AgentSpec

Author = Literal["person", "builder", "copilot", "suggestion", "correction", "migration"]

#: Un argumento que nombra o localiza a una persona (garantía 8; el mismo eje
#: que barre ``tests/isolation/test_51``).
END_CUSTOMER_ARGS: Final = frozenset(
    {
        "customer",
        "customer_id",
        "customer_email",
        "customer_phone",
        "customer_name",
        "client_id",
        "client_phone",
        "client_name",
        "client_document",
        "client_email",
        "patient_id",
        "debtor_id",
        "phone",
        "email",
        "document",
        "wa_id",
        "contact_id",
        "conversation_id",
    }
)
#: Los que pone el servidor o solo escriben, no buscan (el inventario de test_51).
SERVER_SIDE_ARGS: Final = frozenset(
    {
        ("payments.request_review", "customer_name"),
    }
)
_ALWAYS_INJECTED: Final = "conversation_id"


@dataclass(frozen=True)
class Problem:
    pointer: str
    code: str
    message: str


@dataclass(frozen=True)
class ToolInfo:
    """Lo que el validador necesita saber de una herramienta del catálogo."""

    name: str
    #: ``active`` | ``experimental`` | ``deprecated`` | ``internal``.
    status: str = "active"
    #: La integración que necesita (slug), o ``None`` si es nativa.
    integration: str | None = None
    #: Si la integración se ofrece (su estado en el catálogo de integraciones).
    integration_offered: bool = True
    #: Si el cliente la tiene conectada.
    connected: bool = True
    #: Los nombres de sus argumentos.
    args: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Context:
    tools: Mapping[str, ToolInfo] = field(default_factory=dict)
    service_ids: frozenset[str] = frozenset()
    agent_ids: frozenset[str] = frozenset()
    #: Los nombres de los otros clientes del partner (nunca del propio).
    foreign_names: tuple[str, ...] = ()
    #: La longitud del prompt migrado, para la regla de «no crece».
    legacy_chars: int | None = None


def _pydantic_problems(exc: ValidationError) -> list[Problem]:
    out: list[Problem] = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if not str(p).startswith("function-")]
        # Las uniones (``str | None``) meten el nombre del tipo en la ruta.
        loc = [p for p in loc if p not in {"str", "int", "list[str]", "constrained-str"}]
        pointer = "/" + "/".join(loc) if loc else ""
        kind = str(err.get("type", "invalid"))
        code = "platform_key" if kind == "extra_forbidden" else "schema"
        out.append(Problem(pointer, code, str(err.get("msg", "Valor no válido"))))
    return out


#: Lo bastante largo para no confundir un nombre con una palabra corriente.
_MIN_FOREIGN_NAME = 6


def _texts(doc: Mapping[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []

    def walk(node: Any, pointer: str) -> None:
        if isinstance(node, str):
            out.append((pointer, node))
        elif isinstance(node, Mapping):
            for key, value in node.items():
                walk(value, f"{pointer}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{pointer}/{i}")

    walk(doc, "")
    return out


def validate_spec(
    doc: Mapping[str, Any] | AgentSpec,
    ctx: Context,
    *,
    author: Author = "person",
) -> tuple[AgentSpec | None, list[Problem]]:
    """``(spec, [])`` si vale; ``(spec o None, problemas)`` si no. Siempre en el
    mismo orden, para que la consola los pinte igual cada vez."""
    try:
        spec = doc if isinstance(doc, AgentSpec) else AgentSpec.model_validate(doc)
    except ValidationError as exc:
        return None, _pydantic_problems(exc)
    raw = spec.model_dump(mode="json", exclude_none=True, by_alias=True)
    problems: list[Problem] = []

    # Lo que el esquema no puede decir: los límites de las instrucciones.
    if spec.mode == "structured" and spec.instructions_chars() > MAX_INSTRUCTIONS_CHARS:
        problems.append(
            Problem(
                "/instructions/sections",
                "instructions_too_long",
                f"Las instrucciones suman más de {MAX_INSTRUCTIONS_CHARS} caracteres.",
            )
        )
    if spec.mode == "instructions" and spec.instructions and spec.instructions.legacy_text:
        ceiling = max(MAX_INSTRUCTIONS_CHARS, ctx.legacy_chars or 0)
        if len(spec.instructions.legacy_text) > ceiling:
            problems.append(
                Problem(
                    "/instructions/legacy_text",
                    "instructions_too_long",
                    f"Las instrucciones no pueden pasar de {ceiling} caracteres.",
                )
            )

    # Las herramientas: catálogo, permitidas y conectadas.
    strict_customer = spec.mode == "structured" or author != "person"
    named: list[tuple[str, str]] = [(f"/tools/{i}", t) for i, t in enumerate(spec.tools or [])]
    for i, proc in enumerate(spec.procedures or []):
        named.extend((f"/procedures/{i}/tools/{j}", t) for j, t in enumerate(proc.tools or []))
    for pointer, name in named:
        info = ctx.tools.get(name)
        if info is None:
            problems.append(
                Problem(pointer, "tool_unknown", f"La herramienta {name} no existe en el catálogo.")
            )
            continue
        if info.status in {"internal", "deprecated"} or not info.integration_offered:
            problems.append(
                Problem(pointer, "tool_not_allowed", f"La herramienta {name} no se puede usar.")
            )
            continue
        if info.integration is not None and not info.connected:
            problems.append(
                Problem(
                    pointer,
                    "tool_not_connected",
                    f"{name} necesita conectar {info.integration} antes; pídelo en "
                    "«Conectar» en lugar de añadir la herramienta.",
                )
            )
        if strict_customer and pointer.startswith("/tools/"):
            picked = sorted(
                arg
                for arg in info.args & END_CUSTOMER_ARGS
                if arg != _ALWAYS_INJECTED and (name, arg) not in SERVER_SIDE_ARGS
            )
            if picked:
                problems.append(
                    Problem(
                        pointer,
                        "end_customer_argument",
                        f"{name} deja elegir a un cliente final ({', '.join(picked)}).",
                    )
                )

    # Nada de otro cliente: lo que cita es del cliente.
    for i, sid in enumerate((spec.services.service_ids if spec.services else None) or []):
        if sid not in ctx.service_ids:
            problems.append(
                Problem(
                    f"/services/service_ids/{i}",
                    "foreign_reference",
                    "Ese servicio no es de este cliente.",
                )
            )
    for i, target in enumerate((spec.reception.targets if spec.reception else None) or []):
        if target.agent_id not in ctx.agent_ids:
            problems.append(
                Problem(
                    f"/reception/targets/{i}/agent_id",
                    "foreign_reference",
                    "Ese agente no es de este cliente.",
                )
            )
    names = [n for n in ctx.foreign_names if len(n.strip()) >= _MIN_FOREIGN_NAME]
    if names:
        pattern = re.compile(
            r"(?<!\w)(" + "|".join(re.escape(n.strip()) for n in names) + r")(?!\w)", re.I
        )
        for pointer, text in _texts(raw):
            hit = pattern.search(text)
            if hit:
                problems.append(
                    Problem(
                        pointer, "foreign_text", f"El texto nombra a otro cliente ({hit.group(1)})."
                    )
                )

    # El aviso de IA lo decide una persona (16.6).
    if author != "person" and spec.ai_disclosure.decided:
        problems.append(
            Problem(
                "/ai_disclosure/decided",
                "ai_disclosure_decided_by_builder",
                "El aviso de IA lo decide una persona, no el constructor.",
            )
        )
    return spec, problems


# ── el contexto desde la base ────────────────────────────────────────────────


async def load_context(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID | None,
    legacy_chars: int | None = None,
) -> Context:
    """Lo que el validador necesita del cliente del contexto."""
    from nexus_api.api.console.capability_names import requires_connector
    from nexus_api.db.models import (
        Agent,
        Connector,
        PartnerTenant,
        Tenant,
        TenantConnector,
        ToolCatalog,
    )
    from nexus_api.db.models.reservation import ReservationService

    tenant_id = require_current_tenant()
    connected_slugs = set(
        (
            await session.scalars(
                sa.select(Connector.slug)
                .join(TenantConnector, TenantConnector.connector_id == Connector.id)
                .where(
                    TenantConnector.tenant_id == tenant_id,
                    TenantConnector.status.in_(("connected", "partial")),
                )
            )
        ).all()
    )
    tenant = await session.get(Tenant, tenant_id)
    if tenant is not None and getattr(tenant, "agendapro_public_url", None):
        connected_slugs.add("agendapro")
    rows = await session.execute(
        sa.select(ToolCatalog, Connector.slug, Connector.status).outerjoin(
            Connector, Connector.id == ToolCatalog.connector_id
        )
    )
    from nexus_api.api.console.capabilities_client import tenant_has_catalog

    has_catalog = await tenant_has_catalog(session)
    model_args = _model_visible_args()
    tools: dict[str, ToolInfo] = {}
    for tool, slug, connector_status in rows.tuples().all():
        integration = slug or requires_connector(tool.name, "tool")
        # Los argumentos que el modelo puede rellenar son los de la definición
        # que ve (el registro MCP): los que pone el servidor no están ahí.
        props = model_args.get(tool.name)
        if props is None:
            props = frozenset(dict((tool.input_schema or {}).get("properties") or {}))
        connected = (
            integration is None
            or integration in connected_slugs
            or (integration == "channel_catalog" and has_catalog)
        )
        tools[tool.name] = ToolInfo(
            name=tool.name,
            status=getattr(tool.status, "value", str(tool.status)),
            integration=integration,
            integration_offered=connector_status in (None, "available", "beta"),
            connected=connected,
            args=props,
        )
    service_ids = frozenset(
        str(i)
        for i in (
            await session.scalars(
                sa.select(ReservationService.id).where(ReservationService.tenant_id == tenant_id)
            )
        ).all()
    )
    agent_ids = frozenset(
        str(i)
        for i in (
            await session.scalars(sa.select(Agent.id).where(Agent.tenant_id == tenant_id))
        ).all()
    )
    foreign: tuple[str, ...] = ()
    if partner_id is not None:
        foreign = tuple(
            n
            for n in (
                await session.scalars(
                    sa.select(PartnerTenant.client_name).where(
                        PartnerTenant.partner_id == partner_id,
                        PartnerTenant.tenant_id != tenant_id,
                        PartnerTenant.client_name.is_not(None),
                    )
                )
            ).all()
            if n
        )
    return Context(
        tools=tools,
        service_ids=service_ids,
        agent_ids=agent_ids,
        foreign_names=foreign,
        legacy_chars=legacy_chars,
    )


@lru_cache(maxsize=1)
def _model_visible_args() -> dict[str, frozenset[str]]:
    """Los argumentos de cada herramienta tal y como los ve el modelo."""
    try:
        from nexus_mcp import build_default_registry

        registry = build_default_registry()
        return {
            d.name: frozenset(((d.parameters or {}).get("properties") or {}).keys())
            for d in registry.get_tool_definitions(registry.names())
        }
    except Exception:  # sin registro, el esquema del catálogo
        return {}


def problems_out(problems: list[Problem]) -> list[dict[str, str]]:
    return [{"pointer": p.pointer, "code": p.code, "message": p.message} for p in problems]


__all__ = [
    "END_CUSTOMER_ARGS",
    "Context",
    "Problem",
    "ToolInfo",
    "load_context",
    "problems_out",
    "validate_spec",
]
