"""Proper season scores and pooled calibration from simulation marginals."""

from collections import defaultdict
from datetime import timedelta

import numpy as np


def rank_scores(probabilities, observed_categories):
    """Per-team TRPS contributions; categories may represent grouped partial ranks."""
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(observed_categories)
    if p.ndim != 2 or p.shape[1] < 2 or y.shape != (len(p),) or not len(p):
        raise ValueError("Require nonempty team by rank probabilities and observed categories")
    if (
        not np.isfinite(p).all()
        or (p < 0).any()
        or not np.allclose(p.sum(axis=1), 1, atol=1e-10, rtol=0)
        or not np.issubdtype(y.dtype, np.integer)
        or ((y < 1) | (y > p.shape[1])).any()
    ):
        raise ValueError("Invalid rank probabilities or categories")
    empirical = y[:, None] <= np.arange(1, p.shape[1])
    return np.mean((p.cumsum(axis=1)[:, :-1] - empirical) ** 2, axis=1)


def season_origins(matches):
    ordered = sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id))
    if len(ordered) != 380 or len({m.fixture.match_id for m in ordered}) != 380:
        raise ValueError("Origins require a complete 380-match season")
    return {"preseason": ordered[0].fixture.match_date} | {
        f"MW{week}": ordered[week * 10 - 1].available_on for week in (6, 12, 19, 30)
    }


def points_metrics(distribution, actual, uniform):
    values = np.array(sorted(map(int, distribution)))
    p = np.array([distribution[str(v)] for v in values], dtype=float)
    if (
        not len(values)
        or not np.isfinite(p).all()
        or (p < 0).any()
        or not np.isclose(p.sum(), 1, atol=1e-10, rtol=0)
        or not 0 <= uniform < 1
    ):
        raise ValueError("Invalid points distribution or PIT randomizer")
    cdf = p.cumsum()
    mean = float(values @ p)
    result = {
        "points_error": mean - actual,
        "points_sd": float(np.sqrt(((values - mean) ** 2) @ p)),
        "points_crps": float(np.abs(values - actual) @ p - np.sum(p * values * (2 * cdf - p - 1))),
        "pit": float(p[values < actual].sum() + uniform * p[values == actual].sum()),
    }
    for level in (50, 80, 90, 95):
        tail = (1 - level / 100) / 2
        lo, hi = values[np.searchsorted(cdf, [tail, 1 - tail])]
        result[f"coverage_{level}"] = int(lo <= actual <= hi)
        result[f"width_{level}"] = int(hi - lo)
    return result


def score_forecast(forecast, truth, promoted, seed):
    actual = {r["team_id"]: r for r in truth["teams"]}
    if {r["team_id"] for r in forecast["teams"]} != set(actual):
        raise ValueError("Forecast and truth teams differ")
    rng = np.random.default_rng(np.random.SeedSequence([seed, 0x504954]))
    rows = []
    for team in sorted(forecast["teams"], key=lambda r: r["team_id"]):
        target = actual[team["team_id"]]
        p = np.asarray(team["position_probabilities"])
        q = np.asarray(target["position_probabilities"])
        # Expected score over shared observed ranks preserves ties without arbitrary ordering.
        trps = sum(q[i] * rank_scores([p], np.array([i + 1]))[0] for i in np.flatnonzero(q))
        row = {
            "team_id": team["team_id"],
            "promoted": team["team_id"] in promoted,
            "actual_points": target["mean_points"],
            "mean_points": team["mean_points"],
            "trps": float(trps),
            **points_metrics(team["points_distribution"], target["mean_points"], rng.random()),
        }
        for event in ("title", "top_four", "relegation"):
            probability = team[f"{event}_probability"]
            observed = target[f"{event}_probability"]
            row[f"{event}_probability"] = probability
            row[f"{event}_observed"] = observed
            row[f"{event}_brier"] = probability**2 - 2 * probability * observed + observed
        rows.append(row)
    return rows


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["model_id"], row["origin"]].append(row)
    summaries, calibration = [], []
    for (model, origin), group in sorted(groups.items()):
        base = {"model_id": model, "origin": origin}
        errors = np.array([r["points_error"] for r in group])
        promoted = [r["points_error"] for r in group if r["promoted"]]
        summary = base | {
            "club_seasons": len(group),
            "seasons": len({r["season_id"] for r in group}),
            "points_bias": float(errors.mean()),
            "points_rmse": float(np.sqrt(np.mean(errors**2))),
            "promoted_club_seasons": len(promoted),
            "promoted_points_bias": float(np.mean(promoted)) if promoted else None,
            "promoted_overpredicted": sum(e > 0 for e in promoted),
        }
        for key in (
            ("trps", "points_crps", "points_sd")
            + tuple(
                f"{prefix}_{level}"
                for level in (50, 80, 90, 95)
                for prefix in ("coverage", "width")
            )
            + tuple(f"{event}_brier" for event in ("title", "top_four", "relegation"))
        ):
            summary[key] = float(np.mean([r[key] for r in group]))
        summaries.append(summary)
        for event in ("pit", "title", "top_four", "relegation"):
            key = "pit" if event == "pit" else f"{event}_probability"
            for index in range(10):
                selected = [r for r in group if min(int(r[key] * 10), 9) == index]
                calibration.append(
                    base
                    | {
                        "event": event,
                        "bin_lower": index / 10,
                        "bin_upper": (index + 1) / 10,
                        "count": len(selected),
                        "mean_prediction": float(np.mean([r[key] for r in selected]))
                        if selected
                        else None,
                        "observed_frequency": (
                            len(selected) / len(group)
                            if event == "pit"
                            else float(np.mean([r[f"{event}_observed"] for r in selected]))
                            if selected
                            else None
                        ),
                    }
                )
    return summaries, calibration


def final_cutoff(matches):
    return max(m.fixture.match_date for m in matches) + timedelta(days=1)
