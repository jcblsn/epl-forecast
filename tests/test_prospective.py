import fcntl
import json

from epl_forecast import prospective
from epl_forecast.storage import write_json


def fake_snapshot(tmp_path):
    snapshot = tmp_path / "snapshot"
    write_json(snapshot / "manifest.json", {})
    write_json(snapshot / "fpl_bootstrap.json", {"elements": [{"id": 1, "team": 1, "status": "a"}]})
    write_json(snapshot / "fpl_fixtures.json", [{"id": 1, "finished": False}])
    return snapshot


def test_failed_model_does_not_prevent_other_archives(tmp_path, monkeypatch):
    snapshot = fake_snapshot(tmp_path)
    monkeypatch.setattr(prospective, "read_live_snapshot", lambda _: {})
    monkeypatch.setattr(prospective, "verify_capture", lambda _: {"forward_matches": 1})
    calls = []

    def runner(arguments, logfile):
        calls.append(logfile.stem)
        logfile.write_text("test")
        if logfile.stem == "players":
            output = arguments[arguments.index("--output") + 1]
            from pathlib import Path

            p = Path(output) / "player_matches.csv.gz"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"fixture")
        return 1 if logfile.stem == "m7" else 0

    result = prospective.capture_attempt(
        tmp_path / "runs", 2026, runner=runner, snapshot_capturer=lambda *_: snapshot
    )
    assert calls == ["m2", "m5", "m7", "m8", "players", "m6"]
    assert result["status"] == "partial"
    assert result["models"]["m6"]["success"]
    assert not (tmp_path / "runs/last_success.json").exists()
    assert json.loads(next((tmp_path / "runs").glob("*/complete.json")).read_text()) == result


def test_availability_changes_preserve_history_cache_key(tmp_path, monkeypatch):
    snapshot = fake_snapshot(tmp_path)
    monkeypatch.setattr(prospective, "read_live_snapshot", lambda _: {})
    signal, histories = prospective.information_fingerprints(snapshot)
    write_json(snapshot / "fpl_bootstrap.json", {"elements": [{"id": 1, "team": 2, "status": "i"}]})
    changed_signal, changed_histories = prospective.information_fingerprints(snapshot)
    assert changed_signal != signal
    assert changed_histories == histories
    write_json(snapshot / "fpl_fixtures.json", [{"id": 1, "finished": True, "team_h_score": 1}])
    assert prospective.information_fingerprints(snapshot)[1] != histories


def test_running_capture_holds_exclusive_lock(tmp_path):
    with (tmp_path / ".capture.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = prospective.capture_attempt(tmp_path, 2026)
    assert result == {"status": "already_running"}
    assert not list(tmp_path.glob("*/capture.json"))


def test_success_then_changed_availability_preserves_both_attempts(tmp_path, monkeypatch):
    import shutil
    from pathlib import Path

    template = fake_snapshot(tmp_path)
    monkeypatch.setattr(prospective, "read_live_snapshot", lambda _: {})
    monkeypatch.setattr(prospective, "verify_capture", lambda _: {"forward_matches": 1})
    captures, calls = [], []

    def capture(*_):
        target = tmp_path / f"input-{len(captures)}"
        shutil.copytree(template, target)
        captures.append(target)
        return target

    def runner(arguments, logfile):
        calls.append(logfile.stem)
        logfile.write_text("test")
        if logfile.stem == "players":
            output = Path(arguments[arguments.index("--output") + 1])
            output.mkdir(parents=True)
            (output / "player_matches.csv.gz").write_bytes(b"fixture")
        return 0

    root = tmp_path / "runs"
    first = prospective.capture_attempt(root, 2026, runner=runner, snapshot_capturer=capture)
    assert first["status"] == "complete"
    first_bytes = (Path(first["attempt"]) / "complete.json").read_bytes()
    calls.clear()
    skipped = prospective.capture_attempt(root, 2026, runner=runner, snapshot_capturer=capture)
    assert skipped["status"] == "unchanged"
    assert calls == []
    write_json(template / "fpl_bootstrap.json", {"elements": [{"id": 1, "team": 1, "status": "i"}]})
    second = prospective.capture_attempt(root, 2026, runner=runner, snapshot_capturer=capture)
    assert second["status"] == "complete"
    assert second["previous_success"] == first["attempt"]
    assert "players" not in calls
    assert first["player_dataset"] == second["player_dataset"]
    assert (Path(first["attempt"]) / "complete.json").read_bytes() == first_bytes
    assert first["snapshot"] != second["snapshot"]
