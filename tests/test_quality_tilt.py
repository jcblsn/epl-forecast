from dataclasses import replace
from datetime import date

import numpy as np
import pytest
from scipy.optimize import minimize

from epl_forecast.models.dynamic import DynamicAttackDefense
from epl_forecast.models.gaussian import score_laplace_update
from epl_forecast.models.poisson import IndependentPoisson
from epl_forecast.models.quality_tilt import BayesianQualityTilt, QualityTiltFilter
from epl_forecast.models.quality_tilt_scores import GammaPoissonMixture, joint_logpmf


def test_shared_tempo_probability_and_moments():
    scores = GammaPoissonMixture(np.log([1.8, 1.1]), np.zeros((2, 2)), dispersion=3)
    grid, tail = scores.grid(45)
    assert tail < 1e-10
    assert scores.outcome_probabilities() == pytest.approx(
        [np.tril(grid, -1).sum(), np.trace(grid), np.triu(grid, 1).sum()], abs=1e-10
    )
    assert np.exp(scores.log_probability(2, 1)) == pytest.approx(grid[2, 1])
    h, a = scores.sample(np.random.default_rng(25), 300000)
    assert h.mean() == pytest.approx(1.8, abs=0.015)
    assert h.var() == pytest.approx(1.8 + 1.8**2 / 3, abs=0.04)
    assert np.cov(h, a)[0, 1] == pytest.approx(1.8 * 1.1 / 3, abs=0.025)
    poisson = IndependentPoisson(1.8, 1.1)
    limit = GammaPoissonMixture(np.log([1.8, 1.1]), np.zeros((2, 2)), dispersion=1e6)
    assert limit.outcome_probabilities() == pytest.approx(poisson.outcome_probabilities(), abs=1e-6)


def test_correlated_laplace_matches_direct_optimization_and_evidence_quadrature():
    mean = np.log([1.5, 1.0])
    covariance = np.array([[0.12, 0.03], [0.03, 0.1]])
    precision = np.linalg.inv(covariance)
    goals = np.array([2, 0])
    result = score_laplace_update(mean, covariance, np.eye(2), goals, 5)

    def objective(x):
        d = x - mean
        return 0.5 * d @ precision @ d - joint_logpmf(2, 0, *np.exp(x), 5)

    optimum = minimize(objective, mean, method="BFGS", tol=1e-9)
    assert result[0] == pytest.approx(optimum.x, abs=1e-7)
    assert np.linalg.eigvalsh(result[1]).min() > 0
    exact_evidence = GammaPoissonMixture(mean, covariance, 25, 5).log_probability(2, 0)
    assert result[2] == pytest.approx(exact_evidence, abs=0.005)


def test_reparameterization_preserves_m4_poisson_filter(small_history):
    cutoff = date(2020, 8, 20)
    m4 = DynamicAttackDefense(promotion_performance=False).fit(small_history, cutoff)
    m5 = QualityTiltFilter(
        quality_retention=0.85,
        tilt_retention=0.85,
        quality_sd=0.18 / np.sqrt(2),
        tilt_sd=0.18 / np.sqrt(2),
        annual_league_sd=0.06,
        annual_home_sd=0.06,
        dispersion=None,
    ).fit(small_history, cutoff)
    transform = np.eye(len(m4.mean))
    for index in range(2, len(transform), 2):
        transform[index : index + 2, index : index + 2] = [[0.5, 0.5], [0.5, -0.5]]
    assert m5.mean == pytest.approx(transform @ m4.mean, abs=1e-8)
    assert m5.covariance == pytest.approx(transform @ m4.covariance @ transform.T, abs=1e-8)
    fixture = replace(small_history[0].fixture, match_date=cutoff)
    assert m5.predict_match(fixture).probabilities == pytest.approx(
        m4.predict_match(fixture).probabilities, abs=1e-8
    )


def test_ensemble_incremental_replay_and_prior_weights(small_history):
    specs = [dict(dispersion=4), dict(dispersion=80)]
    model = BayesianQualityTilt(specs, [1, 2]).fit(small_history[:5], date(2020, 8, 6))
    model.fit(small_history, date(2020, 8, 20))
    fresh = BayesianQualityTilt(specs, [1, 2]).fit(small_history, date(2020, 8, 20))
    assert model.weights == pytest.approx(fresh.weights, abs=1e-8)
    assert model.weights.sum() == pytest.approx(1)
    assert not np.allclose(model.weights, model.prior_weights)
    changed = [replace(small_history[0], home_goals=9)] + small_history[1:]
    model.fit(changed, date(2020, 8, 20))
    fresh.fit(changed, date(2020, 8, 20))
    assert model.weights == pytest.approx(fresh.weights)
    with pytest.raises(ValueError, match="unavailable"):
        model.fit(changed, date(2020, 8, 1))


def test_forward_states_match_forecast_at_future_dates_and_do_not_mutate_fit(small_history):
    model = BayesianQualityTilt([dict(dispersion=6), dict(dispersion=30)]).fit(
        small_history, date(2020, 8, 20)
    )
    fixture = replace(small_history[0].fixture, match_date=date(2021, 5, 1))
    saved = model.members[0].mean.copy()
    rng = np.random.default_rng(81)
    states = model.sample_forecast_state(rng, 100000)
    first = replace(fixture, match_date=date(2020, 10, 1))
    states.sample_scores(first, rng)
    h, a = states.sample_scores(fixture, rng)
    assert [np.mean(h > a), np.mean(h == a), np.mean(h < a)] == pytest.approx(
        model.predict_match(fixture).probabilities, abs=0.006
    )
    assert model.members[0].mean == pytest.approx(saved)
    with pytest.raises(ValueError, match="chronological"):
        states.sample_scores(first, rng)
    summary = model.team_summary("a", "2020-2021")
    assert summary["quality_sd"] > 0 and summary["tilt_sd"] > 0


def test_separate_transitions_have_semigroup_property():
    model = QualityTiltFilter()
    a, av = model.transition(0.3, 6)
    b, bv = model.transition(0.7, 6)
    total, variance = model.transition(1, 6)
    assert a * b == pytest.approx(total)
    assert av * b**2 + bv == pytest.approx(variance)
    assert total[2] != total[3]
    assert variance[2] != variance[3]
