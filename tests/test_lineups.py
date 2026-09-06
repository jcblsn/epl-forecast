from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from epl_forecast.data.squads import Availability, Candidate, PlayerHistory, Squad
from epl_forecast.lineups import FORMATIONS, availability_probability, sample_lineups

CUTOFF = datetime(2024, 8, 20, tzinfo=UTC)


def observation(player, day, team="one", season="2024-2025", **extra):
    return {
        "player_season_id": f"{season}:{player}",
        "fpl_player_code": str(player),
        "player_name": f"Player {player}",
        "season_id": season,
        "kickoff_time": f"2024-08-{day:02d}T15:00:00Z",
        "match_id": f"match-{day}",
        "team_id": team,
        "position": "MID",
        "minutes": "90",
        "starts": "1",
        "historical_observed_at": "",
        **extra,
    }


def squad():
    players = []
    for role, count in (("GK", 2), ("DEF", 8), ("MID", 8), ("FWD", 4)):
        for i in range(count):
            players.append(
                Candidate(
                    f"{role}:{i}",
                    "",
                    f"{role} {i}",
                    "one",
                    role,
                    CUTOFF,
                    "test snapshot",
                    ((90, 1), (0, 0)),
                )
            )
    return Squad("one", "2024-2025", CUTOFF, tuple(players), "test snapshot")


def test_candidate_pool_cannot_discover_target_or_future_players():
    rows = [observation(1, 10), observation(2, 12, "two"), observation(3, 20)]
    before = PlayerHistory(rows).retrospective_squad("one", "2024-2025", CUTOFF)
    changed = rows[:2] + [observation(999, 20, minutes="0"), observation(888, 22)]
    after = PlayerHistory(changed).retrospective_squad("one", "2024-2025", CUTOFF)
    assert before == after
    assert [p.player_id for p in before.candidates] == ["fpl:1"]
    assert before.candidates[0].membership_observed_at is None
    assert "retrospective" in before.evidence


def test_club_change_uses_last_past_club_and_does_not_reuse_last_season():
    history = PlayerHistory(
        [observation(1, 10), observation(1, 15, "two"), observation(2, 10, season="2023-2024")]
    )
    assert not history.retrospective_squad("one", "2024-2025", CUTOFF).candidates
    assert len(history.retrospective_squad("two", "2024-2025", CUTOFF).candidates) == 1


def test_publication_time_never_substituted_with_kickoff():
    history = PlayerHistory(
        [observation(1, 10), observation(1, 12, historical_observed_at="2024-08-21T00:00:00Z")]
    )
    assert history.exposure("1", CUTOFF, strict=True) == ()
    assert history.exposure("1", CUTOFF) == ((90, 1),)
    with pytest.raises(ValueError, match="Ambiguous player code"):
        PlayerHistory([observation(1, 10), observation(2, 12, fpl_player_code="1")])


def test_lineups_have_eleven_starters_990_minutes_and_at_most_five_substitutions():
    draws = sample_lineups(squad(), CUTOFF, np.random.default_rng(3), 400)
    assert np.all(draws.starts.sum(axis=1) == 11)
    assert np.all(draws.minutes.sum(axis=1) == 990)
    assert np.all((draws.minutes >= 0) & (draws.minutes <= 90))
    assert np.all(((draws.minutes > 0) & ~draws.starts).sum(axis=1) <= 5)
    assert all(tuple(f) in FORMATIONS for f in draws.formations)
    roles = np.array([p.position for p in draws.candidates])
    assert np.all(draws.starts[:, roles == "GK"].sum(axis=1) == 1)
    assert np.all(draws.minutes[:, roles == "GK"].sum(axis=1) == 90)
    assert np.all(draws.minutes[:, [p.anonymous for p in draws.candidates]] == 0)
    assert 0 < draws.starts[:, 0].mean() < 1


def test_absence_expires_and_replacement_preserves_coherence():
    base = squad()
    assumption = Availability(CUTOFF, 0, CUTOFF + timedelta(days=7), "scenario")
    changed = base.with_availability("GK:0", assumption)
    draws = sample_lineups(changed, CUTOFF, np.random.default_rng(3), 100)
    assert np.all(draws.minutes[:, 0] == 0)
    assert np.all(draws.starts[:, 1])
    assert availability_probability(changed.candidates[0], CUTOFF + timedelta(days=7)) == 1
    assert (
        sample_lineups(changed, CUTOFF + timedelta(days=8), np.random.default_rng(3), 100)
        .starts[:, 0]
        .any()
    )
    with pytest.raises(ValueError, match="outside the candidate"):
        base.with_availability("new-target-player", assumption)
    with pytest.raises(ValueError, match="after cutoff"):
        base.with_availability("GK:0", replace(assumption, observed_at=CUTOFF + timedelta(days=1)))


def test_empty_and_unclassified_squads_use_visible_anonymous_replacements():
    base = replace(squad(), candidates=())
    draws = sample_lineups(base, CUTOFF, np.random.default_rng(8), 20)
    assert np.all(draws.minutes.sum(axis=1) == 990)
    assert all(p.anonymous for p in draws.candidates)
    base = replace(base, candidates=(replace(squad().candidates[0], position="UNK"),))
    draws = sample_lineups(base, CUTOFF, np.random.default_rng(8), 20)
    assert np.all(draws.minutes[:, 0] == 0)


def test_invalid_cutoffs_and_probabilities_fail():
    with pytest.raises(ValueError, match="timezone"):
        replace(squad(), cutoff=CUTOFF.replace(tzinfo=None))
    with pytest.raises(ValueError, match="probability"):
        Availability(CUTOFF, float("nan"), CUTOFF + timedelta(days=1), "test")
    with pytest.raises(ValueError, match="at or after"):
        sample_lineups(squad(), CUTOFF - timedelta(seconds=1), np.random.default_rng(3))
    with pytest.raises(ValueError, match="sample size"):
        sample_lineups(squad(), CUTOFF, np.random.default_rng(3), 0)
