"""El catálogo de herramientas de una sesión — Requisitos 5, 13 y 14.

Aquí vive la regla que T001 verificó a nivel de proceso. Aquel spike demostró que se
puede **contener** lo que el harness hereda de la máquina; esto decide qué se expone,
y las dos mitades tienen que sostenerse a la vez: contener sin decidir deja el
catálogo a merced de la fuente, y decidir sin contener deja que el harness añada por
detrás.

Tres reglas, y las tres fallan hacia el lado seguro:

* **Exhaustivo** (R5.1/5.2): sale exactamente lo que la fuente declara. La fuente es
  el catálogo declarativo de Auphere; nada del ambiente de la máquina entra.
* **Fail-closed** (R5.3): si el catálogo no se puede resolver, la sesión **no abre**.
  Una sesión que arranca sin poder demostrar su catálogo es peor que ninguna sesión.
* **Alcance de red** (R14): con dispositivo presente no conviven herramientas que
  alcanzan la web y la ejecución local. Lo no declarado cuenta como que alcanza — si
  no declarar bastara para evadir la regla, la regla no existiría.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

#: La herramienta de ejecución local. Cuando el alcance de red y ella entran en
#: conflicto, gana ella: es el diferencial entero de esta beta (R14.4).
LOCAL_EXECUTION_TOOL = "shell_local"

#: Capacidades que el sustrato trae de fábrica y nosotros no encendemos (R13).
#:
#: No están aquí para "no listarlas": se **caen** aunque la fuente las traiga, porque
#: la garantía no puede depender de que nadie se equivoque al declarar el catálogo.
#: Encender el navegador junto a la ejecución local es la combinación que §III
#: prohíbe; el canal no oficial va contra los ToS de Meta y tenemos el oficial en
#: producción; y cargar apps concede privilegios completos del proceso del gateway.
DISABLED_CAPABILITIES: frozenset[str] = frozenset(
    {
        "browser",
        "computer_use",
        "whatsapp_unofficial",
        "apps_loader",
    }
)


class CatalogUnavailable(RuntimeError):
    """No se pudo resolver el catálogo. La sesión no abre (R5.3)."""


@dataclass(frozen=True)
class Tool:
    """Una herramienta declarada.

    ``reaches_network`` es ternario a propósito: ``None`` significa *sin declarar*, y
    se trata como si alcanzara la red (R14.2). Un booleano con defecto ``False``
    habría convertido el olvido en permiso.
    """

    name: str
    reaches_network: bool | None = False

    @property
    def treated_as_network(self) -> bool:
        return self.reaches_network is not False


CatalogSource = Callable[[], Sequence[Tool]]


def resolve_catalog(source: CatalogSource, *, device_present: bool) -> list[Tool]:
    """Resuelve el catálogo del turno. Falla cerrado.

    ``device_present`` viene de la presencia derivada del latido, no de una columna:
    si la máquina se fue, la combinación peligrosa deja de existir sola.
    """
    try:
        declared = list(source())
    except CatalogUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — cualquier fallo es "no se puede garantizar"
        raise CatalogUnavailable(
            "no se pudo resolver el catálogo de la sesión; no se abre"
        ) from exc

    # R13: lo apagado se cae aunque la fuente lo traiga.
    resolved = [t for t in declared if t.name not in DISABLED_CAPABILITIES]

    # R14: con dispositivo presente, la ejecución local excluye el alcance de red.
    if device_present:
        resolved = [
            t
            for t in resolved
            if t.name == LOCAL_EXECUTION_TOOL or not t.treated_as_network
        ]

    return resolved


def excluded_for_network_reach(
    source: CatalogSource, *, device_present: bool
) -> list[str]:
    """Qué se retiró por alcance de red, para poder **decirlo como estado** (R14.4).

    Existe para que la interfaz pueda explicar por qué falta una herramienta que el
    partner sí tiene contratada. Sin esto, la exclusión sería silenciosa — y una
    ausencia sin explicación es una pantalla que miente por omisión (§V).
    """
    if not device_present:
        return []
    declared = [t for t in source() if t.name not in DISABLED_CAPABILITIES]
    return [
        t.name for t in declared if t.name != LOCAL_EXECUTION_TOOL and t.treated_as_network
    ]


__all__ = [
    "DISABLED_CAPABILITIES",
    "LOCAL_EXECUTION_TOOL",
    "CatalogSource",
    "CatalogUnavailable",
    "Tool",
    "excluded_for_network_reach",
    "resolve_catalog",
]
