from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from epl_forecast.research.player_prior import PlayerPriorFeatures, PriorConfig

PL = "eng-premier-league"
SEASON = "2024-2025"


def appearance(pid="p1", day=date(2024, 8, 1), **kwargs):
    return {
        "player_id": pid,
        "player_name": pid,
        "match_id": f"{pid}-{day}",
        "team_id": "arsenal",
        "competition_id": PL,
        "season_id": SEASON,
        "kickoff_time": f"{day}T14:00:00+00:00",
        "position": "MID",
        "starts": 1,
        "minutes": 90,
        "passes_total": 40,
        "shots": 2,
        "key_passes": 1,
        "duels_won": 5,
        "saves": None,
        "rating": 7.0,
        "provider": "api_football",
        "evidence_basis": "retrospective",
        "retrieved_at": "2026-09-09T12:00:00+00:00",
        **kwargs,
    }


def features(source, pid="p1", cutoff=date(2024, 8, 10), **kwargs):
    return source.for_player(pid, cutoff, PL, SEASON, **kwargs)


def population():
    return [appearance(f"pool{i}") for i in range(100)]


def test_cutoff_ignores_target_statistics_minutes_and_same_london_date():
    past = [appearance()]
    future = appearance(day=date(2024, 8, 10), minutes=120, shots=500, position="GK")
    same_london_date = appearance(
        "p2",
        kickoff_time="2024-08-09T23:30:00+00:00",
        shots=1000,
    )
    original = features(PlayerPriorFeatures(past))
    changed = features(PlayerPriorFeatures([*past, future, same_london_date]))
    assert changed == original
    assert original.latest_evidence_date == date(2024, 8, 1)
    assert features(PlayerPriorFeatures([future])).effective_minutes == 0


def test_backfills_follow_fixture_dates_but_captured_observations_respect_publication():
    retro = features(PlayerPriorFeatures([appearance()]))
    captured = features(PlayerPriorFeatures([appearance(evidence_basis="captured")]))
    assert retro.effective_minutes > 0 and captured.effective_minutes == 0


def test_recent_and_long_features_move_without_target_information():
    rows = [*population(), appearance(shots=1)]
    source = PlayerPriorFeatures(rows)
    before = features(source)
    added = appearance(day=date(2024, 8, 11), shots=12)
    source = PlayerPriorFeatures([*rows, added])
    assert features(source) == before
    after = features(source, cutoff=date(2024, 8, 12))
    assert after.values[1] > before.values[1]
    assert after.values[6] > before.values[6]
    assert after.local_sd < before.local_sd


def test_sparse_rates_shrink_and_stale_uncertainty_widens():
    base = population()
    one = features(PlayerPriorFeatures([*base, appearance(shots=10)]))
    many_rows = [appearance(day=date(2024, 8, 1) + timedelta(days=i), shots=10) for i in range(8)]
    source = PlayerPriorFeatures([*base, *many_rows])
    many = features(source)
    stale = features(source, cutoff=date(2025, 2, 10))
    assert 0 < one.values[1] < many.values[1]
    assert many.local_sd < one.local_sd
    assert many.local_sd < stale.local_sd
    assert stale.days_since_meaningful_minutes > many.days_since_meaningful_minutes


def test_transfers_keep_identity_features_and_reference_squads_remain_with_clubs():
    rows = [appearance(day=date(2024, 8, 1)), appearance(day=date(2024, 8, 8), team_id="chelsea")]
    source = PlayerPriorFeatures(rows)
    same_club = PlayerPriorFeatures([{**r, "team_id": "arsenal"} for r in rows])
    assert features(source) == features(same_club)
    assert source.reference_weights("arsenal", date(2024, 8, 10)) == pytest.approx({"p1": 1.0})
    assert source.reference_weights("chelsea", date(2024, 8, 10)) == pytest.approx({"p1": 1.0})
    assert source.reference_weights("chelsea", date(2024, 8, 8)) == {}


def test_missing_is_not_zero_and_has_no_statistic_exposure():
    missing = features(PlayerPriorFeatures([*population(), appearance(shots=None)]))
    zero = features(PlayerPriorFeatures([*population(), appearance(shots=0)]))
    assert missing.observed_minutes[1] == 0 and zero.observed_minutes[1] > 0
    assert missing.values[1] == 0 and zero.values[1] < 0
    assert missing.relevant_minutes < zero.relevant_minutes
    assert missing.local_sd > zero.local_sd


def test_unseen_player_gets_pooled_role_design_and_sparse_uncertainty():
    source = PlayerPriorFeatures([])
    unseen = features(source, "new")
    assert unseen.role == "UNK" and unseen.age is None
    assert unseen.effective_minutes == unseen.effective_matches == 0
    assert unseen.values[:10] == (0.0,) * 10
    assert np.allclose(source.design(unseen).reshape(4, -1)[0], np.array(unseen.values) / 4)
    assert np.isfinite(unseen.local_sd) and unseen.local_sd > 0.4


def test_age_uses_only_prior_season_profile_and_conflicts_remain_unknown():
    profile = {
        "provider": "api_football",
        "player_id": "p1",
        "birth_date": date(2000, 1, 1),
        "available_on": date(2025, 7, 1),
        "evidence_basis": "retrospective",
    }
    assert features(PlayerPriorFeatures([appearance()], [profile])).age is None
    profile["available_on"] = date(2024, 7, 1)
    known = features(PlayerPriorFeatures([appearance()], [profile]))
    assert 24 < known.age < 25
    conflict = {**profile, "birth_date": date(1990, 1, 1)}
    assert features(PlayerPriorFeatures([appearance()], [profile, conflict])).age is None


def test_reproduction_rating_ablation_and_provider_boundary():
    rows = [*population(), appearance(shots=3)]
    a, b = PlayerPriorFeatures(rows), PlayerPriorFeatures(list(reversed(rows)))
    assert features(a) == features(b)
    no_rating = PlayerPriorFeatures([{**r, "rating": 0} for r in rows])
    assert features(a) == features(no_rating)
    assert (
        features(a, include_rating=True).values != features(no_rating, include_rating=True).values
    )
    assert len(features(a, include_rating=True).values) == len(a.names(True))
    with pytest.raises(ValueError, match="API-FOOTBALL"):
        PlayerPriorFeatures([appearance(provider="fpl")])
    with pytest.raises(ValueError, match="positive"):
        replace(PriorConfig(), shrinkage_minutes=0)
