"""Known-state mechanics checks for the cross-division club-state candidate."""

import argparse
from pathlib import Path

from epl_forecast.artifacts import new_run_directory
from epl_forecast.research.cross_division_diagnostics import (
    coordinate_equivalence,
    crossing_sensitivity,
    promotion_calibration,
    recovery_checks,
)
from epl_forecast.storage import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=30)
    parser.add_argument("--sensitivity-replicates", type=int, default=12)
    parser.add_argument("--transition-replicates", type=int, default=8)
    parser.add_argument("--first-matches", type=int, default=10)
    parser.add_argument("--quality-gaps", type=float, nargs="+", default=[0.0, 0.45])
    args = parser.parse_args()
    new_run_directory(args.output)
    report = {
        "recovery": recovery_checks(args.replicates),
        "crossing_sensitivity": crossing_sensitivity(args.sensitivity_replicates),
        "coordinates": coordinate_equivalence(),
        "promotion_calibration": [
            promotion_calibration(
                replicates=args.transition_replicates,
                quality_gap=gap,
                first_matches=args.first_matches,
            )
            for gap in args.quality_gaps
        ],
    }
    write_json(args.output / "state_mechanics.json", report)
    for row in report["recovery"]["results"]:
        print(
            f"{row['model']:11s} level error {row['level_error']:+.4f}"
            f" (sd {row['level_sd']:.4f}, coverage {row['level_covered']:.2f});"
            f" home coverage {row['home_covered']:.2f};"
            f" quality corr {row['quality_correlation']:.3f}"
            f" mse {row['quality_mse']:.4f}",
            flush=True,
        )
    for row in report["crossing_sensitivity"]:
        print(
            f"crossings {row['crossings_per_season']}: level sd {row['level_posterior_sd']:.4f}"
            f" rmse {row['level_root_mean_squared_error']:.4f}",
            flush=True,
        )
    for block in report["promotion_calibration"]:
        print(f"quality gap {block['quality_gap']:g}", flush=True)
        for row in block["results"]:
            print(
                f"  {row['model']:11s} {row['slice']:16s} n={row['team_matches']:5d}"
                f" mean log-rate error {row['mean_log_rate_error']:+.4f}"
                f" (se {row['standard_error']:.4f}) rmse {row['root_mean_squared_error']:.4f}",
                flush=True,
            )
    print(report["coordinates"], flush=True)


if __name__ == "__main__":
    main()
