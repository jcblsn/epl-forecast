from datetime import date, timedelta

import numpy as np
import pytest

from epl_forecast.research.player_layer import (
    PlayerLayer,
    _mark_values,
    design,
    player_state,
)
from epl_forecast.research.player_layer_evaluation import (
    _matrix,
    _offset,
    build_cases,
    chronological_evaluation,
    crps,
    fit_poisson_ridge,
    paired_bootstrap,
    target_window,
    transfer_episodes,
)
from epl_forecast.research.player_layer_inspector import compare, decompose, local_log_sd

PL = "eng-premier-league"


def appearance(pid="p1", day=date(2024, 8, 1), team="arsenal", **kwargs):
    row = {
        "player_id": pid,
        "player_name": pid,
        "match_id": f"{team}-{day}-{kwargs.get('match_suffix', '')}",
        "team_id": team,
        "competition_id": PL,
        "season_id": "2024-2025",
        "kickoff_time": f"{day}T14:00:00+00:00",
        "position": "FWD",
        "starts": 1,
        "minutes": 90,
        "goals": None,
        "assists": 0,
        "shots": 2,
        "shots_on_target": 1,
        "saves": None,
        "yellow_cards": 0,
        "red_cards": 0,
        "rating": 7.0,
        "passes_total": 30,
        "key_passes": 1,
        "pass_accuracy": "24",
        "tackles": None,
        "interceptions": None,
        "duels_total": 8,
        "duels_won": 4,
        "dribbles_attempted": None,
        "dribbles_successful": None,
        "fouls_drawn": None,
        "fouls_committed": None,
        "team_xg": 1.5,
        "opponent_xg": 1.0,
        "process_xg": 0.4,
        "process_xa": 0.1,
        "process_shots": 2,
        "process_minutes": 90,
        "process_records": 1,
        "provider": "api_football",
        "evidence_basis": "retrospective",
        "retrieved_at": "2026-09-09T12:00:00+00:00",
    }
    row.pop("match_suffix", None)
    row.update({k: v for k, v in kwargs.items() if k != "match_suffix"})
    return row


def history(pid="p1", count=20, start=date(2024, 8, 1), **kwargs):
    return [
        appearance(pid, start + timedelta(days=7 * i), match_suffix=f"{pid}{i}", **kwargs)
        for i in range(count)
    ]


def population(count=40, start=date(2024, 8, 1), length=12):
    rows = []
    for index in range(count):
        rows.extend(
            history(
                f"pool{index}",
                length,
                start,
                team=f"club{index % 8}",
                process_xg=0.1 + 0.05 * (index % 8),
                process_xa=0.05 + 0.02 * (index % 5),
                team_xg=1.0 + 0.2 * (index % 6),
            )
        )
    return rows


def test_provider_zero_is_read_as_zero_and_missing_detail_stays_missing():
    values, available = _mark_values(appearance())
    assert values["goals"] == 0.0 and available["goals"]
    assert values["saves"] == 0.0 and available["saves"]
    assert values["key_passes"] == 1.0 and available["key_passes"]
    bare = appearance(rating=None, passes_total=None, duels_total=None, pass_accuracy=None)
    values, available = _mark_values(bare)
    assert values["shots"] == 2.0 and available["shots"]
    assert not available["key_passes"]
    assert not available["rating"]


def test_pass_accuracy_is_read_as_a_completed_pass_count():
    values, _ = _mark_values(appearance(passes_total=30, pass_accuracy="24"))
    assert values["passes_completed"] == 24.0
    assert values["passes_completed"] <= values["passes_total"]


def test_many_to_one_process_records_are_not_collapsed():
    _, available = _mark_values(appearance(process_records=2))
    assert not available["xg"] and not available["xa"]


def test_estimates_use_only_evidence_before_the_cutoff():
    rows = history(count=6)
    layer = PlayerLayer(rows)
    cutoff = date(2024, 8, 22)
    before = player_state(layer, "p1", cutoff)
    future = history("p1", 4, date(2025, 1, 1), process_xg=9.0)
    later = PlayerLayer([*rows, *future])
    assert player_state(later, "p1", cutoff).long["xg"] == before.long["xg"]
    assert target_window(later, "p1", cutoff, 400, "xg")["total"] > 0


def test_prospective_evidence_waits_for_its_capture_date():
    row = appearance(evidence_basis="observed", retrieved_at="2025-01-01T00:00:00+00:00")
    layer = PlayerLayer([row, *history("p2", 4)])
    assert layer.aggregate("p1", date(2024, 9, 1).toordinal(), "xg", 240)["appearances"] == 0
    assert layer.aggregate("p1", date(2025, 6, 1).toordinal(), "xg", 240)["appearances"] == 1


def test_shrinkage_pulls_a_thin_record_toward_the_role_population():
    rows = [*population(), *history("thin", 1, process_xg=3.0)]
    layer = PlayerLayer(rows)
    state = player_state(layer, "thin", date(2025, 6, 1))
    pool = state.population["xg"]["by_role"]["FWD"]
    assert state.long["xg"]["raw_rate"] > state.long["xg"]["rate"] > pool


def test_thin_evidence_widens_the_player_local_uncertainty():
    rows = [*population(), *history("thin", 1), *history("deep", 30)]
    layer = PlayerLayer(rows)
    cutoff = date(2025, 8, 1)
    thin = player_state(layer, "thin", cutoff)
    deep = player_state(layer, "deep", cutoff)
    assert local_log_sd(thin, "xg", "long_rate") > local_log_sd(deep, "xg", "long_rate")


def test_identity_and_estimate_survive_a_club_change():
    rows = [
        *population(),
        *history("mover", 10, date(2024, 8, 1), team="arsenal"),
        *history("mover", 10, date(2025, 3, 1), team="chelsea"),
    ]
    layer = PlayerLayer(rows)
    state = player_state(layer, "mover", date(2025, 3, 5))
    assert state.club == "chelsea"
    assert state.long["xg"]["appearances"] == 11
    episodes = transfer_episodes(layer, "xg", minimum_prior=5.0, minimum_target=2.0)
    moves = [e for e in episodes if e["player_id"] == "mover"]
    assert len(moves) == 1
    assert moves[0]["club_before"] == "arsenal" and moves[0]["club_after"] == "chelsea"
    assert moves[0]["cutoff"] == date(2025, 3, 1)


def test_context_adjustment_separates_the_player_from_a_strong_club():
    strong = history("strong", 20, team="rich", team_xg=3.0, process_xg=0.6)
    ordinary = history("ordinary", 20, team="poor", team_xg=1.0, process_xg=0.4)
    layer = PlayerLayer([*population(), *strong, *ordinary])
    cutoff = date(2025, 8, 1)
    first = player_state(layer, "strong", cutoff)
    second = player_state(layer, "ordinary", cutoff)
    assert first.long["xg"]["rate"] > second.long["xg"]["rate"]
    assert first.share["xg"]["share"] < second.share["xg"]["share"]


def test_unseen_player_falls_back_to_the_pooled_role_design():
    layer = PlayerLayer(population())
    state = player_state(layer, "unknown", date(2025, 6, 1))
    assert state.role == "UNK" and state.club is None
    for candidate in ("long_run", "recent_long", "context_share"):
        _, values = design(state, candidate, "xg")
        assert np.allclose(values, 0.0)
    names, values = design(state, "api_only", "xg")
    rates = [v for name, v in zip(names, values, strict=True) if name.startswith("api_")]
    assert np.allclose(rates, 0.0)
    assert dict(zip(names, values, strict=True))["log_exposure"] < 0


def test_poisson_ridge_recovers_a_planted_relation():
    generator = np.random.default_rng(0)
    matrix = generator.normal(size=(4000, 1))
    offset = np.zeros(4000)
    response = generator.poisson(np.exp(0.5 + 0.8 * matrix[:, 0]))
    model = fit_poisson_ridge(matrix, offset, response)
    assert abs(model["beta"][0] - 0.5) < 0.1
    assert abs(model["beta"][1] / model["scale"][0] - 0.8) < 0.1


def test_crps_rewards_a_sharper_correct_forecast():
    generator = np.random.default_rng(1)
    sharp = generator.normal(2.0, 0.2, 4096)
    vague = generator.normal(2.0, 2.0, 4096)
    assert crps(sharp, 2.0) < crps(vague, 2.0)


def test_paired_bootstrap_clusters_by_player():
    left = [{"player_id": "a", "cutoff": str(i), "crps": 1.0} for i in range(50)] + [
        {"player_id": f"p{i}", "cutoff": "0", "crps": 1.0} for i in range(10)
    ]
    right = [dict(row, crps=0.0) for row in left]
    result = paired_bootstrap(left, right)
    assert result["players"] == 11 and result["cases"] == 60
    assert result["difference"] == pytest.approx(1.0)


def test_pairwise_comparison_separates_mapping_and_player_uncertainty():
    rows = [
        *population(length=40),
        *history("thin", 1),
        *history("deep", 40, process_xg=0.9),
    ]
    layer = PlayerLayer(rows)
    cutoff = date(2025, 8, 1)
    cases = build_cases(
        layer, [date(2025, 1, 1), date(2025, 2, 1)], 120, "xg", minimum_exposure=0.5
    )
    names, matrix = _matrix(cases, "long_run", "xg")
    model = fit_poisson_ridge(
        matrix, _offset(cases, "xg"), np.array([c["target_total"] for c in cases])
    )
    model["names"] = names
    deep = player_state(layer, "deep", cutoff)
    thin = player_state(layer, "thin", cutoff)
    result = compare(model, deep, thin, "long_run", "xg")
    assert result["log_ratio"] > 0
    assert result["player_local_log_sd"] > 0
    decomposition = decompose(model, deep, "long_run", "xg")
    assert decomposition["contributions"][0]["feature"] == "long_rate"
    assert decomposition["uncertainty"]["mapping_log_sd"] > 0


def test_chronological_evaluation_scores_every_candidate_on_identical_cases():
    rows = population(count=60, start=date(2024, 1, 1), length=100)
    layer = PlayerLayer(rows)
    cutoffs = [date(2024, m, 1) for m in range(2, 13)]
    result = chronological_evaluation(layer, "xg", cutoffs, 60, date(2024, 8, 1))
    scored = result["scored"]
    keys = {
        name: {(s["player_id"], s["cutoff"]) for s in values} for name, values in scored.items()
    }
    assert len({frozenset(v) for v in keys.values()}) == 1
    assert all(len(v) > 0 for v in scored.values())
