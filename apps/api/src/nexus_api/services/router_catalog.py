"""El catálogo de despliegues, los perfiles y el filtro duro del router.

Spec 047, ola 6 (T140, requisitos 39.3, 40.1, 40.2, 41.1 y 41.2). Una fila de
``model_profiles`` es un **despliegue** (ADR-036): un modelo en un proveedor y
una ruta. Este módulo es la **lectura tipada** de ese catálogo y de lo que lo
rodea (precios con vigencia, taxonomía, perfiles, certificaciones por clase), la
**puerta de activación** y el **filtro duro**, que también usa la consola para
«Fijar un modelo» (39.7). La elección —calidad, orden, cadena, afinidad— vive en
el worker (``nexus_worker.runtime.model_resolver.chain_for``), que es el único
punto de decisión (research D20).

Tres reglas que explican la forma del código:

- **Nada de modelos ni de perfiles en el código** (39.3). Aquí hay tipos y
  vocabularios cerrados (estados, residencias, modos de caché), no despliegues.
  Las cifras de cada perfil son datos de ``router_profiles``. Los únicos números
  fijos son los techos del requisito 40.10 (12 llamadas por turno, 3 escalados
  por hora): un perfil puede bajarlos, no subirlos.
- **Una capacidad que nadie declaró es una que no se tiene.** Las filas de antes
  de la 0180 traen ``capabilities = {}``; lo que ya se sabía de ellas (las
  columnas ``supports_tools``, ``supports_vision``, ``max_context`` y
  ``cache_min_tokens``) se conserva, y lo demás queda en su valor seguro.
- **Una fila mal escrita no tumba el router**: se registra y se salta.
"""

from __future__ import annotations

import fnmatch
import math
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, ClassVar

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models.router import ANOMALY_KINDS, DEPLOYMENT_STATUSES, RESIDENCIES

log = structlog.get_logger(__name__)

# ── vocabularios cerrados ──────────────────────────────────────────────────

CACHE_MODES: tuple[str, ...] = ("explicit", "implicit", "none")
#: ``effort`` = ``reasoning_effort``; ``budget`` = presupuesto de pensamiento.
REASONING_CONTROLS: tuple[str, ...] = ("none", "effort", "budget")
REASONING_LEVELS: tuple[str, ...] = ("none", "low", "medium", "high")
TOOL_NAME_CHARSETS: tuple[str, ...] = ("dotted_ok", "no_dots")
#: La gama: «modelos básicos o medios» (historia 12) y el máximo.
TIERS: tuple[str, ...] = ("basic", "medium", "top")

#: Techos del requisito 40.10. Un perfil puede bajarlos, nunca subirlos.
MAX_CALLS_PER_TURN = 12
MAX_ESCALATIONS_PER_HOUR = 3

#: Los estados en los que un despliegue atiende. ``retiring`` sigue atendiendo
#: hasta su ``retire_after`` (41.7): en la fecha, el cron del ciclo de vida lo
#: pasa a ``retired`` y mueve a los agentes fijados en él; hasta entonces ni los
#: fijados ni las conversaciones con afinidad notan nada.
SERVABLE_STATUSES: tuple[str, ...] = ("active", "retiring")


class MissingTask(ValueError):
    """Una llamada a un modelo sin tarea (requisito 40.1)."""


class UnknownTask(ValueError):
    """Una tarea que no está en la taxonomía vigente."""


class NoPolicy(LookupError):
    """El perfil no fija política para esa tarea."""


# ── capacidades ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Capabilities:
    """Lo que sabe hacer un despliegue (``router-and-catalog.md`` §2).

    Las claves del contrato van siempre en :meth:`to_contract`; las demás
    (``structured_outputs``, ``embeddings``, ``rerank`` —necesidades de la
    taxonomía— y las del router: ``tier``, ``quantization``, ``cache_key``,
    ``cache_ttl_s``, ``provider_jurisdiction``, ``cooldown_s``) solo cuando se
    declaran, para que una fila del contrato vuelva igual que entró.
    """

    tools: bool = False
    parallel_tools: bool = False
    strict_structured_outputs: bool = False
    structured_outputs: bool = False
    vision: bool = False
    audio: bool = False
    embeddings: bool = False
    rerank: bool = False
    cache_mode: str = "none"
    cache_min_tokens: int | None = None
    #: El proveedor acepta una clave de caché (``prompt_cache_key``).
    cache_key: bool = False
    #: Cuánto vive la caché del proveedor; la afinidad dura al menos esto.
    cache_ttl_s: int | None = None
    context_management: bool = False
    reasoning_control: str = "none"
    tool_name_charset: str = "dotted_ok"
    context_window: int | None = None
    max_output: int | None = None
    tier: str | None = None
    #: Caduca la certificación por clase si cambia (research D23).
    quantization: str | None = None
    #: ``eu`` si el proveedor es europeo: la restricción soberana lo exige.
    provider_jurisdiction: str | None = None
    #: Cuánto se enfría el despliegue tras un fallo del proveedor (40.6).
    cooldown_s: int = 60

    CONTRACT_KEYS: ClassVar[tuple[str, ...]] = (
        "tools",
        "parallel_tools",
        "strict_structured_outputs",
        "vision",
        "audio",
        "cache_mode",
        "cache_min_tokens",
        "context_management",
        "reasoning_control",
        "tool_name_charset",
        "context_window",
        "max_output",
    )

    def __post_init__(self) -> None:
        for name, allowed in (
            ("cache_mode", CACHE_MODES),
            ("reasoning_control", REASONING_CONTROLS),
            ("tool_name_charset", TOOL_NAME_CHARSETS),
        ):
            if getattr(self, name) not in allowed:
                raise ValueError(f"{name}={getattr(self, name)!r} fuera de {allowed}")
        if self.tier is not None and self.tier not in TIERS:
            raise ValueError(f"tier={self.tier!r} fuera de {TIERS}")

    @classmethod
    def from_json(
        cls, data: Mapping[str, Any] | None, *, defaults: Mapping[str, Any] | None = None
    ) -> Capabilities:
        """Las claves desconocidas se ignoran: una capacidad nueva en los datos
        no puede tumbar a un lector viejo."""
        merged = {**(defaults or {}), **(data or {})}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in merged.items() if k in known and v is not None})

    def satisfies(self, need: str, *, min_context: int | None = None) -> bool:
        """¿Cubre lo que pide la tarea? Una necesidad desconocida no se cubre."""
        if need == "structured_outputs":
            return self.structured_outputs or self.strict_structured_outputs
        if need == "reasoning_control":
            return self.reasoning_control != "none"
        if need == "context_window":
            return min_context is None or (self.context_window or 0) >= min_context
        if need == "other_family":
            # Lo comprueba ``hard_filter`` con la familia juzgada.
            return True
        if need in {
            "tools",
            "strict_structured_outputs",
            "vision",
            "audio",
            "embeddings",
            "rerank",
        }:
            return bool(getattr(self, need))
        return False

    def to_contract(self) -> dict[str, Any]:
        out = {k: getattr(self, k) for k in self.CONTRACT_KEYS}
        defaults = Capabilities()
        for f in fields(self):
            if f.name not in out and getattr(self, f.name) != getattr(defaults, f.name):
                out[f.name] = getattr(self, f.name)
        return out


# ── precios ────────────────────────────────────────────────────────────────


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _num(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


@dataclass(frozen=True)
class Price:
    """Un precio con su vigencia (``model_prices``). Por millón de tokens, salvo
    ``audio_minute`` e ``image``, que son por unidad."""

    valid_from: date
    input: Decimal | None = None
    cache_read: Decimal | None = None
    cache_write: Decimal | None = None
    output: Decimal | None = None
    audio_minute: Decimal | None = None
    image: Decimal | None = None
    #: ``{"above_tokens", "multiplier", "applies_to": "whole_request"}``.
    surcharge: Mapping[str, Any] | None = None
    source_url: str | None = None
    currency: str = "USD"
    unit: str = "per_million_tokens"

    @classmethod
    def from_contract(cls, data: Mapping[str, Any]) -> Price:
        return cls(
            valid_from=date.fromisoformat(str(data["valid_from"])),
            input=_dec(data.get("input")),
            cache_read=_dec(data.get("cache_read")),
            cache_write=_dec(data.get("cache_write")),
            output=_dec(data.get("output")),
            audio_minute=_dec(data.get("audio_minute")),
            image=_dec(data.get("image")),
            surcharge=data.get("long_context_surcharge"),
            source_url=data.get("source"),
            currency=str(data.get("currency") or "USD"),
            unit=str(data.get("unit") or "per_million_tokens"),
        )

    def to_contract(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "valid_from": self.valid_from.isoformat(),
            "source": self.source_url,
            "currency": self.currency,
            "unit": self.unit,
            "input": _num(self.input),
            "cache_read": _num(self.cache_read),
            "cache_write": _num(self.cache_write),
            "output": _num(self.output),
        }
        if self.surcharge is not None:
            out["long_context_surcharge"] = dict(self.surcharge)
        if self.audio_minute is not None:
            out["audio_minute"] = _num(self.audio_minute)
        if self.image is not None:
            out["image"] = _num(self.image)
        return out


@dataclass(frozen=True)
class TokenEstimate:
    """Lo que se espera que gaste una llamada, para ordenar y para el techo."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


#: Para ordenar cuando quien pregunta no sabe cuánto ocupará la llamada: el
#: prompt domina el turno (sistema, historial y herramientas se reenvían enteros)
#: y la respuesta son un par de frases. Solo ordena; el techo por llamada no se
#: comprueba contra esto.
NOMINAL_ESTIMATE = TokenEstimate(input_tokens=1_000, output_tokens=100)


def estimate_cost_micros(price: Price, estimate: TokenEstimate) -> int | None:
    """Coste de la llamada en micro-USD, con el recargo por longitud.

    ``tokens por USD el millón`` ya son micro-USD. None si falta una tarifa que
    la llamada necesita: un coste desconocido no es un coste cero.
    """
    if price.input is None:
        return None
    if estimate.output_tokens and price.output is None:
        return None
    cache_read = price.cache_read if price.cache_read is not None else price.input
    cache_write = price.cache_write if price.cache_write is not None else price.input
    micros = (
        Decimal(estimate.input_tokens) * price.input
        + Decimal(estimate.output_tokens) * (price.output or Decimal(0))
        + Decimal(estimate.cache_read_tokens) * cache_read
        + Decimal(estimate.cache_write_tokens) * cache_write
    )
    surcharge = price.surcharge or {}
    if surcharge.get("applies_to", "whole_request") == "whole_request" and surcharge:
        prompt = estimate.input_tokens + estimate.cache_read_tokens + estimate.cache_write_tokens
        if prompt > int(surcharge.get("above_tokens") or 0):
            micros *= Decimal(str(surcharge.get("multiplier") or 1))
    return math.ceil(micros)


# ── despliegues ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Deployment:
    """Una fila del catálogo. ``key`` es el ``model_id`` de LiteLLM verbatim:
    la misma cadena que va a ``usage_records.model`` y que el AgentSpec guarda
    en ``model_policy.deployment``."""

    key: str
    model: str
    provider: str
    family: str | None = None
    route: str | None = None
    region: str | None = None
    residency: str = "global"
    zero_retention: bool = False
    retention_how: str | None = None
    license_id: str | None = None
    license_url: str | None = None
    license_read_at: datetime | None = None
    contract_dpa: bool = False
    subprocessor_listed: bool = False
    status: str = "draft"
    retire_after: datetime | None = None
    quota: Mapping[str, Any] = field(default_factory=dict)
    capabilities: Capabilities = field(default_factory=Capabilities)
    prices: tuple[Price, ...] = ()
    w_in: Decimal | None = None
    w_cache: Decimal | None = None
    w_out: Decimal | None = None
    id: uuid.UUID | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        if self.status not in DEPLOYMENT_STATUSES:
            raise ValueError(f"status={self.status!r} fuera de {DEPLOYMENT_STATUSES}")
        if self.residency not in RESIDENCIES:
            raise ValueError(f"residency={self.residency!r} fuera de {RESIDENCIES}")

    @property
    def weighted(self) -> bool:
        """Los tres pesos del medidor, o ninguno (spec 007)."""
        return None not in (self.w_in, self.w_cache, self.w_out)

    def price_on(self, day: date) -> Price | None:
        """El de mayor ``valid_from`` que ya está en vigor ese día."""
        valid = [p for p in self.prices if p.valid_from <= day]
        return max(valid, key=lambda p: p.valid_from) if valid else None

    def current_price(self, today: date | None = None) -> Price | None:
        return self.price_on(today or datetime.now(UTC).date())

    @classmethod
    def from_contract(cls, data: Mapping[str, Any]) -> Deployment:
        retention = data.get("retention") or {}
        contract = data.get("contract") or {}
        license_ = data.get("license") or {}
        weights = data.get("meter_weights") or {}
        return cls(
            key=str(data["id"]),
            model=str(data.get("model") or data["id"]),
            provider=str(data["provider"]),
            family=data.get("family"),
            route=data.get("route"),
            region=data.get("region"),
            residency=str(data.get("residency") or "global"),
            zero_retention=bool(retention.get("zero")),
            retention_how=retention.get("how"),
            license_id=license_.get("id"),
            license_url=license_.get("url"),
            license_read_at=_when(license_.get("read_at")),
            contract_dpa=bool(contract.get("dpa")),
            subprocessor_listed=bool(contract.get("subprocessor_listed")),
            status=str(data.get("status") or "draft"),
            retire_after=_when(data.get("retire_after")),
            quota=dict(data.get("quota") or {}),
            capabilities=Capabilities.from_json(data.get("capabilities")),
            prices=tuple(Price.from_contract(p) for p in data.get("prices") or ()),
            w_in=_dec(weights.get("w_in")),
            w_cache=_dec(weights.get("w_cache")),
            w_out=_dec(weights.get("w_out")),
        )

    def to_contract(self) -> dict[str, Any]:
        """La forma de ``router-and-catalog.md`` §2 (lo que verá el admin)."""
        return {
            "id": self.key,
            "model": self.model,
            "family": self.family,
            "provider": self.provider,
            "route": self.route,
            "region": self.region,
            "residency": self.residency,
            "retention": {"zero": self.zero_retention, "how": self.retention_how},
            "license": (
                None
                if self.license_id is None
                else {
                    "id": self.license_id,
                    "url": self.license_url,
                    "read_at": _iso(self.license_read_at),
                }
            ),
            "contract": {
                "dpa": self.contract_dpa,
                "subprocessor_listed": self.subprocessor_listed,
            },
            "status": self.status,
            "retire_after": _iso(self.retire_after),
            "quota": {
                "tpm": self.quota.get("tpm"),
                "rpm": self.quota.get("rpm"),
                "verified_at": self.quota.get("verified_at"),
            },
            "capabilities": self.capabilities.to_contract(),
            "prices": [p.to_contract() for p in sorted(self.prices, key=lambda p: p.valid_from)],
            "meter_weights": {
                "w_in": _num(self.w_in),
                "w_cache": _num(self.w_cache),
                "w_out": _num(self.w_out),
            },
        }


def _when(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def deployment_from_row(row: Mapping[str, Any], *, prices: Iterable[Price]) -> Deployment:
    """Una fila de ``model_profiles`` (0180) con sus precios."""
    key = str(row["model_id"])
    legacy = {
        "tools": row.get("supports_tools"),
        "vision": row.get("supports_vision"),
        "context_window": row.get("max_context"),
        "cache_min_tokens": row.get("cache_min_tokens"),
    }
    capabilities_json = row.get("capabilities") or {}
    model = str(capabilities_json.get("model") or key.rsplit("/", 1)[-1])
    return Deployment(
        id=row.get("id"),
        key=key,
        model=model,
        display_name=row.get("display_name"),
        provider=str(row["provider"]),
        family=row.get("family"),
        route=row.get("route"),
        region=row.get("region"),
        residency=str(row.get("residency") or "global"),
        zero_retention=bool(row.get("zero_retention")),
        retention_how=row.get("retention_how"),
        license_id=row.get("license_id"),
        license_url=row.get("license_url"),
        license_read_at=row.get("license_read_at"),
        contract_dpa=bool(row.get("contract_dpa")),
        subprocessor_listed=bool(row.get("subprocessor_listed")),
        status=str(row.get("status") or "draft"),
        retire_after=row.get("retire_after"),
        quota=dict(row.get("quota") or {}),
        capabilities=Capabilities.from_json(capabilities_json, defaults=legacy),
        prices=tuple(prices),
        w_in=_dec(row.get("quota_weight_input")),
        w_cache=_dec(row.get("quota_weight_cache_read")),
        w_out=_dec(row.get("quota_weight_output")),
    )


# ── activación (requisito 41.2) ─────────────────────────────────────────────

#: Licencias excluidas (constitución §VIII, research D21). Patrones sobre el
#: identificador en minúsculas: Llama 4 por su cláusula para empresas de la UE,
#: Qwen3.8-Flash-Next por su cláusula de modelo como servicio y AGPL por el uso
#: en red.
EXCLUDED_LICENSE_PATTERNS: tuple[str, ...] = ("llama-4*", "qwen3.8-flash-next*", "agpl*")

ACTIVATION_MESSAGES: dict[str, str] = {
    "no_zero_retention": (
        "El contrato no garantiza retención cero ni que no se entrene con los datos, "
        "o no dice cómo se fuerza."
    ),
    "subprocessor_not_listed": (
        "El proveedor no está dado de alta como subprocesador en la lista pública de Auphere."
    ),
    "license_unread": "La licencia de los pesos no está leída entera: falta el enlace o la fecha.",
    "license_excluded": (
        "La licencia no permite ofrecer el modelo como servicio (Llama 4, "
        "Qwen3.8-Flash-Next y AGPL están excluidas)."
    ),
    "unweighted": "Faltan los pesos del medidor por carril: sin ellos el medidor rechaza el turno.",
    "no_class_certification": "No tiene certificación por clase en ninguna tarea.",
}


def license_excluded(license_id: str | None) -> bool:
    if not license_id:
        return False
    normalized = license_id.strip().lower().replace(" ", "-")
    return any(fnmatch.fnmatch(normalized, p) for p in EXCLUDED_LICENSE_PATTERNS)


def activation_problems(
    deployment: Deployment, *, class_certified_tasks: Iterable[str]
) -> tuple[str, ...]:
    """Todo lo que le falta para activarse, de una vez y en orden estable."""
    problems: list[str] = []
    if not (deployment.zero_retention and deployment.contract_dpa and deployment.retention_how):
        problems.append("no_zero_retention")
    if not deployment.subprocessor_listed:
        problems.append("subprocessor_not_listed")
    if deployment.license_id is not None:
        if license_excluded(deployment.license_id):
            problems.append("license_excluded")
        elif not (deployment.license_url and deployment.license_read_at):
            problems.append("license_unread")
    if not deployment.weighted:
        problems.append("unweighted")
    if not any(True for _ in class_certified_tasks):
        problems.append("no_class_certification")
    return tuple(problems)


class ActivationRejected(ValueError):
    def __init__(self, key: str, missing: Sequence[str]) -> None:
        self.key = key
        self.missing = tuple(missing)
        reasons = " ".join(ACTIVATION_MESSAGES[m] for m in self.missing)
        super().__init__(f"{key} no se puede activar. {reasons}")


def require_activatable(deployment: Deployment, *, class_certified_tasks: Iterable[str]) -> None:
    missing = activation_problems(deployment, class_certified_tasks=class_certified_tasks)
    if missing:
        raise ActivationRejected(deployment.key, missing)


# ── taxonomía y perfiles ───────────────────────────────────────────────────


@dataclass(frozen=True)
class TaskSpec:
    code: str
    conversation: bool
    needs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Taxonomy:
    """``router_taxonomy``: una tarea nueva es una versión nueva."""

    version: int
    tasks: Mapping[str, TaskSpec]

    @classmethod
    def from_row(cls, version: int, tasks: Sequence[Mapping[str, Any]]) -> Taxonomy:
        specs = {
            str(t["code"]): TaskSpec(
                code=str(t["code"]),
                conversation=bool(t.get("conversation")),
                needs=tuple(str(n) for n in t.get("needs") or ()),
            )
            for t in tasks
        }
        return cls(version=int(version), tasks=specs)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(self.tasks)

    def require(self, task: str | None) -> TaskSpec:
        if not task:
            raise MissingTask("una llamada a un modelo tiene que llevar su tarea")
        spec = self.tasks.get(task)
        if spec is None:
            raise UnknownTask(f"{task!r} no está en la taxonomía v{self.version}")
        return spec

    def is_conversation(self, task: str) -> bool:
        spec = self.tasks.get(task)
        return bool(spec and spec.conversation)


@dataclass(frozen=True)
class TaskPolicy:
    """La política de una tarea dentro de un perfil (``router-and-catalog.md`` §3)."""

    min_quality: float = 0.0
    max_cost_per_call_micros: int | None = None
    #: Hasta qué gama puede escalar (``TIERS``); None = no escala.
    escalate_to: str | None = None
    reasoning: str = "none"
    #: ``by_risk``, una fracción (0,1) o None.
    judge_sampling: str | float | None = None
    #: El despliegue de reserva cuando nada está certificado (40.8).
    reserve: str | None = None
    latency_p95_ms: int | None = None

    @classmethod
    def from_json(cls, data: Mapping[str, Any], *, latency_p95_ms: int | None) -> TaskPolicy:
        reasoning = str(data.get("reasoning") or "none")
        if reasoning not in REASONING_LEVELS:
            raise ValueError(f"reasoning={reasoning!r} fuera de {REASONING_LEVELS}")
        escalate_to = data.get("escalate_to")
        if escalate_to is not None and escalate_to not in TIERS:
            raise ValueError(f"escalate_to={escalate_to!r} fuera de {TIERS}")
        cost = data.get("max_cost_per_call_micros")
        return cls(
            min_quality=float(data.get("min_quality") or 0.0),
            max_cost_per_call_micros=None if cost is None else int(cost),
            escalate_to=escalate_to,
            reasoning=reasoning,
            judge_sampling=data.get("judge_sampling"),
            reserve=data.get("reserve"),
            latency_p95_ms=latency_p95_ms,
        )


@dataclass(frozen=True)
class ProfilePolicy:
    """Un perfil versionado de ``router_profiles``."""

    profile: str
    version: int
    tasks: Mapping[str, TaskPolicy]
    turn_cost_ceiling_micros: int | None = None
    max_calls_per_turn: int = MAX_CALLS_PER_TURN
    max_escalations_per_hour: int = MAX_ESCALATIONS_PER_HOUR

    @classmethod
    def from_row(cls, profile: str, version: int, policy: Mapping[str, Any]) -> ProfilePolicy:
        latency = policy.get("latency_p95_ms") or {}
        tasks = {
            str(task): TaskPolicy.from_json(data, latency_p95_ms=latency.get(task))
            for task, data in (policy.get("tasks") or {}).items()
        }
        ceiling = policy.get("turn_cost_ceiling_micros")
        calls = int(policy.get("max_calls_per_turn") or MAX_CALLS_PER_TURN)
        escalations = int(policy.get("max_escalations_per_hour") or MAX_ESCALATIONS_PER_HOUR)
        return cls(
            profile=profile,
            version=int(version),
            tasks=tasks,
            turn_cost_ceiling_micros=None if ceiling is None else int(ceiling),
            max_calls_per_turn=min(calls, MAX_CALLS_PER_TURN),
            max_escalations_per_hour=min(escalations, MAX_ESCALATIONS_PER_HOUR),
        )

    def task(self, task: str) -> TaskPolicy | None:
        return self.tasks.get(task)


# ── certificaciones por clase ──────────────────────────────────────────────


@dataclass(frozen=True)
class ClassCertification:
    """``model_task_certifications``: despliegue, tarea y batería."""

    deployment_key: str
    task: str
    battery_version: int
    quality: float
    passed: bool
    scores: Mapping[str, Any]
    certified_at: datetime | None
    invalidated_at: datetime | None

    @property
    def valid(self) -> bool:
        return self.passed and self.invalidated_at is None

    @property
    def latency_p95_ms(self) -> int | None:
        value = self.scores.get("latency_p95_ms")
        if value is None:
            value = (self.scores.get("metrics") or {}).get("latency_p95_ms")
        return None if value is None else int(value)


@dataclass(frozen=True)
class CatalogSnapshot:
    """El catálogo entero en memoria: decenas de filas que cambian casi nunca."""

    taxonomy: Taxonomy
    deployments: Mapping[str, Deployment]
    class_certs: tuple[ClassCertification, ...]
    profiles: Mapping[str, ProfilePolicy]
    #: La batería vigente: una certificación de otra versión ya no cuenta.
    battery_version: int | None

    def class_cert(self, key: str, task: str) -> ClassCertification | None:
        """La certificación vigente más reciente, o None."""
        valid = [
            c
            for c in self.class_certs
            if c.deployment_key == key
            and c.task == task
            and c.valid
            and (self.battery_version is None or c.battery_version == self.battery_version)
        ]
        if not valid:
            return None
        epoch = datetime.min.replace(tzinfo=UTC)
        return max(valid, key=lambda c: c.certified_at or epoch)

    def certified_tasks(self, key: str) -> frozenset[str]:
        return frozenset(c.task for c in self.class_certs if c.deployment_key == key and c.valid)

    def profile(self, name: str) -> ProfilePolicy | None:
        return self.profiles.get(name)


# ── el filtro duro (requisito 40.2.1) ───────────────────────────────────────


@dataclass(frozen=True)
class Rejection:
    """Un candidato descartado y por qué. Va al registro de la decisión."""

    deployment: str
    reason: str

    def as_log(self) -> dict[str, str]:
        return {"deployment": self.deployment, "reason": self.reason}


def hard_reason(
    deployment: Deployment,
    spec: TaskSpec,
    *,
    allowed: AbstractSet[str] | None = None,
    eu_only: bool = False,
    sovereign: bool = False,
    min_context: int | None = None,
    judged_family: str | None = None,
    cooled: AbstractSet[str] = frozenset(),
) -> str | None:
    """Por qué un despliegue no puede hacer esta tarea para este cliente, o None.

    El orden es el de la pregunta que se haría una persona: ¿existe y está
    activo?, ¿se lo dejamos usar a este partner y a este cliente?, ¿sabe hacerlo?,
    ¿corre donde exige el cliente?, ¿no guarda nada?, ¿está caído?
    """
    if deployment.status not in SERVABLE_STATUSES:
        return "status"
    if allowed is not None and deployment.key not in allowed:
        return "not_allowed"
    caps = deployment.capabilities
    for need in spec.needs:
        if not caps.satisfies(need, min_context=min_context):
            return f"capability:{need}"
    if eu_only and deployment.residency != "eu":
        return "residency"
    if not (deployment.zero_retention and deployment.contract_dpa and deployment.retention_how):
        return "retention"
    if not deployment.subprocessor_listed:
        return "subprocessor"
    if sovereign and not (
        deployment.residency == "eu"
        and deployment.license_id is not None
        and caps.provider_jurisdiction == "eu"
    ):
        return "sovereign"
    if "other_family" in spec.needs and judged_family and deployment.family == judged_family:
        return "same_family"
    if deployment.key in cooled:
        return "cooldown"
    return None


def hard_filter(
    deployments: Iterable[Deployment],
    spec: TaskSpec,
    **constraints: Any,
) -> tuple[list[Deployment], list[Rejection]]:
    """Los que pasan y los descartados, en orden de clave (determinista)."""
    kept: list[Deployment] = []
    rejected: list[Rejection] = []
    for deployment in sorted(deployments, key=lambda d: d.key):
        reason = hard_reason(deployment, spec, **constraints)
        if reason is None:
            kept.append(deployment)
        else:
            rejected.append(Rejection(deployment.key, reason))
    return kept, rejected


# ── lectura de la base ─────────────────────────────────────────────────────

_DEPLOYMENTS_SQL = sa.text(
    """
    SELECT id, provider, model_id, display_name, route, region, family, residency,
           zero_retention, retention_how, license_id, license_url, license_read_at,
           contract_dpa, subprocessor_listed, status, retire_after, capabilities, quota,
           supports_tools, supports_vision, max_context, cache_min_tokens,
           quota_weight_input, quota_weight_cache_read, quota_weight_output,
           offer_label, price_input_per_mtok
      FROM model_profiles
    """
)
_PRICES_SQL = sa.text(
    """
    SELECT deployment_id, valid_from, unit, input, cache_read, cache_write, output,
           audio_minute, image, surcharge, source_url, currency
      FROM model_prices
    """
)
_CLASS_CERTS_SQL = sa.text(
    """
    SELECT deployment_id, task, battery_version, scores, quality, passed, certified_at,
           invalidated_at
      FROM model_task_certifications
    """
)
_TAXONOMY_SQL = sa.text("SELECT version, tasks FROM router_taxonomy ORDER BY version DESC LIMIT 1")
_PROFILES_SQL = sa.text(
    "SELECT DISTINCT ON (profile) profile, version, policy FROM router_profiles "
    "ORDER BY profile, version DESC"
)


async def load_snapshot(session: AsyncSession, *, refresh_hop: bool = True) -> CatalogSnapshot:
    """Lee el catálogo de plataforma (sin RLS: es igual para todos).

    Con ``refresh_hop`` también refresca la oferta y el catálogo ejecutable de
    ``core.respond_catalog`` con las mismas filas, para que lo que el router
    elige y lo que el hop acepta salgan de la misma lectura.
    """
    rows = [dict(r) for r in (await session.execute(_DEPLOYMENTS_SQL)).mappings()]
    prices_by: dict[uuid.UUID, list[Price]] = {}
    for p in (await session.execute(_PRICES_SQL)).mappings():
        prices_by.setdefault(p["deployment_id"], []).append(
            Price(
                valid_from=p["valid_from"],
                input=p["input"],
                cache_read=p["cache_read"],
                cache_write=p["cache_write"],
                output=p["output"],
                audio_minute=p["audio_minute"],
                image=p["image"],
                surcharge=p["surcharge"],
                source_url=p["source_url"],
                currency=str(p["currency"]).strip(),
                unit=p["unit"],
            )
        )
    deployments: dict[str, Deployment] = {}
    key_by_id: dict[uuid.UUID, str] = {}
    for row in rows:
        try:
            deployment = deployment_from_row(row, prices=prices_by.get(row["id"], ()))
        except (ValueError, TypeError) as exc:
            log.error("router_catalog.bad_row", model_id=row.get("model_id"), error=str(exc))
            continue
        deployments[deployment.key] = deployment
        key_by_id[row["id"]] = deployment.key

    certs: list[ClassCertification] = []
    for c in (await session.execute(_CLASS_CERTS_SQL)).mappings():
        key = key_by_id.get(c["deployment_id"])
        if key is None:
            continue
        certs.append(
            ClassCertification(
                deployment_key=key,
                task=c["task"],
                battery_version=int(c["battery_version"]),
                quality=float(c["quality"]),
                passed=bool(c["passed"]),
                scores=c["scores"] or {},
                certified_at=c["certified_at"],
                invalidated_at=c["invalidated_at"],
            )
        )
    live = [c.battery_version for c in certs if c.invalidated_at is None]
    battery_version = max(live) if live else None

    taxonomy_row = (await session.execute(_TAXONOMY_SQL)).one_or_none()
    taxonomy = (
        Taxonomy.from_row(taxonomy_row.version, taxonomy_row.tasks)
        if taxonomy_row is not None
        else Taxonomy(version=0, tasks={})
    )
    profiles: dict[str, ProfilePolicy] = {}
    for p in (await session.execute(_PROFILES_SQL)).mappings():
        try:
            profiles[p["profile"]] = ProfilePolicy.from_row(p["profile"], p["version"], p["policy"])
        except (ValueError, TypeError) as exc:
            log.error("router_catalog.bad_profile", profile=p["profile"], error=str(exc))

    if refresh_hop:
        from nexus_api.core import respond_catalog

        respond_catalog.refresh_from_rows(rows)
    return CatalogSnapshot(
        taxonomy=taxonomy,
        deployments=deployments,
        class_certs=tuple(certs),
        profiles=profiles,
        battery_version=battery_version,
    )


# ── la política de modelo del agente (39.1, T145) ──────────────────────────

#: Los perfiles que puede llevar un agente; ``platform`` es de las tareas que no
#: dependen del agente.
AGENT_PROFILES: tuple[str, ...] = ("auto", "economy", "balanced", "max")
#: El perfil cuyas tareas que no son de conversación sigue un agente con «Fijar
#: un modelo» (39.8): las demás tareas siguen la política del router.
PINNED_BASE_PROFILE = "auto"


@dataclass(frozen=True)
class ModelPolicy:
    """La política de modelo de una versión del agente (``model_policy`` del
    AgentSpec, ``contracts/agent-spec.schema.json``).

    **Dónde vive hasta el AgentSpec (bloque D):** en
    ``agent_configs.policies["model_policy"]``, con la misma forma que tendrá en
    el AgentSpec. Va con la versión: se guarda en el borrador, pasa por la
    puerta, se deshace y se restaura como el resto de la versión (39.1). Una
    versión **sin** ``model_policy`` es un agente de hoy: queda fijado en su
    modelo de hoy por el camino de hoy (research D24 y D44, historia 13).
    """

    kind: str
    #: El perfil de las tareas: el elegido, o «Automático» para las que el
    #: modelo fijado no cubre.
    profile: str
    #: Solo con ``kind = pinned``: la clave del despliegue (``model_id``).
    deployment: str | None = None

    def to_policies(self) -> dict[str, str]:
        if self.kind == "pinned":
            return {"kind": "pinned", "deployment": str(self.deployment)}
        return {"kind": "profile", "profile": self.profile}


def model_policy_of(policies: Mapping[str, Any] | None) -> ModelPolicy | None:
    """La política de modelo de ``agent_configs.policies``, o None (un agente
    de hoy). Una política mal escrita se registra y se trata como ausente: el
    agente sigue por el camino de hoy en vez de quedarse sin modelo."""
    raw = (policies or {}).get("model_policy")
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        kind = raw.get("kind")
        if kind == "profile" and raw.get("profile") in AGENT_PROFILES:
            return ModelPolicy(kind="profile", profile=str(raw["profile"]))
        deployment = raw.get("deployment")
        if kind == "pinned" and isinstance(deployment, str) and deployment:
            return ModelPolicy(kind="pinned", profile=PINNED_BASE_PROFILE, deployment=deployment)
    log.warning("router_catalog.bad_model_policy", model_policy=str(raw)[:200])
    return None


# ── con qué política nace un agente (requisito 39.2, T145) ────────────────

#: La política de un agente nuevo cuando «Automático» puede atenderlo. Vive en
#: ``agent_configs.policies["model_policy"]`` con la forma del AgentSpec hasta el
#: bloque D; una versión sin ella es un agente de hoy, fijado en su modelo de hoy.
AUTO_MODEL_POLICY: dict[str, str] = {"kind": "profile", "profile": "auto"}
#: Las tareas de cada turno de un agente.
TURN_TASKS: tuple[str, ...] = ("classify", "answer", "tool_turn")


def auto_servable(
    snapshot: CatalogSnapshot, *, eu_only: bool = False, sovereign: bool = False
) -> bool:
    """¿Atendería «Automático» a un agente que nace hoy, en este cliente?

    Un agente nuevo no tiene certificaciones propias (42.3), así que en las
    tareas de conversación solo le atiende la reserva del perfil (40.8); en
    ``classify``, la reserva o un despliegue certificado por clase con la nota
    del perfil. Todo con el filtro duro del cliente. Con el catálogo de hoy
    (research D44) la respuesta es no, y el agente nace por el camino de hoy:
    la consola no ofrece lo que no puede servir."""
    profile = snapshot.profile("auto")
    if profile is None:
        return False
    for task in TURN_TASKS:
        spec = snapshot.taxonomy.tasks.get(task)
        policy = profile.task(task)
        if spec is None or policy is None:
            return False
        reserve = snapshot.deployments.get(policy.reserve or "")
        if (
            reserve is not None
            and hard_reason(reserve, spec, eu_only=eu_only, sovereign=sovereign) is None
        ):
            continue
        if not spec.conversation and any(
            hard_reason(d, spec, eu_only=eu_only, sovereign=sovereign) is None
            and (cert := snapshot.class_cert(d.key, task)) is not None
            and cert.quality >= policy.min_quality
            for d in snapshot.deployments.values()
        ):
            continue
        return False
    return True


def default_model_policy_for(
    snapshot: CatalogSnapshot, *, eu_only: bool = False, sovereign: bool = False
) -> dict[str, str] | None:
    """«Automático» si puede atender; si no, None (el camino de hoy)."""
    if auto_servable(snapshot, eu_only=eu_only, sovereign=sovereign):
        return dict(AUTO_MODEL_POLICY)
    return None


async def default_model_policy(session: AsyncSession) -> dict[str, str] | None:
    """La política con la que nace un agente del cliente de la sesión. La sesión
    va con el GUC del cliente: su ficha («Solo UE», soberana) la filtra la RLS.
    Si algo no se puede leer, el camino de hoy: un agente que no responde por un
    fallo de lectura es peor que uno que nace como los de hoy."""
    try:
        # Un punto de guardado: una lectura fallida no puede abortar la
        # transacción de quien crea el agente.
        async with session.begin_nested():
            snapshot = await load_snapshot(session, refresh_hop=False)
            row = (
                await session.execute(sa.text("SELECT eu_only, sovereign FROM business_profiles"))
            ).one_or_none()
    except Exception as exc:
        log.warning("router_catalog.default_policy_unreadable", error=str(exc))
        return None
    return default_model_policy_for(
        snapshot,
        eu_only=bool(row.eu_only) if row is not None else False,
        sovereign=bool(row.sovereign) if row is not None else False,
    )


def with_model_policy_default(
    policies: Mapping[str, Any] | None, default: Mapping[str, str] | None
) -> dict[str, Any]:
    """``policies`` con la política por defecto si no trae una. Nunca la pisa."""
    out = dict(policies or {})
    if default is not None and "model_policy" not in out:
        out["model_policy"] = dict(default)
    return out


# ── la configuración del proxy de los proveedores nuevos (T142) ──────────────


def litellm_params_for(deployment: Deployment) -> dict[str, str]:
    """Los ``litellm_params`` con los que se registra el despliegue en el proxy
    LiteLLM (``POST /model/new``, ``model_name`` = ``deployment.key``).

    - **AWS Bedrock** (``aws_bedrock``): el perfil de inferencia ``eu.`` desde
      la región de la fila. **Ninguna clave**: el proxy firma con el rol IAM de
      su tarea de ECS (``bedrock:InvokeModel`` e ``InvokeModelWithResponseStream``
      sobre los perfiles ``eu.`` y sus modelos base en las regiones de la UE).
    - **Scaleway** (``scaleway``): su API compatible con OpenAI. La base y la
      clave salen del entorno del proxy, que las recibe de Secrets Manager
      (``nexus/<entorno>/litellm``: ``SCALEWAY_API_BASE`` y ``SCALEWAY_API_KEY``).
      Ojo: con ``STORE_MODEL_IN_DB`` el proxy guarda el valor al registrar; al
      rotar la clave hay que volver a registrar el modelo.

    La retención cero no va aquí: la pone el transporte en cada petición según
    ``retention_how`` (``llm.RETENTION_WIRE``). Los proveedores directos de hoy
    (Anthropic, OpenAI) ya están registrados y no pasan por aquí."""
    route = deployment.route or deployment.model
    if deployment.provider == "aws_bedrock":
        if not deployment.region:
            raise ValueError(f"{deployment.key}: Bedrock necesita su región")
        return {"model": f"bedrock/{route}", "aws_region_name": deployment.region}
    if deployment.provider == "scaleway":
        return {
            "model": f"openai/{route}",
            "api_base": "os.environ/SCALEWAY_API_BASE",
            "api_key": "os.environ/SCALEWAY_API_KEY",
        }
    raise ValueError(f"{deployment.key}: el proveedor {deployment.provider!r} no se registra aquí")


# ── «desde el siguiente turno» (requisitos 40.13 y 41.9) ───────────────────

#: Lo que el proceso tiene que olvidar cuando el catálogo cambia: el catálogo en
#: memoria del router (``model_resolver.invalidate_catalog`` se apunta al
#: importarse). Los demás procesos lo oyen por el canal de promoción
#: (``CATALOG_CHANGED`` en ``nexus:agent_config:promote``).
_catalog_listeners: list[Callable[[], None]] = []
#: El mensaje del canal de promoción que dice «el catálogo cambió».
CATALOG_CHANGED = "catalog"


def on_catalog_change(callback: Callable[[], None]) -> None:
    if callback not in _catalog_listeners:
        _catalog_listeners.append(callback)


def catalog_changed() -> None:
    """Avisa a este proceso de que el catálogo cambió: el siguiente turno lo lee."""
    for callback in list(_catalog_listeners):
        try:
            callback()
        except Exception as exc:  # pragma: no cover - defensivo
            log.warning("router_catalog.listener_failed", error=str(exc))


async def activate_deployment(session: AsyncSession, key: str) -> Deployment:
    """Pasa un despliegue a ``active`` si cumple el requisito 41.2; si no,
    :class:`ActivationRejected` con todo lo que falta. La auditoría
    (``deployment.activated``) la escribe quien llama, que sabe quién y por qué."""
    snapshot = await load_snapshot(session, refresh_hop=False)
    deployment = snapshot.deployments.get(key)
    if deployment is None:
        raise LookupError(key)
    require_activatable(deployment, class_certified_tasks=snapshot.certified_tasks(key))
    await session.execute(
        sa.text(
            "UPDATE model_profiles SET status = 'active', updated_at = now() WHERE model_id = :k"
        ),
        {"k": key},
    )
    return replace(deployment, status="active")


async def record_anomaly(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    task: str,
    kind: str,
    decision_id: uuid.UUID | None,
) -> None:
    """Lo que Auphere tiene que mirar (``router_anomalies``, por cliente). La
    sesión tiene que estar con el ámbito del cliente: la RLS lo exige."""
    if kind not in ANOMALY_KINDS:
        raise ValueError(f"kind={kind!r} fuera de {ANOMALY_KINDS}")
    await session.execute(
        sa.text(
            "INSERT INTO router_anomalies (tenant_id, task, kind, decision_id) "
            "VALUES (:t, :task, :kind, :d)"
        ),
        {"t": tenant_id, "task": task, "kind": kind, "d": decision_id},
    )


__all__ = [
    "ACTIVATION_MESSAGES",
    "AGENT_PROFILES",
    "AUTO_MODEL_POLICY",
    "CACHE_MODES",
    "CATALOG_CHANGED",
    "EXCLUDED_LICENSE_PATTERNS",
    "MAX_CALLS_PER_TURN",
    "MAX_ESCALATIONS_PER_HOUR",
    "NOMINAL_ESTIMATE",
    "PINNED_BASE_PROFILE",
    "REASONING_CONTROLS",
    "REASONING_LEVELS",
    "SERVABLE_STATUSES",
    "TIERS",
    "TOOL_NAME_CHARSETS",
    "TURN_TASKS",
    "ActivationRejected",
    "Capabilities",
    "CatalogSnapshot",
    "ClassCertification",
    "Deployment",
    "MissingTask",
    "ModelPolicy",
    "NoPolicy",
    "Price",
    "ProfilePolicy",
    "Rejection",
    "TaskPolicy",
    "TaskSpec",
    "Taxonomy",
    "TokenEstimate",
    "UnknownTask",
    "activate_deployment",
    "activation_problems",
    "auto_servable",
    "catalog_changed",
    "default_model_policy",
    "default_model_policy_for",
    "deployment_from_row",
    "estimate_cost_micros",
    "hard_filter",
    "hard_reason",
    "license_excluded",
    "litellm_params_for",
    "load_snapshot",
    "model_policy_of",
    "on_catalog_change",
    "record_anomaly",
    "require_activatable",
    "with_model_policy_default",
]
