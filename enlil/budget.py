from dataclasses import dataclass

# Coste aproximado por 1K tokens en USD (OpenRouter, mayo 2026)
MODEL_COSTS: dict[str, float] = {
    "anthropic/claude-sonnet-4-6":                 0.003,
    "anthropic/claude-sonnet-5":                   0.003,
    "anthropic/claude-opus-4-8":                   0.015,
    "deepseek/deepseek-v4-pro":                    0.0007,
    "deepseek/deepseek-r1":                        0.00055,
    "nvidia/llama-3.1-nemotron-ultra-253b-v1":     0.002,
    "mistralai/mistral-large-2512":                0.002,
    "google/gemini-3.1-pro-preview":               0.003,
    "x-ai/grok-4.3":                               0.003,
    "meta-llama/llama-4-maverick":                 0.0002,
}

TIER_LIMITS: dict[str, int] = {
    "minimal":  2_000,   # 2 dioses
    "standard": 6_000,   # 4 dioses + síntesis
    "full":    16_000,   # 9 dioses + síntesis
}


@dataclass
class BudgetResult:
    tier: str
    max_tokens: int
    estimated_cost_usd: float


def resolve_budget(query: str, explicit_tier: str | None = None) -> BudgetResult:
    if explicit_tier:
        tier = explicit_tier
    elif len(query) > 300:
        tier = "full"
    elif len(query) > 30:
        tier = "standard"
    else:
        tier = "minimal"

    max_tokens = TIER_LIMITS[tier]
    avg_cost = sum(MODEL_COSTS.values()) / len(MODEL_COSTS)
    estimated = (max_tokens / 1000) * avg_cost

    return BudgetResult(tier=tier, max_tokens=max_tokens, estimated_cost_usd=round(estimated, 5))


def estimate_cost(tokens_used: dict[str, int]) -> float:
    total = 0.0
    for model, tokens in tokens_used.items():
        rate = MODEL_COSTS.get(model, 0.003)
        total += (tokens / 1000) * rate
    return round(total, 6)
