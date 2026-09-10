import numpy as np
import pytest

from epl_forecast.research.discovery_sprint import (
    fit_low_score_rho,
    fit_multinomial,
    low_score_adjustment,
    predict_multinomial,
)


def score_row(home_goals=0, away_goals=0):
    return {
        "expected_home_goals": 1.5,
        "expected_away_goals": 1.0,
        "p_home": 0.49,
        "p_draw": 0.26,
        "p_away": 0.25,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "score_log_probability": -2.5,
        "outcome": "D" if home_goals == away_goals else "H" if home_goals > away_goals else "A",
    }


def test_low_score_adjustment_conserves_outcome_probability():
    probabilities, score_log = low_score_adjustment(score_row(), -0.05)
    assert probabilities.sum() == pytest.approx(1)
    assert (probabilities > 0).all()
    assert score_log > -2.5
    fit = fit_low_score_rho([score_row()] * 10)
    assert -0.15 <= fit["rho"] <= 0.15


def test_regularized_multinomial_returns_probabilities():
    x = np.arange(30, dtype=float).reshape(10, 3)
    y = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0])
    fit = fit_multinomial(x, y)
    probabilities = predict_multinomial(fit, x)
    assert probabilities.shape == (10, 3)
    assert probabilities.sum(axis=1) == pytest.approx(1)
