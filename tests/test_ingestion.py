from datetime import UTC, datetime

from epl_forecast.data import api_football as api
from epl_forecast.datasets import Dataset
from epl_forecast.squads import captured_squads


def squad_record(time):
    return {
        "provider": "api_football",
        "retrieved_at": time,
        "evidence_basis": "captured",
        "source_sha256": time.encode().hex().ljust(64, "0")[:64],
        "context": {
            "endpoint": "players/squads",
            "team": 42,
            "season_id": "2026-2027",
            "competition_id": "eng-premier-league",
        },
    }


def test_conflicting_squad_positions_are_unknown_and_empty_capture_removes_members(tmp_path):
    body = {
        "response": [
            {
                "team": {"id": 42, "name": "Arsenal"},
                "players": [
                    {"id": 1, "name": "Player One", "position": "Defender"},
                    {"id": 1, "name": "Player One", "position": "Midfielder"},
                ],
            }
        ]
    }
    api.normalize(squad_record("2026-09-08T10:00:00+00:00"), body, tmp_path)
    data = Dataset(tmp_path)
    assert data.rows("SELECT position FROM memberships") == [{"position": "UNK"}]
    assert (
        len(captured_squads(data, datetime(2026, 9, 8, 11, tzinfo=UTC))["arsenal"].candidates) == 1
    )
    data.close()
    body["response"][0]["players"] = []
    api.normalize(squad_record("2026-09-08T12:00:00+00:00"), body, tmp_path)
    data = Dataset(tmp_path)
    assert not captured_squads(data, datetime(2026, 9, 8, 13, tzinfo=UTC))["arsenal"].candidates
    assert "arsenal" in captured_squads(data, datetime(2026, 9, 8, 11, tzinfo=UTC))
    data.close()


def test_fixture_absence_does_not_become_an_injury_interval(tmp_path):
    from datetime import timedelta

    from epl_forecast.datasets import publish
    from epl_forecast.lineups import availability_probability

    record = squad_record("2026-09-08T10:00:00+00:00")
    api.normalize(
        record,
        {
            "response": [
                {
                    "team": {"id": 42, "name": "Arsenal"},
                    "players": [{"id": 1, "name": "Player One", "position": "Defender"}],
                }
            ]
        },
        tmp_path,
    )
    kickoff = datetime(2026, 9, 9, 14, tzinfo=UTC)
    publish(
        tmp_path,
        {**record, "context": {"endpoint": "fixtures"}},
        {
            "fixtures": [
                {
                    "match_id": "fixture-one",
                    "api_id": 99,
                    "competition_id": "eng-premier-league",
                    "season_id": "2026-2027",
                    "stage": "regular",
                    "status": "scheduled",
                    "home_team_id": "arsenal",
                    "away_team_id": "chelsea",
                    "match_date": "2026-09-09",
                    "kickoff_time": kickoff.isoformat(),
                }
            ]
        },
    )
    injury = {
        **record,
        "retrieved_at": "2026-09-08T11:00:00+00:00",
        "context": {"endpoint": "injuries", "league": 39, "season": 2026},
    }
    api.normalize(
        injury,
        {
            "response": [
                {
                    "league": {"id": 39, "season": 2026},
                    "team": {"id": 42, "name": "Arsenal"},
                    "fixture": {"id": 99},
                    "player": {"id": 1, "type": "Missing Fixture", "reason": "Suspended"},
                }
            ]
        },
        tmp_path,
    )
    data = Dataset(tmp_path)
    player = captured_squads(data, datetime(2026, 9, 8, 12, tzinfo=UTC))["arsenal"].candidates[0]
    assert availability_probability(player, kickoff) == 0
    assert availability_probability(player, kickoff + timedelta(days=2)) == 1
    assert availability_probability(player, kickoff - timedelta(hours=1)) == 1
    data.close()
    api.normalize(
        {**injury, "retrieved_at": "2026-09-08T13:00:00+00:00"}, {"response": []}, tmp_path
    )
    data = Dataset(tmp_path)
    player = captured_squads(data, datetime(2026, 9, 8, 14, tzinfo=UTC))["arsenal"].candidates[0]
    assert player.availability is None
    data.close()
