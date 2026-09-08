"""Freeze locally retained evidence and experiment-specific eligibility."""

import argparse
import json
from pathlib import Path

from epl_forecast.research.readiness import freeze_research


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=int, default=2013)
    parser.add_argument("--end", type=int, default=2026)
    args = parser.parse_args()
    manifest = freeze_research(args.data, args.output, args.start, args.end)
    report = manifest["readiness"]
    print(
        json.dumps(
            {
                "manifest": str(args.output),
                "snapshot_sha256": manifest["canonical_snapshot_sha256"],
                "eligible_cohort_counts": {
                    k: len(v) for k, v in report["eligible_cohorts"].items()
                },
                "missing_recent_player_histories": {
                    k: len(v) for k, v in report["missing_recent_player_histories"].items()
                },
                "roster_experiment_ready": report["roster_experiment_ready"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
