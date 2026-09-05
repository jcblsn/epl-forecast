import json
from datetime import date
from urllib.error import HTTPError

import pytest

from epl_forecast.data.normalize import normalize_rows, normalize_snapshot, parse_date
from epl_forecast.data.sources import SourceAccessError, download, restore_snapshot
from epl_forecast.storage import json_bytes, sha256_bytes, write_immutable

HEADER = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
VALID = "E0,02/09/2020,Arsenal,Chelsea,0,1,A,2.4,3.5,2.9\n"


def entry(payload):
    digest = sha256_bytes(payload)
    return {
        "season_start": 2020,
        "season_id": "2020-2021",
        "division": "E0",
        "competition_id": "eng-premier-league",
        "sha256": digest,
        "url": "https://football-data.co.uk/mmz4281/2021/E0.csv",
        "path": f"raw/football_data/2020-2021/E0/{digest}.csv",
    }


def normalize(text):
    payload = text.encode()
    return normalize_rows(payload, entry(payload), {"Arsenal": "arsenal", "Chelsea": "chelsea"})


def test_dates_availability_and_provenance():
    matches, odds, audit = normalize(HEADER + VALID)
    match = matches[0]
    assert match.fixture.match_date == date(2020, 9, 2)
    assert match.available_on == date(2020, 9, 3)
    assert parse_date("02/09/20") == match.fixture.match_date
    assert match.source_row == 2
    assert match.source_sha256 == sha256_bytes((HEADER + VALID).encode())
    assert match.source_time == ""
    assert odds[0]["observed_at"] == ""
    assert not audit["complete"]


@pytest.mark.parametrize(
    "bad",
    [
        VALID.replace(",0,1,A,", ",-1,1,A,"),
        VALID.replace(",0,1,A,", ",,1,A,"),
        VALID.replace(",0,1,A,", ",0,1,H,"),
        VALID.replace("Arsenal", "Unknown"),
        VALID.replace("02/09/2020", "02/09/2025"),
        VALID.replace("Chelsea", "Arsenal"),
    ],
)
def test_invalid_core_data_rejected(bad):
    with pytest.raises(ValueError):
        normalize(HEADER + bad)


def test_duplicate_pair_rejected_even_if_date_changes():
    with pytest.raises(ValueError, match="Duplicate"):
        normalize(HEADER + VALID + VALID.replace("02/09", "03/09"))


@pytest.mark.parametrize("price", ["1", "0", "nan", "inf", "broken"])
def test_bad_odds_are_audited_without_losing_the_result(price):
    matches, odds, audit = normalize(HEADER + VALID.replace("2.4", price))
    assert len(matches) == 1
    assert odds == []
    assert audit["odds"]["bet365_preclosing"]["invalid"] == 1


def test_immutable_and_checksum_failures(tmp_path):
    payload = (HEADER + VALID).encode()
    source = entry(payload)
    path = tmp_path / source["path"]
    write_immutable(path, payload)
    write_immutable(path, payload)
    with pytest.raises(ValueError, match="immutable"):
        write_immutable(path, b"changed")
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_bytes(json_bytes({"schema_version": 1, "files": [source]}))
    first = normalize_snapshot(tmp_path, snapshot, tmp_path / "first")
    second = normalize_snapshot(tmp_path, snapshot, tmp_path / "second")
    assert first == second
    assert (tmp_path / "first/matches.csv").read_bytes() == (
        tmp_path / "second/matches.csv"
    ).read_bytes()
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        normalize_snapshot(tmp_path, snapshot, tmp_path / "third")


def test_restore_refuses_upstream_drift(tmp_path, monkeypatch):
    from epl_forecast.data import sources

    source = entry((HEADER + VALID).encode())
    monkeypatch.setattr(sources, "download", lambda url: (b"changed", {}))
    with pytest.raises(ValueError, match="Upstream data changed"):
        restore_snapshot(tmp_path, {"files": [source]})
    assert not (tmp_path / source["path"]).exists()


def test_authentication_fails_without_retry(monkeypatch):
    from epl_forecast.data import sources

    calls = []

    def denied(request, timeout):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(sources, "urlopen", denied)
    with pytest.raises(SourceAccessError, match="no authentication retries"):
        download("https://example.com/data.csv")
    assert len(calls) == 1


def test_html_response_is_not_accepted_as_data():
    with pytest.raises(ValueError, match="Missing CSV fields"):
        normalize("<html>Please sign in</html>")


def test_fresh_restore_preserves_processed_bytes(tmp_path, monkeypatch):
    from epl_forecast.data import sources

    payload = (HEADER + VALID).encode()
    source = entry(payload)
    snapshot = {"schema_version": 1, "files": [source]}
    lock = tmp_path / "snapshot.json"
    lock.write_text(json.dumps(snapshot))
    monkeypatch.setattr(sources, "download", lambda url: (payload, {"retrieved_at": "later"}))
    restore_snapshot(tmp_path / "one", snapshot)
    restore_snapshot(tmp_path / "two", snapshot)
    first = normalize_snapshot(tmp_path / "one", lock, tmp_path / "one/processed")
    second = normalize_snapshot(tmp_path / "two", lock, tmp_path / "two/processed")
    assert first == second
