import numpy as np
import pytest

from epl_forecast.research.quality_tilt_reference import (
    prepare,
    production_posterior,
    synthetic_data,
)


def test_reference_data_matches_production_initialization_and_order(small_history):
    data = prepare(small_history)
    assert data["teams"] == sorted(data["teams"])
    assert data["cutoff"] > max(m.fixture.match_date for m in small_history)
    assert np.all(data["years"] > 0)
    generated, truth = synthetic_data(data, np.random.default_rng(98))
    mean, covariance = production_posterior(generated)
    assert truth.shape == mean.shape
    assert np.linalg.eigvalsh(covariance).min() > 0
    assert np.isfinite(mean).all()


def test_reference_likelihood_matches_shared_gamma_production(small_history):
    numpyro = pytest.importorskip("numpyro")
    import jax

    from epl_forecast.models.quality_tilt_scores import joint_logpmf
    from epl_forecast.research.quality_tilt_reference import reference_model

    jax.config.update("jax_enable_x64", True)
    data = prepare(small_history)
    dimension = data["design"].shape[-1]
    fixed = {
        "initial_z": np.zeros(dimension),
        "innovations": np.zeros((len(data["years"]), dimension)),
    }
    model = numpyro.handlers.substitute(reference_model, data=fixed)
    trace = numpyro.handlers.trace(numpyro.handlers.seed(model, 19)).get_trace(data)
    expected = sum(joint_logpmf(m.home_goals, m.away_goals, 1.56, 1.2, 20) for m in small_history)
    assert float(trace["scores"]["fn"].log_prob(trace["scores"]["value"])) == pytest.approx(
        expected
    )
