from dataclasses import replace
from datetime import date

import numpy as np
import pytest

from epl_forecast.cli import fitted_model
from epl_forecast.data.rules import historical_adjustments, league_rules, reviewed_rules_evidence
from epl_forecast.models.base import Forecast
from epl_forecast.simulation import (
    EuropeScenario,
    european_places,
    rank_table,
    simulate_season,
    validate_schedule,
)


def test_reviewed_efl_edition_matches_current_boundaries_only():
    evidence = reviewed_rules_evidence("eng-championship", "2026-2027")
    rules = league_rules("eng-championship", "2026-2027")
    assert evidence["edition"] == "EFL Regulations 2026/27"
    assert evidence["automatic_promotion"] == rules.automatic_promotion == 2
    assert evidence["playoff_end"] == rules.playoff_end == 8
    assert evidence["relegated"] == rules.relegated == 3
    assert reviewed_rules_evidence("eng-championship", "2027-2028") is None
    assert reviewed_rules_evidence("eng-premier-league", "2026-2027") is None


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


def test_championship_projection_conserves_promotion_and_playoff_slots():
    from types import SimpleNamespace

    from epl_forecast.schema import Fixture, Match, fixture_id

    teams = [f"club-{i}" for i in range(24)]
    day = date(2026, 8, 10)
    games = [
        Match(
            Fixture(
                fixture_id("eng-championship", "2026-2027", h, a),
                "eng-championship",
                "2026-2027",
                day,
                h,
                a,
            ),
            1,
            1,
        )
        for h in teams
        for a in teams
        if h != a
    ]
    cutoff = date(2026, 8, 11)
    result = simulate_season(SimpleNamespace(as_of=cutoff), games, [], teams, cutoff, 10, 7)
    assert len(result["teams"]) == 24
    assert sum(r["automatic_promotion_probability"] for r in result["teams"]) == pytest.approx(2)
    assert sum(r["playoff_qualification_probability"] for r in result["teams"]) == pytest.approx(6)
    assert sum(r["relegation_probability"] for r in result["teams"]) == pytest.approx(3)
    assert all("top_four_probability" not in r for r in result["teams"])
    assert result["ranking_rules"] == "efl"
    assert result["disciplinary_tiebreaks_available"] is False


@pytest.mark.parametrize(
    "season,boundary", [("2025-2026", 2), ("2025-2026", 6), ("2026-2027", 8), ("2026-2027", 21)]
)
def test_efl_decisive_boundaries_and_head_to_head(season, boundary):
    teams = [f"t{i}" for i in range(24)]
    points = np.arange(24, 0, -1) * 3
    a, b = boundary - 1, boundary
    points[b] = points[a]
    zeros = np.zeros(24, dtype=int)
    head = np.zeros((24, 24), dtype=int)
    goals = np.zeros_like(head)
    kwargs = dict(
        rules=league_rules("eng-championship", season),
        head_goals=goals,
        wins=zeros,
        away_goals=zeros,
    )
    _, ties, unresolved, used = rank_table(
        teams, points, zeros, zeros, head, goals, np.random.default_rng(0), **kwargs
    )
    assert ties == [(a, b + 1)] and unresolved and used
    head[b, a], head[a, b] = 4, 1
    order, ties, unresolved, used = rank_table(
        teams, points, zeros, zeros, head, goals, np.random.default_rng(0), **kwargs
    )
    assert order[a : b + 1] == [b, a]
    assert not ties and not unresolved and used


@pytest.mark.parametrize(
    "criterion",
    [
        "head_points",
        "head_difference",
        "head_goals",
        "wins",
        "away_goals",
        "discipline",
        "sendings_off",
    ],
)
def test_efl_criteria_precedence_in_three_team_midtable_tie(criterion):
    teams = ["leader", "a", "b", "c", "last"]
    points = np.array([90, 50, 50, 50, 10])
    zeros = np.zeros(5, dtype=int)
    head = np.zeros((5, 5), dtype=int)
    goals = np.zeros_like(head)
    wins, away, discipline, reds = (zeros.copy() for _ in range(4))
    if criterion == "head_points":
        head[2, 1] = 3
        goals[1, 2] = 5
    elif criterion == "head_difference":
        goals[2, 1] = 2
    elif criterion == "head_goals":
        goals[2, 3] = goals[3, 2] = 2
        goals[1, 2] = goals[2, 1] = 1
    elif criterion == "wins":
        wins[2] = 20
        away[1] = 50
    elif criterion == "away_goals":
        away[2] = 20
        discipline[2] = 100
    elif criterion == "discipline":
        discipline[:] = 20
        discipline[2] = 10
        reds[2] = 5
    else:
        reds[:] = 2
        reds[2] = 1
    order, _, _, used = rank_table(
        teams,
        points,
        zeros,
        zeros,
        head,
        np.zeros_like(head),
        np.random.default_rng(0),
        rules=league_rules("eng-championship", "2026-2027"),
        head_goals=goals,
        wins=wins,
        away_goals=away,
        disciplinary_points=discipline,
        serious_sendings_off=reds,
    )
    assert order[1] == 2 and used


def test_efl_does_not_use_head_to_head_away_goals():
    teams = ["a", "b"]
    zeros = np.zeros(2, dtype=int)
    head = np.array([[0, 3], [3, 0]])
    goals = np.array([[0, 2], [2, 0]])
    away = np.array([[0, 1], [2, 0]])
    _, ties, unresolved, _ = rank_table(
        teams,
        zeros,
        zeros,
        zeros,
        head,
        away,
        np.random.default_rng(0),
        rules=league_rules("eng-championship", "2026-2027"),
        head_goals=goals,
        wins=zeros,
        away_goals=zeros,
    )
    assert ties == [(0, 2)] and unresolved
