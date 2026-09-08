from copy import deepcopy
from datetime import date

import numpy as np
import pytest

from epl_forecast.models.centered_quality_tilt import CenteredQualityTiltFilter
from epl_forecast.models.promotion import TeamPrior
from epl_forecast.models.quality_tilt import QT_FROM_AD
from epl_forecast.research.promotion_transition import (
    fit_transition,
    promotion_prior,
    replace_entry_priors,
)
from epl_forecast.research.uncertainty_ladder import MatchedStateForecast


def cohorts():
    rng = np.random.default_rng(82)
    rows = []
    for year in range(2014, 2025):
        for _ in range(3):
            mean = rng.normal(0, 0.3, (2, 3))
            source = {
                "mean": mean.tolist(),
                "covariance": np.tile(np.eye(3) * 0.001, (2, 1, 1)).tolist(),
                "available_on": f"{year}-06-01",
            }
            row = {
                "source": source,
                "season_id": f"{year}-{year + 1}",
                "available_on": f"{year + 1}-06-01",
            }
            for side, dimension in enumerate(("attack", "defense")):
                row[f"entry_{dimension}"] = -0.3 + 0.7 * mean[side, 0]
                row[f"entry_{dimension}_variance"] = 0.002
            rows.append(row)
    return rows


@pytest.mark.parametrize("signals", ["population", "results", "process"])
def test_promotion_cutoff_and_positive_uncertainty(signals):
    rows = cohorts()
    source = rows[-6]["source"]
    cutoff = date(2023, 8, 1)
    left, diagnostics = promotion_prior(rows, source, cutoff, "2023-2024", signals)
    altered = deepcopy(rows)
    for row in altered[-6:]:
        row["entry_attack"] = 50
    right, _ = promotion_prior(altered, source, cutoff, "2023-2024", signals)
    np.testing.assert_array_equal(left.mean, right.mean)
    np.testing.assert_array_equal(left.covariance, right.covariance)
    assert diagnostics["training_cohorts"] == 27
    assert diagnostics["last_training_season"] == "2022-2023"
    assert np.linalg.eigvalsh(left.covariance).min() > 0
    future = {**source, "available_on": "2023-08-02"}
    with pytest.raises(ValueError, match="postdate"):
        promotion_prior(rows, future, cutoff, "2023-2024", signals)


def test_results_bridge_recovers_known_transition():
    fitted = fit_transition(cohorts(), "attack", "results")
    np.testing.assert_allclose(fitted["coefficients"], [-0.3, 0.7], atol=0.025)
    assert fitted["transition_variance"] < 0.01


def test_population_prior_ignores_source_strength_and_noise():
    rows = cohorts()
    source = rows[-6]["source"]
    changed = {
        **source,
        "mean": (np.ones((2, 3)) * 50).tolist(),
        "covariance": np.tile(np.eye(3) * 100, (2, 1, 1)).tolist(),
    }
    first, _ = promotion_prior(rows, source, date(2023, 8, 1), "2023-2024", "population")
    second, _ = promotion_prior(rows, changed, date(2023, 8, 1), "2023-2024", "population")
    np.testing.assert_array_equal(first.mean, second.mean)
    np.testing.assert_array_equal(first.covariance, second.covariance)


def test_process_bridge_propagates_correlated_measurement_noise():
    rows = cohorts()
    for row in rows:
        row["entry_attack"] = -0.3 + 0.4 * sum(row["source"]["mean"][0])
    source = deepcopy(rows[-6]["source"])
    source["covariance"] = np.tile(np.eye(3) * 0.03, (2, 1, 1)).tolist()
    first, _ = promotion_prior(rows, source, date(2023, 8, 1), "2023-2024", "process")
    source["covariance"] = np.tile(np.full((3, 3), 0.02) + np.eye(3) * 0.01, (2, 1, 1)).tolist()
    second, _ = promotion_prior(rows, source, date(2023, 8, 1), "2023-2024", "process")
    assert second.covariance[0, 0] > first.covariance[0, 0]
    np.testing.assert_array_equal(first.mean, second.mean)


def test_entry_replacement_preserves_incumbents_and_parent(full_season):
    cutoff = date(2020, 8, 10)
    parent = CenteredQualityTiltFilter(independent_poisson=True).fit(
        [m for m in full_season if m.available_on <= cutoff], cutoff
    )
    teams = sorted({m.fixture.home_team_id for m in full_season})
    forecast = MatchedStateForecast(parent, teams, full_season[0].fixture.season_id)
    original_mean, original_covariance = forecast.mean.copy(), forecast.covariance.copy()
    parent_mean = parent.mean.copy()
    prior = TeamPrior(np.array([-0.3, -0.2]), np.diag([0.04, 0.09]), "test")
    replace_entry_priors(forecast, {teams[0]: prior})
    index = 2 + 2 * forecast.team_index[teams[0]]
    block = [index, index + 1]
    rest = [i for i in range(len(forecast.mean)) if i not in block]
    np.testing.assert_array_equal(forecast.mean[rest], original_mean[rest])
    np.testing.assert_array_equal(
        forecast.covariance[np.ix_(rest, rest)], original_covariance[np.ix_(rest, rest)]
    )
    np.testing.assert_allclose(forecast.mean[block], QT_FROM_AD @ prior.mean)
    np.testing.assert_allclose(
        forecast.covariance[np.ix_(block, block)], QT_FROM_AD @ prior.covariance @ QT_FROM_AD.T
    )
    assert not forecast.covariance[np.ix_(block, rest)].any()
    assert np.linalg.eigvalsh(forecast.covariance).min() > -1e-9
    np.testing.assert_array_equal(parent.mean, parent_mean)
