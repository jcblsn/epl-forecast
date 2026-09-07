from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest

from epl_forecast.models.xg_quality_tilt import BayesianXGQualityTilt
from epl_forecast.research.xg_diagnostics import ConditionalXGScores, conditional_opportunities


def test_conditional_opportunities_and_score_joint_agree(small_history):
    model = BayesianXGQualityTilt().fit(small_history, small_history[-1].available_on)
    fixture = replace(small_history[0].fixture, match_date=model.as_of + timedelta(days=7))
    before = [m.mean.copy() for m in model.members]
    scores = ConditionalXGScores(model, fixture, 2.3, 0.5)
    grid, tail = scores.grid(20)
    assert tail < 1e-10
    assert sum(scores.outcome_probabilities()) == pytest.approx(1)
    for home, away in [(0, 0), (1, 2), (4, 1)]:
        assert grid[home, away] == pytest.approx(
            np.exp(scores.log_probability(home, away)), abs=1e-12
        )
    for mean, member in zip(before, model.members, strict=True):
        np.testing.assert_array_equal(mean, member.mean)


def test_oracle_zero_xg_has_no_invented_goals(small_history):
    model = BayesianXGQualityTilt().fit(small_history, small_history[-1].available_on)
    fixture = replace(small_history[0].fixture, match_date=model.as_of)
    scores = ConditionalXGScores(model, fixture, 0, 0)
    assert scores.outcome_probabilities() == (0, 1, 0)
    assert scores.log_probability(1, 0) == -np.inf
    assert scores.log_probability(0, 0) == pytest.approx(0, abs=1e-12)


def test_conditioning_opportunities_matches_generative_rejection_sample():
    rng = np.random.default_rng(71)
    n = rng.poisson(1.5 / 0.2, size=1000000)
    xg = rng.gamma(n, 0.2)
    selected = n[(xg > 1.48) & (xg < 1.52)]
    _, weights, counts = conditional_opportunities(np.array([1.5]), 1.5, 0.2)
    assert (weights @ counts).item() == pytest.approx(selected.mean(), abs=0.08)


def test_week_bootstrap_is_paired_and_order_invariant():
    from epl_forecast.research.xg_diagnostics import paired_blocks

    left = {
        str(i): {"match_date": f"2024-08-{i + 1:02d}", "outcome": "H", "p_home": 0.4 + i / 100}
        for i in range(20)
    }
    right = {k: {**v, "p_home": 0.5} for k, v in left.items()}
    expected = paired_blocks(left, right, replicates=100)
    assert paired_blocks(dict(reversed(list(left.items()))), right, replicates=100) == expected
    assert paired_blocks(left, left, replicates=100)["interval_95"] == [0, 0]
    right["0"]["outcome"] = "A"
    with pytest.raises(ValueError, match="disagree"):
        paired_blocks(left, right)
