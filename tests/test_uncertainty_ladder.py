from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from epl_forecast.models.baselines import AttackDefensePoisson
from epl_forecast.models.centered_quality_tilt import CenteredQualityTiltFilter
from epl_forecast.research.uncertainty_ladder import (
    M2SeasonDependence,
    MatchedStateForecast,
    MatchedStateMixture,
)
from epl_forecast.research.uncertainty_report import cluster_interval


def test_cluster_intervals_do_not_treat_clubs_as_independent_seasons():
    values = [-1.0] * 20 + [1.0] * 20
    season = cluster_interval(values, ["a"] * 20 + ["b"] * 20, 42)
    naive = cluster_interval(values, list(range(40)), 42)
    assert season["clusters"] == 2
    assert season["difference"] == naive["difference"] == 0
    assert season["interval_95"] == [-1, 1]
    assert naive["interval_95"][1] < season["interval_95"][1]
    assert cluster_interval(values, ["only"] * 40, 42)["interval_95"] is None


def test_matched_switches_preserve_fitted_mean_and_parent_predictions(full_season):
    cutoff = date(2020, 8, 10)
    fitted = CenteredQualityTiltFilter(independent_poisson=True).fit(
        [m for m in full_season if m.available_on <= cutoff], cutoff
    )
    teams = sorted({m.fixture.home_team_id for m in full_season})
    fixture = next(m.fixture for m in full_season if m.fixture.match_date > cutoff)
    mean, covariance = fitted.mean.copy(), fitted.covariance.copy()
    fixed = MatchedStateForecast(fitted, teams, fixture.season_id, posterior=False)
    posterior = MatchedStateForecast(fitted, teams, fixture.season_id)
    evolving = MatchedStateForecast(fitted, teams, fixture.season_id, evolution=True)
    conditional = MatchedStateForecast(fitted, teams, fixture.season_id, fixed_teams=[teams[0]])
    for variant in (fixed, posterior, evolving, conditional):
        assert np.array_equal(variant.mean, fixed.mean)
    assert np.array_equal(fitted.mean, mean)
    assert np.array_equal(fitted.covariance, covariance)
    assert evolving.predict_match(fixture).probabilities == pytest.approx(
        fitted.predict_match(fixture).probabilities, abs=1e-10
    )
    index = 2 + 2 * conditional.team_index[teams[0]]
    assert not conditional.covariance[index : index + 2].any()
    assert np.linalg.eigvalsh(posterior.covariance - conditional.covariance).min() > -1e-9
    paths = evolving.sample_forecast_state(np.random.default_rng(1), 100)
    paths.sample_scores(fixture, np.random.default_rng(2))
    with pytest.raises(ValueError, match="chronological"):
        paths.sample_scores(replace(fixture, match_date=cutoff), np.random.default_rng(3))


def test_m2_copula_preserves_score_marginals_but_adds_cross_match_dependence(full_season):
    cutoff = date(2020, 10, 1)
    fitted = AttackDefensePoisson().fit(full_season, cutoff)
    teams = sorted({m.fixture.home_team_id for m in full_season})
    fixture = replace(full_season[0].fixture, match_date=cutoff)
    repeat = replace(fixture, match_date=cutoff + timedelta(days=1))
    correlations = []
    for weight in (0.0, 0.5):
        forecast = M2SeasonDependence(fitted, teams, weight)
        assert forecast.predict_match(fixture) == fitted.predict_match(fixture)
        rng = np.random.default_rng(71)
        paths = forecast.sample_forecast_state(rng, 100000)
        home, away = paths.sample_scores(fixture, rng)
        later, _ = paths.sample_scores(repeat, rng)
        scores = fitted.predict_match(fixture).scores
        assert home.mean() == pytest.approx(scores.home_rate, abs=0.02)
        assert away.mean() == pytest.approx(scores.away_rate, abs=0.02)
        assert abs(np.corrcoef(home, away)[0, 1]) < 0.015
        observed = [np.mean(home > away), np.mean(home == away), np.mean(home < away)]
        assert observed == pytest.approx(fitted.predict_match(fixture).probabilities, abs=0.006)
        correlations.append(np.corrcoef(home, later)[0, 1])
    assert abs(correlations[0]) < 0.015
    assert correlations[1] > 0.3


def test_matched_state_mixture_preserves_members_and_switches(full_season):
    from epl_forecast.models.quality_tilt import BayesianQualityTilt

    cutoff = date(2020, 8, 10)
    teams = sorted({m.fixture.home_team_id for m in full_season})
    specifications = [
        dict(
            quality_retention=0.85,
            quality_sd=0.09,
            tilt_retention=0.5,
            tilt_sd=0.07,
            dispersion=None,
        ),
        dict(
            quality_retention=0.97,
            quality_sd=0.16,
            tilt_retention=0.85,
            tilt_sd=0.14,
            dispersion=None,
        ),
    ]
    fitted = BayesianQualityTilt(specifications=specifications).fit(full_season[:80], cutoff)
    mixture = MatchedStateMixture(
        fitted, teams, "2020-2021", posterior=False, evolution=True, innovations=False
    )
    assert len(mixture.members) == 2
    assert all(not member.posterior and member.evolution for member in mixture.members)
    assert all(not member.innovations for member in mixture.members)
    full = MatchedStateMixture(fitted, teams, "2020-2021")
    assert full.predict_match(full_season[90].fixture).probabilities == pytest.approx(
        fitted.predict_match(full_season[90].fixture).probabilities
    )
    states = mixture.sample_forecast_state(np.random.default_rng(4), 20)
    goals = states.sample_scores(full_season[90].fixture, np.random.default_rng(5))
    assert all(values.shape == (20,) for values in goals)
