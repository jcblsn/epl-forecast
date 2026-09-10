import numpy as np

from epl_forecast.models.promotion import CHAMPIONSHIP, PL
from epl_forecast.research.cross_division_diagnostics import (
    TRUE_LEVEL,
    coordinate_equivalence,
    crossing_sensitivity,
    recovery_checks,
    two_division_history,
)


def test_the_generator_produces_both_divisions_and_matched_xg_rows():
    matches, observations, quality, _ = two_division_history(0, seasons=2, clubs=6, crossings=2)
    competitions = {m.fixture.competition_id for m in matches}
    assert competitions == {PL, CHAMPIONSHIP}
    assert len(observations) == len(matches)
    for match, row in zip(matches, observations, strict=True):
        assert row["match_id"] == match.fixture.match_id
        assert (row["home_goals"], row["away_goals"]) == (match.home_goals, match.away_goals)
        assert row["available_on"] > row["match_date"]
    assert len(quality) == 12


def test_the_lower_division_scores_less_at_the_planted_level():
    matches, _, _, _ = two_division_history(1, seasons=3, clubs=8, crossings=0)
    goals = {}
    for competition in (PL, CHAMPIONSHIP):
        rows = [m for m in matches if m.fixture.competition_id == competition]
        goals[competition] = np.mean([m.home_goals + m.away_goals for m in rows])
    assert goals[CHAMPIONSHIP] < goals[PL]


def test_recovery_reports_coverage_for_both_observation_models():
    report = recovery_checks(replicates=2, seasons=2)
    assert report["true_division_level"] == TRUE_LEVEL
    assert [row["model"] for row in report["results"]] == ["goals_only", "goals_xg"]
    for row in report["results"]:
        assert 0.0 <= row["level_covered"] <= 1.0
        assert row["quality_correlation"] > 0.5


def test_more_observed_transitions_do_not_widen_the_division_level():
    rows = crossing_sensitivity(replicates=2, seasons=2, counts=(0, 4))
    assert rows[1]["level_posterior_sd"] <= rows[0]["level_posterior_sd"]


def test_the_attack_defence_rotation_is_numerically_exact():
    report = coordinate_equivalence(seasons=2)
    assert report["mean_max_absolute_difference"] < 1e-12
    assert report["covariance_max_absolute_difference"] < 1e-12
