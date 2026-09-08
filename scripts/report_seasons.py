"""Export pooled season score comparisons and calibration figures."""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from epl_forecast.artifacts import retain_execution
from epl_forecast.cli import save_rows
from epl_forecast.season_evaluation import summarize

ORIGINS = ["preseason", "MW6", "MW12", "MW19", "MW30"]
MODELS = ["M2", "M4", "M5", "M7"]


def read_rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def paired_comparisons(rows, seed=20260908, samples=10000):
    lookup = {(r["model_id"], r["origin"], r["season_id"], r["team_id"]): r for r in rows}
    if len(lookup) != len(rows):
        raise ValueError("Duplicate club-season origins")
    baseline_keys = {(o, s, t) for m, o, s, t in lookup if m == "M2"}
    for model in MODELS:
        if {(o, s, t) for m, o, s, t in lookup if m == model} != baseline_keys:
            raise ValueError("Models must have matched club-season origins")
    rng = np.random.default_rng(seed)
    output = []
    for origin in ORIGINS:
        baseline = [r for r in rows if r["model_id"] == "M2" and r["origin"] == origin]
        seasons = sorted({r["season_id"] for r in baseline})
        indices = rng.integers(0, len(seasons), size=(samples, len(seasons)))
        for model in MODELS[1:]:
            for metric in (
                "trps",
                "points_crps",
                "title_brier",
                "top_four_brier",
                "relegation_brier",
            ):
                grouped = []
                for season in seasons:
                    differences = [
                        float(lookup[model, origin, season, r["team_id"]][metric])
                        - float(r[metric])
                        for r in baseline
                        if r["season_id"] == season
                    ]
                    if len(differences) != 20:
                        raise ValueError("Paired comparisons require complete seasons")
                    grouped.append(np.mean(differences))
                delta = np.array(grouped)
                lo, hi = np.quantile(delta[indices].mean(axis=1), [0.025, 0.975])
                output.append(
                    {
                        "model_id": model,
                        "origin": origin,
                        "metric": metric,
                        "difference_vs_M2": float(delta.mean()),
                        "season_cluster_ci_low": float(lo),
                        "season_cluster_ci_high": float(hi),
                        "club_seasons": len(baseline),
                        "seasons": len(seasons),
                    }
                )
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    retain_execution(args.output)
    rows = read_rows(args.evaluation / "club_seasons.csv")
    calibration = read_rows(args.evaluation / "calibration.csv")
    summary = read_rows(args.evaluation / "summary.csv")
    numeric_rows = []
    for row in rows:
        converted = {}
        for key, value in row.items():
            if key == "promoted":
                converted[key] = value == "True"
            elif key in ("model_id", "origin", "season_id", "team_id", "as_of"):
                converted[key] = value
            else:
                converted[key] = float(value)
        numeric_rows.append(converted)
    subgroup_scores = []
    for promoted in (True, False):
        scores, _ = summarize([r for r in numeric_rows if r["promoted"] == promoted])
        subgroup_scores.extend(
            {"subgroup": "promoted" if promoted else "incumbent", **r} for r in scores
        )
    save_rows(args.output / "subgroups.csv", subgroup_scores)
    save_rows(args.output / "paired_comparisons.csv", paired_comparisons(rows))
    fig, axes = plt.subplots(5, 4, figsize=(15, 15), sharex=True, sharey=True)
    for i, origin in enumerate(ORIGINS):
        for j, model in enumerate(MODELS):
            ax = axes[i, j]
            selected = [
                r
                for r in calibration
                if r["model_id"] == model and r["origin"] == origin and r["event"] == "pit"
            ]
            ax.bar(
                [float(r["bin_lower"]) for r in selected],
                [float(r["observed_frequency"]) for r in selected],
                width=0.1,
                align="edge",
                edgecolor="white",
            )
            ax.axhline(0.1, color="black", linestyle="--", linewidth=1)
            ax.set_title(f"{model} · {origin}")
            ax.set_xlim(0, 1)
    counts = sorted({int(r["club_seasons"]) for r in summary})
    fig.suptitle(f"Randomized points PIT · club-seasons per panel: {counts}")
    fig.supxlabel("PIT")
    fig.supylabel("Fraction of club-seasons")
    fig.tight_layout()
    fig.savefig(args.output / "points_pit.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(5, 3, figsize=(13, 18), sharex=True, sharey=True)
    for i, origin in enumerate(ORIGINS):
        for j, event in enumerate(("title", "top_four", "relegation")):
            ax = axes[i, j]
            ax.plot([0, 1], [0, 1], "k--", linewidth=1)
            for model in MODELS:
                selected = [
                    r
                    for r in calibration
                    if r["model_id"] == model
                    and r["origin"] == origin
                    and r["event"] == event
                    and int(r["count"])
                ]
                x = [float(r["mean_prediction"]) for r in selected]
                y = [float(r["observed_frequency"]) for r in selected]
                (line,) = ax.plot(x, y, label=model, linewidth=1)
                ax.scatter(
                    x, y, s=[8 + int(r["count"]) / 2 for r in selected], color=line.get_color()
                )
            ax.set_title(f"{origin} · {event}")
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
    axes[0, 0].legend()
    fig.suptitle("Event reliability · marker area reflects bin count; sparse bins are noisy")
    fig.supxlabel("Mean forecast probability")
    fig.supylabel("Observed frequency")
    fig.tight_layout()
    fig.savefig(args.output / "event_reliability.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 4, figsize=(16, 4), sharey=True)
    for ax, level in zip(axes, (50, 80, 90, 95), strict=True):
        for model in MODELS:
            selected = {r["origin"]: r for r in summary if r["model_id"] == model}
            ax.plot(
                ORIGINS,
                [float(selected[o][f"coverage_{level}"]) for o in ORIGINS],
                marker="o",
                label=model,
            )
        ax.axhline(level / 100, color="black", linestyle="--")
        ax.set_title(f"{level}% central points interval")
        ax.set_ylim(0, 1)
        ax.tick_params(axis="x", rotation=30)
    axes[0].legend()
    fig.supylabel("Empirical coverage")
    fig.tight_layout()
    fig.savefig(args.output / "points_coverage.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
