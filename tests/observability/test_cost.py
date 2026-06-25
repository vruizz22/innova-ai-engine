from __future__ import annotations

from anthropic.types import Usage

from src.observability.cost import TokenUsage, cost_usd, usage_from_response


def test_usage_from_response_coalesces_optional_cache_fields() -> None:
    raw = Usage(
        input_tokens=200,
        output_tokens=100,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
    )

    usage = usage_from_response(raw)

    assert usage.input_tokens == 200
    assert usage.output_tokens == 100
    assert usage.cache_creation_input_tokens == 0
    assert usage.cache_read_input_tokens == 0


def test_token_usage_add_accumulates_every_field() -> None:
    a = TokenUsage(
        input_tokens=10,
        output_tokens=20,
        cache_creation_input_tokens=30,
        cache_read_input_tokens=40,
    )
    b = TokenUsage(
        input_tokens=1,
        output_tokens=2,
        cache_creation_input_tokens=3,
        cache_read_input_tokens=4,
    )

    total = a + b

    assert total.input_tokens == 11
    assert total.output_tokens == 22
    assert total.cache_creation_input_tokens == 33
    assert total.cache_read_input_tokens == 44


def test_cache_hit_rate_is_reads_over_all_input() -> None:
    usage = TokenUsage(input_tokens=200, cache_read_input_tokens=800)

    assert usage.total_input_tokens == 1000
    assert usage.cache_hit_rate == 0.8


def test_cache_hit_rate_zero_without_input() -> None:
    assert TokenUsage().cache_hit_rate == 0.0


def test_cost_usd_haiku_prices_each_token_class() -> None:
    usage = TokenUsage(input_tokens=200, output_tokens=100, cache_read_input_tokens=800)
    # (200*1.0 + 100*5.0 + 800*0.10) / 1e6
    assert cost_usd(usage, "claude-haiku-4-5") == 0.00078


def test_cost_usd_sonnet_includes_cache_write_rate() -> None:
    usage = TokenUsage(
        input_tokens=1000,
        output_tokens=500,
        cache_creation_input_tokens=2000,
        cache_read_input_tokens=4000,
    )
    # (1000*3 + 500*15 + 2000*3.75 + 4000*0.30) / 1e6
    assert cost_usd(usage, "claude-sonnet-4-6") == 0.0192


def test_cost_usd_unknown_model_degrades_to_zero() -> None:
    usage = TokenUsage(input_tokens=1000, output_tokens=1000)

    assert cost_usd(usage, "gpt-imaginary") == 0.0
