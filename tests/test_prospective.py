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
    assert {c[c.index("--competition") + 1] for c in commands} == {
        "eng-premier-league",
        "eng-championship",
    }
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
