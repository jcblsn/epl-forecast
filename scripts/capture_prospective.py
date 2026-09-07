"""Archive M2/M5/M6/M7/M8 when captured information changes or six hours pass."""

import argparse
import os
import plistlib
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from epl_forecast.prospective import capture_attempt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("runs/prospective"))
    parser.add_argument("--season-start", type=int)
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--install-launch-agent", action="store_true")
    args = parser.parse_args()
    if args.simulations < 1:
        parser.error("Simulations must be positive")
    if args.install_launch_agent:
        repo = Path(__file__).resolve().parents[1]
        uv = shutil.which("uv")
        if uv is None:
            raise ValueError("uv must be installed before registering capture")
        root = args.root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        label = "org.epl-forecast.prospective"
        path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
        path.parent.mkdir(parents=True, exist_ok=True)
        arguments = [
            uv,
            "run",
            "--locked",
            "python",
            str(Path(__file__).resolve()),
            "--root",
            str(root),
            "--simulations",
            str(args.simulations),
        ]
        if args.season_start:
            arguments.extend(["--season-start", str(args.season_start)])
        payload = plistlib.dumps(
            {
                "Label": label,
                "ProgramArguments": arguments,
                "WorkingDirectory": str(repo),
                "StartInterval": 1800,
                "RunAtLoad": True,
                "ProcessType": "Background",
                "StandardOutPath": str(root / "launchd.log"),
                "StandardErrorPath": str(root / "launchd-errors.log"),
                "EnvironmentVariables": {"OPENBLAS_NUM_THREADS": "1"},
            }
        )
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(f"Existing launch agent differs; inspect {path} before replacing")
        path.write_bytes(payload)
        subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=True)
        print(f"Registered half-hourly local capture: {path}")
        return
    now = datetime.now(UTC)
    season = args.season_start or now.year - (now.month < 7)
    result = capture_attempt(args.root, season, args.simulations, args.force)
    print(f"Prospective capture: {result['status']}; {result.get('attempt', '')}", flush=True)
    if result["status"] in {"partial", "failed"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
