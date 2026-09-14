"""Spec 007 · US2 — el partner no ve un salto en su factura.

El consumo de los clientes finales del partner es el grueso de lo que paga, y es
**pesado en prompt y ligero en salida** — justo el perfil contrario al del
trabajo de teammate. La corrección del margen no puede llegarle como una subida
de precio a quien no tiene la culpa del defecto.

Los pesos viejos se reproducen aquí para poder comparar: son los de la migración
0115, que ya no existen en el código.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pytest

from nexus_api.billing.pricing import CREDIT_USD_PER_MILLION
from nexus_api.metering.quota import quota_tokens
from tests.unit.test_quota_margin import PRICES, lanes_of

#: Los pesos únicos de la 0115, para el antes/después. Están aquí y no en el
#: código porque en el código ya no están: el after no se puede comparar con un
#: before que se borró.
OLD_WEIGHTS = {
    "openai/gpt-5.6-sol": Decimal("1.828"),
    "anthropic/claude-sonnet-4-6": Decimal("1.371"),
    "openai/gpt-4o": Decimal("1.724"),
    "openai/gpt-5.6-terra": Decimal("1.000"),
    "anthropic/claude-haiku-4-5": Decimal("0.457"),
    "openai/gpt-5.6-luna": Decimal("0.100"),
}
OLD_CACHE_WEIGHT = Decimal("0.1")

#: El turno típico de cliente final: mucho prefijo, mucha caché, poca respuesta.
END_CUSTOMER_TURN = (10_000, 8_000, 1_000)


def old_quota(prompt: int, cache: int, out: int, model: str) -> int:
    """La fórmula de la 004: un peso al total, y 0,1 plano a la caché."""
    native = (
        Decimal(prompt - cache)
        + (Decimal(cache) * OLD_CACHE_WEIGHT).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        + Decimal(out)
    )
    return int((native * OLD_WEIGHTS[model]).quantize(Decimal(1), rounding=ROUND_HALF_UP))


#: Cuánto puede moverse el turno de cliente final, hacia arriba, sin que eso sea
#: una subida de precio que haya que anunciar. Dos por ciento: por debajo del
#: ruido de un mes con más o menos tráfico.
MAX_RISE_PCT = Decimal("2")


@pytest.mark.parametrize("model", list(PRICES))
def test_the_end_customer_turn_barely_moves(model: str) -> None:
    """R5.1 — no sube de forma material en ningún modelo del catálogo.

    **No en todos baja, y eso no es un defecto.** El cambio sigue el ratio
    salida/entrada que cobra el proveedor, porque el peso único de la 0115 se
    calibró con una mezcla en la que la salida casi no pesaba:

    ===========================  =====  ======
    ratio salida/entrada         ratio  cambio
    ===========================  =====  ======
    ``gpt-4o``                    4,0x  -16,0 %
    ``sol`` · ``sonnet`` · ``haiku`` 5,0x  -1,2 %
    ``terra`` · ``luna``          6,0x   +1,9 %
    ===========================  =====  ======

    Los dos que suben tienen la salida relativamente más cara y estaban
    subvencionados **de más**: ahora pagan lo suyo. Un 1,9 % sobre el turno
    típico de un cliente final es invisible en una factura, y el alternativa
    —dejarles el peso viejo— sería conservar a propósito el defecto que esta
    spec corrige, en los dos modelos donde más se nota.
    """
    prompt, cache, out = END_CUSTOMER_TURN
    before = old_quota(prompt, cache, out, model)
    after = quota_tokens(
        prompt_tokens=prompt, cache_read=cache, output_tokens=out, weights=lanes_of(model)
    )
    change = (Decimal(after) / Decimal(before) - 1) * 100
    assert change <= MAX_RISE_PCT, f"{model}: {before} → {after} ({change:+.1f} %)"


@pytest.mark.parametrize("model", ["openai/gpt-5.6-sol", "anthropic/claude-sonnet-4-6"])
def test_the_models_actually_served_get_cheaper(model: str) -> None:
    """Los dos que el producto sirve hoy —Companion y teammates— **bajan**.

    Es la afirmación que importa comercialmente, y se fija aparte del caso
    general para que se rompa si alguien cambia el modelo por defecto sin mirar
    qué le pasa a la factura.
    """
    prompt, cache, out = END_CUSTOMER_TURN
    before = old_quota(prompt, cache, out, model)
    after = quota_tokens(
        prompt_tokens=prompt, cache_read=cache, output_tokens=out, weights=lanes_of(model)
    )
    assert after < before, f"{model}: {before} → {after}"


def test_the_typical_turn_falls_by_about_one_percent_on_sonnet() -> None:
    """La cifra que la spec afirma, fijada para que no se mueva sin que se vea."""
    prompt, cache, out = END_CUSTOMER_TURN
    model = "anthropic/claude-sonnet-4-6"
    assert old_quota(prompt, cache, out, model) == 5_210
    assert (
        quota_tokens(
            prompt_tokens=prompt, cache_read=cache, output_tokens=out, weights=lanes_of(model)
        )
        == 5_148
    )


def test_a_partner_with_three_clients_pays_less_than_before() -> None:
    """R5.1 — la afirmación en dólares, no en porcentajes.

    Tres barberías a 7.200 turnos al mes cada una, que es el orden de magnitud
    del primer cliente real.
    """
    prompt, cache, out = END_CUSTOMER_TURN
    model = "anthropic/claude-sonnet-4-6"
    turns = 3 * 7_200

    def invoice(qty: int) -> Decimal:
        return (Decimal(turns * qty) * CREDIT_USD_PER_MILLION / Decimal(1_000_000)).quantize(
            Decimal("0.01")
        )

    before = invoice(old_quota(prompt, cache, out, model))
    after = invoice(
        quota_tokens(
            prompt_tokens=prompt, cache_read=cache, output_tokens=out, weights=lanes_of(model)
        )
    )
    assert before == Decimal("1125.36")
    assert after == Decimal("1111.97")
    assert after < before
