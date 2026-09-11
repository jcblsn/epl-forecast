"""Matched Championship entry states for relegated clubs: retained, generic, mapped.

The Championship filter never sees a club's Premier League matches, so a relegated
club enters on whatever Championship state it last had, however stale. This
compares that treatment against a generic relegated-club prior and an
opponent-adjusted mapping from its Premier League season into Championship entry
strength, on the same seasons, fixtures and score law.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance
from epl_forecast.cli import save_rows
from epl_forecast.datasets import Dataset
from epl_forecast.models.promotion import (
    CHAMPIONSHIP,
    PL,
    RelegationBridge,
    completed_seasons,
    division_cohort,
    preceding_season,
)
from epl_forecast.models.xg_quality_tilt import XG_DYNAMICS, XGQualityTiltFilter
from epl_forecast.research.uncertainty_ladder import MatchedStateForecast
from epl_forecast.research.uncertainty_report import cluster_interval
from epl_forecast.season_evaluation import (
    final_cutoff,
    promotion_season_truth,
    score_forecast,
    season_origins,
)
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import file_hash, write_json

TREATMENTS = ("retained", "generic", "mapped")


def season_teams(matches, competition, season):
    return {
        team
        for m in matches
        if m.fixture.competition_id == competition and m.fixture.season_id == season
        for team in (m.fixture.home_team_id, m.fixture.away_team_id)
    }


def gaussian_log_score(mean, variance, observed):
    return float(0.5 * (np.log(2 * np.pi * variance) + (observed - mean) ** 2 / variance))


def entry_prior_rows(matches, season, cutoff, relegated, model_priors):
    """Each treatment's entry prior beside the club's realized first ten Championship matches."""
    seasons = completed_seasons(matches, final_cutoff([m for m in matches]))
    source = seasons.get((PL, preceding_season(season)))
    target = seasons.get((CHAMPIONSHIP, season))
    if source is None or target is None:
        return []
    realized = {r["team_id"]: r for r in division_cohort(source, target)}
    bridge = RelegationBridge([m for m in matches if m.available_on <= cutoff], cutoff, season)
    rows = []
    for team in sorted(relegated):
        observed = realized.get(team)
        if observed is None:
            continue
        for treatment in TREATMENTS:
            prior = model_priors[treatment][team]
            for i, dimension in enumerate(("attack", "defense")):
                rows.append(
                    {
                        "season_id": season,
                        "team_id": team,
                        "treatment": treatment,
                        "dimension": dimension,
                        "prior_mean": float(prior.mean[i]),
                        "prior_sd": float(np.sqrt(prior.covariance[i, i])),
                        "prior_source": prior.source,
                        "premier_league_value": float(bridge.source.teams[team].mean[i])
                        if bridge.source and team in bridge.source.teams
                        else None,
                        "realized_entry": observed[f"entry_{dimension}"],
                        "realized_entry_variance": observed[f"entry_{dimension}_variance"],
                        "squared_error": float(
                            (prior.mean[i] - observed[f"entry_{dimension}"]) ** 2
                        ),
                        "log_score": gaussian_log_score(
                            prior.mean[i],
                            prior.covariance[i, i] + observed[f"entry_{dimension}_variance"],
                            observed[f"entry_{dimension}"],
                        ),
                        "first_ten_points": observed["first_ten_points"],
                    }
                )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2016, 2026)))
    parser.add_argument("--simulations", type=int, default=4000)
    parser.add_argument("--opening-matches", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260910)
    args = parser.parse_args()
    data = Dataset(args.data)
    try:
        matches = data.matches()
        observations = data.process()
        provenance = data.provenance()
    finally:
        data.close()
    metadata = {
        "execution": execution_provenance(),
        "seasons": args.seasons,
        "simulations": args.simulations,
        "opening_matches": args.opening_matches,
        "seed": args.seed,
        "competition_id": CHAMPIONSHIP,
        "data_manifest": provenance,
        "parent": "M7 fixed p=0.2 Championship filter; identical incumbent state, dynamics and independent-Poisson score law",
        "treatments": {
            "retained": "current behavior: the club keeps its last Championship state, decayed by the elapsed calendar time",
            "generic": "relegation bridge evaluated at the cohort-mean Premier League season, so every relegated club shares one prior",
            "mapped": "relegation bridge evaluated at the club's own opponent-adjusted Premier League season",
        },
        "target": "First ten Championship appearances, exposure-adjusted with completed target-season opponent strengths",
        "labels": "Bridge coefficients use only earlier completed cohorts; no evaluated season's own label enters its prior",
        "code_hashes": {str(p): file_hash(p) for p in sorted(Path("src").rglob("*.py"))},
        "runner_hash": file_hash(Path(__file__)),
    }
    metadata_path = args.output / "manifest.json"
    if metadata_path.exists() and json.loads(metadata_path.read_text()) != metadata:
        raise ValueError("Resume manifest differs; use a new output directory")
    write_json(metadata_path, metadata)
    championship = [m for m in matches if m.fixture.competition_id == CHAMPIONSHIP]
    season_rows, match_rows, prior_rows, bridge_rows = [], [], [], []
    for year in args.seasons:
        season = f"{year}-{year + 1}"
        games = sorted(
            [m for m in championship if m.fixture.season_id == season],
            key=lambda m: (m.fixture.match_date, m.fixture.match_id),
        )
        teams = sorted({m.fixture.home_team_id for m in games})
        previous = season_teams(matches, CHAMPIONSHIP, preceding_season(season))
        previous_pl = season_teams(matches, PL, preceding_season(season))
        relegated = sorted((set(teams) - previous) & previous_pl)
        if len(teams) != 24 or len(previous) != 24 or len(relegated) != 3:
            raise ValueError(f"Incomplete relegation cohort for {season}")
        cutoff = season_origins(games)["preseason"]
        truth = promotion_season_truth(matches, season, games, teams, args.seed)
        opening_ids = {}
        for team in relegated:
            appearances = [
                m for m in games if team in (m.fixture.home_team_id, m.fixture.away_team_id)
            ][: args.opening_matches]
            for order, match in enumerate(appearances, start=1):
                key = match.fixture.match_id
                opening_ids[key] = min(opening_ids.get(key, order), order)
        model_priors = {}
        for treatment in TREATMENTS:
            print(f"Fitting {season} {treatment}", flush=True)
            parent = XGQualityTiltFilter(observations, 0.2, **XG_DYNAMICS)
            parent.primary_competition = CHAMPIONSHIP
            parent.relegation_entry = treatment
            parent.fit([m for m in matches if m.available_on <= cutoff], cutoff)
            model = MatchedStateForecast(parent, teams, season, evolution=True)
            model_priors[treatment] = {t: parent.team_state(t, season) for t in relegated}
            bridge_rows.append(
                {
                    "season_id": season,
                    "treatment": treatment,
                    **(
                        parent._boundary_bridge(season, cutoff).diagnostics()
                        if treatment != "retained"
                        else {"cohorts": 0}
                    ),
                }
            )
            forecast = simulate_season(
                model,
                [],
                [m.fixture for m in games],
                teams,
                cutoff,
                args.simulations,
                args.seed + year,
                [],
                playoff_winner=teams[0],
            )
            base = {
                "season_id": season,
                "model_id": treatment,
                "origin": "preseason",
                "as_of": str(cutoff),
            }
            entry_cohorts = {
                t: "relegated_from_pl"
                if t in relegated
                else "incumbent"
                if t in previous
                else "promoted_from_lower"
                for t in teams
            }
            scores = [
                {**base, **r}
                for r in score_forecast(
                    forecast, truth, set(relegated), args.seed + year, entry_cohorts
                )
            ]
            season_rows.extend(scores)
            for match in games:
                if match.fixture.match_id not in opening_ids:
                    continue
                prediction = model.predict_match(match.fixture)
                outcome = (
                    0
                    if match.home_goals > match.away_goals
                    else 1
                    if match.home_goals == match.away_goals
                    else 2
                )
                appearance = opening_ids[match.fixture.match_id]
                match_rows.append(
                    {
                        **base,
                        "match_id": match.fixture.match_id,
                        "appearance": appearance,
                        "log_loss": -float(np.log(prediction.probabilities[outcome])),
                        "brier": float(
                            sum(
                                (p - (i == outcome)) ** 2
                                for i, p in enumerate(prediction.probabilities)
                            )
                        ),
                        "score_nll": -float(
                            prediction.scores.log_probability(match.home_goals, match.away_goals)
                        ),
                    }
                )
        prior_rows.extend(entry_prior_rows(matches, season, cutoff, relegated, model_priors))
    comparisons = []
    for rows, key, scope, metrics in (
        (
            [r for r in season_rows if r["entry_cohort"] == "relegated_from_pl"],
            "team_id",
            "relegated_clubs",
            ("trps", "points_crps", "coverage_90", "width_90", "relegation_brier"),
        ),
        (
            season_rows,
            "team_id",
            "all_clubs",
            ("trps", "points_crps", "coverage_90", "width_90", "relegation_brier"),
        ),
        (match_rows, "match_id", "opening_matches", ("log_loss", "brier", "score_nll")),
        (
            [r for r in match_rows if r["appearance"] <= 5],
            "match_id",
            "opening_five",
            ("log_loss", "brier", "score_nll"),
        ),
        (
            [{**r, "metric_scope": r["dimension"]} for r in prior_rows],
            "team_id",
            "entry_strength",
            ("squared_error", "log_score"),
        ),
    ):
        for candidate, comparator in (
            ("generic", "retained"),
            ("mapped", "retained"),
            ("mapped", "generic"),
        ):
            field = "treatment" if scope == "entry_strength" else "model_id"
            indexed = {}
            for variant in (candidate, comparator):
                selected = [r for r in rows if r[field] == variant]
                index = {}
                for row in selected:
                    index[row["season_id"], row[key], row.get("dimension", "")] = row
                indexed[variant] = index
            a, b = indexed[candidate], indexed[comparator]
            if a.keys() != b.keys():
                raise ValueError("Unmatched relegation evaluation cohorts")
            keys = sorted(a)
            for metric in metrics:
                comparisons.append(
                    {
                        "candidate": candidate,
                        "comparator": comparator,
                        "scope": scope,
                        "metric": metric,
                        **cluster_interval(
                            [a[k][metric] - b[k][metric] for k in keys],
                            [k[0] for k in keys],
                            args.seed,
                        ),
                    }
                )
    save_rows(args.output / "club_seasons.csv", season_rows)
    save_rows(args.output / "opening_matches.csv", match_rows)
    save_rows(args.output / "entry_priors.csv", prior_rows)
    write_json(args.output / "bridges.json", bridge_rows)
    write_json(args.output / "comparisons.json", comparisons)
    print(args.output / "comparisons.json", flush=True)


if __name__ == "__main__":
    main()
