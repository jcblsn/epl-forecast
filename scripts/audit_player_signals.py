"""Audit availability and stability of retained player signals before choosing features."""

import argparse
import json
from pathlib import Path

from epl_forecast.artifacts import retain_execution
from epl_forecast.datasets import Dataset
from epl_forecast.research.player_signals import signal_audit
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.storage import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seasons", nargs="*", default=None)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    retain_execution(args.output)
    data = (
        frozen_dataset(args.data, args.manifest) if args.manifest else Dataset(args.data)
    )
    try:
        report = signal_audit(data, args.seasons)
    finally:
        data.close()
    write_json(args.output / "signal_audit.json", report)
    print(
        json.dumps(
            {
                "process_seasons": report["player_process"]["by_season"],
                "appearance_reliability": report["appearances"]["reliability"],
                "process_reliability": report["player_process"]["reliability"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
