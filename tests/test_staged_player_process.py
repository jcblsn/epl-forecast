import importlib.util
import sys

import pytest

from epl_forecast.data.capture import WriterBusy, retain, writer_lock


def test_staged_publication_preserves_retrieval_time_and_respects_writer(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "stage_player_process", "scripts/stage_player_process.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stage, canonical = tmp_path / "stage", tmp_path / "data"
    manifest = tmp_path / "input.json"
    manifest.write_text("{}")

    class Frozen:
        def rows(self, query):
            return [{"match_id": "m", "source_match_id": "1", "season_id": "2023-2024"}]

        def close(self):
            pass

    monkeypatch.setattr(module, "frozen_dataset", lambda *args: Frozen())
    record = retain(
        stage,
        "understat",
        "https://understat.com/getMatchData/1",
        b"{}",
        "2026-09-08T12:00:00+00:00",
        "retrospective",
        {"kind": "players", "match_id": "m"},
    )
    captured = []
    monkeypatch.setattr(module, "ingest", lambda root, request, payload: captured.append(request))
    argv = [
        "stage_player_process",
        "capture",
        "--data",
        str(canonical),
        "--stage",
        str(stage),
        "--manifest",
        str(manifest),
        "--seasons",
        "2023",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    module.main()
    argv[1] = "publish"
    with writer_lock(canonical), pytest.raises(WriterBusy):
        module.main()
    assert not captured
    module.main()
    assert captured[0]["retrieved_at"] == record["retrieved_at"]
    assert captured[0]["source_sha256"] == record["source_sha256"]
    assert captured[0]["context"] == record["context"]
    assert (stage / "publish_complete.json").exists()
