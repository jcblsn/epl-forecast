from datetime import UTC, datetime

import pytest

from epl_forecast.market import (
    devig_odds,
    fit_logarithmic_pool,
    logarithmic_pool,
    market_assisted_probabilities,
)


def prediction(match, probability, outcome="H"):
    return {
        "match_id": match,
        "outcome": outcome,
        "p_home": probability,
        "p_draw": (1 - probability) / 2,
        "p_away": (1 - probability) / 2,
    }


def test_devig_and_logarithmic_pool_conserve_probability():
    market, overround = devig_odds(2, 4, 4)
    assert market == pytest.approx((0.5, 0.25, 0.25))
    assert overround == 1
    assert logarithmic_pool((0.6, 0.2, 0.2), market, 0) == pytest.approx((0.6, 0.2, 0.2))
    assert logarithmic_pool((0.6, 0.2, 0.2), market, 1) == pytest.approx(market)
    with pytest.raises(ValueError):
        devig_odds(1, 2, 3)


def test_fit_selects_boundary_when_market_dominates():
    structural = [prediction(str(i), 0.4) for i in range(8)]
    market = [prediction(str(i), 0.8) for i in range(8)]
    result = fit_logarithmic_pool(structural, market)
    assert result["market_weight"] == 1
    assert result["market_log_loss"] < result["structural_log_loss"]


def test_market_assisted_output_retains_quote_provenance():
    quote = {
        "family": "market_average_preclosing",
        "home_odds": 2,
        "draw_odds": 4,
        "away_odds": 4,
        "retrieved_at": datetime(2026, 9, 9, 12, tzinfo=UTC),
    }
    result = market_assisted_probabilities((0.6, 0.2, 0.2), quote, {"market_weight": 1})
    assert sum(result[f"p_{side}"] for side in ("home", "draw", "away")) == pytest.approx(1)
    assert result["market_family"] == "market_average_preclosing"
    assert result["market_observed_at"].endswith("+00:00")
