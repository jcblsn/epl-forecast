"""Matched preseason promoted priors: population, results, correlated process."""

import argparse
import json
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance
from epl_forecast.cli import save_rows
from epl_forecast.data.rules import historical_adjustments
from epl_forecast.models.baselines import AttackDefensePoisson
from epl_forecast.models.xg_quality_tilt import XG_DYNAMICS, XGQualityTiltFilter
from epl_forecast.research.promotion_transition import (
    championship_observations,
    promotion_prior,
    replace_entry_priors,
    transition_cohorts,
)
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.research.uncertainty_ladder import MatchedStateForecast
from epl_forecast.research.uncertainty_report import cluster_interval
from epl_forecast.season_evaluation import final_cutoff, score_forecast, season_origins
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import file_hash, json_bytes, write_immutable, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2016, 2026)))
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260910)
    args = parser.parse_args()
    metadata = {
        "execution": execution_provenance(),
        "manifest_sha256": file_hash(args.manifest),
        "seasons": args.seasons,
        "simulations": args.simulations,
        "seed": args.seed,
        "parent": "M7 fixed p=0.2; identical incumbent state, dynamics and independent-Poisson conditional score law",
        "source": "Season aggregate home/division-adjusted Championship goals/shots/SOT, not a dynamically filtered ending state; results/process share complete cases.",
        "target": "First ten PL appearances, exposure-adjusted using completed target-season opponent strengths; retrospective training labels only from earlier completed seasons.",
        "horizon": "Preseason forecasts, including each promoted team's first five appearances; not daily-refitted opening-match forecasts. Results assumed available next day; archived retrieval is not contemporaneous evidence.",
        "uncertainty": "Pooled attack/defense transitions, diagonal between dimensions; correlated source measurement noise within each dimension, coefficient and transition uncertainty. Shared bridge-parameter draws across promoted clubs are not simulated.",
    }
    write_immutable(args.output / "manifest.json", json_bytes(metadata))
    frozen = json.loads(args.manifest.read_text())
    eligible = frozen["readiness"]["eligible_cohorts"]["matched_uncertainty_ladder"]
    data = frozen_dataset(args.data, args.manifest)
    try:
        matches, observations = data.matches(), data.process()
        sources = championship_observations(data)
    finally:
        data.close()
    cohorts = transition_cohorts(matches, sources)
    write_immutable(args.output / "training_cohorts.json", json_bytes(cohorts))
    premier = [m for m in matches if m.fixture.competition_id == "eng-premier-league"]
    season_rows, match_rows, prior_rows = [], [], []
    for year in args.seasons:
        season, previous_season = f"{year}-{year + 1}", f"{year - 1}-{year}"
        if ["eng-premier-league", season] not in eligible:
            raise ValueError("Target season not admitted by frozen manifest")
        games = sorted(
            [m for m in premier if m.fixture.season_id == season],
            key=lambda m: (m.fixture.match_date, m.fixture.match_id),
        )
        teams = sorted({m.fixture.home_team_id for m in games})
        previous = {
            m.fixture.home_team_id for m in premier if m.fixture.season_id == previous_season
        }
        promoted = set(teams) - previous
        if len(previous) != 20 or len(promoted) != 3:
            raise ValueError("Incomplete promotion cohort")
        cutoff = season_origins(games)["preseason"]
        print(f"Fitting {season}", flush=True)
        parent = XGQualityTiltFilter(observations, 0.2, **XG_DYNAMICS).fit(
            [m for m in matches if m.available_on <= cutoff], cutoff
        )
        end = final_cutoff(games)
        truth_model = AttackDefensePoisson()
        truth_model.as_of = end
        truth = simulate_season(
            truth_model, games, [], teams, end, 1, args.seed, historical_adjustments(season, end)
        )
        opening_ids = {
            m.fixture.match_id
            for team in promoted
            for m in [m for m in games if team in (m.fixture.home_team_id, m.fixture.away_team_id)][
                :5
            ]
        }
        for variant in ("coarse", "population", "results", "process"):
            model = MatchedStateForecast(parent, teams, season, evolution=True)
            if variant != "coarse":
                priors = {}
                for team in sorted(promoted):
                    prior, diagnostics = promotion_prior(
                        cohorts, sources[previous_season, team], cutoff, season, variant
                    )
                    priors[team] = prior
                    prior_rows.append(
                        {
                            "season_id": season,
                            "team_id": team,
                            "variant": variant,
                            "mean": prior.mean.tolist(),
                            "covariance": prior.covariance.tolist(),
                            **diagnostics,
                        }
                    )
                replace_entry_priors(model, priors)
            print(f"Simulating {season} {variant}", flush=True)
            forecast = simulate_season(
                model,
                [],
                [m.fixture for m in games],
                teams,
                cutoff,
                args.simulations,
                args.seed + year,
                historical_adjustments(season, cutoff),
            )
            base = {
                "season_id": season,
                "model_id": variant,
                "origin": "preseason",
                "as_of": str(cutoff),
            }
            scores = [
                {**base, **r} for r in score_forecast(forecast, truth, promoted, args.seed + year)
            ]
            season_rows.extend(scores)
            opening = []
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
                opening.append(
                    {
                        **base,
                        "match_id": match.fixture.match_id,
                        "log_loss": -float(np.log(prediction.probabilities[outcome])),
                        "score_nll": -prediction.scores.log_probability(
                            match.home_goals, match.away_goals
                        ),
                    }
                )
            match_rows.extend(opening)
            write_immutable(
                args.output / "cells" / f"{season}-{variant}.json",
                json_bytes(
                    {"forecast": forecast, "season_scores": scores, "opening_matches": opening}
                ),
            )
    comparisons = []
    for rows, key, scope, metrics in (
        (
            season_rows,
            "team_id",
            "all_clubs",
            ("points_crps", "coverage_90", "width_90", "relegation_brier", "trps"),
        ),
        (
            [r for r in season_rows if r["promoted"]],
            "team_id",
            "promoted",
            ("points_crps", "coverage_90", "width_90", "relegation_brier", "trps"),
        ),
        (match_rows, "match_id", "opening_matches", ("log_loss", "score_nll")),
    ):
        for candidate, comparator in (
            ("population", "coarse"),
            ("results", "population"),
            ("process", "results"),
            ("process", "population"),
        ):
            indexed = {
                v: {(r["season_id"], r[key]): r for r in rows if r["model_id"] == v}
                for v in (candidate, comparator)
            }
            a, b = indexed[candidate], indexed[comparator]
            if a.keys() != b.keys():
                raise ValueError("Unmatched transition evaluation cohorts")
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
    write_json(args.output / "opening_matches.json", match_rows)
    write_json(args.output / "priors.json", prior_rows)
    write_json(args.output / "comparisons.json", comparisons)
    write_json(
        args.output / "completion.json",
        {
            "seasons": args.seasons,
            "season_rows": len(season_rows),
            "opening_match_rows": len(match_rows),
            "outputs": {
                name: file_hash(args.output / name)
                for name in (
                    "manifest.json",
                    "training_cohorts.json",
                    "club_seasons.csv",
                    "opening_matches.json",
                    "priors.json",
                    "comparisons.json",
                )
            },
        },
    )


if __name__ == "__main__":
    main()
