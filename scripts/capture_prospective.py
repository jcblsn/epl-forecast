"""Run the twelve-hour local collector and forecast archive for both leagues."""

import argparse
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

from epl_forecast.data.capture import SourceAccessError, writer_lock
from epl_forecast.data.collect import collect
from epl_forecast.prospective import capture_attempt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("runs/prospective"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--backfill-requests", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--collect-only", action="store_true")
    mode.add_argument("--forecast-only", action="store_true")
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
            "0",
        ]
        config = {
            "Label": label,
            "ProgramArguments": command,
            "WorkingDirectory": str(repo),
            "StartInterval": 12 * 3600,
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
        config["ProgramArguments"].append("--forecast-only")
        path.write_bytes(plistlib.dumps(config))
        capture_label = "org.epl-forecast.collect"
        capture_path = path.with_name(capture_label + ".plist")
        capture_config = {
            **config,
            "Label": capture_label,
            "ProgramArguments": [
                uv,
                "run",
                "--locked",
                "python",
                str(Path(__file__).resolve()),
                "--data",
                str(args.data.resolve()),
                "--collect-only",
            ],
            "StandardOutPath": str(args.root.resolve() / "collection.log"),
            "StandardErrorPath": str(args.root.resolve() / "collection-errors.log"),
        }
        subprocess.run(
            ["launchctl", "bootout", f"{domain}/{capture_label}"], capture_output=True, check=False
        )
        capture_path.write_bytes(plistlib.dumps(capture_config))
        subprocess.run(["launchctl", "bootstrap", domain, str(capture_path)], check=True)
        subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
        backfill_label = "org.epl-forecast.backfill"
        subprocess.run(
            ["launchctl", "bootout", f"{domain}/{backfill_label}"], capture_output=True, check=False
        )
        backfill_path = path.with_name(backfill_label + ".plist")
        if args.backfill_requests:
            backfill_config = {
                **config,
                "Label": backfill_label,
                "StartInterval": 3600,
                "ProgramArguments": [
                    uv,
                    "run",
                    "--locked",
                    "epl-forecast",
                    "data",
                    "backfill",
                    "--root",
                    str(args.data.resolve()),
                    "--max-requests",
                    str(args.backfill_requests),
                ],
                "StandardOutPath": str(args.root.resolve() / "backfill.log"),
                "StandardErrorPath": str(args.root.resolve() / "backfill-errors.log"),
            }
            backfill_path.write_bytes(plistlib.dumps(backfill_config))
            subprocess.run(["launchctl", "bootstrap", domain, str(backfill_path)], check=True)
        else:
            backfill_path.unlink(missing_ok=True)
        print(f"Installed twelve-hour collector: {path}")
        return
    if args.collect_only:
        try:
            with writer_lock(args.data):
                result = collect(args.data)
        except SourceAccessError as error:
            result = {"status": "skipped", "reason": str(error)}
    else:
        result = capture_attempt(
            args.root,
            args.data,
            args.simulations,
            args.force,
            args.backfill_requests,
            collect_first=not args.forecast_only,
        )
    print({k: v for k, v in result.items() if k != "data"}, flush=True)
    if result["status"] in ("partial", "failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
