from __future__ import annotations

from anthropic.types import Usage
from pydantic import BaseModel

_PER_MTOK = 1_000_000.0


class ModelPricing(BaseModel):
    """USD per 1M tokens (Anthropic list pricing). Cache write is the higher rate paid
    once to seed an ephemeral block; cache read is the discounted hit rate."""

    input_per_mtok: float
    output_per_mtok: float
    cache_write_per_mtok: float
    cache_read_per_mtok: float


# Reference list prices for the models this repo calls (A9.4 cost dashboard). Kept as a
# constant table — like the model ids in the adapters — rather than env so the cost math
# is reproducible; revisit on a pricing change.
_PRICING: dict[str, ModelPricing] = {
    "claude-sonnet-4-6": ModelPricing(
        input_per_mtok=3.0,
        output_per_mtok=15.0,
        cache_write_per_mtok=3.75,
        cache_read_per_mtok=0.30,
    ),
    "claude-haiku-4-5": ModelPricing(
        input_per_mtok=1.0,
        output_per_mtok=5.0,
        cache_write_per_mtok=1.25,
        cache_read_per_mtok=0.10,
    ),
}


class TokenUsage(BaseModel):
    """SDK-agnostic token tally for one or more LLM calls. Adapters map the Anthropic
    `Usage` into this so the domain/services never depend on the SDK type, and it sums so
    a service can accumulate a per-guide / per-submission total."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=(
                self.cache_creation_input_tokens + other.cache_creation_input_tokens
            ),
            cache_read_input_tokens=(self.cache_read_input_tokens + other.cache_read_input_tokens),
        )

    @property
    def total_input_tokens(self) -> int:
        """All input billed: fresh + cache-write (seeding) + cache-read (hits)."""
        return self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens

    @property
    def cache_hit_rate(self) -> float:
        """Share of input tokens served from cache (0..1); 0 when there is no input."""
        denom = self.total_input_tokens
        return self.cache_read_input_tokens / denom if denom else 0.0


def usage_from_response(usage: Usage) -> TokenUsage:
    """Map an Anthropic `Usage` (cache fields are Optional) into our `TokenUsage`."""
    return TokenUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
        cache_read_input_tokens=usage.cache_read_input_tokens or 0,
    )


def cost_usd(usage: TokenUsage, model: str) -> float:
    """Compute the USD cost of `usage` at `model` list prices. Unknown models cost 0.0
    (the metric degrades gracefully rather than crashing the worker)."""
    pricing = _PRICING.get(model)
    if pricing is None:
        return 0.0
    return (
        usage.input_tokens * pricing.input_per_mtok
        + usage.output_tokens * pricing.output_per_mtok
        + usage.cache_creation_input_tokens * pricing.cache_write_per_mtok
        + usage.cache_read_input_tokens * pricing.cache_read_per_mtok
    ) / _PER_MTOK
