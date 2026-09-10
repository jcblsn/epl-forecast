"""Prior sensitivity of the cross-division scoring level in the uncentered coordinate."""

import argparse
import json
from datetime import date
from pathlib import Path

from epl_forecast.artifacts import new_run_directory, provenance
from epl_forecast.datasets import Dataset, load_dataset
from epl_forecast.research.cross_division_diagnostics import scoring_level_prior_sensitivity
from epl_forecast.storage import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2025, 7, 1))
    args = parser.parse_args()
    new_run_directory(args.output)
    matches, _, manifest = load_dataset(args.data)
    data = Dataset(args.data)
    try:
        observations = data.process()
    finally:
        data.close()
    report = {
        "goals_only": scoring_level_prior_sensitivity(matches, args.as_of),
        "goals_xg": scoring_level_prior_sensitivity(matches, args.as_of, observations),
    }
    write_json(args.output / "scoring_level_identification.json", report)
    write_json(args.output / "provenance.json", provenance({"as_of": str(args.as_of)}, manifest))
    for name, block in report.items():
        print(
            f"{name}: level range {block['championship_scoring_level_range']:.4f}"
            f" = {block['championship_scoring_level_range_in_posterior_sd']:.2f} posterior SD;"
            f" home advantage range {block['home_advantage_range']:.4f}",
            flush=True,
        )
    print(json.dumps(report["goals_xg"]["grid"], indent=2), flush=True)


if __name__ == "__main__":
    main()
