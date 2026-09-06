from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from epl_forecast.data.squads import Availability, PlayerHistory
from epl_forecast.models.player_quality import PlayerQualityFilter
from epl_forecast.models.quality_tilt import QualityTiltFilter


def history_for(matches):
    rows = []
    for match in matches:
        for team in (match.fixture.home_team_id, match.fixture.away_team_id):
            for i, role in enumerate(["GK"] + ["DEF"] * 4 + ["MID"] * 4 + ["FWD"] * 3):
                rows.append(
                    {
                        "match_id": match.fixture.match_id,
                        "team_id": team,
                        "season_id": match.fixture.season_id,
                        "kickoff_time": f"{match.fixture.match_date}T15:00:00Z",
                        "player_season_id": f"{team}-{i}",
                        "fpl_player_code": f"{team}-{i}",
                        "player_name": f"{team}-{i}",
                        "position": role,
                        "minutes": "90" if i < 11 else "0",
                        "starts": "1" if i < 11 else "0",
                    }
                )
    return PlayerHistory(rows)


def test_joint_updates_covariance_incremental_and_new_clubs(small_history):
    history = history_for(small_history)
    model = PlayerQualityFilter(history).fit(small_history[:1], date(2020, 8, 2))
    model.fit(small_history, date(2020, 8, 20))
    fresh = PlayerQualityFilter(history).fit(small_history, date(2020, 8, 20))
    assert model.mean == pytest.approx(fresh.mean, abs=1e-9)
    assert model.covariance == pytest.approx(fresh.covariance, abs=1e-9)
    assert len(model.player_index) == 44
    club = 2 + 2 * model.team_index["a"]
    player = model.player_index["fpl:a-0"]
    assert abs(model.covariance[club, player]) > 1e-4
    assert model.covariance[player, player] < model.player_sd**2
    assert np.linalg.eigvalsh(model.covariance).min() > 0
    before = model.mean.copy()
    model.predict_match(replace(small_history[0].fixture, match_date=date(2020, 9, 1)))
    assert model.mean == pytest.approx(before)


def test_absence_reacts_and_expires_with_same_fitted_model(small_history):
    cutoff = date(2020, 8, 20)
    model = PlayerQualityFilter(history_for(small_history), lineup_draws=128).fit(
        small_history, cutoff
    )
    fixture = replace(small_history[0].fixture, match_date=cutoff + timedelta(days=1))
    squad = model.squad(fixture, "a")
    player = "fpl:a-0"
    # A controlled strong goalkeeper verifies direction independently of weak goals-only learning.
    model.mean[model.player_index[player]] = 2
    before = model.predict_match(fixture).probabilities[0]
    observed = datetime(2020, 8, 20, tzinfo=UTC)
    absence = Availability(observed, 0, observed + timedelta(days=3), "test")
    model.squads = {"a": squad.with_availability(player, absence)}
    after = model.predict_match(fixture).probabilities[0]
    assert before - after > 0.03
    assert model.lineup_summary(fixture)[0]["lineup_selection_quality_sd"] >= 0
    later = replace(fixture, match_date=cutoff + timedelta(days=4))
    recovered = model.predict_match(later).probabilities
    model.squads = {"a": squad}
    assert recovered == pytest.approx(model.predict_match(later).probabilities, abs=1e-12)


def test_future_observations_cannot_change_fit_or_candidate_squad(small_history):
    history = history_for(small_history)
    cutoff = date(2020, 8, 3)
    past = [m for m in small_history if m.available_on <= cutoff]
    full = PlayerQualityFilter(history).fit(past, cutoff)
    limited = PlayerQualityFilter(history_for(past)).fit(past, cutoff)
    assert full.player_index == limited.player_index
    assert full.mean == pytest.approx(limited.mean)
    fixture = replace(small_history[0].fixture, match_date=cutoff)
    assert full.squad(fixture, "a") == limited.squad(fixture, "a")


def test_forward_score_frequencies_agree_with_direct_distribution(small_history):
    model = PlayerQualityFilter(history_for(small_history), lineup_draws=256).fit(
        small_history, date(2020, 8, 20)
    )
    fixture = replace(small_history[0].fixture, match_date=date(2020, 10, 1))
    rng = np.random.default_rng(31)
    states = model.sample_forecast_state(rng, 12000)
    home, away = states.sample_scores(fixture, rng)
    frequency = [np.mean(home > away), np.mean(home == away), np.mean(home < away)]
    assert frequency == pytest.approx(model.predict_match(fixture).probabilities, abs=0.018)


def test_no_player_observations_preserves_parent_posterior(small_history):
    cutoff = date(2020, 8, 20)
    model = PlayerQualityFilter(PlayerHistory([])).fit(small_history, cutoff)
    parent = QualityTiltFilter(dispersion=None).fit(small_history, cutoff)
    assert model.mean == pytest.approx(parent.mean)
    assert model.covariance == pytest.approx(parent.covariance)


def test_m6_ensemble_support_and_nested_mixture_reporting(small_history):
    from epl_forecast.models.player_quality import BayesianPlayerQuality
    from epl_forecast.models.quality_tilt import BayesianQualityTilt

    model = BayesianPlayerQuality(history_for(small_history), lineup_draws=8).fit(
        small_history, date(2020, 8, 20)
    )
    parent = BayesianQualityTilt(independent_poisson=True)
    assert model.specifications == parent.specifications
    assert all(m.dispersion is None for m in model.members)
    fixture = replace(small_history[0].fixture, match_date=date(2020, 8, 21))
    scores = model.predict_match(fixture).scores
    assert len(scores.components) == 32
    grid, tail = scores.grid(20)
    assert grid.sum() + tail == pytest.approx(1)
    assert scores.uncertainty_components()["total_score_covariance"][0][0] > 0
    assert model.lineup_summary(fixture)[0]["team_id"] == "a"
