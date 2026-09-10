"""De-vigging and a small calibrated structural/market probability pool."""

import numpy as np
from scipy.optimize import minimize_scalar

from epl_forecast.evaluation import individual_metrics
from epl_forecast.schema import OUTCOMES


def devig_odds(home_odds, draw_odds, away_odds):
    prices = np.asarray([home_odds, draw_odds, away_odds], dtype=float)
    if not np.isfinite(prices).all() or (prices <= 1).any():
        raise ValueError("Decimal odds must be finite and greater than one")
    implied = 1 / prices
    return tuple(implied / implied.sum()), float(implied.sum())


def logarithmic_pool(structural, market, market_weight):
    structural = np.asarray(structural, dtype=float)
    market = np.asarray(market, dtype=float)
    if (
        structural.shape != (3,)
        or market.shape != (3,)
        or not np.isfinite(structural).all()
        or not np.isfinite(market).all()
        or (structural <= 0).any()
        or (market <= 0).any()
        or not np.isclose(structural.sum(), 1)
        or not np.isclose(market.sum(), 1)
        or not np.isfinite(market_weight)
        or not 0 <= market_weight <= 1
    ):
        raise ValueError("Invalid structural/market pool inputs")
    logits = (1 - market_weight) * np.log(structural) + market_weight * np.log(market)
    probabilities = np.exp(logits - logits.max())
    return tuple(probabilities / probabilities.sum())


def _matched_arrays(structural_rows, market_rows):
    def index(rows):
        result = {}
        for row in rows:
            if row["match_id"] in result:
                raise ValueError(f"Duplicate pooled prediction: {row['match_id']}")
            result[row["match_id"]] = row
        return result

    structural, market = index(structural_rows), index(market_rows)
    ids = sorted(structural.keys() & market.keys())
    if not ids:
        raise ValueError("No matched structural and market predictions")
    if any(structural[key]["outcome"] != market[key]["outcome"] for key in ids):
        raise ValueError("Structural and market predictions disagree on outcomes")
    s = np.array(
        [[structural[key][f"p_{side}"] for side in ("home", "draw", "away")] for key in ids],
        dtype=float,
    )
    m = np.array(
        [[market[key][f"p_{side}"] for side in ("home", "draw", "away")] for key in ids],
        dtype=float,
    )
    outcomes = np.array([OUTCOMES.index(structural[key]["outcome"]) for key in ids])
    individual_metrics(s, outcomes)
    individual_metrics(m, outcomes)
    return ids, s, m, outcomes


def fit_logarithmic_pool(structural_rows, market_rows):
    ids, structural, market, outcomes = _matched_arrays(structural_rows, market_rows)

    def objective(weight):
        logits = (1 - weight) * np.log(structural) + weight * np.log(market)
        probabilities = np.exp(logits - logits.max(axis=1, keepdims=True))
        probabilities /= probabilities.sum(axis=1, keepdims=True)
        return float(individual_metrics(probabilities, outcomes)[0].mean())

    interior = minimize_scalar(objective, bounds=(0, 1), method="bounded")
    choices = [(0.0, objective(0)), (1.0, objective(1)), (float(interior.x), interior.fun)]
    weight, loss = min(choices, key=lambda pair: pair[1])
    return {
        "market_weight": weight,
        "matches": len(ids),
        "log_loss": float(loss),
        "structural_log_loss": objective(0),
        "market_log_loss": objective(1),
    }


def market_assisted_probabilities(structural, quote, pool):
    market, implied_sum = devig_odds(quote["home_odds"], quote["draw_odds"], quote["away_odds"])
    probabilities = logarithmic_pool(structural, market, pool["market_weight"])
    return {
        "p_home": probabilities[0],
        "p_draw": probabilities[1],
        "p_away": probabilities[2],
        "market_probabilities": {
            "p_home": market[0],
            "p_draw": market[1],
            "p_away": market[2],
        },
        "market_family": quote["family"],
        "market_observed_at": str(quote["retrieved_at"]),
        "decimal_odds": {
            "home": float(quote["home_odds"]),
            "draw": float(quote["draw_odds"]),
            "away": float(quote["away_odds"]),
        },
        "raw_implied_probability_sum": implied_sum,
        "market_weight": pool["market_weight"],
    }
