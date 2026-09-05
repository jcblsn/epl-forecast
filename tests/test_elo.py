from dataclasses import replace
from datetime import date

import numpy as np
import pytest
from scipy.optimize import check_grad
from scipy.special import expit

from epl_forecast.models.elo import (
    EloOrderedLogit,
    elo_history,
    ordered_log_probabilities,
    ordered_logit_objective,
)


@pytest.mark.parametrize("goals, expected_change", [((2, 0), 10), ((1, 1), 0), ((0, 2), -10)])
def test_elo_expected_update_and_rating_conservation(small_history, goals, expected_change):
    match = replace(small_history[0], home_goals=goals[0], away_goals=goals[1])
    ratings, differences, _ = elo_history([match], k_factor=20, home_advantage=0)
    assert ratings[match.fixture.home_team_id] == expected_change
    assert ratings[match.fixture.away_team_id] == -expected_change
    assert differences.tolist() == [0]
    assert sum(ratings.values()) == 0


def test_home_advantage_reduces_reward_for_expected_home_win(small_history):
    match = replace(small_history[0], home_goals=2, away_goals=0)
    ratings, _, _ = elo_history([match], k_factor=20, home_advantage=60)
    change = 20 * (1 - 1 / (1 + 10 ** (-60 / 400)))
    assert ratings[match.fixture.home_team_id] == pytest.approx(change)
    assert 0 < change < 10


def test_pre_update_features_and_same_day_batch_are_order_invariant(small_history):
    first, second, third = [replace(m, home_goals=2, away_goals=0) for m in small_history[:3]]
    second = replace(second, fixture=replace(second.fixture, match_date=first.fixture.match_date))
    history = [first, second, third]
    ratings, differences, outcomes = elo_history(history, 20, 0)
    assert differences.tolist() == [0, 0, 20]
    assert outcomes.tolist() == [0, 0, 0]
    assert sum(ratings.values()) == pytest.approx(0)
    shuffled_ratings, shuffled_differences, _ = elo_history(list(reversed(history)), 20, 0)
    assert shuffled_ratings == ratings
    np.testing.assert_array_equal(shuffled_differences, differences)
    changed = [first, replace(second, home_goals=0, away_goals=9), third]
    _, changed_differences, _ = elo_history(changed, 20, 0)
    np.testing.assert_array_equal(changed_differences[:2], differences[:2])
    assert changed_differences[2] != differences[2]


def test_ordered_probabilities_match_cdf_and_remain_valid_in_extremes():
    parameters = np.array([0.3, 2.0, 0.5])
    differences = np.array([-500.0, -2, 0, 2, 500.0])
    log_p = ordered_log_probabilities(parameters, differences)
    assert np.all(np.isfinite(log_p))
    probabilities = np.exp(log_p)
    np.testing.assert_allclose(probabilities.sum(axis=1), 1, atol=1e-14)
    assert np.all(probabilities >= 0)
    eta = parameters[0] + parameters[1] * differences[1:-1]
    np.testing.assert_allclose(
        probabilities[1:-1, 1], expit(parameters[2] - eta) - expit(-parameters[2] - eta)
    )
    neutral = np.exp(ordered_log_probabilities(np.array([0, 2, np.log(5 / 3)]), np.array([0])))
    np.testing.assert_allclose(neutral[0], [0.375, 0.25, 0.375])
    assert np.all(np.diff(probabilities[:, 0]) > 0)
    assert np.all(np.diff(probabilities[:, 2]) < 0)


@pytest.mark.parametrize("threshold", [0.01, 0.5, 10.0])
def test_ordered_logit_gradient(threshold):
    parameters = np.array([0.2, 1.8, threshold])
    differences = np.array([-3.0, -0.5, 0.0, 0.2, 1.1, 4.0])
    outcomes = np.array([0, 1, 2, 1, 0, 2])
    prior = np.array([0.3, 2.3, 0.5])

    def objective(p):
        return ordered_logit_objective(p, differences, outcomes, 1.0, prior)

    assert check_grad(lambda p: objective(p)[0], lambda p: objective(p)[1], parameters) < 0.0003


@pytest.mark.parametrize("goals", [(0, 0), (4, 0), (0, 4)])
def test_single_class_fit_is_finite_and_has_no_score_distribution(small_history, goals):
    history = [replace(m, home_goals=goals[0], away_goals=goals[1]) for m in small_history]
    model = EloOrderedLogit().fit(history, date(2020, 9, 1))
    forecast = model.predict_match(replace(history[0].fixture, match_date=date(2020, 9, 2)))
    assert all(0 < p < 1 for p in forecast.probabilities)
    assert sum(forecast.probabilities) == pytest.approx(1)
    assert forecast.scores is None
    assert model.coefficients[1] >= 0
    assert model.coefficients[2] > 0


@pytest.mark.parametrize(
    "parameters", [{"k_factor": 0}, {"home_advantage": np.inf}, {"calibration_ridge": -1}]
)
def test_invalid_parameters_are_rejected(parameters):
    with pytest.raises(ValueError):
        EloOrderedLogit(**parameters)
