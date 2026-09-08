from datetime import UTC, date, datetime

import pytest

from epl_forecast.research.roster_transition import (
    captured_transfer_players,
    departure_exposure,
    departure_status,
)

END, CUTOFF = date(2024, 5, 20), date(2024, 8, 10)


def move(day, origin="a", destination="b"):
    return {
        "transfer_date": date.fromisoformat(day),
        "from_team_id": origin,
        "to_team_id": destination,
    }


def test_departure_chain_and_information_boundary():
    assert departure_status("a", [move("2024-06-01")], END, CUTOFF) == (True, None)
    assert departure_status(
        "a", [move("2024-06-01"), move("2024-07-01", "b", "a")], END, CUTOFF
    ) == (False, None)
    assert departure_status("a", [move("2024-08-10")], END, CUTOFF) == (False, None)
    assert (
        departure_status("a", [move("2024-06-01"), move("2024-06-01", "b", "c")], END, CUTOFF)[0]
        is None
    )
    assert departure_status("a", [move("2024-06-01", "b", "c")], END, CUTOFF)[0] is None
    assert departure_status("a", [move("2024-06-01", "a", None)], END, CUTOFF)[0] is None


def test_missing_history_is_unknown_not_retention():
    args = ("a", {"p1": 60, "p2": 40}, {"p1": [move("2024-06-01")]})
    incomplete = departure_exposure(*args, {"p1"}, END, CUTOFF)
    assert incomplete["departure_minutes_share"] is None
    assert incomplete["departure_share_bounds"] == [0.6, 1.0]
    complete = departure_exposure(*args, {"p1", "p2"}, END, CUTOFF)
    assert complete["departure_minutes_share"] == 0.6
    assert complete["unknown_minutes_share"] == 0
    with pytest.raises(ValueError, match="follow"):
        departure_exposure(*args, {"p1"}, CUTOFF, END)


def test_capture_timing_never_inherits_transfer_event_date():
    manifests = [
        {
            "request": {
                "context": {"endpoint": "transfers", "player": 1},
                "retrieved_at": "2026-09-08T12:00:00+00:00",
            }
        }
    ]
    players = [{"api_id": 1, "player_id": "p1"}]
    assert captured_transfer_players(manifests, players) == {"p1"}
    assert captured_transfer_players(manifests, players, datetime(2024, 8, 10, tzinfo=UTC)) == set()
