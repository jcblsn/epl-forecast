from datetime import date

import numpy as np
import pytest

from epl_forecast.models.promotion import CHAMPIONSHIP, PL
from epl_forecast.research.cross_division_diagnostics import (
    TRUE_SCORING_LEVEL,
    coordinate_equivalence,
    crossing_sensitivity,
    promotion_calibration,
    recovery_checks,
    scoring_level_prior_sensitivity,
    two_division_history,
)
from epl_forecast.schema import Fixture, fixture_id


def test_the_generator_produces_both_divisions_and_matched_xg_rows():
    history = two_division_history(0, seasons=2, clubs=6, crossings=2)
    matches, observations, quality = history.matches, history.observations, history.quality
    competitions = {m.fixture.competition_id for m in matches}
    assert competitions == {PL, CHAMPIONSHIP}
    assert len(observations) == len(matches)
    for match, row in zip(matches, observations, strict=True):
        assert row["match_id"] == match.fixture.match_id
        assert (row["home_goals"], row["away_goals"]) == (match.home_goals, match.away_goals)
        assert row["available_on"] > row["match_date"]
    assert len(quality) == 12


def test_the_lower_division_scores_less_at_the_planted_level():
    matches = two_division_history(1, seasons=3, clubs=8, crossings=0).matches
    goals = {}
    for competition in (PL, CHAMPIONSHIP):
        rows = [m for m in matches if m.fixture.competition_id == competition]
        goals[competition] = np.mean([m.home_goals + m.away_goals for m in rows])
    assert goals[CHAMPIONSHIP] < goals[PL]


def test_recovery_reports_coverage_for_both_observation_models():
    report = recovery_checks(replicates=2, seasons=2)
    assert report["true_division_scoring_level"] == TRUE_SCORING_LEVEL
    assert [row["model"] for row in report["results"]] == ["goals_only", "goals_xg"]
    for row in report["results"]:
        assert 0.0 <= row["level_covered"] <= 1.0
        assert row["quality_correlation"] > 0.5


def test_more_observed_transitions_do_not_widen_the_division_scoring_level():
    rows = crossing_sensitivity(replicates=2, seasons=2, counts=(0, 4))
    assert rows[1]["level_posterior_sd"] <= rows[0]["level_posterior_sd"]


def test_the_attack_defence_rotation_is_numerically_exact():
    report = coordinate_equivalence(seasons=2)
    assert report["mean_max_absolute_difference"] < 1e-12
    assert report["covariance_max_absolute_difference"] < 1e-12


def test_a_planted_strength_gap_shifts_the_lower_division_population():
    with_gap = two_division_history(0, seasons=2, clubs=6, crossings=0, quality_gap=0.5)
    lower = [v for k, v in with_gap.quality.items() if k.startswith("ch")]
    upper = [v for k, v in with_gap.quality.items() if k.startswith("pl")]
    assert np.mean(lower) < np.mean(upper)
    flat = two_division_history(0, seasons=2, clubs=6, crossings=0, quality_gap=0.0)
    assert flat.transitions == []
    assert with_gap.transitions == []


def test_transitions_record_both_directions_of_every_crossing():
    seasons, crossings = 3, 2
    history = two_division_history(0, seasons=seasons, clubs=6, crossings=crossings)
    assert len(history.transitions) == seasons * crossings * 2
    assert {row["to"] for row in history.transitions} == {PL, CHAMPIONSHIP}
    for row in history.transitions:
        assert row["team_id"] in history.quality


def test_true_log_rates_reproduce_the_generating_scoring_level():
    history = two_division_history(0, seasons=2, clubs=6, crossings=0)
    top = next(m.fixture for m in history.matches if m.fixture.competition_id == PL)
    lower = Fixture(
        fixture_id(CHAMPIONSHIP, top.season_id, top.home_team_id, top.away_team_id),
        CHAMPIONSHIP,
        top.season_id,
        top.match_date,
        top.home_team_id,
        top.away_team_id,
    )
    difference = history.true_log_rates(lower) - history.true_log_rates(top)
    assert difference == pytest.approx([TRUE_SCORING_LEVEL, TRUE_SCORING_LEVEL])


def test_a_carried_state_overstates_promoted_clubs_when_the_divisions_differ():
    """The additive scoring level cannot absorb an absolute population gap."""
    flat = promotion_calibration(replicates=2, seasons=4, quality_gap=0.0, first_matches=5)
    gapped = promotion_calibration(replicates=2, seasons=4, quality_gap=0.5, first_matches=5)

    def promoted(report, model="goals_only"):
        return next(
            row["mean_log_rate_error"]
            for row in report["results"]
            if row["model"] == model and row["slice"] == "promoted"
        )

    assert promoted(gapped) > promoted(flat)
    assert promoted(gapped) > 0


def test_prior_sensitivity_reports_the_scoring_level_range_against_its_posterior_sd():
    history = two_division_history(0, seasons=2, clubs=6, crossings=2)
    report = scoring_level_prior_sensitivity(history.matches, date(2020, 8, 1))
    assert len(report["grid"]) == 27
    assert report["championship_scoring_level_range"] >= 0
    assert report["championship_scoring_level_range_in_posterior_sd"] >= 0
    assert report["observations"] == "goals only"
