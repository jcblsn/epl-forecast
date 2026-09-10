"""Evaluate a chronological known-minutes attacking roster bridge on saved M2/M7 forecasts."""

import argparse
import csv
import gzip
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import new_run_directory, provenance, write_csv
from epl_forecast.research.portable_players import PortablePlayerLayer, portable_observation_rows
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.research.roster_bridge import (
    BASELINES,
    chronological_bridge,
    distribution,
    prepare_cases,
)
from epl_forecast.storage import file_hash, write_json


def serializable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, date):
        return str(value)
    raise TypeError(type(value).__name__)


def paired_summary(rows, model_id, subgroup):
    rows = [
        row for row in rows if row["model_id"] == model_id and (subgroup == "all" or row[subgroup])
    ]
    groups = defaultdict(dict)
    for row in rows:
        groups[row["match_id"]][row["variant"]] = row
    if not groups:
        return {"fixtures": 0}
    result = {"fixtures": len(groups), "metrics": {}}
    for metric in ("score_nll", "log_loss", "brier"):
        blocks = defaultdict(list)
        for pair in groups.values():
            day = date.fromisoformat(pair["baseline"]["match_date"])
            blocks[day.isocalendar()[:2]].append(
                pair["roster_delta"][metric] - pair["baseline"][metric]
            )
        values = list(blocks.values())
        sums, counts = np.array([sum(v) for v in values]), np.array([len(v) for v in values])
        generator = np.random.default_rng(17)
        indices = generator.integers(0, len(values), size=(2000, len(values)))
        samples = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
        result["metrics"][metric] = {
            "baseline": float(np.mean([pair["baseline"][metric] for pair in groups.values()])),
            "roster_delta": float(
                np.mean([pair["roster_delta"][metric] for pair in groups.values()])
            ),
            "difference": float(sums.sum() / counts.sum()),
            "interval": np.quantile(samples, [0.025, 0.975]).tolist(),
            "calendar_week_blocks": len(values),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("runs/research-ready-v2-player-layer/manifest.json")
    )
    parser.add_argument(
        "--baselines",
        type=Path,
        default=Path("docs/experiments/m8/chronological_predictions.csv.gz"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-scored", type=date.fromisoformat, default=date(2024, 8, 1))
    parser.add_argument("--reference-matches", type=int, default=8)
    parser.add_argument("--minimum-training", type=int, default=200)
    parser.add_argument("--prepared", type=Path)
    args = parser.parse_args()
    new_run_directory(args.output)
    config = {
        "first_scored": str(args.first_scored),
        "reference_matches": args.reference_matches,
        "minimum_training": args.minimum_training,
        "mapping": "two coefficients, no intercept, ridge=1, Poisson mean estimating equation",
        "forecast": "fixed baseline distribution with plug-in expected player trait shift; player uncertainty retained as an audit",
        "oracle": "actual target identities and minutes",
        "baselines_sha256": file_hash(args.baselines),
    }
    with gzip.open(args.baselines, "rt") as stream:
        baselines = [row for row in csv.DictReader(stream) if row["model_id"] in BASELINES]
    errors = []
    for row in baselines:
        scores = distribution(row)
        errors.append(
            abs(
                scores.log_probability(int(row["home_goals"]), int(row["away_goals"]))
                - float(row["score_log_probability"])
            )
        )
        errors.extend(
            abs(p - float(row[key]))
            for p, key in zip(
                scores.outcome_probabilities(), ("p_home", "p_draw", "p_away"), strict=True
            )
        )
    if max(errors) > 1e-8:
        raise ValueError("Saved baseline reconstruction changed original forecast scores")
    print(f"Baseline reconstruction max error {max(errors):.3g}", flush=True)
    data = frozen_dataset(args.data, args.manifest)
    try:
        data_manifest = data.provenance()
        if args.prepared:
            with gzip.open(args.prepared, "rt") as stream:
                saved = json.load(stream)
            if saved["config"] != config:
                raise ValueError("Prepared cases use different experiment settings")
            cases, excluded = saved["cases"], saved["excluded"]
            for case in cases:
                for key in ("cutoff", "match_date"):
                    case[key] = date.fromisoformat(case[key])
                for side in ("home", "away"):
                    for key in ("mean", "variance"):
                        case[side][key] = np.asarray(case[side][key])
        else:
            snapshot = json.loads(args.manifest.read_text())
            portable = PortablePlayerLayer(
                portable_observation_rows(data), snapshot["canonical_snapshot_sha256"]
            )
            appearances = data.rows(
                "SELECT * FROM appearances WHERE competition_id IN ('eng-premier-league','eng-championship') ORDER BY kickoff_time,player_id"
            )
            availability = data.rows("SELECT * FROM availability WHERE provider='api_football'")
            cases, excluded = prepare_cases(
                baselines,
                appearances,
                portable,
                availability,
                reference_matches=args.reference_matches,
                progress=lambda index, total, prepared: print(
                    f"Prepared {index}/{total}; eligible {prepared}", flush=True
                ),
            )
    finally:
        data.close()
    with gzip.open(args.output / "cases.json.gz", "wt") as stream:
        json.dump(
            {"config": config, "cases": cases, "excluded": excluded},
            stream,
            default=serializable,
            allow_nan=False,
        )
    print(f"Scoring {len(cases)} cases", flush=True)
    evaluation = chronological_bridge(cases, args.first_scored, args.minimum_training)
    predictions = evaluation.pop("predictions")
    if not predictions:
        raise ValueError("No eligible scored fixtures")
    write_csv(args.output / "predictions.csv", list(predictions[0]), predictions)
    summary = {
        "config": config,
        "baseline_reconstruction_max_error": max(errors),
        "prepared_fixtures": len(cases),
        "excluded": excluded,
        "evaluation": evaluation,
        "comparisons": {
            model: {
                subgroup: paired_summary(predictions, model, subgroup)
                for subgroup in (
                    "all",
                    "transfer",
                    "injury",
                    "large_lineup_change",
                    "opening",
                    "promoted",
                )
            }
            for model in BASELINES
        },
    }
    write_json(args.output / "summary.json", summary)
    write_json(args.output / "provenance.json", provenance(config, data_manifest))
    print(json.dumps(summary["comparisons"], indent=2), flush=True)


if __name__ == "__main__":
    main()
