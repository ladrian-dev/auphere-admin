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
  ``connection_requests``, no en ``tools``. Una de ``booking.*`` (spec 048) sale
  como ``tool_retired`` con su sustituta de Reservas en ``replacement``;
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
from nexus_api.services.agent_spec.retired import RETIRED_TOOLS
from nexus_api.services.agent_spec.retired import replacement as retired_replacement
from nexus_api.services.agent_spec.schema import (
    MAX_INSTRUCTIONS_CHARS,
    TOOL_NAME_PATTERN,
    AgentSpec,
)

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
_TOOL_NAME: Final = re.compile(TOOL_NAME_PATTERN)


@dataclass(frozen=True)
class Problem:
    pointer: str
    code: str
    message: str
    #: Spec 048: what to put instead (``tool_retired``), for the console's fix.
    replacement: str | None = None


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
    #: Spec 047, enmienda del 2026-10-29 (62, D62): su integración es un conector
    #: del catálogo, con activación por agente. Solo entonces una herramienta sin
    #: conectar puede quedar «pendiente de conexión»: el turno la retiene hasta que
    #: la conexión exista y esté activada (``activations.tool_policy``). Las que
    #: dependen de otra cosa (el catálogo de Meta del canal) no tienen activación
    #: que las retenga, así que sin conectar siguen sin poder entrar.
    activatable: bool = True
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

    def usable(self, name: str) -> bool:
        """Spec 047, enmienda del 2026-10-30 (65.2): la herramienta está disponible
        para el cliente. Existe en el catálogo, se ofrece, el AgentSpec admite su
        nombre (65.13), no está retirada, y su conector está conectado o tiene
        activación (62.1) y su módulo está encendido."""
        info = self.tools.get(name)
        return (
            info is not None
            and info.status not in {"internal", "deprecated"}
            and info.integration_offered
            and name not in RETIRED_TOOLS
            and _TOOL_NAME.fullmatch(name) is not None
            and (info.connected or (info.integration is not None and info.activatable))
        )

    def available_tools(self) -> list[str]:
        """Las herramientas disponibles para el cliente (65.2), por orden."""
        return sorted(name for name in self.tools if self.usable(name))

    def offered_connectors(self) -> frozenset[str]:
        """Las integraciones que son un conector ofrecido **para un AgentSpec**: con
        activación y con al menos una herramienta disponible. Un conector cuyas
        herramientas el AgentSpec no admite (las de Composio) no lo es: conectarlo
        no le daría nada al agente (65.3 y 65.13)."""
        return frozenset(
            info.integration
            for name, info in self.tools.items()
            if info.integration is not None and info.activatable and self.usable(name)
        )

    def skill_integrations(self) -> frozenset[str]:
        """Lo que una habilidad puede pedir: un conector ofrecido, o algo que no se
        conecta y el cliente ya tiene (el módulo Reservas encendido, el catálogo de
        Meta enlazado)."""
        here = frozenset(
            info.integration
            for name, info in self.tools.items()
            if info.integration is not None and info.connected and self.usable(name)
        )
        return self.offered_connectors() | here


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

    # Las herramientas: catálogo y permitidas (conectadas o pendientes de conexión).
    strict_customer = spec.mode == "structured" or author != "person"
    named: list[tuple[str, str]] = [(f"/tools/{i}", t) for i, t in enumerate(spec.tools or [])]
    for i, proc in enumerate(spec.procedures or []):
        named.extend((f"/procedures/{i}/tools/{j}", t) for j, t in enumerate(proc.tools or []))
    for pointer, name in named:
        # Spec 048 (requisito 2.3): retired by name — the code decides it, so a
        # catalog that has not run 0205 yet does not let it back in.
        instead = retired_replacement(name)
        if instead is not None:
            problems.append(
                Problem(
                    pointer,
                    "tool_retired",
                    f"{name} está retirada: el agente reserva con Reservas. Usa {instead}.",
                    replacement=instead,
                )
            )
            continue
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
        # Spec 047, enmienda del 2026-10-29 (requisito 62.4, D53 y D62): sin conectar
        # no es un problema si su integración es un conector con activación: queda
        # «pendiente de conexión» (la petición va en ``connection_requests``) y el
        # runtime no la ve hasta que la conexión exista y esté activada para el
        # agente (``activations.tool_policy``). Si no lo es, no hay nada que la
        # retenga en el turno: se pide conectar antes.
        if info.integration is not None and not info.connected and not info.activatable:
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

    # Spec 047, enmienda del 2026-10-30 (65.3): una habilidad o una petición de
    # conexión solo nombran lo que existe. Pedir conectar algo que no es un
    # conector ofrecido acabaría en un «Conectar {X}» que no lleva a nada; un
    # módulo (Reservas) o el catálogo de Meta nunca se «conectan» desde el agente.
    if spec.skills or spec.connection_requests:
        skill_ok = ctx.skill_integrations()
        connect_ok = ctx.offered_connectors()
        for i, skill in enumerate(spec.skills or []):
            if skill.integration is not None and skill.integration not in skill_ok:
                problems.append(
                    Problem(
                        f"/skills/{i}/integration",
                        "integration_unknown",
                        f"No tenemos {skill.integration} para este cliente: la habilidad "
                        "no puede depender de ella.",
                    )
                )
        for i, request in enumerate(spec.connection_requests or []):
            if request.integration not in connect_ok:
                problems.append(
                    Problem(
                        f"/connection_requests/{i}/integration",
                        "integration_unknown",
                        f"{request.integration} no es una integración que se pueda conectar.",
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
    rows = await session.execute(
        sa.select(ToolCatalog, Connector.slug, Connector.status).outerjoin(
            Connector, Connector.id == ToolCatalog.connector_id
        )
    )
    from nexus_api.api.console.capabilities_client import tenant_has_catalog
    from nexus_api.api.console.capability_names import RESERVAS_MODULE, requires_module
    from nexus_api.services.reservations.passing import reservas_enabled

    has_catalog = await tenant_has_catalog(session)
    # Spec 047, enmienda del 2026-10-29 (D67): la agenda (``reservas.*``) es del
    # módulo Reservas, que no es un conector ni se conecta desde el agente. Con el
    # módulo apagado para el cliente cuenta como sin conectar y sin activación:
    # ``sanitize`` la quita, la puerta da ``tool_not_connected`` y el constructor la
    # ve «SIN ACTIVAR». En el turno respondería «Reservas no está activo».
    reservas_on = await reservas_enabled(session, tenant_id)
    model_args = _model_visible_args()
    tools: dict[str, ToolInfo] = {}
    for tool, slug, connector_status in rows.tuples().all():
        integration = slug or requires_connector(tool.name, "tool") or requires_module(tool.name)
        # Los argumentos que el modelo puede rellenar son los de la definición
        # que ve (el registro MCP): los que pone el servidor no están ahí.
        props = model_args.get(tool.name)
        if props is None:
            props = frozenset(dict((tool.input_schema or {}).get("properties") or {}))
        connected = (
            integration is None
            or integration in connected_slugs
            or (integration == "channel_catalog" and has_catalog)
            or (integration == RESERVAS_MODULE and reservas_on)
        )
        tools[tool.name] = ToolInfo(
            name=tool.name,
            status=getattr(tool.status, "value", str(tool.status)),
            integration=integration,
            integration_offered=connector_status in (None, "available", "beta"),
            connected=connected,
            activatable=slug is not None,
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
    out: list[dict[str, str]] = []
    for p in problems:
        item = {"pointer": p.pointer, "code": p.code, "message": p.message}
        if p.replacement is not None:
            item["replacement"] = p.replacement
        out.append(item)
    return out


__all__ = [
    "END_CUSTOMER_ARGS",
    "Context",
    "Problem",
    "ToolInfo",
    "load_context",
    "problems_out",
    "validate_spec",
]
