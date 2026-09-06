from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from epl_forecast.cli import fitted_model
from epl_forecast.data.rules import historical_adjustments
from epl_forecast.models.base import Forecast
from epl_forecast.simulation import (
    EuropeScenario,
    european_places,
    rank_table,
    simulate_season,
    validate_schedule,
)


class FixedHomeWin:
    def sample(self, rng, size):
        return np.ones(size, dtype=int), np.zeros(size, dtype=int)


class FixedModel:
    def __init__(self, as_of):
        self.as_of = as_of

    def predict_match(self, fixture):
        return Forecast((1.0, 0.0, 0.0), FixedHomeWin())


def test_schedule_rejects_missing_duplicate_and_future_results(full_season):
    teams = sorted({m.fixture.home_team_id for m in full_season})
    cutoff = date(2020, 8, 10)
    played = [m for m in full_season if m.available_on <= cutoff]
    remaining = [m.fixture for m in full_season if m.available_on > cutoff]
    validate_schedule(teams, played, remaining, cutoff)
    for bad in (remaining[:-1], remaining[:-1] + [remaining[0]]):
        with pytest.raises(ValueError, match="every ordered"):
            validate_schedule(teams, played, bad, cutoff)
    with pytest.raises(ValueError, match="available"):
        validate_schedule(teams, full_season, [], cutoff)


def test_fixed_remainder_conserves_probabilities_and_scores(full_season):
    teams = sorted({m.fixture.home_team_id for m in full_season})
    cutoff = date(2020, 8, 10)
    played = [m for m in full_season if m.available_on <= cutoff]
    remaining = [m.fixture for m in full_season if m.available_on > cutoff]
    result = simulate_season(FixedModel(cutoff), played, remaining, teams, cutoff, 8, 101)
    repeat = simulate_season(FixedModel(cutoff), played, remaining, teams, cutoff, 8, 101)
    assert result == repeat
    assert result["played_matches"] == 90
    assert result["remaining_matches"] == 290
    assert result["unresolved_decisive_tie_rate"] == 1
    for row in result["teams"]:
        assert row["points_distribution"] == {"57": 1.0}
        assert row["goal_difference_distribution"] == {"0": 1.0}
        assert row["position_probabilities"] == pytest.approx([0.05] * 20)
        assert row["title_probability"] == pytest.approx(0.05)
        assert row["relegation_probability"] == pytest.approx(0.15)
    assert sum(r["title_probability"] for r in result["teams"]) == pytest.approx(1)
    assert sum(r["relegation_probability"] for r in result["teams"]) == pytest.approx(3)


def test_played_scores_are_fixed_and_only_known_deductions_apply(full_season):
    teams = sorted({m.fixture.home_team_id for m in full_season})
    cutoff = date(2020, 10, 1)
    altered = [replace(full_season[0], home_goals=4)] + full_season[1:]
    adjustment = {
        "team_id": teams[0],
        "points": -6,
        "known_on": "2020-09-01",
        "source": "test sanction",
    }
    result = simulate_season(FixedModel(cutoff), altered, [], teams, cutoff, 1, 0, [adjustment])
    row = result["teams"][0]
    assert row["mean_points"] == 51
    assert row["mean_goal_difference"] == 3
    assert result["remaining_matches"] == 0
    with pytest.raises(ValueError, match="not known"):
        simulate_season(
            FixedModel(cutoff),
            altered,
            [],
            teams,
            cutoff,
            1,
            0,
            [{**adjustment, "known_on": "2020-10-02"}],
        )


def test_head_to_head_breaks_decisive_tie_but_not_shared_midtable():
    teams = ["a", "b", "c", "d"]
    points = np.array([60, 60, 30, 20])
    zeros = np.zeros(4, dtype=int)
    head = np.zeros((4, 4), dtype=int)
    away = np.zeros_like(head)
    head[1, 0] = 4
    head[0, 1] = 1
    order, ties, unresolved, used = rank_table(
        teams, points, zeros, zeros, head, away, np.random.default_rng(0), relegated=0
    )
    assert order[:2] == [1, 0]
    assert not ties and not unresolved and used
    head[:] = 3
    away[1, 0] = 2
    order, _, _, _ = rank_table(
        teams, points, zeros, zeros, head, away, np.random.default_rng(0), relegated=0
    )
    assert order[0] == 1
    points[:] = [60, 30, 30, 20]
    _, ties, unresolved, used = rank_table(
        teams, points, zeros, zeros, head, away, np.random.default_rng(0), relegated=0
    )
    assert ties == [(1, 3)] and not used and not unresolved


def test_europe_cup_passdowns_and_external_winner():
    teams = [f"t{i}" for i in range(20)]
    scenario = EuropeScenario("four places, both cup winners in UCL", 4, "t0", "t1")
    places = european_places(teams, scenario)
    assert places["champions_league"] == set(teams[:4])
    assert places["europa_league"] == {"t4", "t5"}
    assert places["conference_league"] == {"t6"}
    scenario = EuropeScenario("five places, cup winners outside", 5, "non-pl-team", "t10")
    places = european_places(teams, scenario)
    assert places["europa_league"] == {"t5", "non-pl-team"}
    assert places["conference_league"] == {"t10"}
    scenario = EuropeScenario("cup winner takes league Europa place", 4, "t4", "t4")
    places = european_places(teams, scenario)
    assert places["europa_league"] == {"t4", "t5"}
    assert places["conference_league"] == {"t6"}


def test_historical_appeal_is_not_backdated():
    def everton_points(cutoff):
        return sum(
            event["points"]
            for event in historical_adjustments("2023-2024", cutoff)
            if event["team_id"] == "everton"
        )

    assert everton_points(date(2023, 11, 17)) == 0
    assert everton_points(date(2023, 11, 18)) == -10
    assert everton_points(date(2024, 2, 26)) == -10
    assert everton_points(date(2024, 2, 27)) == -6
    assert everton_points(date(2024, 4, 9)) == -8


def test_future_score_mutation_cannot_change_a_simulated_remainder(full_season):
    cutoff = date(2020, 8, 10)
    config = {
        "competition_id": "eng-premier-league",
        "train_window_days": 365,
        "min_train_matches": 1,
        "models": [{"id": "poisson", "kind": "league_poisson"}],
    }

    def simulate(matches):
        model, _, _ = fitted_model(matches, config, "poisson", cutoff)
        teams = sorted({m.fixture.home_team_id for m in matches})
        played = [m for m in matches if m.available_on <= cutoff]
        remaining = [m.fixture for m in matches if m.available_on > cutoff]
        return simulate_season(model, played, remaining, teams, cutoff, 12, 42)

    mutated = [
        replace(m, home_goals=15, away_goals=12) if m.available_on > cutoff else m
        for m in full_season
    ]
    assert simulate(full_season) == simulate(mutated)


def test_conditional_european_slots_are_conserved(full_season):
    cutoff = date(2020, 8, 1)
    teams = sorted({m.fixture.home_team_id for m in full_season})
    europe = EuropeScenario("hypothetical cup winners", 5, teams[0], teams[1])
    result = simulate_season(
        FixedModel(cutoff),
        [],
        [m.fixture for m in full_season],
        teams,
        cutoff,
        10,
        10,
        europe=europe,
    )
    for competition, slots in (
        ("champions_league", 5),
        ("europa_league", 2),
        ("conference_league", 1),
    ):
        assert sum(
            row["conditional_europe_probabilities"][competition] for row in result["teams"]
        ) == pytest.approx(slots)


def test_simulation_reuses_one_joint_state_per_path(full_season):
    teams = sorted({m.fixture.home_team_id for m in full_season})
    cutoff = date(2020, 8, 1)

    class UncertainModel:
        as_of = cutoff
        calls = 0

        def predict_match(self, fixture):
            raise AssertionError("Posterior simulation must condition on its shared states")

        def sample_forecast_state(self, rng, size=1):
            self.calls += 1
            strong = rng.random(size) < 0.5

            class States:
                as_of = cutoff

                def sample_scores(self, fixture, rng):
                    home, away = np.zeros(size, dtype=int), np.zeros(size, dtype=int)
                    if fixture.home_team_id == teams[0]:
                        home, away = strong.astype(int), (~strong).astype(int)
                    if fixture.away_team_id == teams[0]:
                        home, away = (~strong).astype(int), strong.astype(int)
                    return home, away

            states = States()
            states.size = size
            return states

    model = UncertainModel()
    result = simulate_season(model, [], [m.fixture for m in full_season], teams, cutoff, 64, 13)
    assert model.calls == 1
    assert result["state_uncertainty"] == "posterior"
    assert set(result["teams"][0]["points_distribution"]) == {"0", "114"}
    assert sum(t["title_probability"] for t in result["teams"]) == pytest.approx(1)
    assert sum(t["relegation_probability"] for t in result["teams"]) == pytest.approx(3)
