from dataclasses import replace
from datetime import date

import numpy as np
import pytest
from scipy.optimize import check_grad

from epl_forecast.evaluation import individual_metrics, metrics, rolling_predictions
from epl_forecast.models.baselines import (
    AttackDefensePoisson,
    LeagueFrequency,
    LeaguePoisson,
    poisson_objective,
)
from epl_forecast.models.elo import EloOrderedLogit
from epl_forecast.models.poisson import IndependentPoisson
from epl_forecast.schema import Fixture, fixture_id


@pytest.mark.parametrize(
    "model_type", [LeagueFrequency, LeaguePoisson, AttackDefensePoisson, EloOrderedLogit]
)
def test_fit_rejects_same_day_and_future_results(small_history, model_type):
    with pytest.raises(ValueError, match="unavailable"):
        model_type().fit(small_history, date(2020, 8, 12))


@pytest.mark.parametrize(
    "model_type", [LeagueFrequency, LeaguePoisson, AttackDefensePoisson, EloOrderedLogit]
)
def test_predictions_for_unseen_teams_are_valid(small_history, model_type):
    day = date(2020, 8, 20)
    model = model_type().fit(small_history, day)
    fixture = Fixture(
        fixture_id("eng-premier-league", "2020-2021", "new", "other"),
        "eng-premier-league",
        "2020-2021",
        day,
        "new",
        "other",
    )
    forecast = model.predict_match(fixture)
    assert np.isclose(sum(forecast.probabilities), 1)
    assert all(0 < p < 1 for p in forecast.probabilities)
    with pytest.raises(ValueError, match="predates"):
        model.predict_match(replace(fixture, match_date=date(2020, 8, 1)))


def test_all_zero_training_still_has_finite_score_likelihood(small_history):
    history = [replace(m, home_goals=0, away_goals=0) for m in small_history]
    model = AttackDefensePoisson().fit(history, date(2020, 9, 1))
    forecast = model.predict_match(replace(history[0].fixture, match_date=date(2020, 9, 2)))
    assert np.isfinite(forecast.scores.log_probability(4, 3))
    assert model.attack.sum() == pytest.approx(0, abs=1e-10)
    assert model.defense.sum() == pytest.approx(0, abs=1e-10)


def test_same_day_and_future_labels_cannot_change_forecasts(small_history):
    config = {
        "competition_id": "eng-premier-league",
        "train_window_days": 365,
        "min_train_matches": 3,
        "models": [
            {"id": "m0", "kind": "league_frequency"},
            {"id": "m1", "kind": "league_poisson"},
            {"id": "m2", "kind": "attack_defense_poisson"},
            {"id": "m3", "kind": "elo_ordered_logit"},
        ],
    }
    cutoff = date(2020, 8, 8)
    history = [
        replace(m, fixture=replace(m.fixture, match_date=cutoff))
        if m.fixture.match_date == date(2020, 8, 9)
        else m
        for m in small_history
    ]
    mutated = [
        replace(m, home_goals=9, away_goals=8) if m.fixture.match_date >= cutoff else m
        for m in history
    ]
    original = rolling_predictions(history, config, cutoff, date(2020, 8, 9))
    altered = rolling_predictions(mutated, config, cutoff, date(2020, 8, 9))
    fields = ["model_id", "match_id", "train_matches", "p_home", "p_draw", "p_away"]
    assert [{k: row[k] for k in fields} for row in original] == [
        {k: row[k] for k in fields} for row in altered
    ]
    assert len(original) == 8
    assert all(row["train_date_max"] < str(cutoff) for row in original)


def test_score_grid_orientation_tail_and_unbounded_likelihood():
    distribution = IndependentPoisson(2.2, 0.7)
    grid, tail = distribution.grid(15)
    home, draw, away = distribution.outcome_probabilities()
    assert home == pytest.approx(np.tril(grid, -1).sum(), abs=1e-8)
    assert draw == pytest.approx(np.trace(grid), abs=1e-8)
    assert away == pytest.approx(np.triu(grid, 1).sum(), abs=1e-8)
    assert grid.sum() + tail == pytest.approx(1)
    tiny_grid, large_tail = distribution.grid(1)
    assert tiny_grid.sum() < 0.3 and large_tail > 0.7
    assert np.isfinite(distribution.log_probability(20, 16))
    x, y = distribution.sample(np.random.default_rng(10), 100000)
    assert x.max() > 1 and y.max() > 1
    assert x.mean() == pytest.approx(2.2, abs=0.02)
    assert y.mean() == pytest.approx(0.7, abs=0.02)


def test_poisson_gradient_matches_numerical_derivatives():
    parameters = np.array([0.2, 0.1, 0.3, -0.2, 0.4, -0.5, 0.1, 0.2])
    args = (
        np.array([0, 1, 2, 0]),
        np.array([1, 2, 0, 2]),
        np.array([2, 1, 0, 3]),
        np.array([0, 1, 2, 2]),
        np.array([1, 0.8, 0.7, 0.2]),
        5.0,
    )
    error = check_grad(
        lambda x: poisson_objective(x, *args)[0],
        lambda x: poisson_objective(x, *args)[1],
        parameters,
    )
    assert error < 1e-5


def test_known_proper_scores_and_calibration():
    p = np.array([[0.5, 0.25, 0.25], [0.1, 0.7, 0.2]])
    loss, brier = individual_metrics(p, np.array([0, 1]))
    assert loss == pytest.approx([-np.log(0.5), -np.log(0.7)])
    assert brier == pytest.approx([0.375, 0.14])
    rows = [
        {"p_home": a, "p_draw": b, "p_away": c, "outcome": outcome}
        for (a, b, c), outcome in zip(p, ["H", "D"], strict=True)
    ]
    summary, bins = metrics(rows)
    assert summary["log_loss"] == pytest.approx(loss.mean())
    assert summary["score_nll"] is None
    assert sum(row["count"] for row in bins) == 3 * len(rows)
    with pytest.raises(ValueError, match="sum"):
        individual_metrics(p * 0.9, np.array([0, 1]))
