"""Valoración del consumo (WP-19).

Lo que se fija aquí es la diferencia entre "cuesta cero" y "no lo sé", que
es la decisión de diseño de todo el módulo: un cero se suma en cualquier
panel de margen como si el evento fuese gratis y nadie vuelve a mirarlo;
un NULL se encuentra con ``WHERE cost_usd IS NULL`` y se reprecia.

También se fija la aritmética, porque el error típico aquí no da
excepción: multiplicar por la tarifa sin dividir entre el millón produce
una factura un millón de veces mayor y perfectamente creíble en un log.
"""

from __future__ import annotations

from decimal import Decimal

from nexus_worker.metering.pricing import ModelPrice, price_row

SONNET = ModelPrice(
    model_id="anthropic/claude-sonnet-4-6",
    input_per_mtok=Decimal("3"),
    output_per_mtok=Decimal("15"),
    cache_read_per_mtok=Decimal("0.3"),
    cache_write_per_mtok=Decimal("3.75"),
    cache_min_tokens=1024,
)
# En catálogo pero sin tarifas cargadas. Fue el caso real de gpt-4o y
# whisper entre la 0072 y la 0076; ahora es el caso de cualquier modelo
# que alguien añada al catálogo antes de saber lo que cuesta, que es la
# situación que este módulo tiene que seguir sabiendo tratar.
SIN_TARIFA = ModelPrice(model_id="proveedor/modelo-sin-tarifa")
VOZ = ModelPrice(model_id="deepgram/nova-3", per_minute=Decimal("0.0043"))

CATALOG = {p.model_id: p for p in (SONNET, SIN_TARIFA, VOZ)}


def _row(meter: str, quantity: str, model: str | None = SONNET.model_id) -> dict:
    return {"meter": meter, "quantity": Decimal(quantity), "model": model}


def test_token_meters_are_priced_per_million() -> None:
    # Un millón de tokens de entrada cuesta exactamente la tarifa.
    assert price_row(_row("llm.input_tokens", "1000000"), CATALOG) == Decimal("3.00000000")
    assert price_row(_row("llm.output_tokens", "1000"), CATALOG) == Decimal("0.01500000")


def test_reading_from_cache_is_an_order_of_magnitude_cheaper() -> None:
    """La razón por la que el medidor de caché existe separado: si se
    valorara como entrada normal, el ahorro del prompt caching sería
    invisible en la contabilidad."""
    tokens = "100000"
    como_entrada = price_row(_row("llm.input_tokens", tokens), CATALOG)
    desde_cache = price_row(_row("llm.cache_read", tokens), CATALOG)
    assert como_entrada == Decimal("0.30000000")
    assert desde_cache == Decimal("0.03000000")


def test_writing_to_cache_costs_more_than_plain_input() -> None:
    """Cachear no es gratis: la primera escritura vale 1,25x la entrada.
    Sin esta fila, un prompt que se cachea y nunca se reutiliza parecería
    más barato de lo que es."""
    tokens = "100000"
    assert price_row(_row("llm.cache_write", tokens), CATALOG) == Decimal("0.37500000")
    assert price_row(_row("llm.input_tokens", tokens), CATALOG) == Decimal("0.30000000")


def test_voice_is_priced_per_minute_not_per_million() -> None:
    row = _row("voice.minutes", "10", model="deepgram/nova-3")
    assert price_row(row, CATALOG) == Decimal("0.04300000")


def test_what_cannot_be_priced_is_none_and_never_zero() -> None:
    """Las cuatro formas de no saber el precio. Todas devuelven None, y
    ninguna devuelve 0: la fila entra sin precio y se puede reprecificar
    después. Un cero sería indistinguible de algo realmente gratis."""
    # 1 · la fila no dice de qué modelo salió
    assert price_row(_row("llm.input_tokens", "1000", model=None), CATALOG) is None
    # 2 · el modelo no está en catálogo
    assert price_row(_row("llm.input_tokens", "1000", model="anthropic/inventado"), CATALOG) is None
    # 3 · el modelo está, pero sin esa tarifa cargada
    assert price_row(_row("llm.input_tokens", "1000", model=SIN_TARIFA.model_id), CATALOG) is None
    # 4 · el medidor no se valora por tarifa de modelo
    assert price_row(_row("channel.message", "1"), CATALOG) is None


def test_a_float_quantity_does_not_poison_the_arithmetic() -> None:
    """El stream transporta texto y el JSON puede devolver float. Pasar un
    float a la multiplicación arrastraría error binario a una columna de
    dinero."""
    row = {"meter": "llm.input_tokens", "quantity": 1500.0, "model": SONNET.model_id}
    assert price_row(row, CATALOG) == Decimal("0.00450000")
