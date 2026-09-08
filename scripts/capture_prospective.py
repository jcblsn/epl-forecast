"""Run the ten-minute local collector and forecast archive for both leagues."""

import argparse
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from epl_forecast.prospective import capture_attempt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("runs/prospective"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--backfill-requests", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--install-launch-agent", action="store_true")
    args = parser.parse_args()
    if args.simulations < 1 or args.backfill_requests < 0:
        parser.error("Invalid simulation or backfill request budget")
    if args.install_launch_agent:
        repo = Path(__file__).resolve().parents[1]
        uv = shutil.which("uv")
        if uv is None:
            raise ValueError("uv must be installed")
        label = "org.epl-forecast.prospective"
        path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
        args.root.mkdir(parents=True, exist_ok=True)
        command = [
            uv,
            "run",
            "--locked",
            "python",
            str(Path(__file__).resolve()),
            "--root",
            str(args.root.resolve()),
            "--data",
            str(args.data.resolve()),
            "--simulations",
            str(args.simulations),
            "--backfill-requests",
            str(args.backfill_requests),
        ]
        config = {
            "Label": label,
            "ProgramArguments": command,
            "WorkingDirectory": str(repo),
            "StartInterval": 600,
            "RunAtLoad": True,
            "ProcessType": "Background",
            "StandardOutPath": str(args.root.resolve() / "launchd.log"),
            "StandardErrorPath": str(args.root.resolve() / "launchd-errors.log"),
            "EnvironmentVariables": {"OPENBLAS_NUM_THREADS": "1"},
        }
        domain = f"gui/{os.getuid()}"
        subprocess.run(
            ["launchctl", "bootout", f"{domain}/{label}"], capture_output=True, check=False
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps(config))
        subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
        print(f"Installed ten-minute collector: {path}")
        return
    result = capture_attempt(
        args.root, args.data, args.simulations, args.force, args.backfill_requests
    )
    print(result, flush=True)
    if result["status"] in ("partial", "failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
