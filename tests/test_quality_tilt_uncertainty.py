import numpy as np
import pytest
from scipy.integrate import quad
from scipy.stats import norm, poisson

from epl_forecast.research.quality_tilt_uncertainty import (
    EvidenceCheckedFilter,
    importance_update,
    relevant_functionals,
)


def test_importance_evidence_and_moments_match_scalar_quadrature():
    mean, variance, goals = 0.3, 0.4, 3

    def density(x):
        return norm.pdf(x, mean, np.sqrt(variance)) * poisson.pmf(goals, np.exp(x))

    mass = quad(density, -8, 8, epsabs=1e-12)[0]
    expected = quad(lambda x: x * density(x), -8, 8, epsabs=1e-12)[0] / mass
    expected_variance = (
        quad(lambda x: (x - expected) ** 2 * density(x), -8, 8, epsabs=1e-12)[0] / mass
    )
    m, c, check = importance_update(
        np.array([mean]),
        np.array([[variance]]),
        np.ones((1, 1)),
        np.array([goals]),
        None,
        12,
        power=17,
    )
    assert check["importance"] == pytest.approx(np.log(mass), abs=0.0002)
    assert m[0] == pytest.approx(expected, abs=0.0003)
    assert c[0, 0] == pytest.approx(expected_variance, abs=0.0005)
    assert abs(check["importance"] - np.log(mass)) < abs(check["laplace"] - np.log(mass))


def test_evidence_only_check_leaves_filter_state_unchanged(small_history):
    from epl_forecast.models.quality_tilt import QualityTiltFilter
    from epl_forecast.research.quality_tilt_reference import prepare

    data = prepare(small_history)
    base = QualityTiltFilter().fit(small_history, data["cutoff"])
    checked = EvidenceCheckedFilter(power=8).fit(small_history, data["cutoff"])
    assert np.array_equal(base.mean, checked.mean)
    assert np.array_equal(base.covariance, checked.covariance)
    assert base.log_evidence == checked.log_evidence
    assert len(checked.integration_checks) == base.updates
    assert all(0 < row["ess_fraction"] <= 1 for row in checked.integration_checks)


def test_league_and_common_tilt_offset_preserves_rates(small_history):
    from epl_forecast.research.quality_tilt_reference import prepare

    data = prepare(small_history)
    functionals = relevant_functionals(data)
    shift = np.zeros(functionals.shape[1])
    shift[0], shift[3::2] = 0.4, -0.2
    assert np.allclose((functionals @ shift)[2:], 0)
