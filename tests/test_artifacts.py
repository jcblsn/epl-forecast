import subprocess
import sys

from epl_forecast.artifacts import execution_provenance, new_run_directory, retain_execution
from epl_forecast.storage import file_hash


def test_execution_provenance_detects_runner_lock_and_dirty_changes(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    script = tmp_path / "scripts" / "research.py"
    script.parent.mkdir()
    script.write_text("print(1)\n")
    lock = tmp_path / "uv.lock"
    lock.write_text("version = 1\n")
    git("add", ".")
    git("commit", "-m", "fixture")
    monkeypatch.setattr(sys, "argv", [str(script), "--seed", "7"])
    clean = execution_provenance(tmp_path)
    assert clean["commit"] == git("rev-parse", "HEAD")
    assert clean["dirty"] is False
    assert clean["argv"] == [str(script), "--seed", "7"]
    assert clean["invoked_file_sha256"] == file_hash(script)
    assert {"numpy", "scipy", "duckdb"} <= clean["dependencies"].keys()
    script.write_text("print(2)\n")
    lock.write_text("version = 2\n")
    changed = execution_provenance(tmp_path)
    assert changed["dirty"] is True
    assert changed["commit"] == clean["commit"]
    assert (
        changed["execution_files"]["scripts/research.py"]
        != clean["execution_files"]["scripts/research.py"]
    )
    assert changed["lockfile_sha256"] != clean["lockfile_sha256"]


def test_execution_provenance_outside_checkout_is_explicitly_unknown(tmp_path):
    result = execution_provenance(tmp_path)
    assert result["commit"] is None
    assert result["dirty"] is None
    assert result["lockfile_sha256"] is None


def test_run_directory_retains_each_distinct_execution_without_overwrite(tmp_path, monkeypatch):
    import json

    directory = tmp_path / "run"
    new_run_directory(directory)
    paths = list((directory / "executions").glob("*.json"))
    assert len(paths) == 1
    original = paths[0].read_bytes()
    retain_execution(directory)
    assert len(list((directory / "executions").glob("*.json"))) == 1
    monkeypatch.setattr(sys, "argv", ["changed-invocation", "--seed", "2"])
    retain_execution(directory)
    assert len(list((directory / "executions").glob("*.json"))) == 2
    assert paths[0].read_bytes() == original
    assert json.loads(original)["commit"]
