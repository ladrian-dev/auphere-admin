"""Escalado a soporte y consciencia de los límites (CO-08, §4 y §5).

Dos piezas que solo tienen sentido juntas:

- **El documento de capacidades** (:func:`load_capabilities`) — qué existe,
  qué llega, qué no está, qué está fuera de alcance y qué se retiró. Lo
  mantenemos a mano en ``docs/companion/capabilities.yaml``; **no se
  infiere**. Una capacidad inventada es una promesa rota con el cliente de
  un partner.
- **Los dos tickets** (:func:`build_support_proposal`) — lo que el Companion
  ofrece cuando topa con una pared. §25 de la investigación en una frase:

      El Companion nunca cierra una conversación con un "no". La cierra con
      un camino: o lo hace, o abre el camino para que alguien lo haga.

Tres cosas que hacen que esto no sea "una herramienta que manda un correo"
------------------------------------------------------------------------

- **Pasan por el mismo ciclo propose→confirm que cualquier escritura.**
  Se declaran ``propose`` y ``always_ask``; la única ``mutates`` del
  catálogo sigue siendo ``console.apply`` (garantía E4). Nadie manda un
  ticket a nombre del partner sin que el partner lo vea.

- **``checked`` no es texto libre.** Sale de las etiquetas del catálogo de
  herramientas de las lecturas ya hechas en este turno — la misma
  procedencia que sostiene R1. Un ticket sin expediente es exactamente lo
  que §25.1 existe para evitar, así que sin ni una lectura la propuesta se
  **rechaza**: el modelo tiene que mirar antes de escalar.

- **``topic`` y ``sla`` son identificadores estables, no prosa.** ``topic``
  es la clave de agregación del §25.2 (*"siete partners han pedido Shopify
  este trimestre"*); ``sla`` lo decide un mapa cerrado sobre la categoría y
  la familia, nunca el modelo. La interfaz traduce; el backend no emite
  frases para humanos (§1.4 de CONTRACT-V1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml

from nexus_api.companion.tools.errors import ToolError

log = structlog.get_logger(__name__)

# ── el documento de capacidades ────────────────────────────────────────

#: Raíz del repositorio, subiendo desde
#: ``apps/api/src/nexus_api/companion/tools/support.py``. En la imagen de
#: producción la misma cuenta da ``/app``, y el Dockerfile copia el
#: documento a ``/app/docs/companion/``.
_REPO_ROOT = Path(__file__).resolve().parents[6]

CAPABILITIES_PATH = _REPO_ROOT / "docs" / "companion" / "capabilities.yaml"

#: Los cinco estados del §5.2 y lo que cada uno autoriza a decir. El motor
#: usa dos de ellos (ver :func:`_capability_gate`); el resto es contrato con
#: el modelo, que lo lee en la respuesta de la herramienta.
CAPABILITY_STATUSES: frozenset[str] = frozenset(
    {"available", "planned", "absent", "out_of_scope", "retired"}
)

CAPABILITY_FAMILIES: frozenset[str] = frozenset({"connector", "channel", "capability", "platform"})


@dataclass(frozen=True)
class Capability:
    key: str
    family: str
    status: str
    label: str
    #: ``note`` en SINGULAR: ``notes`` y ``reason`` están prohibidos en toda
    #: respuesta de ``/console/*`` (§1.1 de CONTRACT-V1).
    note: str | None
    eta: str | None
    replaced_by: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityDocument:
    version: str
    entries: tuple[Capability, ...]

    def get(self, key: str) -> Capability | None:
        return next((e for e in self.entries if e.key == key), None)


class CapabilitiesUnavailable(RuntimeError):
    """El documento no se pudo leer.

    Se propaga en vez de devolver un documento vacío a propósito: un
    catálogo vacío le diría al Companion que **nada** existe, y entonces
    negaría capacidades que sí tenemos. Fallar ruidosamente es la única
    respuesta honesta.
    """


_cache: CapabilityDocument | None = None


def load_capabilities(*, force: bool = False) -> CapabilityDocument:
    """Lee y valida ``capabilities.yaml``. Cacheado por proceso.

    Sin TTL: el archivo viaja en la imagen y no cambia mientras el proceso
    vive. Cambiarlo es desplegar, que es justo lo que se quiere de un
    documento que promete cosas a un cliente.
    """
    global _cache
    if _cache is not None and not force:
        return _cache
    try:
        raw = yaml.safe_load(CAPABILITIES_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CapabilitiesUnavailable(str(exc)) from exc
    if not isinstance(raw, dict):
        raise CapabilitiesUnavailable("el documento de capacidades no es un mapa")

    version = str(raw.get("version") or "").strip()
    if not version:
        raise CapabilitiesUnavailable("el documento de capacidades no declara 'version'")

    entries: list[Capability] = []
    for item in raw.get("entries") or []:
        if not isinstance(item, dict):
            raise CapabilitiesUnavailable("una entrada de capacidades no es un mapa")
        key = str(item.get("key") or "").strip()
        family = str(item.get("family") or "").strip()
        status = str(item.get("status") or "").strip()
        if not key or family not in CAPABILITY_FAMILIES or status not in CAPABILITY_STATUSES:
            raise CapabilitiesUnavailable(f"entrada de capacidades inválida: {key or item!r}")
        note = item.get("note")
        eta = item.get("eta")
        entries.append(
            Capability(
                key=key,
                family=family,
                status=status,
                label=str(item.get("label") or key),
                note=str(note).strip() if note else None,
                eta=str(eta).strip() if eta else None,
                replaced_by=tuple(str(r) for r in (item.get("replaced_by") or [])),
            )
        )
    keys = [e.key for e in entries]
    if len(keys) != len(set(keys)):
        raise CapabilitiesUnavailable("hay claves repetidas en el documento de capacidades")

    _cache = CapabilityDocument(version=version, entries=tuple(entries))
    return _cache


def reset_capabilities_cache_for_tests() -> None:
    global _cache
    _cache = None


# ── el vocabulario de ``topic`` (§4.2) ─────────────────────────────────
#
# ``topic`` es la clave de agregación. Las FAMILIAS son cerradas; los slugs
# dentro de cada una, no — un `topic` nuevo es un dato, y rechazar un ticket
# por una discusión de taxonomía sería exactamente el "no" que §25 evita.

TOPIC_FAMILIES: tuple[str, ...] = (
    "connector",  # un conector concreto: connector.shopify
    "channel",  # un canal: channel.instagram
    "capability",  # una capacidad de la plataforma: capability.evals_console
    "platform",  # una incidencia nuestra: platform.publish_failed
    "quota",  # un tope alcanzado: quota.clients
    "permission",  # algo que el rol no permite: permission.billing
)

#: Familia de escape. Un ``topic`` que no encaje en ninguna de las seis va
#: aquí en vez de rechazarse: una fila en ``other.*`` es un dato; un ticket
#: no abierto no es nada.
TOPIC_FALLBACK_FAMILY = "other"

_SLUG = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
TOPIC_MAX_LEN = 60


def normalise_topic(raw: str) -> str:
    """``<familia>.<slug>``, con familia cerrada y slug estable.

    Nunca lanza: lo peor que puede pasar es que el ticket acabe en
    ``other.<algo>``, y eso sigue siendo agregable.
    """
    cleaned = re.sub(r"[^a-z0-9._-]+", "_", str(raw or "").strip().lower()).strip("._-")
    family, _, rest = cleaned.partition(".")
    if family in TOPIC_FAMILIES and rest:
        slug = rest.replace(".", "_")
    else:
        family = TOPIC_FALLBACK_FAMILY
        slug = cleaned.replace(".", "_") or "unspecified"
    slug = "_".join(part for part in _SLUG.findall(slug)) or "unspecified"
    return f"{family}.{slug}"[:TOPIC_MAX_LEN].rstrip("._-")


def topic_family(topic: str) -> str:
    return topic.partition(".")[0]


# ── la expectativa de respuesta (§4.4) ─────────────────────────────────

SLA_BUSINESS_HOURS = "business_hours"
SLA_NEXT_BUSINESS_DAY = "next_business_day"
SLA_BEST_EFFORT = "best_effort"

SLAS: frozenset[str] = frozenset({SLA_BUSINESS_HOURS, SLA_NEXT_BUSINESS_DAY, SLA_BEST_EFFORT})

#: Familias donde un ``help`` significa "hay trabajo parado ahora mismo".
_URGENT_FAMILIES: frozenset[str] = frozenset({"platform", "quota", "permission"})


def sla_for(category: str, topic: str) -> str:
    """La expectativa la decide el MOTOR, no el modelo.

    Un plazo redactado por el modelo es una promesa que Auphere no hizo, y
    la interfaz no tendría forma de traducirla. Por eso es un mapa cerrado
    de tres valores.
    """
    if category == "capability":
        # Una petición de hoja de ruta no tiene reloj. Darle uno sería
        # mentir con un formato estable, que es la peor clase de mentira.
        return SLA_BEST_EFFORT
    if topic_family(topic) in _URGENT_FAMILIES:
        return SLA_BUSINESS_HOURS
    return SLA_NEXT_BUSINESS_DAY


# ── la propuesta de ticket (§4.2) ──────────────────────────────────────

CATEGORY_HELP = "help"
CATEGORY_CAPABILITY = "capability"

#: ``kind`` de la acción → categoría del ticket. Espeja el §4.1.
SUPPORT_KINDS: dict[str, str] = {
    "support_help": CATEGORY_HELP,
    "support_capability": CATEGORY_CAPABILITY,
}

#: Tope de entradas del expediente que viajan en el ticket. Las lecturas de
#: un turno están acotadas por ``companion_max_tool_calls_per_turn``; esto
#: es la red de abajo para que la tarjeta siga siendo legible.
CHECKED_MAX = 12

NEED_MAX_CHARS = 1_000
ALTERNATIVE_MAX_CHARS = 1_000


@dataclass(frozen=True)
class SupportTicketDraft:
    """El ticket calculado y no abierto. Es el ``preview`` del §4.2."""

    category: str
    topic: str
    client_ref: str | None
    need: str
    checked: tuple[str, ...]
    alternative: str | None
    bridge: bool
    sla: str

    def as_preview(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "topic": self.topic,
            "client_ref": self.client_ref,
            "need": self.need,
            "checked": list(self.checked),
            "alternative": self.alternative,
            "bridge": self.bridge,
        }

    def as_body(self) -> dict[str, Any]:
        """Lo que se manda a ``POST /console/support/tickets``."""
        return {
            "category": self.category,
            "topic": self.topic,
            "client_ref": self.client_ref,
            "need": self.need,
            "checked": list(self.checked),
            "alternative": self.alternative,
            "bridge": self.bridge,
        }


class SupportRefused(Exception):
    """El ticket no se puede preparar, y el motivo es del modelo."""

    def __init__(self, error: ToolError) -> None:
        super().__init__(error.message)
        self.error = error


def _dedupe(labels: tuple[str, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for label in labels:
        text = str(label).strip()
        if text and text not in seen:
            seen.append(text)
    return tuple(seen[:CHECKED_MAX])


def _capability_gate(category: str, topic: str, document: CapabilityDocument) -> None:
    """Las dos frases del §5.2 que se aplican en el motor.

    Las demás son contrato con el modelo (las lee en la respuesta de
    ``console.get_capabilities``). Estas dos no, porque son las dos que
    producen una promesa rota si el modelo se las salta.
    """
    if category != CATEGORY_CAPABILITY:
        # Una incidencia sobre algo fuera de alcance sigue siendo una
        # incidencia. ``help`` nunca se bloquea.
        return
    entry = document.get(topic)
    if entry is None:
        return
    if entry.status == "out_of_scope":
        raise SupportRefused(
            ToolError(
                "out_of_scope",
                f"{entry.label} está fuera de alcance a propósito, no es un hueco: "
                f"{entry.note or 'es una decisión, no una carencia'}. "
                "Explícaselo con esas palabras y no abras un ticket de capacidad; "
                "si además hay una incidencia concreta, eso sí es support.request_help.",
            )
        )
    if entry.status == "available":
        raise SupportRefused(
            ToolError(
                "already_available",
                f"{entry.label} ya existe en la plataforma. Pedirlo como capacidad "
                "nueva confundiría a soporte. Ayúdale a usarlo, y si algo no le "
                "funciona abre support.request_help en vez de esto.",
            )
        )


def build_support_draft(
    kind: str,
    args: dict[str, Any],
    *,
    checked: tuple[str, ...],
    document: CapabilityDocument,
    client_ref: str | None,
) -> SupportTicketDraft:
    """Valida y compone el ticket. **No escribe nada.**

    ``checked`` son las etiquetas de las lecturas del turno y llegan del
    juego de herramientas, no de un argumento: es lo que hace que el
    expediente sea verificable.
    """
    category = SUPPORT_KINDS.get(kind)
    if category is None:  # pragma: no cover - el catálogo fija los dos
        raise SupportRefused(ToolError("unknown_tool", f"No sé abrir un ticket {kind!r}."))

    need = str(args.get("need") or "").strip()
    if not need:
        raise SupportRefused(
            ToolError(
                "bad_arguments",
                "Falta 'need': una frase con lo que la persona necesita conseguir, "
                "no lo que falla. Soporte tiene que poder leerla sin contexto.",
            )
        )
    if len(need) > NEED_MAX_CHARS:
        need = need[:NEED_MAX_CHARS].rstrip()

    topic = normalise_topic(str(args.get("topic") or ""))
    _capability_gate(category, topic, document)

    entries = _dedupe(checked)
    if not entries:
        # §25.1 entero cabe aquí: un ticket sin expediente es lo que este
        # mecanismo existe para evitar. No es un aviso, es un rechazo.
        raise SupportRefused(
            ToolError(
                "no_evidence",
                "Todavía no has leído nada en este turno, así que el ticket iría "
                "sin expediente y soporte empezaría de cero. Mira primero lo que "
                "haga al caso —el catálogo de conectores, las herramientas del "
                "cliente, el plan del partner, lo que corresponda— y vuelve a "
                "intentarlo. Es la parte que hace útil el escalado.",
            )
        )

    alternative_raw = str(args.get("alternative") or "").strip()
    alternative = alternative_raw[:ALTERNATIVE_MAX_CHARS] or None
    bridge = bool(args.get("bridge"))
    if bridge and not alternative:
        raise SupportRefused(
            ToolError(
                "bad_arguments",
                "Marcaste 'bridge' pero no describiste la solución puente. Un puente "
                "sin explicación no se puede evaluar ni etiquetar: pon en "
                "'alternative' qué camino intermedio propones y cuáles son sus "
                "limitaciones, o quita 'bridge'.",
            )
        )

    return SupportTicketDraft(
        category=category,
        topic=topic,
        client_ref=client_ref,
        need=need,
        checked=entries,
        alternative=alternative,
        bridge=bridge,
        sla=sla_for(category, topic),
    )


def ticket_title(draft: SupportTicketDraft) -> str:
    if draft.category == CATEGORY_CAPABILITY:
        return f"Pedir a Auphere la capacidad «{draft.topic}»"
    return f"Abrir un ticket de soporte sobre «{draft.topic}»"


def ticket_impact(draft: SupportTicketDraft) -> list[dict[str, str]]:
    impact = [
        {"key": "sla", "value": draft.sla, "severity": "info"},
        {"key": "checked_items", "value": str(len(draft.checked)), "severity": "info"},
    ]
    if draft.bridge:
        # §25.4: el puente se etiqueta Y el ticket se abre igual. Un puente
        # que nadie registra se convierte en deuda invisible.
        impact.append({"key": "bridge_offered", "value": "true", "severity": "warn"})
    return impact


__all__ = [
    "CAPABILITIES_PATH",
    "CAPABILITY_FAMILIES",
    "CAPABILITY_STATUSES",
    "CATEGORY_CAPABILITY",
    "CATEGORY_HELP",
    "CHECKED_MAX",
    "SLAS",
    "SLA_BEST_EFFORT",
    "SLA_BUSINESS_HOURS",
    "SLA_NEXT_BUSINESS_DAY",
    "SUPPORT_KINDS",
    "TOPIC_FALLBACK_FAMILY",
    "TOPIC_FAMILIES",
    "CapabilitiesUnavailable",
    "Capability",
    "CapabilityDocument",
    "SupportRefused",
    "SupportTicketDraft",
    "build_support_draft",
    "load_capabilities",
    "normalise_topic",
    "reset_capabilities_cache_for_tests",
    "sla_for",
    "ticket_impact",
    "ticket_title",
    "topic_family",
]
