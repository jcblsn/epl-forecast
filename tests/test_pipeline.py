import json
from datetime import UTC, datetime, timedelta

from test_publication import sample_forecast, sample_run

from epl_forecast import pipeline
from epl_forecast.pipeline import due, snapshot_id

NOW = datetime(2026, 9, 10, 22, 43, 3, tzinfo=UTC)


def test_snapshot_id_is_a_sortable_second():
    assert snapshot_id(NOW) == "2026-09-10T224303Z"


class Completed:
    def __init__(self, returncode):
        self.returncode, self.stdout, self.stderr = returncode, "", "forecast failed"


class FakeDataset:
    def fixtures(self):
        return []

    def close(self):
        pass


def test_a_division_that_fails_does_not_hold_back_the_others(tmp_path, monkeypatch):
    """One division that cannot be forecast leaves the others published."""

    def fake_forecast(data, league, cutoff, output, simulations):
        if league == "eng-championship":
            return Completed(1)
        output.mkdir(parents=True, exist_ok=True)
        (output / "forecast.json").write_text(json.dumps(sample_forecast(competition=league)))
        (output / "run.json").write_text(json.dumps(sample_run()))
        return Completed(0)

    def fake_verify(data, archive, output):
        output.mkdir(parents=True, exist_ok=True)
        (output / "verification.json").write_text(
            json.dumps({"archives": {str(archive): {"checks": [], "failures": 0}}})
        )
        return Completed(0)

    monkeypatch.setattr(pipeline, "run_forecast", fake_forecast)
    monkeypatch.setattr(pipeline, "verify_archive", fake_verify)
    monkeypatch.setattr(pipeline, "Dataset", lambda *args, **kwargs: FakeDataset())
    monkeypatch.setattr(pipeline, "information_fingerprint", lambda dataset: "fingerprint")
    monkeypatch.setattr(pipeline, "realized_outcomes", lambda fixtures: {})
    runs = tmp_path / "runs"
    result = pipeline.operate(
        data=tmp_path / "data",
        site=tmp_path / "site",
        runs=runs,
        force=True,
        collect_first=False,
    )
    assert result["status"] == "partial"
    assert [row.split("/")[1] for row in result["published"]] == [
        "eng-premier-league",
        "eng-league-one",
        "eng-league-two",
    ]
    assert [failure["league"] for failure in result["failures"]] == ["eng-championship"]
    # The state stays unwritten, so the next run tries the division that failed again.
    assert not (runs / "state.json").exists()


def test_new_information_or_a_stale_publication_is_due():
    state = {"fingerprint": "abc", "published_at": NOW.isoformat()}
    assert not due(state, "abc", NOW + timedelta(hours=6), 12)
    assert due(state, "def", NOW + timedelta(hours=6), 12)
    assert due(state, "abc", NOW + timedelta(hours=12), 12)
    assert due({}, "abc", NOW, 12)
    assert due({"fingerprint": "abc"}, "abc", NOW, 12)
