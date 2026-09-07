import gzip
import json
from datetime import date

import pytest

from epl_forecast.data.understat import parse_payload, reconcile
from epl_forecast.schema import Fixture, Match, fixture_id
from epl_forecast.storage import sha256_bytes


def example():
    key = fixture_id("eng-premier-league", "2024-2025", "manchester-united", "fulham")
    match = Match(
        Fixture(
            key, "eng-premier-league", "2024-2025", date(2024, 8, 16), "manchester-united", "fulham"
        ),
        1,
        0,
    )
    row = {
        "id": "26602",
        "isResult": True,
        "h": {"title": "Manchester United"},
        "a": {"title": "Fulham"},
        "goals": {"h": "1", "a": "0"},
        "xG": {"h": "2.04268", "a": "0"},
        "datetime": "2024-08-16 19:00:00",
    }
    return match, row


def run(rows, matches):
    payload = json.dumps({"dates": rows}).encode()
    return reconcile(payload, 2024, matches, sha256_bytes(payload))


def test_provider_semantics_aliases_zero_and_availability():
    match, row = example()
    records, report = run([row], [match])
    assert not report["issues"] and not report["missing_canonical"]
    assert report["zero_xg_sides"] == 1
    assert records[0]["home_xg"] == 2.04268
    assert records[0]["available_on"] == "2024-08-17"
    assert records[0]["provider"] == "understat"
    assert "unverified" in records[0]["availability_basis"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("datetime", "2024-08-17 19:00:00"),
        ("goals", {"h": "2", "a": "0"}),
        ("xG", {"h": "nan", "a": "0"}),
        ("xG", {"h": "-1", "a": "0"}),
        ("h", {"title": "Unknown"}),
        ("isResult", "true"),
    ],
)
def test_mismatch_never_enters_observations(field, value):
    match, row = example()
    row[field] = value
    records, report = run([row], [match])
    assert records == []
    assert len(report["issues"]) == 1
    assert report["missing_canonical"] == [match.fixture.match_id]


def test_duplicate_and_missing_results():
    match, row = example()
    records, report = run([row, row], [match])
    assert len(records) == 1 and len(report["issues"]) == 1
    row["isResult"] = False
    records, report = run([row], [match])
    assert not records and report["unfinished"] == 1 and report["missing_canonical"]


def test_raw_integrity_and_gzip():
    match, row = example()
    payload = gzip.compress(json.dumps({"dates": [row]}).encode(), mtime=0)
    assert parse_payload(payload)["dates"] == [row]
    records, _ = reconcile(payload, 2024, [match], sha256_bytes(payload))
    assert len(records) == 1
    with pytest.raises(ValueError, match="checksum"):
        reconcile(payload, 2024, [match], "wrong")
    with pytest.raises(ValueError, match="dates"):
        parse_payload(b'{"changed_contract": []}')


def test_snapshot_pins_raw_bytes_and_rejects_drift(tmp_path, monkeypatch):
    from epl_forecast.data import understat

    _, row = example()
    payload = json.dumps({"dates": [row]}).encode()
    metadata = {
        "url": understat.source_url(2024),
        "sha256": sha256_bytes(payload),
        "bytes": len(payload),
        "retrieved_at": "2026-09-06T12:00:00+00:00",
    }
    monkeypatch.setattr(understat, "download", lambda *a, **kw: (payload, metadata))
    manifest_path = tmp_path / "snapshot.json"
    manifest = understat.fetch_snapshot(tmp_path, manifest_path, 2024, 2024)
    raw = tmp_path / manifest["files"][0]["path"]
    assert raw.read_bytes() == payload
    monkeypatch.setattr(understat, "download", lambda *a, **kw: pytest.fail("Unexpected network"))
    assert understat.fetch_snapshot(tmp_path, manifest_path, 2024, 2024) == manifest
    raw.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        understat.fetch_snapshot(tmp_path, manifest_path, 2024, 2024)


def test_date_correction_requires_exact_source_and_fixture(monkeypatch):
    from epl_forecast.data import understat

    match, row = example()
    row["datetime"] = "2024-08-17 00:00:00"
    payload = json.dumps({"dates": [row]}).encode()
    correction = {
        "source_sha256": sha256_bytes(payload),
        "source_match_id": row["id"],
        "source_datetime": row["datetime"],
        "match_id": match.fixture.match_id,
        "canonical_date": str(match.fixture.match_date),
    }
    original = understat.Path.read_text
    monkeypatch.setattr(
        understat.Path,
        "read_text",
        lambda p: (
            json.dumps([correction]) if p.name == "understat_date_corrections.json" else original(p)
        ),
    )
    records, report = run([row], [match])
    assert records[0]["match_date"] == "2024-08-16"
    assert records[0]["source_datetime"] == "2024-08-17 00:00:00"
    assert report["date_corrections"] == [correction]
    row["xG"]["h"] = "2.1"
    records, report = run([row], [match])
    assert not records and report["issues"][0]["error"] == "Date mismatch"


def test_player_sample_preserves_nonadditivity_and_own_goal_semantics(tmp_path, monkeypatch):
    from epl_forecast.data import understat
    from epl_forecast.storage import json_bytes, write_immutable

    roster = {}
    for side in "ha":
        roster[side] = {}
        for i in range(11):
            key = f"{side}{i}"
            roster[side][key] = dict.fromkeys(
                (
                    "time",
                    "shots",
                    "xG",
                    "xA",
                    "key_passes",
                    "xGChain",
                    "xGBuildup",
                    "goals",
                    "own_goals",
                ),
                "0",
            )
            roster[side][key].update(player_id=key, player=key, position="GK" if i == 0 else "DC")
    roster["h"]["h0"].update(shots="1", xG="1.2", own_goals="1")
    stamp = "2024-08-16 19:00:00"
    shot = {"match_id": "1", "player_id": "h0", "date": stamp, "xG": "1.2", "result": "SavedShot"}
    payload = json_bytes(
        {
            "rosters": roster,
            "shots": {"h": [shot, {**shot, "xG": "0", "result": "OwnGoal"}], "a": []},
        }
    )
    league = json_bytes(
        {"dates": [{}], "players": [{"id": k} for side in roster.values() for k in side]}
    )
    league_hash = sha256_bytes(league)
    write_immutable(tmp_path / f"raw/understat/2024/{league_hash}.bin", league)
    fixture = {
        "match_id": "fixture",
        "source_match_id": "1",
        "season_id": "2024-2025",
        "match_date": "2024-08-16",
        "source_datetime": stamp,
        "source_sha256": league_hash,
        "home_xg": 1.0,
        "away_xg": 0,
        "home_goals": 0,
        "away_goals": 1,
    }
    metadata = {
        "sha256": sha256_bytes(payload),
        "bytes": len(payload),
        "retrieved_at": "2026-09-06T12:00:00+00:00",
        "url": "https://understat.com/getMatchData/1",
    }
    monkeypatch.setattr(understat, "download", lambda *a, **kw: (payload, metadata))
    manifest = tmp_path / "players.json"
    report = understat.audit_player_matches(tmp_path, manifest, [fixture])
    assert report["passed"] and report["sample_matches"] == 1
    assert report["nonadditive_match_sides"] == 1
    assert report["matches"][0]["sides"][0]["own_goal_events"] == 1
    monkeypatch.setattr(understat, "download", lambda *a, **kw: pytest.fail("Unexpected network"))
    assert understat.audit_player_matches(tmp_path, manifest, [fixture]) == report
