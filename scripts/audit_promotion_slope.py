"""Measure how much of a promoted club's Championship state actually transfers."""

import argparse
import json
from datetime import date
from pathlib import Path

from epl_forecast.artifacts import new_run_directory, provenance
from epl_forecast.datasets import load_dataset
from epl_forecast.research.cross_division_diagnostics import promotion_slope_audit
from epl_forecast.storage import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2025, 7, 1))
    parser.add_argument("--target-season", default="2025-2026")
    args = parser.parse_args()
    new_run_directory(args.output)
    matches, _, manifest = load_dataset(args.data)
    report = promotion_slope_audit(matches, args.as_of, args.target_season)
    write_json(args.output / "promotion_slope.json", report)
    config = {"as_of": str(args.as_of), "target_season": args.target_season}
    write_json(args.output / "provenance.json", provenance(config, manifest))
    print(json.dumps(report, indent=2, default=float), flush=True)


if __name__ == "__main__":
    main()
