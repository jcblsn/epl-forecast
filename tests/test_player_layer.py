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
    assert target_window(later, "p1", cutoff, 120, "xg")["total"] > 0


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
    episodes = transfer_episodes(
        layer, "xg", minimum_prior=5.0, minimum_target=2.0, horizon_days=60
    )
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


def test_combined_mark_is_the_sum_of_its_components():
    values, available = _mark_values(appearance(process_xg=0.4, process_xa=0.1))
    assert values["xg_plus_xa"] == pytest.approx(0.5)
    assert available["xg_plus_xa"]
    _, unavailable = _mark_values(appearance(process_records=None))
    assert not unavailable["xg_plus_xa"]


def test_combined_candidate_reads_the_summed_mark_not_the_component():
    rows = [
        *population(),
        *history("shooter", 20, process_xg=0.8, process_xa=0.0),
        *history("creator", 20, process_xg=0.0, process_xa=0.8),
    ]
    layer = PlayerLayer(rows)
    cutoff = date(2025, 8, 1)
    shooter = player_state(layer, "shooter", cutoff)
    creator = player_state(layer, "creator", cutoff)
    _, combined_shooter = design(shooter, "combined_long", "xg")
    _, combined_creator = design(creator, "combined_long", "xg")
    assert combined_shooter == pytest.approx(combined_creator)
    _, own_shooter = design(shooter, "long_run", "xg")
    _, own_creator = design(creator, "long_run", "xg")
    assert own_shooter[0] > own_creator[0]


def test_pairwise_comparison_reports_role_relative_and_absolute_scales():
    rows = [
        *population(length=40),
        *history("striker", 40, process_xg=0.7, position="FWD"),
        *history("winger", 40, process_xg=0.35, position="MID"),
    ]
    layer = PlayerLayer(rows)
    cases = build_cases(
        layer, [date(2025, 1, 1), date(2025, 2, 1)], 120, "xg", minimum_exposure=0.5
    )
    names, matrix = _matrix(cases, "long_run", "xg")
    model = fit_poisson_ridge(
        matrix, _offset(cases, "xg"), np.array([c["target_total"] for c in cases])
    )
    model["names"] = names
    cutoff = date(2025, 8, 1)
    striker = player_state(layer, "striker", cutoff)
    winger = player_state(layer, "winger", cutoff)
    result = compare(model, striker, winger, "long_run", "xg")
    assert result["left_role"] == "FWD" and result["right_role"] == "MID"
    pools = [state.population["xg"]["by_role"][state.role] for state in (striker, winger)]
    assert result["rate_log_ratio"] - result["log_ratio"] == pytest.approx(
        np.log(pools[0] / pools[1])
    )
    assert result["rate_interval_95"][0] < result["rate_ratio"] < result["rate_interval_95"][1]
    assert result["rate_ratio"] > 1.5


@pytest.mark.parametrize("horizon", [90, 180, 240])
def test_transfer_target_uses_explicit_horizon(horizon):
    start = date(2025, 1, 1)
    rows = [
        *history("mover", 12, date(2024, 8, 1), team="arsenal"),
        *history("mover", 40, start, team="chelsea"),
    ]
    episodes = transfer_episodes(PlayerLayer(rows), "xg", horizon_days=horizon)
    assert len(episodes) == 1
    episode = episodes[0]
    count = len(range(0, horizon, 7))
    assert episode["target_appearances"] == count
    assert episode["target_total"] == pytest.approx(count * 0.4)
    assert episode["horizon_days"] == horizon


def test_transfer_evaluator_rejects_mismatched_horizons():
    from epl_forecast.research.player_layer_evaluation import evaluate_transfers

    with pytest.raises(ValueError, match="horizons must agree"):
        evaluate_transfers(None, "xg", [{"horizon_days": 240}], [], horizon_days=90)


def test_api_design_and_uncertainty_ignore_player_process_coverage():
    from epl_forecast.research.player_layer_evaluation import evidence_exposure

    rows = [*population(), *history("p1", 30)]
    stripped = [dict(row, process_records=None, team_xg=None) for row in rows]
    cutoff = date(2025, 8, 1)
    states = [player_state(PlayerLayer(values), "p1", cutoff) for values in (rows, stripped)]
    for candidate in ("api_only", "api_rating"):
        left, right = [design(state, candidate, "xg") for state in states]
        assert left[0] == right[0]
        assert left[1] == pytest.approx(right[1])
        assert "process_coverage" not in left[0]
        assert evidence_exposure({"state": states[0]}, candidate) == evidence_exposure(
            {"state": states[1]}, candidate
        )


def test_depth_matched_api_excludes_older_history_but_full_api_retains_it():
    old = history("p1", 20, date(2023, 1, 1), shots=20, process_records=None)
    current = [*population(), *history("p1", 20)]
    cutoff = date(2025, 1, 1)
    states = [player_state(PlayerLayer(rows), "p1", cutoff) for rows in (current, [*old, *current])]
    matched = [design(state, "api_depth_matched", "xg")[1] for state in states]
    assert matched[0] == pytest.approx(matched[1])
    full = [design(state, "api_only", "xg")[1] for state in states]
    assert not np.allclose(full[0], full[1])
    assert states[1].api["process_window_start"] == "2024-08-01"


def test_signal_reliability_includes_sparse_zeros_and_excludes_missing_detail():
    from epl_forecast.research.player_signals import appearance_coverage

    rows = history(count=8, shots=None, key_passes=None)
    rows[0]["shots"] = 2
    audit = appearance_coverage(rows)
    assert audit["by_role"]["shots"]["FWD"]["observed"] == 1
    assert audit["reliability"]["shots"]["player_seasons"] == 1
    assert audit["reliability"]["key_passes"]["player_seasons"] == 1
    for row in rows:
        row.update(rating=None, passes_total=None, duels_total=None, pass_accuracy=None)
    audit = appearance_coverage(rows)
    assert "key_passes" not in audit["reliability"]


def test_targets_do_not_treat_a_truncated_horizon_as_complete():
    layer = PlayerLayer(
        [
            *history("mover", 12, date(2024, 8, 1), team="arsenal"),
            *history("mover", 10, date(2025, 1, 1), team="chelsea"),
        ]
    )
    assert target_window(layer, "mover", date(2025, 1, 1), 60, "xg") is not None
    assert target_window(layer, "mover", date(2025, 1, 1), 90, "xg") is None
    assert transfer_episodes(layer, "xg", horizon_days=90) == []
