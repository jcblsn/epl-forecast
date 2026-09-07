"""Reusable chronological, high-information and state diagnostics for M7."""

import argparse
import csv
import json
from collections import defaultdict
from itertools import groupby
from pathlib import Path

import numpy as np

from epl_forecast.cli import load_config, save_rows
from epl_forecast.data.normalize import load_processed
from epl_forecast.evaluation import metrics
from epl_forecast.models import make_model
from epl_forecast.research.xg_diagnostics import (
    ConditionalXGScores,
    adaptation_diagnostic,
    audit_forecast_archive,
    paired_blocks,
)
from epl_forecast.storage import file_hash, write_json
from epl_forecast.training import training_matches


def historical_diagnostics(rows, matches, observations, focus_model="M7-xg-v1"):
    groups = defaultdict(dict)
    for row in rows:
        if row["match_id"] in groups[row["model_id"]]:
            raise ValueError("Duplicate model/fixture diagnostic row")
        groups[row["model_id"]][row["match_id"]] = row
    ids = set(next(iter(groups.values())))
    if any(set(g) != ids for g in groups.values()):
        raise ValueError("Model fixture sets differ")
    membership = defaultdict(set)
    for match in matches:
        if match.fixture.competition_id == "eng-premier-league":
            membership[match.fixture.season_id].update(
                [match.fixture.home_team_id, match.fixture.away_team_id]
            )
    labels, counts = {}, defaultdict(int)
    canonical = {m.fixture.match_id: m for m in matches}
    for key in sorted(ids, key=lambda k: (canonical[k].fixture.match_date, k)):
        fixture = canonical[key].fixture
        year = int(fixture.season_id[:4])
        previous = membership[f"{year - 1}-{year}"]
        teams = fixture.home_team_id, fixture.away_team_id
        early = any(counts[fixture.season_id, t] < 5 for t in teams)
        promoted = any(t not in previous for t in teams)
        labels[key] = ["overall", "opening_five" if early else "after_opening_five"]
        if promoted:
            labels[key].append("promoted_team")
            labels[key].append("promoted_opening" if early else "promoted_later")
        for team in teams:
            counts[fixture.season_id, team] += 1
    summaries, calibration, processes = [], [], []
    for model, predictions in groups.items():
        for label in sorted({x for tags in labels.values() for x in tags}):
            subset = [r for key, r in predictions.items() if label in labels[key]]
            summary, bins = metrics(subset)
            summaries.append({"model_id": model, "slice": label, **summary})
            if label == "overall":
                calibration.extend({"model_id": model, **b} for b in bins)
        errors, uncertainty = [], []
        for key, row in predictions.items():
            if not row.get("log_home_rate_mean"):
                continue
            for side in ("home", "away"):
                mean = float(row[f"log_{side}_rate_mean"])
                variance = float(row[f"log_{side}_rate_variance"])
                predicted = np.exp(mean + variance / 2)
                errors.append(predicted - observations[key][f"{side}_xg"])
                uncertainty.append(variance)
        if errors:
            processes.append(
                {
                    "model_id": model,
                    "side_observations": len(errors),
                    "xg_mean_squared_error": float(np.mean(np.square(errors))),
                    "xg_rate_bias": float(np.mean(errors)),
                    "mean_log_rate_variance": float(np.mean(uncertainty)),
                }
            )
    pairs = []
    m7 = groups[focus_model]
    for other in groups:
        if other == focus_model:
            continue
        for label in sorted({x for tags in labels.values() for x in tags}):
            keys = [key for key in sorted(ids) if label in labels[key]]
            result = paired_blocks({k: m7[k] for k in keys}, {k: groups[other][k] for k in keys})

            def residuals(predictions, keys=keys):
                return np.array(
                    [
                        [
                            float(predictions[k][f"p_{side}"])
                            - (predictions[k]["outcome"] == outcome)
                            for side, outcome in zip(("home", "draw", "away"), "HDA", strict=True)
                        ]
                        for k in keys
                    ]
                ).ravel()

            result["probability_error_correlation"] = float(
                np.corrcoef(residuals(m7), residuals(groups[other]))[0, 1]
            )
            pairs.append({"left": focus_model, "right": other, "slice": label, **result})
    return {
        "slices": summaries,
        "calibration": calibration,
        "process": processes,
        "paired_week_bootstrap": pairs,
    }, labels


def oracle_predictions(matches, observations, config, ids):
    spec = next(s for s in config["models"] if s["id"] == "M7-xg-v1")
    model = make_model(spec)
    target = sorted(
        [m for m in matches if m.fixture.match_id in ids],
        key=lambda m: (m.fixture.match_date, m.fixture.match_id),
    )
    rows = []
    season = None
    for day, games in groupby(target, key=lambda m: m.fixture.match_date):
        training = training_matches(matches, config, spec, day)
        model.fit(training, day)
        for match in games:
            if season != match.fixture.season_id:
                season = match.fixture.season_id
                print(f"Conditioning on target xG: {season}", flush=True)
            xg = observations[match.fixture.match_id]
            scores = ConditionalXGScores(model, match.fixture, xg["home_xg"], xg["away_xg"])
            p = scores.outcome_probabilities()
            rows.append(
                {
                    "match_id": match.fixture.match_id,
                    "season_id": season,
                    "match_date": str(day),
                    "forecast_as_of": str(day),
                    "model_id": "M7-target-xg-oracle",
                    "deployable": False,
                    "information_condition": "realized target xG; target goals excluded",
                    "p_home": p[0],
                    "p_draw": p[1],
                    "p_away": p[2],
                    "outcome": match.outcome,
                    "score_log_probability": scores.log_probability(
                        match.home_goals, match.away_goals
                    ),
                    "conditional_grid_tail": scores.tail_mass,
                }
            )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluations", type=Path, nargs="+", required=True)
    parser.add_argument("--config", type=Path, default=Path("configs/xg_quality_tilt.toml"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-oracle", action="store_true")
    parser.add_argument("--focus-model", default="M7-xg-v1")
    parser.add_argument("--include-markets", action="store_true")
    parser.add_argument("--adaptation-replicates", type=int, default=0)
    parser.add_argument("--archives", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    config = load_config(args.config)
    matches, _, _ = load_processed(Path("data/processed"))
    spec = next(s for s in config["models"] if s["id"] == "M7-xg-v1")
    path = Path(spec["parameters"]["observations_path"])
    if file_hash(path) != spec["parameters"]["observations_sha256"]:
        raise ValueError("xG checksum mismatch")
    observations = {r["match_id"]: r for r in json.loads(path.read_text())}
    files = [root / "predictions.csv" for root in args.evaluations]
    rows = [row for file in files for row in csv.DictReader(file.open())]
    if args.include_markets:
        market_files = [root / "market_predictions.csv" for root in args.evaluations]
        rows.extend(row for file in market_files for row in csv.DictReader(file.open()))
        files.extend(market_files)
    report, labels = historical_diagnostics(rows, matches, observations, args.focus_model)
    report["inputs"] = {str(p): file_hash(p) for p in [args.config, path, *files]}
    report["scope"] = "Historical development diagnostics; retrospective next-day xG assumed"
    if args.adaptation_replicates:
        report["adaptation"] = adaptation_diagnostic(matches, args.adaptation_replicates)
    if args.archives:
        report["archives"] = [audit_forecast_archive(path) for path in args.archives]
    write_json(args.output / "report.json", report)
    if not args.skip_oracle:
        oracle = oracle_predictions(matches, observations, config, set(labels))
        save_rows(args.output / "oracle_predictions.csv", oracle)
        report["oracle"] = [
            {"slice": label, **metrics([r for r in oracle if label in labels[r["match_id"]]])[0]}
            for label in sorted({x for tags in labels.values() for x in tags})
        ]
        report["oracle_max_conditional_grid_tail"] = max(r["conditional_grid_tail"] for r in oracle)
        report["oracle_predictions_sha256"] = file_hash(args.output / "oracle_predictions.csv")
        write_json(args.output / "report.json", report)
    print(f"Wrote {args.output / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
