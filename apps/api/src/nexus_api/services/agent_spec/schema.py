"""El AgentSpec v1 — spec 047, T078 (requisito 16.1; research D4).

El documento tipado de una versión de agente, igual campo a campo que
``specs/047-la-fabrica-de-agentes/contracts/agent-spec.schema.json`` (la prueba
de contrato lo compara). De él sale el prompt (``compiler.py``) y sobre él se
proponen y validan los cambios (``validator.py``).

- ``extra="forbid"`` en todos los niveles: una clave de plataforma no cabe
  (requisito 15.4).
- Dos modos. «instructions» guarda el prompt de un agente de antes, byte a byte,
  en ``instructions.legacy_text``; «structured» es el de los agentes nuevos.
- Los límites van **dentro** del tipo (``Annotated``), como en el ClientSpec:
  puestos en el ``Field`` de un campo opcional, Pydantic no los aplica a la unión.
"""

from __future__ import annotations

from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

SCHEMA_VERSION: Final = "1"
#: Lo que suman las secciones de un agente «structured» (requisito 16.1).
MAX_INSTRUCTIONS_CHARS: Final = 8000

TOOL_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
_UUID: dict[str, Any] = {"format": "uuid"}
_UNIQUE: dict[str, Any] = {"uniqueItems": True}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _unique(values: list[Any] | None) -> list[Any] | None:
    if values is not None and len(values) != len({repr(v) for v in values}):
        raise ValueError("items must be unique")
    return values


ToolName = Annotated[str, Field(pattern=TOOL_NAME_PATTERN)]
_Uuid = Annotated[str, Field(json_schema_extra=_UUID)]
_Integration = Annotated[str, Field(pattern=r"^[a-z0-9_]{1,40}$")]
_Language = Annotated[str, Field(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
_Phone = Annotated[str, Field(pattern=r"^\+[1-9][0-9]{6,14}$")]


class Identity(_Strict):
    name: str = Field(min_length=1, max_length=40)
    #: «¿Qué tiene que hacer?». Dato no confiable para el constructor (§III).
    description: str = Field(min_length=20, max_length=1024)
    goal: Annotated[str, Field(max_length=500)] | SkipJsonSchema[None] = None


class Voice(_Strict):
    # ``register`` sombrearía ``BaseModel.register`` (ABC): el campo va con alias.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    tone: Annotated[str, Field(max_length=200)] | SkipJsonSchema[None] = None
    languages: (
        Annotated[list[_Language], Field(min_length=1, max_length=5, json_schema_extra=_UNIQUE)]
        | SkipJsonSchema[None]
    ) = None
    register_: Literal["tu", "usted", "vos"] | SkipJsonSchema[None] = Field(
        default=None, alias="register"
    )
    greeting: Annotated[str, Field(max_length=300)] | SkipJsonSchema[None] = None

    _languages_unique = field_validator("languages")(_unique)


class Section(_Strict):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=8000)


class Instructions(_Strict):
    sections: Annotated[list[Section], Field(max_length=20)] | SkipJsonSchema[None] = None
    legacy_text: str | SkipJsonSchema[None] = None


class Procedure(_Strict):
    id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    title: str = Field(min_length=1, max_length=80)
    when: str = Field(min_length=1, max_length=300)
    steps: str = Field(min_length=1, max_length=2000)
    tools: (
        Annotated[list[ToolName], Field(max_length=10, json_schema_extra=_UNIQUE)]
        | SkipJsonSchema[None]
    ) = None

    _tools_unique = field_validator("tools")(_unique)


class Faq(_Strict):
    q: str = Field(min_length=1, max_length=300)
    a: str = Field(min_length=1, max_length=2000)


class Services(_Strict):
    mode: Literal["all", "list"]
    service_ids: (
        Annotated[list[_Uuid], Field(max_length=200, json_schema_extra=_UNIQUE)]
        | SkipJsonSchema[None]
    ) = None
    #: Preguntas frecuentes propias del agente (capa del agente, garantía 9).
    faqs: Annotated[list[Faq], Field(max_length=100)] | SkipJsonSchema[None] = None

    _ids_unique = field_validator("service_ids")(_unique)


class Skill(_Strict):
    key: str = Field(pattern=r"^[a-z0-9_.]{1,60}$")
    enabled: bool
    integration: _Integration | None = None
    fallback: Annotated[str, Field(max_length=300)] | SkipJsonSchema[None] = None


class ConnectionRequest(_Strict):
    integration: _Integration
    reason: str = Field(max_length=200)


Trigger = Literal[
    "asks_for_human", "failed_attempts", "complaint", "payment_issue", "emergency", "out_of_scope"
]


class CustomTrigger(_Strict):
    custom: str = Field(min_length=1, max_length=300)


class Escalation(_Strict):
    triggers: (
        Annotated[list[Trigger | CustomTrigger], Field(max_length=20, json_schema_extra=_UNIQUE)]
        | SkipJsonSchema[None]
    ) = None
    failed_attempts: int = Field(default=2, ge=1, le=5)
    message: Annotated[str, Field(max_length=500)] | SkipJsonSchema[None] = None

    _triggers_unique = field_validator("triggers")(_unique)


class TeamMember(_Strict):
    phone_e164: _Phone
    level: Literal["full", "readonly"]
    label: Annotated[str, Field(max_length=60)] | SkipJsonSchema[None] = None


class AiDisclosure(_Strict):
    """Lo decide una persona (requisito 16.6)."""

    decided: bool
    mode: Literal["first_message", "on_ask"] | SkipJsonSchema[None] = None
    text: Annotated[str, Field(max_length=200)] | SkipJsonSchema[None] = None


class ProfilePolicy(_Strict):
    kind: Literal["profile"]
    profile: Literal["auto", "economy", "balanced", "max"]


class PinnedPolicy(_Strict):
    kind: Literal["pinned"]
    deployment: str = Field(pattern=r"^[a-z0-9][a-z0-9._:/-]{2,120}$")


class Memory(_Strict):
    scope: Literal["shared", "own"]


class ReceptionTarget(_Strict):
    agent_id: _Uuid
    when: str = Field(min_length=1, max_length=300)


class Reception(_Strict):
    enabled: bool
    targets: Annotated[list[ReceptionTarget], Field(max_length=10)] | SkipJsonSchema[None] = None


class TestSuiteRef(_Strict):
    suite_id: _Uuid
    revision: int = Field(ge=1)


def _modes(schema: dict[str, Any]) -> None:
    schema["allOf"] = [
        {
            "if": {"properties": {"mode": {"const": "structured"}}},
            "then": {"required": ["voice", "instructions", "services", "tools", "escalation"]},
        },
        {
            "if": {"properties": {"mode": {"const": "instructions"}}},
            "then": {
                "required": ["instructions"],
                "properties": {"instructions": {"required": ["legacy_text"]}},
            },
        },
    ]


class AgentSpec(_Strict):
    """AgentSpec v1 (``agent-spec.schema.json``)."""

    model_config = ConfigDict(extra="forbid", json_schema_extra=_modes)

    schema_version: Literal["1"]
    mode: Literal["instructions", "structured"]
    identity: Identity
    voice: Voice | SkipJsonSchema[None] = None
    instructions: Instructions | SkipJsonSchema[None] = None
    procedures: Annotated[list[Procedure], Field(max_length=30)] | SkipJsonSchema[None] = None
    services: Services | SkipJsonSchema[None] = None
    skills: Annotated[list[Skill], Field(max_length=30)] | SkipJsonSchema[None] = None
    tools: (
        Annotated[list[ToolName], Field(max_length=60, json_schema_extra=_UNIQUE)]
        | SkipJsonSchema[None]
    ) = None
    connection_requests: (
        Annotated[list[ConnectionRequest], Field(max_length=10)] | SkipJsonSchema[None]
    ) = None
    escalation: Escalation | SkipJsonSchema[None] = None
    rules: (
        Annotated[list[Annotated[str, Field(min_length=1, max_length=300)]], Field(max_length=30)]
        | SkipJsonSchema[None]
    ) = None
    team_access: Annotated[list[TeamMember], Field(max_length=50)] | SkipJsonSchema[None] = None
    ai_disclosure: AiDisclosure
    model_policy: ProfilePolicy | PinnedPolicy
    memory: Memory
    reception: Reception | SkipJsonSchema[None] = None
    test_suite: TestSuiteRef | SkipJsonSchema[None] = None

    _tools_unique = field_validator("tools")(_unique)

    @model_validator(mode="after")
    def _the_mode_has_what_it_needs(self) -> AgentSpec:
        if self.mode == "structured":
            missing = [
                name
                for name in ("voice", "instructions", "services", "tools", "escalation")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError("a structured spec needs " + ", ".join(missing))
        elif self.instructions is None or self.instructions.legacy_text is None:
            raise ValueError("an instructions spec needs instructions.legacy_text")
        return self

    # ── lecturas cómodas ────────────────────────────────────────────────────

    def instructions_chars(self) -> int:
        if self.instructions is None or self.instructions.sections is None:
            return 0
        return sum(len(s.body) for s in self.instructions.sections)

    def all_tools(self) -> list[str]:
        """Las herramientas de la versión (la lista blanca) más las que citan los
        procedimientos, en orden y sin repetir."""
        seen: dict[str, None] = dict.fromkeys(self.tools or [])
        for proc in self.procedures or []:
            seen.update(dict.fromkeys(proc.tools or []))
        return list(seen)


def dump(spec: AgentSpec) -> dict[str, Any]:
    """El documento como se guarda en ``agent_configs.spec``: sin los opcionales
    vacíos y con ``from`` y demás alias tal cual."""
    return spec.model_dump(mode="json", exclude_none=True, by_alias=True)


__all__ = [
    "MAX_INSTRUCTIONS_CHARS",
    "SCHEMA_VERSION",
    "TOOL_NAME_PATTERN",
    "AgentSpec",
    "AiDisclosure",
    "ConnectionRequest",
    "CustomTrigger",
    "Escalation",
    "Faq",
    "Identity",
    "Instructions",
    "Memory",
    "PinnedPolicy",
    "Procedure",
    "ProfilePolicy",
    "Reception",
    "ReceptionTarget",
    "Section",
    "Services",
    "Skill",
    "TeamMember",
    "TestSuiteRef",
    "ToolName",
    "Voice",
    "dump",
]
