import json
from datetime import UTC, datetime
from types import SimpleNamespace

from epl_forecast import prospective
from epl_forecast.data.capture import retain
from epl_forecast.datasets import publish


def test_collector_uses_one_cutoff_after_collection(tmp_path, monkeypatch):
    root = tmp_path / "data"
    captured = []
    commands = []

    def collect(data_root):
        timestamp = datetime.now(UTC).isoformat()
        captured.append(timestamp)
        publish(
            data_root,
            {
                "provider": "test",
                "retrieved_at": timestamp,
                "evidence_basis": "prospective",
                "source_sha256": "a" * 64,
                "context": {},
            },
            {},
        )
        return {"status": "complete", "errors": []}

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(prospective, "collect", collect)
    monkeypatch.setattr(prospective.subprocess, "run", run)
    report = prospective.capture_attempt(tmp_path / "runs", root)
    assert report["status"] == "complete"
    cutoffs = {c[c.index("--cutoff") + 1] for c in commands}
    assert len(cutoffs) == 1
    assert datetime.fromisoformat(cutoffs.pop()) >= datetime.fromisoformat(captured[0])
    competitions = [c[c.index("--competition") + 1] for c in commands]
    assert set(competitions) == {
        "eng-premier-league",
        "eng-championship",
        "eng-league-one",
        "eng-league-two",
    }
    assert competitions.count("eng-league-one") == competitions.count("eng-league-two") == 2
    assert json.loads((tmp_path / "runs" / "state.json").read_text())["fingerprint"]


def test_normalize_rejects_corrupted_raw_capture(tmp_path):
    import pytest

    from epl_forecast.data.collect import normalize

    record = retain(
        tmp_path, "fpl", "https://example.test", b"{}", "2026-09-08T00:00:00+00:00", "prospective"
    )
    (tmp_path / record["raw_path"]).write_bytes(b"modified")
    with pytest.raises(ValueError, match="hash mismatch"):
        normalize(tmp_path)


def test_final_fixture_capture_has_bounded_correction_checkpoints():
    from datetime import timedelta

    from epl_forecast.data.collect import fixture_details_due

    kickoff = datetime(2026, 9, 1, 15, tzinfo=UTC)
    fixtures = [{"fixture": {"id": 10, "date": kickoff.isoformat(), "status": {"short": "FT"}}}]

    def records(hours):
        return [
            {
                "provider": "api_football",
                "context": {"endpoint": "fixtures", "ids": "10-11"},
                "retrieved_at": (kickoff + timedelta(hours=hours)).isoformat(),
            }
        ]

    assert fixture_details_due(fixtures, [], kickoff + timedelta(hours=3)) == [10]
    assert fixture_details_due(fixtures, records(3), kickoff + timedelta(hours=4)) == []
    assert fixture_details_due(fixtures, records(3), kickoff + timedelta(days=1)) == [10]
    assert fixture_details_due(fixtures, records(25), kickoff + timedelta(days=2)) == []
    assert fixture_details_due(fixtures, records(25), kickoff + timedelta(days=7)) == [10]
    assert fixture_details_due(fixtures, records(169), kickoff + timedelta(days=30)) == []


def test_forecast_worker_does_not_block_on_collection(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "audits").mkdir(parents=True)
    (root / "audits" / "collection.json").write_text(
        json.dumps({"status": "complete", "errors": []})
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Forecast worker must use the independently captured archive")

    monkeypatch.setattr(prospective, "collect", forbidden)
    monkeypatch.setattr(
        prospective.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    report = prospective.capture_attempt(tmp_path / "runs", root, collect_first=False)
    assert report["status"] == "complete"
    assert len(report["forecasts"]) == 14


def test_market_snapshot_changes_forecast_fingerprint(tmp_path):
    from epl_forecast.datasets import Dataset

    before = Dataset(tmp_path)
    try:
        first = prospective.information_fingerprint(before)
    finally:
        before.close()
    publish(
        tmp_path,
        {
            "provider": "football_data",
            "retrieved_at": "2026-09-09T12:00:00+00:00",
            "evidence_basis": "prospective",
            "source_sha256": "b" * 64,
            "context": {},
        },
        {
            "odds": [
                {
                    "match_id": "match",
                    "competition_id": "eng-premier-league",
                    "season_id": "2026-2027",
                    "family": "market_average_preclosing",
                    "home_odds": 2,
                    "draw_odds": 3,
                    "away_odds": 4,
                }
            ]
        },
    )
    after = Dataset(tmp_path)
    try:
        second = prospective.information_fingerprint(after)
    finally:
        after.close()
    assert first != second
