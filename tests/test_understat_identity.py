import json

from epl_forecast.data.understat_ingest import ingest
from epl_forecast.datasets import Dataset, publish


def test_understat_uses_retained_exact_names_without_future_or_ambiguous_links(tmp_path):
    request = {
        "provider": "api_football",
        "retrieved_at": "2026-09-01T12:00:00+00:00",
        "source_sha256": "a" * 64,
        "evidence_basis": "retrospective",
        "context": {},
    }
    fixture = {
        "match_id": "m",
        "competition_id": "eng-premier-league",
        "season_id": "2023-2024",
        "home_team_id": "a",
        "away_team_id": "b",
        "match_date": "2024-05-01",
        "status": "finished",
        "stage": "regular",
        "home_goals": 0,
        "away_goals": 0,
    }
    publish(
        tmp_path,
        request,
        {
            "fixtures": [fixture],
            "players": [
                {"player_id": "p1", "name": "Pau Francisco Torres", "birth_date": "1997-01-16"},
                {"player_id": "p2", "name": "Other Person"},
                {"player_id": "p3", "name": "Same Name"},
                {"player_id": "p4", "name": "Same Name"},
            ],
            "appearances": [
                {"match_id": "m", "player_id": player, "team_id": "a"}
                for player in ("p1", "p2", "p3", "p4")
            ],
        },
    )
    publish(
        tmp_path,
        {**request, "source_sha256": "b" * 64},
        {"players": [{"player_id": "p1", "name": "Pau Torres"}]},
    )
    publish(
        tmp_path,
        {**request, "retrieved_at": "2026-09-09T12:00:00+00:00", "source_sha256": "c" * 64},
        {"players": [{"player_id": "p2", "name": "Future Name", "understat_id": "2"}]},
    )
    roster = {
        str(i): {
            "player_id": str(i),
            "player": name,
            "position": "DC",
            "time": "90",
            "xG": "0",
            "xA": "0",
            "shots": "0",
        }
        for i, name in enumerate(("Pau Torres", "Future Name", "Same Name"), 1)
    }
    source = {
        **request,
        "provider": "understat",
        "retrieved_at": "2026-09-08T12:00:00+00:00",
        "source_sha256": "d" * 64,
        "context": {"kind": "players", "match_id": "m"},
    }
    ingest(tmp_path, source, json.dumps({"rosters": {"h": roster, "a": {}}}).encode())
    data = Dataset(tmp_path)
    try:
        records = {
            r["understat_id"]: r["player_id"] for r in data.rows("SELECT * FROM player_process")
        }
        assert records == {"1": "p1", "2": None, "3": None}
        assert (
            data.rows("SELECT name FROM players WHERE player_id='p1'")[0]["name"]
            == "Pau Francisco Torres"
        )
    finally:
        data.close()
