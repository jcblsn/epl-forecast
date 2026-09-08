"""Paired attribution with season and match-dependence sensitivity."""

from collections import defaultdict
from datetime import date

import numpy as np

COMPARISONS = [
    ("posterior", "fixed", "current-state uncertainty"),
    ("drift", "posterior", "deterministic future mean reversion"),
    ("evolution", "drift", "future innovation uncertainty"),
    ("evolution", "conditional_promoted", "current promoted-state uncertainty"),
    ("xg", "evolution", "xG observations at fixed dynamics and score law"),
    ("gamma_scores", "evolution", "shared match tempo at fixed fitted state"),
    ("M2_calibrated", "M2", "chronologically calibrated M2 season dependence"),
    ("M4", "M2_calibrated", "M4 versus split-product M2"),
    ("M5", "M2_calibrated", "M5 versus split-product M2"),
    ("M7", "M2_calibrated", "M7 versus split-product M2"),
]


def cluster_interval(values, clusters, seed, samples=4000):
    groups = defaultdict(list)
    for value, cluster in zip(values, clusters, strict=True):
        groups[cluster].append(value)
    if not groups:
        raise ValueError("Cannot compare empty samples")
    totals = np.array([sum(v) for v in groups.values()])
    counts = np.array([len(v) for v in groups.values()])
    if len(groups) < 2:
        interval = None
    else:
        rng = np.random.default_rng(seed)
        draws = rng.integers(len(groups), size=(samples, len(groups)))
        means = totals[draws].sum(axis=1) / counts[draws].sum(axis=1)
        interval = list(map(float, np.quantile(means, [0.025, 0.975])))
    return {
        "difference": float(totals.sum() / counts.sum()),
        "interval_95": interval,
        "clusters": len(groups),
        "observations": int(counts.sum()),
    }


def attribution_report(season_rows, match_rows, seed=20260909):
    season_metrics = [
        "trps",
        "points_crps",
        "points_sd",
        "coverage_90",
        "width_90",
        "title_brier",
        "top_four_brier",
        "relegation_brier",
    ]
    result = {
        "season_comparisons": [],
        "match_comparisons": [],
        "missing_comparisons": [],
        "interpretation": "Differences are candidate minus comparator. Lower losses are better; greater width or coverage alone is not a proper-score improvement. Season intervals resample entire seasons. Match intervals show iid-match, calendar-week and season dependence separately. Single-season intervals are not estimated.",
    }
    origins = sorted({r["origin"] for r in season_rows})
    for candidate, comparator, mechanism in COMPARISONS:
        for origin in origins:
            for kind, rows, key, metrics, schemes in (
                ("season", season_rows, "team_id", season_metrics, ("season",)),
                (
                    "match",
                    match_rows,
                    "match_id",
                    ("log_loss", "score_nll"),
                    ("iid_match", "calendar_week", "season"),
                ),
            ):
                selected = {
                    name: {
                        (r["season_id"], r[key]): r
                        for r in rows
                        if r["model_id"] == name and r["origin"] == origin
                    }
                    for name in (candidate, comparator)
                }
                a, b = selected[candidate], selected[comparator]
                if not a or not b:
                    result["missing_comparisons"].append(
                        {
                            "candidate": candidate,
                            "comparator": comparator,
                            "origin": origin,
                            "kind": kind,
                        }
                    )
                    continue
                if a.keys() != b.keys():
                    raise ValueError(
                        f"Unmatched {kind} cohorts for {candidate} versus {comparator}"
                    )
                keys = sorted(a)
                for scheme in schemes:
                    clusters = []
                    for k in keys:
                        if scheme == "season":
                            cluster = k[0]
                        elif scheme == "calendar_week":
                            iso = date.fromisoformat(a[k]["match_date"]).isocalendar()
                            cluster = iso.year, iso.week
                        else:
                            cluster = k
                        clusters.append(cluster)
                    for metric in metrics:
                        result[f"{kind}_comparisons"].append(
                            {
                                "candidate": candidate,
                                "comparator": comparator,
                                "mechanism": mechanism,
                                "origin": origin,
                                "metric": metric,
                                "dependence": scheme,
                                **cluster_interval(
                                    [float(a[k][metric]) - float(b[k][metric]) for k in keys],
                                    clusters,
                                    seed,
                                ),
                            }
                        )
    return result
