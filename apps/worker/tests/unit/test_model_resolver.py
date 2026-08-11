"""Resolución de la cadena de modelos por rol (WP-19).

La cadena es lo que el router recorre cuando un modelo falla, así que su
forma decide dos cosas a la vez: qué modelo atiende al cliente y cuánto
tarda el peor caso. Se fija aquí porque el fallo típico no revienta —
produce una cadena plausible que reintenta de más, o que se queda sin
red y tumba el turno a la primera caída del proveedor.
"""

from __future__ import annotations

from nexus_worker.runtime.model_resolver import ModelBinding, chain_for

GLOBAL_DEFAULT = "anthropic/claude-sonnet-4-6"
GLOBAL_FALLBACK = "anthropic/claude-haiku-4-5"


def test_without_a_binding_it_falls_back_to_the_global_config() -> None:
    """Migrar a la tabla es opt-in por cliente y por rol: un tenant sin
    fila se comporta exactamente como antes de WP-19."""
    chain = chain_for({}, "respond", default_model=GLOBAL_DEFAULT, global_fallback=GLOBAL_FALLBACK)
    assert chain == (GLOBAL_DEFAULT, GLOBAL_FALLBACK)


def test_a_binding_wins_over_the_global_model() -> None:
    bindings = {"respond": ModelBinding(role="respond", model_id="anthropic/claude-haiku-4-5")}
    chain = chain_for(
        bindings, "respond", default_model=GLOBAL_DEFAULT, global_fallback=GLOBAL_FALLBACK
    )
    # El global deja de aparecer como primario; el fallback global cierra
    # la cadena, pero deduplicado porque aquí coincide con el elegido.
    assert chain == ("anthropic/claude-haiku-4-5",)


def test_the_tenants_own_fallbacks_go_before_the_global_one() -> None:
    """El orden importa: el respaldo que eligió el cliente se intenta
    antes que el genérico de la plataforma."""
    bindings = {
        "respond": ModelBinding(
            role="respond",
            model_id="anthropic/claude-sonnet-4-6",
            fallback_chain=("openai/gpt-4o",),
        )
    }
    chain = chain_for(
        bindings, "respond", default_model="da-igual", global_fallback=GLOBAL_FALLBACK
    )
    assert chain == ("anthropic/claude-sonnet-4-6", "openai/gpt-4o", GLOBAL_FALLBACK)


def test_a_repeated_model_is_not_tried_twice() -> None:
    """Un duplicado en la cadena duplicaría la latencia del peor caso sin
    ganar nada: el mismo modelo ya falló dos veces con reintento."""
    bindings = {
        "respond": ModelBinding(
            role="respond",
            model_id=GLOBAL_FALLBACK,
            fallback_chain=("openai/gpt-4o", GLOBAL_FALLBACK),
        )
    }
    chain = chain_for(bindings, "respond", default_model="x", global_fallback=GLOBAL_FALLBACK)
    assert chain == (GLOBAL_FALLBACK, "openai/gpt-4o")


def test_a_binding_for_one_role_does_not_leak_into_another() -> None:
    """Elegir modelo de ``classify`` no puede cambiar el de ``respond``:
    son decisiones de coste independientes."""
    bindings = {"classify": ModelBinding(role="classify", model_id="anthropic/claude-haiku-4-5")}
    assert chain_for(bindings, "respond", default_model=GLOBAL_DEFAULT, global_fallback=None) == (
        GLOBAL_DEFAULT,
    )


def test_the_chain_never_ends_up_empty() -> None:
    """Sin fallback global configurado la cadena sigue teniendo el
    primario: quedarse sin modelos sería un turno que no se intenta."""
    assert chain_for({}, "respond", default_model=GLOBAL_DEFAULT, global_fallback=None) == (
        GLOBAL_DEFAULT,
    )
