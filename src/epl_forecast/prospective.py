"""Local recurring capture with immutable attempts and isolated model failures."""

import fcntl
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from epl_forecast.data.live import capture_snapshot, read_live_snapshot, timestamp
from epl_forecast.storage import file_hash, json_bytes, sha256_bytes, write_immutable, write_json


def information_fingerprints(snapshot):
    read_live_snapshot(snapshot)
    players = json.loads((snapshot / "fpl_bootstrap.json").read_text())["elements"]
    fixtures = json.loads((snapshot / "fpl_fixtures.json").read_text())
    player_fields = (
        "id",
        "team",
        "element_type",
        "status",
        "chance_of_playing_next_round",
        "chance_of_playing_this_round",
        "news",
        "news_added",
    )
    fixture_fields = (
        "id",
        "event",
        "team_h",
        "team_a",
        "kickoff_time",
        "started",
        "finished",
        "finished_provisional",
        "team_h_score",
        "team_a_score",
    )
    signal = {
        "players": [
            {k: p.get(k) for k in player_fields} for p in sorted(players, key=lambda p: p["id"])
        ],
        "fixtures": [
            {k: f.get(k) for k in fixture_fields} for f in sorted(fixtures, key=lambda f: f["id"])
        ],
    }
    histories = {
        "players": sorted(p["id"] for p in players),
        "results": [f for f in signal["fixtures"] if f["finished"] or f["finished_provisional"]],
    }
    return sha256_bytes(json_bytes(signal)), sha256_bytes(json_bytes(histories))


def verify_capture(directory):
    archive = json.loads((directory / "archive.json").read_text())
    for name, expected in archive["files"].items():
        if Path(name).name != name or file_hash(directory / name) != expected:
            raise ValueError("Forecast archive hash mismatch")
    forecast = json.loads((directory / "forecast.json").read_text())
    rows = {r["match_id"]: r for r in forecast["matches"]}
    for key in archive["forward_match_ids"]:
        row = rows[key]
        if timestamp(row["kickoff_time"]) <= timestamp(archive["archived_at"]):
            raise ValueError("Forward archive includes a forecast completed after kickoff")
    return {
        "archive_sha256": file_hash(directory / "archive.json"),
        "forward_matches": len(archive["forward_match_ids"]),
    }


def run_command(arguments, output):
    environment = {**os.environ, "OPENBLAS_NUM_THREADS": "1"}
    with output.open("w") as stream:
        try:
            result = subprocess.run(
                arguments,
                stdout=stream,
                stderr=subprocess.STDOUT,
                env=environment,
                timeout=1800,
                check=False,
            )
            return result.returncode
        except subprocess.TimeoutExpired:
            stream.write("\nCapture command exceeded 30 minutes.\n")
            return 124


def capture_attempt(
    root,
    season_start,
    simulations=2000,
    force=False,
    runner=run_command,
    snapshot_capturer=capture_snapshot,
):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".capture.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "already_running"}
        now = datetime.now(UTC)
        attempt = root / now.strftime("%Y-%m-%dT%H%M%S.%fZ")
        attempt.mkdir(exist_ok=False)
        manifest = {
            "started_at": now.isoformat(),
            "attempt": str(attempt),
            "season_start": season_start,
            "status": "running",
            "commands": [],
            "models": {},
        }
        manifest_path = attempt / "capture.json"
        write_json(manifest_path, manifest)
        state_path = root / "last_success.json"
        previous = json.loads(state_path.read_text()) if state_path.exists() else {}
        try:
            snapshot = snapshot_capturer(Path("snapshots"), season_start)
            signal, histories = information_fingerprints(snapshot)
            manifest.update(
                {
                    "snapshot": str(snapshot),
                    "snapshot_sha256": file_hash(snapshot / "manifest.json"),
                    "information_fingerprint": signal,
                    "histories_fingerprint": histories,
                    "previous_success": previous.get("attempt"),
                }
            )
            recent = (
                previous and (now - timestamp(previous["completed_at"])).total_seconds() < 6 * 3600
            )
            if not force and recent and signal == previous.get("information_fingerprint"):
                manifest["status"] = "unchanged"
                manifest["completed_at"] = datetime.now(UTC).isoformat()
                write_immutable(attempt / "complete.json", json_bytes(manifest))
                return manifest

            def command(label, arguments):
                logfile = attempt / f"{label}.log"
                code = runner(arguments, logfile)
                manifest["commands"].append(
                    {"label": label, "arguments": arguments, "exit_code": code, "log": str(logfile)}
                )
                write_json(manifest_path, manifest)
                return code == 0

            def record_model(label, output, success):
                result = {"success": success, "directory": str(output)}
                if success:
                    try:
                        result.update(verify_capture(output))
                    except (OSError, ValueError, KeyError) as error:
                        result.update({"success": False, "error": str(error)})
                manifest["models"][label] = result
                write_json(manifest_path, manifest)

            configuration = "configs/process_quality_tilt.toml"
            for label, model_id in [
                ("m2", "M2-attack-defense-v1"),
                ("m5", "M5-quality-tilt-poisson"),
                ("m7", "M7-xg-v1"),
                ("m8", "M8-process-v1"),
            ]:
                output = attempt / label
                success = command(
                    label,
                    [
                        sys.executable,
                        "-m",
                        "epl_forecast.cli",
                        "forecast",
                        "--snapshot",
                        str(snapshot),
                        "--config",
                        configuration,
                        "--model",
                        model_id,
                        "--simulations",
                        str(simulations),
                        "--output",
                        str(output),
                    ],
                )
                record_model(label, output, success)
            old_players = (
                Path(previous["player_dataset"]) if previous.get("player_dataset") else None
            )
            reuse = (
                histories == previous.get("histories_fingerprint")
                and old_players is not None
                and old_players.exists()
                and file_hash(old_players) == previous.get("player_sha256")
            )
            if reuse:
                player_dataset, captured = old_players, True
            else:
                player_output = attempt / "players"
                captured = command(
                    "players",
                    [
                        sys.executable,
                        "scripts/capture_player_histories.py",
                        "--snapshot",
                        str(snapshot),
                        "--output",
                        str(player_output),
                    ],
                )
                player_dataset = player_output / "player_matches.csv.gz"
            if captured:
                manifest["player_dataset"] = str(player_dataset)
                manifest["player_sha256"] = file_hash(player_dataset)
                success = command(
                    "m6",
                    [
                        sys.executable,
                        "scripts/forecast_player_quality.py",
                        "--snapshot",
                        str(snapshot),
                        "--live-players",
                        str(player_dataset),
                        "--output",
                        str(attempt / "m6"),
                        "--forecast-only",
                        "--simulations",
                        str(simulations),
                    ],
                )
            else:
                success = False
            record_model("m6", attempt / "m6/current", success)
            manifest["status"] = (
                "complete" if all(m["success"] for m in manifest["models"].values()) else "partial"
            )
            manifest["completed_at"] = datetime.now(UTC).isoformat()
            manifest["attempt"] = str(attempt)
            write_immutable(attempt / "complete.json", json_bytes(manifest))
            if manifest["status"] == "complete":
                temporary = root / ".last_success.tmp"
                write_json(temporary, manifest)
                temporary.replace(state_path)
            return manifest
        except Exception as error:
            manifest.update(
                {
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            )
            write_immutable(attempt / "complete.json", json_bytes(manifest))
            raise
        finally:
            write_json(manifest_path, manifest)
