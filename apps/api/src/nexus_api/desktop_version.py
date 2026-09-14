"""La versión mínima admisible de la aplicación de escritorio (spec 008, R4).

**La capacidad existe y está apagada**, y ése es el estado del primer
despliegue. Se construye ahora porque después ya habría versiones viejas
instaladas sin forma legible de avisarlas; exigir un mínimo con una sola versión
publicada no protegería de nada y podría cerrarle la puerta a la primera beta.

Tres reglas que vienen de mirar qué hace la industria, no de suponerlo — Slack
depreca dos veces al año con **seis meses** de preaviso y calendario publicado;
Zoom fija un mínimo trimestral con **noventa días** de aviso:

1. **Ausente es válido, y es el defecto.** Sin mínimo declarado no se rechaza
   nada.
2. **Avisar y bloquear son distintos.** Una versión vieja pero admisible sigue
   funcionando. Sólo la que cae por debajo del mínimo se rechaza.
3. **Nunca sin preaviso.** Hay una fecha de entrada en vigor, y antes de ella la
   puerta no cierra aunque el mínimo ya esté declarado. Es lo que convierte el
   preaviso en algo comprobable en vez de en una intención.

Y una cuarta que no es de la industria sino de esta plataforma: **el bloqueo se
reserva a que el contrato del puente se haya roto o a un problema de
seguridad** (R4.7). No es una palanca para empujar mejoras — una máquina
bloqueada es un partner que no puede trabajar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

#: Los únicos motivos que justifican dejar a alguien fuera (R4.7).
BLOCKING_REASONS = frozenset({"contract", "security"})


class MalformedVersion(ValueError):
    """La versión que declara la máquina no se puede comparar."""


@dataclass(frozen=True)
class MinimumVersion:
    """Qué se exige, por qué y desde cuándo.

    ``effective_from`` no es decoración: mientras no llegue, la puerta **no
    cierra**. Poder declarar un mínimo con fecha futura es lo que permite avisar
    antes de rechazar, que es la parte del patrón que más fácil se salta.
    """

    version: str
    reason: str
    effective_from: datetime


def parse_version(raw: str) -> tuple[int, ...]:
    """``"1.2.3"`` → ``(1, 2, 3)``. Levanta si no se puede comparar.

    **No se cae a un valor por defecto.** Una versión ilegible tratada como
    ``(0, 0, 0)`` quedaría siempre por debajo del mínimo y dejaría fuera a una
    máquina por un error de formato nuestro; tratada como infinito, pasaría
    siempre. Las dos son decisiones silenciosas, así que no se toma ninguna:
    quien llame decide qué hacer con el error, y lo que hace el latido es
    **dejar pasar** (ver ``is_blocked``).
    """
    core = raw.strip().split("+", 1)[0].split("-", 1)[0]
    if not core:
        raise MalformedVersion(f"versión vacía: {raw!r}")
    try:
        parts = tuple(int(p) for p in core.split("."))
    except ValueError as exc:
        raise MalformedVersion(f"versión no comparable: {raw!r}") from exc
    if not parts:
        raise MalformedVersion(f"versión vacía: {raw!r}")
    return parts


def _padded(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)), b + (0,) * (width - len(b))


def is_blocked(
    app_version: str | None,
    minimum: MinimumVersion | None,
    *,
    now: datetime | None = None,
) -> bool:
    """¿Se rechaza a esta máquina?

    Cuatro formas de que la respuesta sea **no**, y las cuatro son deliberadas:

    * **No hay mínimo declarado** — el estado del primer despliegue (R4.4).
    * **Todavía no ha entrado en vigor** — el preaviso (R4.5).
    * **La máquina no dice qué versión trae.** Las versiones viejas de la
      aplicación puede que no lo manden; dejarlas fuera por eso sería usar el
      mecanismo contra justo las instalaciones que vino a avisar.
    * **La versión no se puede leer.** Un error de formato nuestro no puede
      dejar a un partner sin trabajar. Falla **abierto**, a diferencia de casi
      todo lo demás en esta plataforma, y por eso está escrito aquí: el riesgo
      de dejar pasar una versión vieja es mucho menor que el de bloquear a
      alguien por un guion mal puesto.
    """
    if minimum is None:
        return False
    moment = now or datetime.now(UTC)
    if moment < minimum.effective_from:
        return False
    if not app_version:
        return False
    try:
        theirs = parse_version(app_version)
        ours = parse_version(minimum.version)
    except MalformedVersion:
        return False
    left, right = _padded(theirs, ours)
    return left < right
