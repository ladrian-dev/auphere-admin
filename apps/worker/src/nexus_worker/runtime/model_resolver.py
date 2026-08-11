"""Resolución de modelo por tenant y rol (WP-19, plataforma v2).

Hasta aquí el modelo se fijaba con variables de entorno **globales**
(``llm_classify_model`` / ``llm_respond_model``) y el fallback a pelo en
``bootstrap.py``. Ponerle un modelo más rápido a un cliente sensible a
latencia obligaba a un redeploy que afectaba a todos los demás.

Cómo encaja:

- Se lee **dentro de la sesión ya scopeada del ``AgentLoader``**, no en una
  propia. Eso no es comodidad: ``tenant_model_bindings`` lleva RLS forzada
  y leerla ahí hace que el aislamiento lo imponga Postgres, no un WHERE
  que alguien pueda olvidar. Un tenant sin fila simplemente no ve ninguna.
- Sin binding, el rol cae a la configuración global. Migrar a esta tabla
  es por tanto opt-in por cliente y por rol: una fila cambia un rol de un
  cliente y no toca a nadie más.
- ``fallback_chain`` se guarda como cadenas y no como FKs porque un
  fallback que revienta al resolverse no es un fallback. Se filtran las
  entradas vacías al leer; lo demás se pasa tal cual al router, que ya
  sabe recorrer una cadena con reintentos.
"""

from __future__ import annotations

import decimal
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ModelBinding:
    """Lo que un tenant eligió para un rol."""

    role: str
    model_id: str
    # Modelos a los que caer, en orden, antes del fallback global.
    fallback_chain: tuple[str, ...] = ()
    # Techo de coste por turno. Se lee ya para que el binding esté
    # completo; quien corta es WP-20.
    max_cost_per_turn_usd: decimal.Decimal | None = None

    def chain(self, *, global_fallback: str | None = None) -> tuple[str, ...]:
        """Cadena completa de intentos, sin repetidos y en orden."""
        models = [self.model_id, *self.fallback_chain]
        if global_fallback:
            models.append(global_fallback)
        # ``dict.fromkeys`` deduplica conservando el orden — importa: un
        # modelo repetido en la cadena se reintentaría dos veces y
        # duplicaría la latencia del peor caso sin ganar nada.
        return tuple(dict.fromkeys(m for m in models if m))


_BINDINGS_SQL = sa.text(
    """
    SELECT b.role,
           p.model_id,
           b.fallback_chain,
           b.max_cost_per_turn_usd
      FROM tenant_model_bindings b
      JOIN model_profiles p ON p.id = b.model_profile_id
    """
)


async def load_bindings(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, ModelBinding]:
    """Bindings del tenant activo en la sesión.

    Sin ``WHERE tenant_id``: la sesión ya está scopeada y la RLS de la
    tabla es quien filtra. Añadir el WHERE aquí escondería una RLS rota
    en vez de dejar que un test de aislamiento la cace.
    """
    try:
        rows = (await session.execute(_BINDINGS_SQL)).all()
    except Exception as exc:
        # Un fallo leyendo la elección de modelo no puede tumbar el turno:
        # sin bindings el runtime usa la configuración global, que es
        # exactamente el comportamiento de antes de WP-19.
        log.warning("model_resolver.load_failed", tenant_id=str(tenant_id), error=str(exc))
        return {}

    bindings: dict[str, ModelBinding] = {}
    for role, model_id, fallback_chain, max_cost in rows:
        chain: Sequence[object] = fallback_chain if isinstance(fallback_chain, list) else ()
        bindings[role] = ModelBinding(
            role=role,
            model_id=model_id,
            fallback_chain=tuple(str(m) for m in chain if isinstance(m, str) and m),
            max_cost_per_turn_usd=max_cost,
        )
    return bindings


def chain_for(
    bindings: dict[str, ModelBinding],
    role: str,
    *,
    default_model: str,
    global_fallback: str | None = None,
) -> tuple[str, ...]:
    """Cadena de modelos para un rol, con caída a la configuración global.

    Es el único punto donde se decide entre "lo que eligió el cliente" y
    "lo que dice la variable de entorno", para que no haya dos respuestas
    distintas según por dónde se entre.
    """
    binding = bindings.get(role)
    if binding is None:
        models = [default_model, global_fallback] if global_fallback else [default_model]
        return tuple(dict.fromkeys(m for m in models if m))
    return binding.chain(global_fallback=global_fallback)
