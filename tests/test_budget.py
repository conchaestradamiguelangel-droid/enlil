import os
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("ENLIL_DB", ":memory:")

from enlil.budget import resolve_budget, estimate_cost, TIER_LIMITS, MODEL_COSTS


class TestResolveBudget:
    def test_explicit_tier_respected(self):
        for tier in ["minimal", "standard", "full"]:
            b = resolve_budget("cualquier texto", explicit_tier=tier)
            assert b.tier == tier

    def test_auto_minimal_for_short_query(self):
        b = resolve_budget("hola")
        assert b.tier == "minimal"

    def test_auto_standard_for_medium_query(self):
        b = resolve_budget("a" * 150)
        assert b.tier == "standard"

    def test_auto_full_for_long_query(self):
        b = resolve_budget("a" * 600)
        assert b.tier == "full"

    def test_max_tokens_match_tier(self):
        for tier in ["minimal", "standard", "full"]:
            b = resolve_budget("x", explicit_tier=tier)
            assert b.max_tokens == TIER_LIMITS[tier]

    def test_cost_is_positive(self):
        b = resolve_budget("x", explicit_tier="full")
        assert b.estimated_cost_usd > 0

    def test_cost_scales_with_tier(self):
        b_min = resolve_budget("x", explicit_tier="minimal")
        b_full = resolve_budget("x", explicit_tier="full")
        assert b_full.estimated_cost_usd > b_min.estimated_cost_usd


class TestEstimateCost:
    def test_known_model(self):
        cost = estimate_cost({"anthropic/claude-sonnet-4-6": 1000})
        assert cost == round(MODEL_COSTS["anthropic/claude-sonnet-4-6"], 6)

    def test_unknown_model_uses_default(self):
        cost = estimate_cost({"modelo/desconocido": 1000})
        assert cost > 0

    def test_zero_tokens(self):
        assert estimate_cost({}) == 0.0

    def test_multiple_models(self):
        cost = estimate_cost({
            "anthropic/claude-sonnet-4-6": 500,
            "openai/gpt-oss-120b:free": 500,
        })
        assert cost > 0
