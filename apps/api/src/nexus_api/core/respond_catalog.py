"""Qué modelos se ofrecen, y qué modelos puede ejecutar un hop.

Son dos conjuntos distintos y confundirlos costó un corte:

- ``RESPOND_MODELS`` es la **oferta al partner**: Sol, Terra y Luna. Es lo
  que la consola deja elegir para el rol ``respond``. Tres ids de OpenAI
  verbatim; no existe el alias ``gpt-5.6`` (404 en el vendor, probado el
  2026-09-01).
- ``HOP_MODEL_IDS`` es lo que un hop puede **ejecutar**: todo el catálogo
  activo de ``model_profiles``. Incluye Anthropic, que es con lo que
  producción responde a diario, y ``whisper-1`` y ``gpt-4o``, que sirven
  a visión, transcripción, grader y evals.

Validar el hop contra la oferta —que es lo que hacía este módulo— mata el
turno de cualquier tenant con binding a Anthropic con un
``UnknownCatalogModel`` que **nadie captura**. Demo Farmacia tiene ese
binding en staging y en producción. Tras ADR-036 la verdad de los modelos
es ``model_profiles``, y este conjunto es su espejo en código: el test
guardián falla si divergen.

Un id fuera de ``HOP_MODEL_IDS`` sigue siendo un error humano (409), nunca
un ``acompletion`` a pelo contra el vendor.
"""

from __future__ import annotations

SOL_MODEL_ID = "openai/gpt-5.6-sol"

RESPOND_MODELS: tuple[tuple[str, str], ...] = (
    (SOL_MODEL_ID, "Sol"),
    ("openai/gpt-5.6-terra", "Terra"),
    ("openai/gpt-5.6-luna", "Luna"),
)

RESPOND_MODEL_IDS: tuple[str, ...] = tuple(model_id for model_id, _ in RESPOND_MODELS)
RESPOND_MODEL_ID_SET: frozenset[str] = frozenset(RESPOND_MODEL_IDS)
RESPOND_ROLE: str = "respond"

#: Catálogo de plataforma: todo lo que ``model_profiles`` publica como
#: ``active``. Espejo en código de la tabla — sembrado por las migraciones
#: 0072, 0076 y 0095 — para no consultar la BD en el camino caliente del
#: hop. ``test_respond_catalog`` compara los dos conjuntos y falla si
#: alguien añade una fila y no la añade aquí.
HOP_MODEL_IDS: tuple[str, ...] = (
    *RESPOND_MODEL_IDS,
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-haiku-4-5-20251001",
    "openai/gpt-4o",
    "openai/whisper-1",
)
HOP_MODEL_ID_SET: frozenset[str] = frozenset(HOP_MODEL_IDS)

# Same human phrase the channel uses when a hop cannot complete (QA-14).
HUMAN_TURN_ERROR = "Disculpa, tuve un inconveniente."


class UnknownCatalogModel(ValueError):
    """id fuera del catálogo de plataforma. No llamar a ``acompletion``."""

    def __init__(self, model_id: str) -> None:
        super().__init__(model_id)
        self.model_id = model_id


def require_hop_model(model_id: str) -> str:
    """Rechaza un hop cuyo id no está en el catálogo de plataforma.

    Contra ``HOP_MODEL_IDS``, no contra la oferta: un tenant con binding a
    Anthropic ejecuta un hop perfectamente válido. Lo que la consola deja
    *elegir* es ``RESPOND_MODEL_IDS`` y eso lo comprueba ``console/models``.
    """
    if model_id not in HOP_MODEL_ID_SET:
        raise UnknownCatalogModel(model_id)
    return model_id


def hop_models_in_catalog(*model_ids: str) -> bool:
    """True si todos los ids no vacíos son ejecutables por un hop.

    Contra el catálogo de plataforma, no contra la oferta: quien pregunta
    —el Playground— quiere saber si el turno va a poder correr, y un
    despliegue cuyo modelo global de QA sea Anthropic corre perfectamente.
    """
    return all(model_id in HOP_MODEL_ID_SET for model_id in model_ids if model_id)


__all__ = [
    "HOP_MODEL_IDS",
    "HOP_MODEL_ID_SET",
    "HUMAN_TURN_ERROR",
    "RESPOND_MODELS",
    "RESPOND_MODEL_IDS",
    "RESPOND_MODEL_ID_SET",
    "RESPOND_ROLE",
    "SOL_MODEL_ID",
    "UnknownCatalogModel",
    "hop_models_in_catalog",
    "require_hop_model",
]
