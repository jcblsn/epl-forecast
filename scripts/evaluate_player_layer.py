"""Chronological and cross-club evaluation of standalone player-process representations."""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import new_run_directory, provenance, write_csv
from epl_forecast.datasets import Dataset
from epl_forecast.research.player_layer import (
    CANDIDATE_NOTES,
    CANDIDATES,
    PlayerLayer,
    observation_rows,
)
from epl_forecast.research.player_layer_evaluation import (
    chronological_evaluation,
    evaluate_transfers,
    paired_bootstrap,
    summarize,
    transfer_episodes,
)
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.storage import write_json

SCORE_FIELDS = [
    "player_id",
    "player_name",
    "cutoff",
    "role",
    "changed_club",
    "club_before",
    "club_after",
    "prior_effective_exposure",
    "target_exposure",
    "observed",
    "expected",
    "parameter_sd",
    "crps",
    "absolute_error",
    "covered_50",
    "covered_90",
    "interval_width_90",
]


def month_starts(start, end):
    cutoffs, current = [], start
    while current <= end:
        cutoffs.append(current)
        current = (current.replace(day=28) + timedelta(days=7)).replace(day=1)
    return cutoffs


def slices(scores):
    def group(predicate):
        selected = [s for s in scores if predicate(s)]
        return summarize(selected)

    return {
        "all": summarize(scores),
        "changed_club": group(lambda s: s["changed_club"]),
        "same_club": group(lambda s: not s["changed_club"]),
        "low_history": group(lambda s: s["prior_effective_exposure"] < 5),
        "high_history": group(lambda s: s["prior_effective_exposure"] >= 20),
        **{
            f"role_{role}": group(lambda s, role=role: s["role"] == role)
            for role in ("GK", "DEF", "MID", "FWD")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--marks", nargs="+", default=["xg", "xa", "process_shots"])
    parser.add_argument("--first-cutoff", default="2023-09-01")
    parser.add_argument("--last-cutoff", default="2026-06-01")
    parser.add_argument("--first-scored", default="2025-01-01")
    parser.add_argument("--horizon-days", type=int, default=90)
    args = parser.parse_args()
    new_run_directory(args.output)
    data = frozen_dataset(args.data, args.manifest) if args.manifest else Dataset(args.data)
    try:
        rows = observation_rows(data)
        manifest = data.provenance()
    finally:
        data.close()
    layer = PlayerLayer(rows)
    cutoffs = month_starts(date.fromisoformat(args.first_cutoff), date.fromisoformat(args.last_cutoff))
    first_scored = date.fromisoformat(args.first_scored)
    summary = {"horizon_days": args.horizon_days, "marks": {}, "candidate_notes": CANDIDATE_NOTES}
    for mark in args.marks:
        print(f"Evaluating {mark}", flush=True)
        evaluation = chronological_evaluation(
            layer, mark, cutoffs, args.horizon_days, first_scored
        )
        scored = evaluation["scored"]
        episodes = transfer_episodes(layer, mark)
        transfers = evaluate_transfers(
            layer, mark, episodes, evaluation.get("all_cases", []), args.horizon_days
        )
        reference = "long_run"
        summary["marks"][mark] = {
            "cases": evaluation["cases"],
            "chronological": {name: slices(values) for name, values in scored.items()},
            "chronological_paired_vs_long_run": {
                name: paired_bootstrap(values, scored[reference])
                for name, values in scored.items()
                if name != reference
            },
            "transfer_episodes": len(episodes),
            "transfer": {name: summarize(values) for name, values in transfers.items()},
            "transfer_paired_vs_long_run": {
                name: paired_bootstrap(values, transfers[reference])
                for name, values in transfers.items()
                if name != reference
            },
            "fitted_coefficients": {
                name: dict(
                    zip(
                        ["intercept", *(model["names"] or [])],
                        [float(v) for v in model["beta"]],
                        strict=True,
                    )
                )
                for name, model in evaluation.get("models", {}).items()
            },
        }
        for name in CANDIDATES:
            write_csv(args.output / f"{mark}_{name}_chronological.csv", SCORE_FIELDS, scored[name])
            write_csv(args.output / f"{mark}_{name}_transfer.csv", SCORE_FIELDS, transfers[name])
    write_json(args.output / "summary.json", summary)
    write_json(
        args.output / "provenance.json",
        provenance({"marks": args.marks, "horizon_days": args.horizon_days}, manifest),
    )
    print(
        json.dumps(
            {
                mark: {
                    name: {
                        "crps": round(values["all"]["crps"], 5) if values["all"] else None,
                        "coverage_90": round(values["all"]["coverage_90"], 3)
                        if values["all"]
                        else None,
                    }
                    for name, values in block["chronological"].items()
                }
                for mark, block in summary["marks"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
