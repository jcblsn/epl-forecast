from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest
from test_xg_quality_tilt import observations

from epl_forecast.models.process_observation import ProcessObservation
from epl_forecast.models.process_quality_tilt import (
    BayesianProcessQualityTilt,
    ProcessQualityTiltFilter,
)
from epl_forecast.models.process_scores import ProcessScoreMixture, process_goal_probabilities
from epl_forecast.models.quality_tilt_scores import ScoreMixture, score_diagnostics


def test_score_recursion_matches_integrated_likelihood():
    rates = np.array([0.1, 1.5, 5.0])
    values = process_goal_probabilities(rates, 0.3, 12)
    for g in range(13):
        for i, rate in enumerate(rates):
            expected = np.exp(ProcessObservation([g], [np.nan], 0.3)([np.log(rate)])[0])
            assert values[i, g] == pytest.approx(expected, abs=1e-12)


def test_score_probabilities_uncertainty_and_diagnostics():
    scores = ProcessScoreMixture(np.log([1.8, 0.9]), np.array([[0.08, 0.02], [0.02, 0.05]]))
    grid, tail = scores.grid(60)
    expected = [np.tril(grid, -1).sum(), np.trace(grid), np.triu(grid, 1).sum()]
    np.testing.assert_allclose(scores.outcome_probabilities(), expected, atol=1e-10)
    assert tail < 1e-10
    assert np.exp(scores.log_probability(2, 1)) == pytest.approx(grid[2, 1])
    diagnostics = score_diagnostics(scores)
    assert diagnostics["p_scoreless"] == pytest.approx(grid[0, 0])
    assert diagnostics["p_total_goals_ge6"] == pytest.approx(
        1 - sum(grid[h, a] for h in range(6) for a in range(6 - h))
    )
    covariance = ScoreMixture([scores], [1.0]).uncertainty_components()
    process = np.array(covariance["match_tempo_covariance"])
    np.testing.assert_allclose(process, np.diag([scores.home_rate, scores.away_rate]) * 0.5)
    home, away = scores.sample(np.random.default_rng(104), 100000)
    np.testing.assert_allclose(np.cov(home, away), covariance["total_score_covariance"], atol=0.05)


def test_chronological_cutoff_and_late_observations(small_history):
    rows = observations(small_history)
    cutoff = small_history[4].available_on
    model = ProcessQualityTiltFilter(rows).fit(small_history[:5], cutoff)
    changed = [dict(r) for r in rows]
    for r in changed[5:]:
        r["home_xg"] = 50
    other = ProcessQualityTiltFilter(changed).fit(small_history[:5], cutoff)
    np.testing.assert_array_equal(model.mean, other.mean)
    late = [{**r, "available_on": str(cutoff + timedelta(days=100))} for r in rows]
    left = ProcessQualityTiltFilter(late).fit(small_history[:5], cutoff)
    right = ProcessQualityTiltFilter().fit(small_history[:5], cutoff)
    np.testing.assert_array_equal(left.mean, right.mean)
    assert model.xg_updates == 5
    assert left.xg_updates == 0


def test_incremental_and_evolving_process_forecasts(small_history):
    rows = observations(small_history)
    model = BayesianProcessQualityTilt(rows, scale_order=3)
    for i, match in enumerate(small_history):
        model.fit(small_history[: i + 1], match.available_on)
    batch = BayesianProcessQualityTilt(rows, scale_order=3).fit(small_history, model.as_of)
    np.testing.assert_allclose(model.weights, batch.weights, atol=1e-12)
    for a, b in zip(model.members, batch.members, strict=True):
        np.testing.assert_allclose(a.mean, b.mean, atol=1e-7)
        assert np.linalg.eigvalsh(a.covariance).min() > 0
    fixture = replace(small_history[0].fixture, match_date=model.as_of + timedelta(days=180))
    prediction = model.predict_match(fixture)
    paths = model.sample_forecast_state(np.random.default_rng(40), 50000)
    home, away = paths.sample_scores(fixture, np.random.default_rng(41))
    actual = [(home > away).mean(), (home == away).mean(), (home < away).mean()]
    np.testing.assert_allclose(actual, prediction.probabilities, atol=0.013)
    for member in model.members:
        assert not np.allclose(
            member.forecast_moments(fixture)[1],
            member.forecast_moments(replace(fixture, match_date=model.as_of))[1],
        )
