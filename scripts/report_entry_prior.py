"""Summary tables for the entry-prior comparison, read from a completed run directory."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

TREATMENTS = ("current", "population", "transition", "source", "memory", "two_division")


def read(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def number(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except ValueError:
        return value


def rows(path):
    return [{k: number(v) for k, v in row.items()} for row in read(path)]


def table(title, header, lines):
    print(f"\n### {title}\n")
    print("| " + " | ".join(header) + " |")
    print("| " + " | ".join("---" for _ in header) + " |")
    for line in lines:
        print("| " + " | ".join(line) + " |")


def interval(row):
    if row["interval_95"] is None:
        return f"{row['difference']:+.4f}"
    low, high = row["interval_95"]
    return f"{row['difference']:+.4f} [{low:+.4f}, {high:+.4f}]"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--decimals", type=int, default=4)
    args = parser.parse_args()
    seasons = rows(args.run / "club_seasons.csv")
    openings = rows(args.run / "opening_matches.csv")
    priors = rows(args.run / "entry_priors.csv")
    comparisons = json.loads((args.run / "comparisons.json").read_text())

    crossers = [r for r in seasons if r["entry_cohort"] != "continuing"]
    for origin in sorted({r["origin"] for r in seasons}):
        lines = []
        for treatment in TREATMENTS:
            selected = [r for r in crossers if r["model_id"] == treatment and r["origin"] == origin]
            if not selected:
                continue
            lines.append(
                [
                    treatment,
                    str(len(selected)),
                    f"{np.mean([r['trps'] for r in selected]):.4f}",
                    f"{np.mean([r['points_crps'] for r in selected]):.3f}",
                    f"{100 * np.mean([r['coverage_90'] for r in selected]):.1f}%",
                    f"{np.mean([r['width_90'] for r in selected]):.2f}",
                ]
            )
        table(
            f"Boundary crossers, {origin}",
            ["Prior", "Club-seasons", "Rank RPS", "Points CRPS", "90% coverage", "90% width"],
            lines,
        )

    for scope, selected in (
        ("first five appearances", [r for r in openings if r["appearance"] <= 5]),
        ("first ten appearances", openings),
    ):
        lines = []
        for treatment in TREATMENTS:
            picked = [r for r in selected if r["model_id"] == treatment]
            if not picked:
                continue
            lines.append(
                [
                    treatment,
                    str(len(picked)),
                    f"{np.mean([r['log_loss'] for r in picked]):.5f}",
                    f"{np.mean([r['score_nll'] for r in picked]):.5f}",
                    f"{np.mean([r['brier'] for r in picked]):.5f}",
                ]
            )
        table(
            f"Opening matches, {scope}",
            ["Prior", "Matches", "H/D/A log loss", "Score NLL", "Brier"],
            lines,
        )

    for target in ("entry", "season"):
        grouped = defaultdict(list)
        for row in priors:
            if row["target"] == target:
                grouped[row["treatment"], row["dimension"]].append(row)
        lines = []
        for treatment in TREATMENTS:
            for dimension in ("attack", "defense"):
                selected = grouped.get((treatment, dimension))
                if not selected:
                    continue
                errors = np.array([r["prior_mean"] - r["realized"] for r in selected])
                lines.append(
                    [
                        treatment,
                        dimension,
                        f"{np.mean([r['prior_sd'] for r in selected]):.3f}",
                        f"{np.sqrt(np.mean(errors**2)):.3f}",
                        f"{errors.mean():+.3f}",
                        f"{np.mean([r['log_score'] for r in selected]):.3f}",
                    ]
                )
        table(
            f"Entry-strength accuracy against the realized {target} label",
            ["Prior", "Dimension", "Prior SD", "RMSE", "Bias", "Gaussian log score"],
            lines,
        )

    for breakout in ("transition", "age_bucket"):
        lines = []
        for key in sorted({r[breakout] for r in crossers}):
            for treatment in TREATMENTS:
                picked = [
                    r
                    for r in crossers
                    if r[breakout] == key
                    and r["model_id"] == treatment
                    and r["origin"] == "preseason"
                ]
                if not picked:
                    continue
                lines.append(
                    [
                        key,
                        treatment,
                        str(len(picked)),
                        f"{np.mean([r['points_crps'] for r in picked]):.3f}",
                        f"{100 * np.mean([r['coverage_90'] for r in picked]):.1f}%",
                        f"{np.mean([r['width_90'] for r in picked]):.2f}",
                    ]
                )
        table(
            f"Preseason boundary crossers by {breakout}",
            [breakout, "Prior", "Club-seasons", "Points CRPS", "90% coverage", "90% width"],
            lines,
        )

    print("\n### Paired differences with season-clustered 95% intervals\n")
    print("| Scope | Candidate − comparator | Metric | Difference |")
    print("| --- | --- | --- | --- |")
    for row in comparisons:
        scope = row["scope"]
        for extra in ("transition", "age_bucket"):
            if row.get(extra):
                scope = f"{scope} ({row[extra]})"
        print(
            f"| {scope} | {row['candidate']} − {row['comparator']} | {row['metric']} "
            f"| {interval(row)} |"
        )


if __name__ == "__main__":
    main()
