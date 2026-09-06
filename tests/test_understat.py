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
