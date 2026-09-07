import json

import pytest

from epl_forecast.data import player_process
from epl_forecast.storage import file_hash, write_json


def test_identity_requires_unique_fixture_team_match(tmp_path, monkeypatch):
    match = "eng-premier-league:2024-2025:a:b"
    payload = {
        "rosters": {
            "h": {
                "1": {
                    "player_id": "1",
                    "player": "Alex Example",
                    "position": "Sub",
                    "time": "20",
                    "xG": "0.2",
                    "xA": "0.1",
                    "shots": "1",
                }
            },
            "a": {},
        }
    }
    raw = tmp_path / "match.json"
    write_json(raw, payload)
    manifest = tmp_path / "sample.json"
    write_json(
        manifest, {"files": [{"path": raw.name, "sha256": file_hash(raw), "match_id": match}]}
    )
    players = tmp_path / "players.csv"
    players.write_text("fixture")
    candidate = {
        "match_id": match,
        "team_id": "a",
        "player_name": "Alex_Example_12",
        "fpl_player_code": "42",
        "player_season_id": "2024-2025:12",
        "position": "MID",
        "source_sha256": "source",
        "minutes": "20",
    }
    monkeypatch.setattr(player_process, "load_player_history", lambda _: [candidate])
    result = player_process.identity_audit(manifest, players, tmp_path)
    assert result["records"][0]["status"] == "linked"
    assert result["records"][0]["process_role"] == "MID"
    assert "substitute role remains unobserved" in result["records"][0]["role_source"]
    duplicate = {**candidate, "fpl_player_code": "43", "player_season_id": "2024-2025:13"}
    monkeypatch.setattr(player_process, "load_player_history", lambda _: [candidate, duplicate])
    assert (
        player_process.identity_audit(manifest, players, tmp_path)["records"][0]["status"]
        == "unresolved"
    )
    payload["rosters"]["h"]["1"]["player"] = "A Example"
    raw.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="hash"):
        player_process.identity_audit(manifest, players, tmp_path)


def test_unknown_role_cannot_silently_become_a_forward():
    assert player_process.process_role("DMC") == "MID"
    assert player_process.process_role("Sub") is None
    with pytest.raises(ValueError, match="Unknown"):
        player_process.process_role("unknown")
