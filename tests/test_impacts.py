from datetime import date

import numpy as np
import pytest

from epl_forecast.models.base import Forecast
from epl_forecast.publication import derive_impact
from epl_forecast.simulation import simulate_season

CUTOFF = date(2020, 8, 10)


class RandomScores:
    def __init__(self, home_rate, away_rate):
        self.home_rate, self.away_rate = home_rate, away_rate

    def sample(self, rng, size):
        return rng.poisson(self.home_rate, size), rng.poisson(self.away_rate, size)


class RandomModel:
    def __init__(self, as_of, teams):
        self.as_of = as_of
        self.rates = {team: 0.8 + 0.04 * index for index, team in enumerate(sorted(teams))}

    def predict_match(self, fixture):
        return Forecast(
            (0.4, 0.3, 0.3),
            RandomScores(self.rates[fixture.home_team_id], self.rates[fixture.away_team_id]),
        )


class AlwaysHomeWin:
    def sample(self, rng, size):
        return np.ones(size, dtype=int), np.zeros(size, dtype=int)


class FixedModel:
    def __init__(self, as_of):
        self.as_of = as_of

    def predict_match(self, fixture):
        return Forecast((1.0, 0.0, 0.0), AlwaysHomeWin())


def season_parts(full_season):
    teams = sorted({m.fixture.home_team_id for m in full_season})
    played = [m for m in full_season if m.available_on <= CUTOFF]
    remaining = [m.fixture for m in full_season if m.available_on > CUTOFF]
    return teams, played, remaining


def run(full_season, model=None, simulations=400, count=3):
    teams, played, remaining = season_parts(full_season)
    wanted = {fixture.match_id for fixture in remaining[:count]}
    return simulate_season(
        model or RandomModel(CUTOFF, teams),
        played,
        remaining,
        teams,
        CUTOFF,
        simulations,
        7,
        impact_fixtures=wanted,
    )


def test_conditioning_returns_the_published_event_in_aggregate(full_season):
    result = run(full_season)
    impacts = result["match_impacts"]
    events = {
        (row["team_id"], event): value
        for row in result["teams"]
        for event, value in row.items()
        if event.endswith("_probability")
    }
    assert len(impacts["fixtures"]) == 3
    assert impacts["horizon_days"] == 7
    for fixture in impacts["fixtures"]:
        counts = fixture["outcome_counts"]
        assert sum(counts.values()) == result["simulations"]
        for row in fixture["impacts"]:
            assert row["baseline"] == pytest.approx(events[(row["team_id"], row["event"])])
            recovered = sum(
                counts[name] / result["simulations"] * row["conditional"][name]
                for name in ("home", "draw", "away")
                if counts[name]
            )
            assert recovered == pytest.approx(row["baseline"], abs=1e-12)


def test_impacts_rank_by_movement_and_report_their_swing(full_season):
    impacts = run(full_season)["match_impacts"]
    tops = [fixture["top_rms_movement"] for fixture in impacts["fixtures"]]
    assert tops == sorted(tops, reverse=True)
    for fixture in impacts["fixtures"]:
        movements = [row["rms_movement"] for row in fixture["impacts"]]
        assert movements == sorted(movements, reverse=True)
        assert fixture["top_rms_movement"] == movements[0]
        for row in fixture["impacts"]:
            present = [value for value in row["conditional"].values() if value is not None]
            assert row["swing"] == pytest.approx(max(present) - min(present))
            assert row["swing"] >= row["rms_movement"] - 1e-12
        assert {row["team_id"] for row in fixture["impacts"]} == {
            fixture["home_team_id"],
            fixture["away_team_id"],
        }


def test_a_certain_result_moves_nothing_and_is_a_thin_sample(full_season):
    impacts = run(full_season, model=FixedModel(CUTOFF), simulations=8, count=1)["match_impacts"]
    fixture = impacts["fixtures"][0]
    assert fixture["outcome_counts"] == {"home": 8, "draw": 0, "away": 0}
    assert impacts["smallest_outcome_count"] == 0
    for row in fixture["impacts"]:
        assert row["rms_movement"] == pytest.approx(0.0)
        assert row["swing"] == pytest.approx(0.0)
        assert row["conditional"]["draw"] is None and row["conditional"]["away"] is None
        assert row["conditional"]["home"] == pytest.approx(row["baseline"])
        assert not row["sufficient_sample"]


def test_no_requested_fixtures_publishes_no_impact_surface(full_season):
    teams, played, remaining = season_parts(full_season)
    result = simulate_season(RandomModel(CUTOFF, teams), played, remaining, teams, CUTOFF, 8, 7)
    assert result["match_impacts"] is None
    assert derive_impact(result, {}) is None


def test_derive_impact_keeps_five_fixtures_and_both_participants(full_season):
    result = run(full_season, count=8)
    kickoffs = {
        fixture["match_id"]: "2020-08-11T14:00:00+00:00"
        for fixture in result["match_impacts"]["fixtures"]
    }
    published = derive_impact(result, kickoffs)
    assert len(published["fixtures"]) == 5
    assert published["horizon_days"] == 7
    for fixture in published["fixtures"]:
        assert fixture["kickoff_time"] == "2020-08-11T14:00:00+00:00"
        assert len(fixture["impacts"]) == 4
        assert {row["team_id"] for row in fixture["impacts"]} == {
            fixture["home_team_id"],
            fixture["away_team_id"],
        }
        movements = [row["rms_movement"] for row in fixture["impacts"]]
        assert movements == sorted(movements, reverse=True)
