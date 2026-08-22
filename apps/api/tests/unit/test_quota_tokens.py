"""C3 — la cuota es uncached + 0.1 x cache_read + output, nunca el bruto."""

from __future__ import annotations

from nexus_api.metering.quota import (
    billable_qty_for_meter,
    cache_read_quota_tokens,
    quota_input_tokens,
    quota_tokens,
    uncached_input_tokens,
)


def test_cache_read_counts_one_tenth_not_zero_and_not_one() -> None:
    prompt, cache, output = 10_000, 9_000, 100
    assert uncached_input_tokens(prompt, cache) == 1_000
    assert cache_read_quota_tokens(cache) == 900
    assert quota_input_tokens(prompt_tokens=prompt, cache_read=cache) == 1_900
    assert quota_tokens(prompt_tokens=prompt, cache_read=cache, output_tokens=output) == 2_000


def test_prompt_bruto_plus_cache_read_is_not_the_quota() -> None:
    """Si alguien suma prompt + cache_read, este test tiene que romper."""
    prompt, cache, output = 10_000, 9_000, 100
    naive = prompt + cache + output
    policy = quota_tokens(prompt_tokens=prompt, cache_read=cache, output_tokens=output)
    assert naive != policy
    assert naive == 19_100
    assert policy == 2_000


def test_cache_write_is_out_of_the_cap() -> None:
    assert (
        quota_tokens(
            prompt_tokens=1_000,
            cache_read=0,
            output_tokens=50,
            cache_write=8_000,
        )
        == 1_050
    )


def test_rounding_is_half_away_not_bankers() -> None:
    """25 * 0.1 = 2.5. ``round()`` de Python da 2; la cuota da 3."""
    assert round(2.5) == 2
    assert cache_read_quota_tokens(25) == 3
    assert cache_read_quota_tokens(15) == 2
    assert cache_read_quota_tokens(5) == 1
    assert cache_read_quota_tokens(4) == 0


def test_input_billable_plus_cache_quantity_is_not_the_quota() -> None:
    """input.billable + cache_read*1 (nativo) no es la cuota."""
    prompt, cache, output = 10_000, 9_000, 100
    input_billable = billable_qty_for_meter(
        "llm.input_tokens", prompt, prompt_tokens=prompt, cache_read=cache
    )
    cache_native = float(cache)
    wrong = input_billable + cache_native
    right = float(quota_tokens(prompt_tokens=prompt, cache_read=cache, output_tokens=output))
    assert input_billable == 1_000.0
    assert billable_qty_for_meter("llm.cache_read", cache) == 900.0
    assert billable_qty_for_meter("llm.cache_write", 500) == 0.0
    assert wrong != right
    assert wrong == 10_000.0
    assert right == 2_000.0


def test_companion_and_channel_debit_the_same_call_once() -> None:
    """La misma llamada no se cobra dos veces si se suman Companion y canal."""
    prompt, cache, output, write = 10_000, 9_000, 100, 400
    companion = quota_tokens(
        prompt_tokens=prompt,
        cache_read=cache,
        output_tokens=output,
        cache_write=write,
    )
    channel = (
        billable_qty_for_meter("llm.input_tokens", prompt, prompt_tokens=prompt, cache_read=cache)
        + billable_qty_for_meter("llm.cache_read", cache)
        + billable_qty_for_meter("llm.output_tokens", output)
        + billable_qty_for_meter("llm.cache_write", write)
    )
    assert companion == int(channel)
    double = companion + int(channel)
    assert double == 2 * companion
    assert double != companion
