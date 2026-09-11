"""Proper season scores and pooled calibration from simulation marginals."""

from collections import defaultdict
from datetime import timedelta

import numpy as np

from epl_forecast.competitions import COMPETITIONS, adjacent
from epl_forecast.data.rules import league_rules
from epl_forecast.models.baselines import AttackDefensePoisson
from epl_forecast.simulation import simulate_season


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


def rank_metrics(probabilities, observed_probabilities, pit_uniform, observed_uniform):
    p = np.asarray(probabilities, dtype=float)
    q = np.asarray(observed_probabilities, dtype=float)
    if (
        p.ndim != 1
        or p.shape != q.shape
        or len(p) < 2
        or not np.isfinite(p).all()
        or not np.isfinite(q).all()
        or (p < 0).any()
        or (q < 0).any()
        or not np.isclose(p.sum(), 1, atol=1e-10, rtol=0)
        or not np.isclose(q.sum(), 1, atol=1e-10, rtol=0)
        or not 0 <= pit_uniform < 1
        or not 0 <= observed_uniform < 1
    ):
        raise ValueError("Invalid rank distributions or PIT randomizers")
    ranks = np.arange(1, len(p) + 1)
    actual_index = int(np.searchsorted(q.cumsum(), observed_uniform, side="right"))
    actual_index = min(actual_index, len(p) - 1)
    mean = float(ranks @ p)
    result = {
        "actual_rank": float(ranks @ q),
        "rank_error": mean - float(ranks @ q),
        "rank_sd": float(np.sqrt(((ranks - mean) ** 2) @ p)),
        "rank_pit": float(p[:actual_index].sum() + pit_uniform * p[actual_index]),
    }
    cdf = p.cumsum()
    for level in (50, 80, 90, 95):
        tail = (1 - level / 100) / 2
        lo, hi = np.searchsorted(cdf, [tail, 1 - tail])
        result[f"rank_coverage_{level}"] = float(q[lo : hi + 1].sum())
        result[f"rank_width_{level}"] = int(hi - lo)
    return result


def season_origins(matches):
    ordered = sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id))
    competitions = {m.fixture.competition_id for m in ordered}
    teams = {
        team
        for match in ordered
        for team in (match.fixture.home_team_id, match.fixture.away_team_id)
    }
    expected_teams = {c.competition_id: c.teams for c in COMPETITIONS}
    team_count = expected_teams.get(next(iter(competitions))) if len(competitions) == 1 else None
    expected_matches = team_count * (team_count - 1) if team_count else None
    if (
        expected_matches is None
        or len(teams) != team_count
        or len(ordered) != expected_matches
        or len({m.fixture.match_id for m in ordered}) != expected_matches
    ):
        raise ValueError("Origins require a complete supported league season")
    matches_per_week = team_count // 2
    return {"preseason": ordered[0].fixture.match_date} | {
        f"MW{week}": ordered[week * matches_per_week - 1].available_on for week in (6, 12, 19, 30)
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


def score_forecast(forecast, truth, promoted, seed, entry_cohorts=None):
    actual = {r["team_id"]: r for r in truth["teams"]}
    if {r["team_id"] for r in forecast["teams"]} != set(actual):
        raise ValueError("Forecast and truth teams differ")
    points_rng = np.random.default_rng(np.random.SeedSequence([seed, 0x504954]))
    rank_rng = np.random.default_rng(np.random.SeedSequence([seed, 0x52414E4B]))
    rows = []
    for team in sorted(forecast["teams"], key=lambda r: r["team_id"]):
        target = actual[team["team_id"]]
        p = np.asarray(team["position_probabilities"])
        q = np.asarray(target["position_probabilities"])
        # Expected score over shared observed ranks preserves ties without arbitrary ordering.
        trps = sum(q[i] * rank_scores([p], np.array([i + 1]))[0] for i in np.flatnonzero(q))
        rank = rank_metrics(p, q, rank_rng.random(), rank_rng.random())
        row = {
            "competition_id": forecast.get("competition_id", "eng-premier-league"),
            "team_id": team["team_id"],
            "promoted": team["team_id"] in promoted,
            "entry_cohort": (entry_cohorts or {}).get(team["team_id"], "incumbent"),
            "actual_points": target["mean_points"],
            "mean_points": team["mean_points"],
            "rank_rps": float(trps),
            "trps": float(trps),
            **rank,
            **points_metrics(
                team["points_distribution"], target["mean_points"], points_rng.random()
            ),
        }
        events = [
            event
            for event in (
                "title",
                "top_four",
                "top_five",
                "relegation",
                "automatic_promotion",
                "playoff_qualification",
                "promotion",
            )
            if f"{event}_probability" in team and f"{event}_probability" in target
        ]
        for event in events:
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
        groups[
            row.get("competition_id", "eng-premier-league"), row["model_id"], row["origin"]
        ].append(row)
    summaries, calibration = [], []
    for (competition, model, origin), group in sorted(groups.items()):
        base = {"competition_id": competition, "model_id": model, "origin": origin}
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
            ("rank_rps", "rank_sd", "points_crps", "points_sd")
            + tuple(
                f"{prefix}_{level}"
                for level in (50, 80, 90, 95)
                for prefix in ("coverage", "width")
            )
            + tuple(
                f"rank_{prefix}_{level}"
                for level in (50, 80, 90, 95)
                for prefix in ("coverage", "width")
            )
        ):
            summary[key] = float(np.mean([r[key] for r in group]))
        events = sorted(
            key.removesuffix("_brier")
            for key in group[0]
            if key.endswith("_brier")
            and all(
                key in row and f"{key.removesuffix('_brier')}_probability" in row for row in group
            )
        )
        for event in events:
            summary[f"{event}_brier"] = float(np.mean([r[f"{event}_brier"] for r in group]))
        summaries.append(summary)
        for event in ("points_pit", "rank_pit", *events):
            key = (
                "pit"
                if event == "points_pit"
                else event
                if event == "rank_pit"
                else f"{event}_probability"
            )
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
                            if event in ("points_pit", "rank_pit")
                            else float(np.mean([r[f"{event}_observed"] for r in selected]))
                            if selected
                            else None
                        ),
                    }
                )
    return summaries, calibration


def final_cutoff(matches):
    return max(m.fixture.match_date for m in matches) + timedelta(days=1)


def season_teams(matches, competition, season):
    return {
        team
        for match in matches
        if match.fixture.competition_id == competition and match.fixture.season_id == season
        for team in (match.fixture.home_team_id, match.fixture.away_team_id)
    }


def playoff_winner(matches, competition, season, final_order):
    """The club promoted through the playoffs, read off the next season of the division above.

    Newcomers to the division above also include clubs relegated into it, so only
    arrivals from this division count, less those it promoted automatically.
    """
    upper = adjacent(competition, -1).competition_id
    year = int(season[:4])
    current = season_teams(matches, upper, season)
    following = season_teams(matches, upper, f"{year + 1}-{year + 2}")
    division = season_teams(matches, competition, season)
    automatic = league_rules(competition, season).automatic_promotion
    winners = ((following - current) & division) - set(final_order[:automatic])
    if len(winners) != 1:
        raise ValueError(f"Cannot identify observed {competition} playoff winner for {season}")
    return next(iter(winners))


def season_truth(season_matches, teams, seed, adjustments, **kwargs):
    """The realized final table: fixed results plus every sanction in force at the end."""
    cutoff = final_cutoff(season_matches)
    truth_model = AttackDefensePoisson()
    truth_model.as_of = cutoff
    return simulate_season(
        truth_model, season_matches, [], teams, cutoff, 1, seed, adjustments, **kwargs
    )


def promotion_season_truth(matches, season, season_matches, teams, seed, adjustments=()):
    """Realized table of a promoting division, with the observed playoff winner as truth."""
    competition = season_matches[0].fixture.competition_id
    if not league_rules(competition, season).promotes:
        raise ValueError("Playoff truth requires a division with a promotion bracket")
    truth = season_truth(season_matches, teams, seed, list(adjustments), playoff_winner=teams[0])
    final_order = [
        row["team_id"] for row in sorted(truth["teams"], key=lambda row: row["mean_position"])
    ]
    winner = playoff_winner(matches, competition, season, final_order)
    truth["playoff_model"] = {"format": "observed", "winner": winner}
    for row in truth["teams"]:
        row["playoff_promotion_probability"] = float(row["team_id"] == winner)
        row["promotion_probability"] = (
            row["automatic_promotion_probability"] + row["playoff_promotion_probability"]
        )
    return truth
