import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import poisson

from epl_forecast.models.process_observation import ProcessObservation


@pytest.mark.parametrize("xg", [0.0, 0.2, 2.5, np.nan])
@pytest.mark.parametrize("scale", [0.08, 0.4, 1.2])
def test_derivatives(xg, scale):
    goals = 0 if xg == 0 else 2
    likelihood = ProcessObservation([goals], [xg], scale)
    eta, step = np.array([0.3]), 1e-4
    value, gradient, curvature = likelihood(eta)
    upper, lower = likelihood(eta + step)[0], likelihood(eta - step)[0]
    assert gradient[0] == pytest.approx((upper - lower) / (2 * step), abs=1e-6)
    assert curvature[0, 0] == pytest.approx(-(upper - 2 * value + lower) / step**2, abs=2e-5)


@pytest.mark.parametrize("goals", [0, 1, 4])
def test_missing_xg_integrates_joint_distribution(goals):
    eta, scale = np.array([0.4]), 0.3

    def density(x):
        return np.exp(ProcessObservation([goals], [x], scale)(eta)[0])

    integrated = quad(density, 0, np.inf, epsabs=1e-10)[0]
    if goals == 0:
        integrated += np.exp(-np.exp(eta[0]) / scale)
    missing = np.exp(ProcessObservation([goals], [np.nan], scale)(eta)[0])
    assert integrated == pytest.approx(missing, abs=1e-9)


def test_goal_marginal_normalization_and_moments():
    rate, scale = 1.7, 0.35
    goals = np.arange(70)
    probabilities = np.array(
        [np.exp(ProcessObservation([g], [np.nan], scale)([np.log(rate)])[0]) for g in goals]
    )
    assert probabilities.sum() == pytest.approx(1, abs=1e-12)
    assert probabilities @ goals == pytest.approx(rate, abs=1e-10)
    assert probabilities @ (goals - rate) ** 2 == pytest.approx(rate * (1 + 2 * scale))


def test_observed_goals_do_not_independently_update_state():
    zero = ProcessObservation([0], [1.3], 0.25)([0.2])
    three = ProcessObservation([3], [1.3], 0.25)([0.2])
    np.testing.assert_allclose(zero[1], three[1], atol=1e-12)
    np.testing.assert_allclose(zero[2], three[2], atol=1e-12)
    assert three[0] - zero[0] == pytest.approx(poisson.logpmf(3, 1.3) - poisson.logpmf(0, 1.3))


def test_sampling_matches_process_and_goal_moments():
    rate, scale = 1.4, 0.4
    goals, xg = ProcessObservation([], [], scale).sample(
        np.full(200000, np.log(rate)), np.random.default_rng(891)
    )
    assert xg.mean() == pytest.approx(rate, abs=0.015)
    assert xg.var() == pytest.approx(2 * rate * scale, abs=0.03)
    assert goals.mean() == pytest.approx(rate, abs=0.015)
    assert goals.var() == pytest.approx(rate * (1 + 2 * scale), abs=0.04)
    assert np.cov(goals, xg)[0, 1] == pytest.approx(2 * rate * scale, abs=0.03)


@pytest.mark.parametrize(
    "goals,xg,scale",
    [
        ([1], [0], 0.2),
        ([-1], [1], 0.2),
        ([0.5], [1], 0.2),
        ([0], [-1], 0.2),
        ([0], [np.inf], 0.2),
        ([0], [1], 0),
        ([0], [1], np.nan),
        ([0, 1], [1], 0.2),
    ],
)
def test_invalid_observations(goals, xg, scale):
    with pytest.raises(ValueError):
        ProcessObservation(goals, xg, scale)


def test_large_line_search_proposals_have_finite_likelihood():
    likelihood = ProcessObservation([2, 1], [np.nan, 1.3], 0.1)
    value, gradient, curvature = likelihood([20, 20])
    assert np.isfinite(value)
    assert np.isfinite(gradient).all()
    assert np.isfinite(curvature).all()


def test_bessel_density_matches_independent_packet_sum():
    from scipy.special import gammaln, logsumexp

    for rate, x, q in [(0.01, 0.002, 1.0), (1.3, 2.1, 0.25), (12, 10, 0.08)]:
        n = np.arange(1, 1000)
        value = (
            logsumexp(
                n * np.log(rate / q)
                - rate / q
                - gammaln(n + 1)
                + (n - 1) * np.log(x)
                - x / q
                - gammaln(n)
                - n * np.log(q)
            )
            - x
        )
        actual = ProcessObservation([0], [x], q)([np.log(rate)])[0]
        assert actual == pytest.approx(value, abs=1e-11)


def test_line_search_backtracks_unresolvable_proposals():
    from epl_forecast.models.gaussian import LikelihoodDomainError, likelihood_laplace_update

    calls = []

    def likelihood(eta):
        calls.append(float(eta[0]))
        if eta[0] > 3:
            raise LikelihoodDomainError("proposal beyond numerical domain")
        rate = np.exp(eta[0])
        return 20 * eta[0] - rate, np.array([20 - rate]), np.array([[rate]])

    mean, covariance, evidence = likelihood_laplace_update(
        np.zeros(1), np.ones((1, 1)), np.ones((1, 1)), likelihood
    )
    assert max(calls) > 3
    assert abs(mean[0] + np.exp(mean[0]) - 20) < 1e-7
    assert covariance[0, 0] > 0
    assert np.isfinite(evidence)
