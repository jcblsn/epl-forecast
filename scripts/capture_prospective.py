"""Run the twelve-hour local collector and forecast archive for both leagues."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from epl_forecast.data.capture import SourceAccessError, writer_lock
from epl_forecast.data.collect import collect
from epl_forecast.prospective import capture_attempt, install_launch_agent


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
        uv = shutil.which("uv")
        if uv is None:
            raise ValueError("uv must be installed")
        worker = [uv, "run", "--locked", "python", str(Path(__file__).resolve())]
        install_launch_agent(
            "org.epl-forecast.collect",
            [*worker, "--data", str(args.data.resolve()), "--collect-only"],
            args.root,
            12 * 3600,
            logs="collection",
        )
        path = install_launch_agent(
            "org.epl-forecast.prospective",
            [
                *worker,
                "--root",
                str(args.root.resolve()),
                "--data",
                str(args.data.resolve()),
                "--simulations",
                str(args.simulations),
                "--backfill-requests",
                "0",
                "--forecast-only",
            ],
            args.root,
            12 * 3600,
            logs="launchd",
        )
        backfill_label = "org.epl-forecast.backfill"
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{backfill_label}"],
            capture_output=True,
            check=False,
        )
        backfill_path = path.with_name(backfill_label + ".plist")
        if args.backfill_requests:
            install_launch_agent(
                backfill_label,
                [
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
                args.root,
                3600,
                logs="backfill",
            )
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
