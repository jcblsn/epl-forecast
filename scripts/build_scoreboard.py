"""Build the permanent matched research scoreboard from retained forecasts."""

import argparse
import csv
import gzip
from pathlib import Path

from epl_forecast.artifacts import new_run_directory
from epl_forecast.cli import save_rows
from epl_forecast.research.scoreboard import build_scoreboard
from epl_forecast.storage import file_hash, write_json


def read_rows(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--markets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--candidates",
        nargs="+",
        default=["M2-attack-defense-v1", "M5-quality-tilt-poisson", "M7-xg-v1"],
    )
    parser.add_argument(
        "--retained",
        nargs="+",
        default=["M2-attack-defense-v1", "M5-quality-tilt-poisson", "M7-xg-v1"],
    )
    parser.add_argument("--reference", default="M2-attack-defense-v1")
    parser.add_argument("--preclosing", default="market:market_average_preclosing")
    parser.add_argument("--closing", default="market:market_average_closing")
    parser.add_argument("--calibration-bins", type=int, default=10)
    args = parser.parse_args()
    if args.calibration_bins < 1:
        parser.error("Calibration bins must be positive")
    new_run_directory(args.output)
    result = build_scoreboard(
        read_rows(args.predictions),
        read_rows(args.markets),
        args.candidates,
        args.reference,
        args.preclosing,
        args.closing,
        args.retained,
        args.calibration_bins,
    )
    save_rows(args.output / "overall.csv", result["overall"])
    save_rows(args.output / "by_season.csv", result["by_season"])
    save_rows(args.output / "calibration.csv", result["calibration"])
    save_rows(args.output / "comparisons.csv", result["comparisons"])
    write_json(
        args.output / "manifest.json",
        {
            "predictions": str(args.predictions),
            "predictions_sha256": file_hash(args.predictions),
            "markets": str(args.markets),
            "markets_sha256": file_hash(args.markets),
            "matched_fixtures": len(result["matched_fixture_ids"]),
            "candidate_ids": args.candidates,
            "retained_structural_ids": args.retained,
            "reference_id": args.reference,
            "preclosing_market_id": args.preclosing,
            "closing_market_id": args.closing,
            "best_retained_structural_model": result["best_retained_structural_model"],
            "calibration_bins": args.calibration_bins,
            "interpretation": "Historical descriptive scoreboard; gap fractions are scale, not targets or deployment evidence.",
        },
    )


if __name__ == "__main__":
    main()
