import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import poisson

from epl_forecast.models.xg_observation import ChanceObservation


@pytest.mark.parametrize("goals", [0, 1, 4])
@pytest.mark.parametrize("p", [0.1, 0.35])
def test_integrating_xg_recovers_poisson_goal_marginal(goals, p):
    rate = 1.4

    def density(x):
        return np.exp(ChanceObservation([goals], [x], p)(np.log([rate]))[0])

    mass = quad(density, 0, np.inf, epsabs=1e-9)[0]
    if goals == 0:
        mass += np.exp(-rate / p)
    assert mass == pytest.approx(poisson.pmf(goals, rate), abs=1e-8)


@pytest.mark.parametrize("xg", [np.nan, 0.0, 0.001, 1.3, 8.0])
def test_likelihood_derivatives(xg):
    model = ChanceObservation([0], [xg], 0.2)
    eta, step = np.array([-0.3]), 1e-5
    value, score, curvature = model(eta)
    plus, minus = model(eta + step), model(eta - step)
    assert score[0] == pytest.approx((plus[0] - minus[0]) / (2 * step), abs=1e-8)
    assert curvature[0, 0] == pytest.approx(-(plus[1][0] - minus[1][0]) / (2 * step), abs=1e-8)
    assert np.isfinite(value)


def test_series_extends_for_large_xg_and_rate():
    model = ChanceObservation([12], [35], 0.1)
    value, score, curvature = model(np.log([30]))
    assert np.isfinite(value) and np.isfinite(score).all() and np.isfinite(curvature).all()
    assert len(model.terms[0][0]) == 128


def test_opportunity_generative_moments():
    rate, p, size = 1.5, 0.2, 300000
    model = ChanceObservation([], [], p)
    goals, xg = model.sample(np.full(size, np.log(rate)), np.random.default_rng(409))
    assert goals.mean() == pytest.approx(rate, abs=0.015)
    assert goals.var() == pytest.approx(rate, abs=0.025)
    assert xg.mean() == pytest.approx(rate, abs=0.01)
    assert xg.var() == pytest.approx(2 * p * rate, abs=0.012)
    assert np.cov(goals, xg)[0, 1] == pytest.approx(p * rate, abs=0.01)


def test_zero_atom_and_invalid_inputs():
    value, score, curvature = ChanceObservation([0], [0], 0.2)(np.log([1.4]))
    assert value == pytest.approx(-7)
    assert score[0] == pytest.approx(-7)
    assert curvature[0, 0] == pytest.approx(7)
    with pytest.raises(ValueError, match="zero xG"):
        ChanceObservation([1], [0], 0.2)
    with pytest.raises(ValueError, match="Goals"):
        ChanceObservation([0.5], [1], 0.2)
    with pytest.raises(ValueError, match="xG"):
        ChanceObservation([1], [np.inf], 0.2)
