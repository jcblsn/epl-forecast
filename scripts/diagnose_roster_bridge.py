"""Identification and representation check for the failed known-minutes roster bridge."""

import argparse
import gzip
import json
from datetime import date
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import new_run_directory
from epl_forecast.research.roster_bridge import BASELINES, representation_audit
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("runs/roster-bridge-v1/cases.json.gz"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-scored", type=date.fromisoformat, default=date(2024, 8, 1))
    parser.add_argument("--draws", type=int, default=400)
    args = parser.parse_args()
    new_run_directory(args.output)
    with gzip.open(args.cases, "rt") as stream:
        saved = json.load(stream)
    cases = [case for case in saved["cases"] if case["cutoff"] >= str(args.first_scored)]
    if not cases:
        raise ValueError("No scored cases in the retained bridge run")
    for case in cases:
        for side in ("home", "away"):
            case[side]["mean"] = np.asarray(case[side]["mean"])
    audit = {
        "config": {
            "cases_sha256": file_hash(args.cases),
            "bridge_config": saved["config"],
            "first_scored": str(args.first_scored),
            "permutation_draws": args.draws,
            "question": "Can any coefficient choice for this design improve the fixed baselines?",
        },
        "scored_fixtures": len(cases),
        "audits": [representation_audit(cases, model, draws=args.draws) for model in BASELINES],
    }
    write_json(args.output / "representation_audit.json", audit)
    for entry in audit["audits"]:
        print(f"== {entry['model_id']} fixtures {entry['fixtures']}", flush=True)
        for stratum in entry["strata"]:
            print(
                f"  change>={stratum['minimum_changed_match_equivalents']:g}"
                f" n={stratum['team_matches']:5d}"
                f" share={stratum['share_of_team_matches']:.3f}"
                f" beta={np.round(stratum['beta'], 3)}"
                f" se={np.round(stratum['standard_error'], 3)}"
                f" gain={stratum['gain']:.3f}"
                f" p={stratum['p_value']:.3f}",
                flush=True,
            )


if __name__ == "__main__":
    main()
