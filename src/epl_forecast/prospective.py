"""The information gate and the launch agent behind scheduled product runs."""

import json
import subprocess
from pathlib import Path

from epl_forecast.storage import sha256_bytes


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
