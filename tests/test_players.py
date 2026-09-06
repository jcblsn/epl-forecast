from copy import deepcopy

import pytest

from epl_forecast.data.players import normalize_player_matches, read_player_csv


def appearance(player, fixture, day, minutes=90, home=True, opponent="2", **extra):
    return {
        "name": f"Player {player}",
        "element": str(player),
        "fixture": str(fixture),
        "kickoff_time": f"2023-01-{day:02d}T15:00:00Z",
        "minutes": str(minutes),
        "was_home": str(home),
        "opponent_team": opponent,
        "team_h_score": "1",
        "team_a_score": "0",
        **extra,
    }


def normalize(rows, players=None):
    return normalize_player_matches(
        "2022-23", rows, players or [], {"1": "one", "2": "two", "3": "three"}, "hash"
    )


def fixture(number, day, minutes=90):
    return [
        appearance(1, number, day, minutes),
        appearance(2, number, day, home=False, opponent="1"),
    ]


def test_prior_minutes_ignore_target_future_and_same_day_and_include_bench():
    rows = fixture(1, 1, 90) + fixture(2, 3, 0) + fixture(3, 5, 20) + fixture(4, 5, 70)
    original, _ = normalize(rows)
    changed = deepcopy(rows)
    changed[4]["minutes"] = "80"
    extended, _ = normalize(changed + fixture(5, 7, 90))
    for table in [original, extended]:
        target = next(r for r in table if r["fpl_element_id"] == "1" and r["fpl_fixture_id"] == "4")
        assert target["expected_minutes_prior5"] == 45
        assert target["prior5_count"] == 2
        assert target["prior5_latest_kickoff"].startswith("2023-01-03")
    assert original[0]["expected_minutes_prior5"] == ""


def test_fixture_club_beats_final_squad_and_preserves_unknown_starts():
    rows = fixture(1, 1)
    players = [{"id": "1", "code": "123", "team": "3", "element_type": "2"}]
    normalized, report = normalize(rows, players)
    assert normalized[0]["team_id"] == "one"
    assert normalized[0]["fpl_player_code"] == "123"
    assert normalized[0]["starts"] == ""
    assert report["final_club_disagrees_with_fixture"] == 1


def test_cancelled_rows_and_duplicate_handling():
    rows = fixture(1, 1)
    cancelled = {**rows[0], "team_h_score": "", "team_a_score": ""}
    normalized, report = normalize([cancelled, *rows, rows[0]])
    assert len(normalized) == 2
    assert report["unplayed_rows_excluded"] == 1
    assert report["identical_duplicates_excluded"] == 1
    with pytest.raises(ValueError, match="Conflicting completed"):
        normalize([*rows, {**rows[0], "minutes": "45"}])


def test_manager_is_not_a_player_and_ambiguous_club_fails():
    rows = fixture(1, 1)
    normalized, report = normalize([*rows, appearance(3, 1, 1, position="AM")])
    assert len(normalized) == 2
    assert report["manager_rows_excluded"] == 1
    with pytest.raises(ValueError, match="Ambiguous fixture-side"):
        normalize([*rows, appearance(4, 1, 1, opponent="3")])


def test_legacy_encoding(tmp_path):
    path = tmp_path / "players.csv"
    path.write_bytes("name,minutes\nAndré,90\n".encode("latin-1"))
    rows, encoding = read_player_csv(path)
    assert encoding == "latin-1"
    assert rows[0]["name"] == "André"


def test_zero_placeholder_starts_and_xg_are_unknown():
    rows = [{**row, "starts": "0", "expected_goals": "0.00"} for row in fixture(1, 1)]
    normalized, report = normalize(rows)
    assert all(row["starts"] == "" and row["expected_goals"] == "" for row in normalized)
    assert report["fixtures_with_placeholder_starts"] == 1
    assert report["fixtures_with_placeholder_xg"] == 1
