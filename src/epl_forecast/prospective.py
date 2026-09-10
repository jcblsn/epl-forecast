"""Scheduled local collection and immutable forecast attempts for both leagues."""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from epl_forecast.data.capture import SourceAccessError, writer_lock
from epl_forecast.data.collect import backfill, collect
from epl_forecast.datasets import Dataset
from epl_forecast.storage import json_bytes, sha256_bytes, write_immutable, write_json


def information_fingerprint(data):
    fields = {
        "fixtures": "match_id, kickoff_time, status, home_goals, away_goals",
        "memberships": "player_id, team_id, season_id, basis",
        "availability": "player_id, fpl_code, scope, status, reason, chance_next_round",
        "team_process": "match_id, team_id, xg",
        "odds": "match_id, family, home_odds, draw_odds, away_odds, retrieved_at",
    }
    records = {
        table: data.rows(f"SELECT DISTINCT {columns} FROM {table} ORDER BY ALL")
        for table, columns in fields.items()
    }
    return sha256_bytes(json.dumps(records, default=str, sort_keys=True).encode())


def capture_attempt(
    root=Path("runs/prospective"),
    data_root=Path("data"),
    simulations=2000,
    force=False,
    backfill_requests=0,
    collect_first=True,
):
    root, data_root = Path(root), Path(data_root)
    root.mkdir(parents=True, exist_ok=True)
    if collect_first:
        try:
            with writer_lock(data_root):
                collection = collect(data_root)
        except SourceAccessError as error:
            return {"status": "skipped", "reason": str(error)}
    else:
        collection = json.loads((data_root / "audits" / "collection.json").read_text())
    now = datetime.now(UTC)
    data = Dataset(data_root, now)
    try:
        fingerprint = information_fingerprint(data)
        inputs = data.provenance()
    finally:
        data.close()
    state_path = root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    last = (
        datetime.fromisoformat(state["last_forecast_at"]) if state.get("last_forecast_at") else None
    )
    due = (
        force
        or fingerprint != state.get("fingerprint")
        or last is None
        or (now - last).total_seconds() >= 12 * 3600
    )
    result = {"status": collection["status"], "collection": collection}
    if due:
        attempt = root / now.strftime("%Y-%m-%dT%H%M%S.%fZ")
        attempt.mkdir()
        results = []
        for league, config in [
            ("eng-premier-league", "configs/baselines.toml"),
            ("eng-championship", "configs/championship.toml"),
        ]:
            for name, path, model in [
                ("M2", config, "M2-attack-defense-v1"),
                ("M5", "configs/quality_tilt.toml", "M5-quality-tilt-v1"),
                ("M6", None, "M6-player-quality-v1"),
                ("M7", "configs/xg_quality_tilt.toml", "M7-xg-v1"),
                ("M8", "configs/process_quality_tilt.toml", "M8-process-v1"),
            ]:
                output = attempt / league / name
                command = [
                    sys.executable,
                    "-m",
                    "epl_forecast.cli",
                    "forecast",
                    "--data",
                    str(data_root),
                    "--competition",
                    league,
                    "--cutoff",
                    now.isoformat(),
                    "--config",
                    path,
                    "--model",
                    model,
                    "--output",
                    str(output),
                    "--simulations",
                    str(simulations),
                ]
                if name == "M6":
                    command = [
                        sys.executable,
                        "scripts/forecast_player_quality.py",
                        "--forecast-only",
                        "--data",
                        str(data_root),
                        "--competition",
                        league,
                        "--cutoff",
                        now.isoformat(),
                        "--output",
                        str(output),
                        "--simulations",
                        str(simulations),
                    ]
                completed = subprocess.run(command, text=True, capture_output=True, check=False)
                results.append(
                    {"league": league, "model": name, "returncode": completed.returncode}
                )
                write_immutable(
                    attempt / f"{league}-{name}.log", (completed.stdout + completed.stderr).encode()
                )
        complete = all(r["returncode"] == 0 for r in results)
        result.update(
            status="complete" if complete and not collection["errors"] else "partial",
            attempt=str(attempt),
            forecasts=results,
            data=inputs,
        )
        write_immutable(attempt / "manifest.json", json_bytes(result))
        if complete:
            write_json(
                state_path, {"fingerprint": fingerprint, "last_forecast_at": now.isoformat()}
            )
    if backfill_requests:
        with writer_lock(data_root):
            result["backfill"] = backfill(data_root, max_requests=backfill_requests)
    return result


def install_launch_agent(label, arguments, root, interval_seconds, logs=None):
    """Install and start a per-user launchd job, replacing any earlier one."""
    import os
    import plistlib

    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    logs = logs or label.rsplit(".", 1)[-1]
    path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    config = {
        "Label": label,
        "ProgramArguments": list(arguments),
        "WorkingDirectory": str(Path(__file__).resolve().parents[2]),
        "StartInterval": int(interval_seconds),
        "RunAtLoad": True,
        "ProcessType": "Background",
        "StandardOutPath": str(root / f"{logs}.log"),
        "StandardErrorPath": str(root / f"{logs}-errors.log"),
        "EnvironmentVariables": {"OPENBLAS_NUM_THREADS": "1"},
    }
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True, check=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(config))
    subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
    return path
