from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from epl_forecast.research.roster_bridge import (
    BASELINES,
    attainable_gain,
    chronological_bridge,
    design,
    distribution,
    fit_mapping,
    permuted_gain,
    reference_roster,
    representation_audit,
    roster_delta,
)


def player(shooting, creation):
    return SimpleNamespace(
        traits=(
            SimpleNamespace(mean=shooting, variance=0.2, appearances=10),
            SimpleNamespace(mean=creation, variance=0.1, appearances=10),
        )
    )


def test_core_xi_reference_preserves_only_the_most_used_identities():
    rosters = {
        "first": {f"p{i}": 1 for i in range(11)} | {"rotation": 0.5},
        "second": {f"p{i}": 1 for i in range(10)} | {"p10": 0.2, "rotation": 1},
    }
    core = reference_roster(rosters, ["first", "second"], "core_xi")
    average = reference_roster(rosters, ["first", "second"], "average")
    assert len(core) == 11
    assert sum(core.values()) == 11
    assert set(core) < set(average)
    assert "rotation" in core
    assert "p10" not in core


def baseline(day, home_goals=1, away_goals=0, model_id=BASELINES[0]):
    return {
        "model_id": model_id,
        "match_id": str(day),
        "season_id": "2024-2025",
        "match_date": str(day),
        "forecast_as_of": str(day),
        "home_goals": home_goals,
        "away_goals": away_goals,
        "outcome": "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D",
        "expected_home_goals": 1.5,
        "expected_away_goals": 1.0,
        "effective_specifications": 1.0,
        "log_home_rate_mean": np.log(1.5) - 0.05,
        "log_away_rate_mean": -0.05,
        "log_home_rate_variance": 0.1,
        "log_away_rate_variance": 0.1,
        "log_rate_covariance": 0.01,
    }


def cases(count, seed=0):
    generator = np.random.default_rng(seed)
    result = []
    for i in range(count):
        day = date(2024, 1, 1) + timedelta(days=i)
        changes = generator.normal(0, 0.5, size=(2, 2))
        goals = generator.poisson(np.array([1.5, 1.0]) * np.exp(changes @ [0.6, 0.3]))
        result.append(
            {
                "match_id": str(day),
                "match_date": day,
                "cutoff": day,
                "home": {
                    "mean": changes[0],
                    "changed_match_equivalents": float(np.abs(changes[0]).sum()),
                },
                "away": {
                    "mean": changes[1],
                    "changed_match_equivalents": float(np.abs(changes[1]).sum()),
                },
                "baselines": {m: baseline(day, *goals, model_id=m) for m in BASELINES},
                "slices": {},
            }
        )
    return result


def test_identical_personnel_cancel_mean_and_uncertainty_exactly():
    roster = {"elite": 1.0, "ordinary": 0.5}
    people = {"elite": player(0.9, 0.1), "ordinary": player(0.1, 0.2)}
    delta = roster_delta(roster, roster, people)
    assert delta["mean"] == pytest.approx([0, 0])
    assert delta["variance"] == pytest.approx([0, 0])
    assert delta["changed_match_equivalents"] == 0


def test_roster_replacement_preserves_distinct_traits_and_shared_draw_cancellation():
    people = {"shooter": player(0.9, 0.1), "creator": player(0.1, 0.9), "regular": player(0.2, 0.2)}
    delta = roster_delta({"shooter": 1, "regular": 1}, {"creator": 1, "regular": 1}, people)
    assert delta["mean"] == pytest.approx([0.8, -0.8])
    assert delta["variance"] == pytest.approx([0.4, 0.2])


def test_chronological_mapping_recovers_a_planted_personnel_effect():
    fitted = fit_mapping(cases(4000), BASELINES[0])
    assert fitted["beta"] == pytest.approx([0.6, 0.3], abs=0.06)
    assert fitted["design_rank"] == 2


def test_bridge_preserves_m7_state_covariance_and_shifts_only_own_attack():
    row = baseline(date(2024, 8, 1), model_id=BASELINES[1])
    original = distribution(row)
    shifted = distribution(row, [0.2, 0])
    assert shifted.home_rate == pytest.approx(original.home_rate * np.exp(0.2))
    assert shifted.away_rate == pytest.approx(original.away_rate)
    assert shifted.log_covariance == pytest.approx(original.log_covariance)


def test_future_outcomes_cannot_change_an_earlier_mapping_or_prediction():
    history = cases(50)
    first = history[40]["cutoff"]
    expected = chronological_bridge(history, first, minimum_training=20)
    for case in history[40:]:
        for row in case["baselines"].values():
            row["home_goals"] = 20
            row["outcome"] = "H"
    actual = chronological_bridge(history, first, minimum_training=20)
    assert actual["mappings"][:2] == expected["mappings"][:2]
    assert actual["predictions"][1]["p_home"] == expected["predictions"][1]["p_home"]
    assert actual["mappings"][0]["last_training_match"] < str(first)


def test_attainable_gain_bounds_any_chronological_mapping_on_the_same_design():
    history = cases(600)
    matrix, response, offset, _ = design(history, BASELINES[0])
    ceiling = attainable_gain(matrix, response, offset)
    fitted = fit_mapping(history, BASELINES[0])
    eta = offset + matrix @ np.asarray(fitted["beta"])
    chronological = float(np.sum(response * eta - np.exp(eta)))
    reference = float(np.sum(response * offset - np.exp(offset)))
    assert ceiling["gain"] >= chronological - reference
    assert ceiling["team_matches"] == 1200


def test_permutation_null_rejects_a_design_carrying_no_fixture_signal():
    history = cases(400)
    matrix, response, offset, _ = design(history, BASELINES[0])
    generator = np.random.default_rng(3)
    scrambled = generator.normal(0, 0.5, size=matrix.shape)
    assert permuted_gain(matrix, response, offset, draws=60)["p_value"] < 0.1
    assert permuted_gain(scrambled, response, offset, draws=60)["p_value"] > 0.1


def test_representation_audit_reports_strata_by_personnel_change():
    history = cases(200)
    for index, case in enumerate(history):
        for side in ("home", "away"):
            case[side]["changed_match_equivalents"] = float(index % 8)
    audit = representation_audit(history, BASELINES[0], thresholds=(0.0, 4.0), draws=20)
    assert [s["minimum_changed_match_equivalents"] for s in audit["strata"]] == [0.0, 4.0]
    assert audit["strata"][0]["share_of_team_matches"] == 1.0
    assert audit["strata"][1]["team_matches"] < audit["strata"][0]["team_matches"]
    assert audit["changed_match_equivalents"]["share_at_least_2"] == pytest.approx(0.75)
