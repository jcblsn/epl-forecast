"""Matched entry priors for every club crossing a division boundary, in every division.

The current rule is implicit: a promoted club is initialized by the Championship
bridge, and every other entrant keeps whatever target-division state it last
held, however old, or the flat league population prior when it has none. This
compares that rule against an explicit hierarchy — population, transition
identity, transition plus source-division strength, and transition plus a
time-weighted memory of the club's own older target-division form — on the same
seasons, fixtures, dynamics and score law.

`two_division` is the memory rule fitted with only the Premier League and the
Championship visible, which is the product before League One and League Two were
modeled; set against `memory` it measures what the lower divisions add.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance
from epl_forecast.cli import save_rows
from epl_forecast.competitions import COMPETITION_IDS
from epl_forecast.data.rules import league_rules
from epl_forecast.datasets import Dataset
from epl_forecast.models.entry_prior import LABELS, LEVELS, club_features
from epl_forecast.models.promotion import (
    completed_seasons,
    entry_label,
    season_strengths,
)
from epl_forecast.models.quality_tilt import AD_FROM_QT
from epl_forecast.models.xg_quality_tilt import XG_DYNAMICS, XGQualityTiltFilter
from epl_forecast.research.uncertainty_ladder import MatchedStateForecast
from epl_forecast.research.uncertainty_report import cluster_interval
from epl_forecast.sanctions import REGISTRIES, load_registry
from epl_forecast.season_evaluation import (
    final_cutoff,
    promotion_season_truth,
    score_forecast,
    season_origins,
    season_truth,
)
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import file_hash, write_json

TOP_TWO = COMPETITION_IDS[:2]
TREATMENTS = ("current", *LEVELS, "two_division")
ORIGINS = ("preseason", "MW6")
COMPARISONS = (
    ("population", "current"),
    ("transition", "current"),
    ("source", "current"),
    ("memory", "current"),
    ("transition", "population"),
    ("source", "transition"),
    ("memory", "source"),
    ("memory", "two_division"),
)
SEASON_METRICS = ("trps", "points_crps", "coverage_90", "width_90", "points_sd")


def age_bucket(age):
    if age is None:
        return "no_target_history"
    return "recent_returner" if age <= 3 else "stale_history"


def gaussian_log_score(mean, variance, observed):
    return float(0.5 * (np.log(2 * np.pi * variance) + (observed - mean) ** 2 / variance))


def entrant_features(seasons, competition, season, teams):
    return {
        team: features
        for team in teams
        if (features := club_features(seasons, competition, season, team)) is not None
    }


def realized_labels(seasons, competition, season, first):
    """Each club's opening and whole-season target-division strength, for scoring priors only."""
    matches = seasons[competition, season]
    strengths = season_strengths(matches)
    rows = {}
    for team in strengths.teams:
        label = entry_label(strengths, matches, team, first)
        summary = strengths.teams[team]
        rows[team] = {
            **label,
            **{
                f"season_{dimension}{suffix}": float(value)
                for i, dimension in enumerate(("attack", "defense"))
                for suffix, value in (
                    ("", summary.mean[i]),
                    ("_variance", summary.covariance[i, i]),
                )
            },
        }
    return rows


def prior_rows(season, competition, treatment, entrants, priors, labels):
    rows = []
    for team, features in sorted(entrants.items()):
        prior, observed = priors[team], labels.get(team)
        if observed is None:
            continue
        mean = AD_FROM_QT @ prior.mean
        covariance = AD_FROM_QT @ prior.covariance @ AD_FROM_QT.T
        for i, dimension in enumerate(("attack", "defense")):
            for target in ("entry", "season"):
                rows.append(
                    {
                        "competition_id": competition,
                        "season_id": season,
                        "team_id": team,
                        "treatment": treatment,
                        "transition": features["transition"],
                        "memory_age": features["memory_age"],
                        "age_bucket": age_bucket(features["memory_age"]),
                        "dimension": dimension,
                        "target": target,
                        "prior_mean": float(mean[i]),
                        "prior_sd": float(np.sqrt(covariance[i, i])),
                        "prior_source": prior.source,
                        "realized": observed[f"{target}_{dimension}"],
                        "realized_variance": observed[f"{target}_{dimension}_variance"],
                        "squared_error": float((mean[i] - observed[f"{target}_{dimension}"]) ** 2),
                        "log_score": gaussian_log_score(
                            float(mean[i]),
                            float(covariance[i, i]) + observed[f"{target}_{dimension}_variance"],
                            observed[f"{target}_{dimension}"],
                        ),
                    }
                )
    return rows


def match_rows(model, games, opening, base, entrants):
    rows = []
    for match in games:
        appearance = opening.get(match.fixture.match_id)
        if appearance is None:
            continue
        prediction = model.predict_match(match.fixture)
        outcome = (
            0
            if match.home_goals > match.away_goals
            else 1
            if match.home_goals == match.away_goals
            else 2
        )
        sides = [
            entrants[team]
            for team in (match.fixture.home_team_id, match.fixture.away_team_id)
            if team in entrants
        ]
        rows.append(
            {
                **base,
                "match_id": match.fixture.match_id,
                "appearance": appearance,
                "transition": sides[0]["transition"] if len(sides) == 1 else "mixed",
                "age_bucket": age_bucket(sides[0]["memory_age"]) if len(sides) == 1 else "mixed",
                "log_loss": -float(np.log(prediction.probabilities[outcome])),
                "brier": float(
                    sum((p - (i == outcome)) ** 2 for i, p in enumerate(prediction.probabilities))
                ),
                "score_nll": -float(
                    prediction.scores.log_probability(match.home_goals, match.away_goals)
                ),
            }
        )
    return rows


def compare(rows, key, field, metrics, seed, scope, extra=None):
    comparisons = []
    for candidate, comparator in COMPARISONS:
        indexed = {}
        for variant in (candidate, comparator):
            indexed[variant] = {
                (
                    r["competition_id"],
                    r["season_id"],
                    r[key],
                    r.get("dimension", ""),
                    r.get("target", ""),
                ): r
                for r in rows
                if r[field] == variant
            }
        a, b = indexed[candidate], indexed[comparator]
        if not a or not b:
            continue
        if a.keys() != b.keys():
            raise ValueError(f"Unmatched entry-prior cohorts in scope {scope}")
        keys = sorted(a)
        for metric in metrics:
            comparisons.append(
                {
                    "scope": scope,
                    **(extra or {}),
                    "candidate": candidate,
                    "comparator": comparator,
                    "metric": metric,
                    **cluster_interval(
                        [a[k][metric] - b[k][metric] for k in keys],
                        [f"{k[0]}:{k[1]}" for k in keys],
                        seed,
                    ),
                }
            )
    return comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--competitions", nargs="+", choices=COMPETITION_IDS, default=list(TOP_TWO))
    parser.add_argument("--seasons", nargs="+", type=int, default=list(range(2016, 2026)))
    parser.add_argument("--treatments", nargs="+", choices=TREATMENTS, default=list(TREATMENTS))
    parser.add_argument("--simulations", type=int, default=4000)
    parser.add_argument("--opening-matches", type=int, default=10)
    parser.add_argument("--label", choices=LABELS, default="season")
    parser.add_argument("--seed", type=int, default=20260910)
    args = parser.parse_args()
    if "two_division" in args.treatments and not set(args.competitions) <= set(TOP_TWO):
        raise ValueError("The two-division rule exists only in the Premier League and Championship")
    data = Dataset(args.data)
    try:
        matches = data.matches()
        observations = data.process()
        provenance = data.provenance()
        sanctions = load_registry(data)
    finally:
        data.close()
    metadata = {
        "execution": execution_provenance(),
        "competitions": args.competitions,
        "seasons": args.seasons,
        "treatments": args.treatments,
        "simulations": args.simulations,
        "opening_matches": args.opening_matches,
        "training_label": args.label,
        "origins": list(ORIGINS),
        "seed": args.seed,
        "data_manifest": provenance,
        "parent": "M7 fixed p=0.2 filter per division; identical incumbent state, dynamics and independent-Poisson score law",
        "treatment_definitions": {
            "current": "today's implicit rule: the promotion bridge into the Premier League, and otherwise the club's last target-division state however old, or the flat population prior",
            "population": "flat target-league population prior for every entrant",
            "transition": "intercept-only prior learned from earlier entrants of the same transition",
            "source": "transition prior plus the club's immediately preceding source-division season, where that division is modeled",
            "memory": "source prior plus the club's own older target-division season, weighted by a learned decay timescale",
            "two_division": "the memory rule fitted with only the Premier League and the Championship visible",
        },
        "training_label_definition": {
            "season": "the club's whole-season division-relative target strength, a smoothed retrospective state used only to discover the mapping",
            "entry": "the club's exposure-adjusted first-ten-match target strength",
        },
        "chronology": "entry-prior coefficients use only transitions whose target season finished and was available before the forecast cutoff",
        "code_hashes": {str(p): file_hash(p) for p in sorted(Path("src").rglob("*.py"))},
        "runner_hash": file_hash(Path(__file__)),
        "reviewed_adjustment_hashes": {
            name: file_hash(Path("src/epl_forecast/data") / name) for name in REGISTRIES
        },
    }
    metadata_path = args.output / "manifest.json"
    if metadata_path.exists() and json.loads(metadata_path.read_text()) != metadata:
        raise ValueError("Resume manifest differs; use a new output directory")
    write_json(metadata_path, metadata)
    panel = completed_seasons(matches, final_cutoff(matches))
    season_rows, opening_rows, entry_rows, model_rows = [], [], [], []
    for competition in args.competitions:
        league = [m for m in matches if m.fixture.competition_id == competition]
        for year in args.seasons:
            season = f"{year}-{year + 1}"
            games = sorted(
                [m for m in league if m.fixture.season_id == season],
                key=lambda m: (m.fixture.match_date, m.fixture.match_id),
            )
            teams = sorted({m.fixture.home_team_id for m in games})
            origins = season_origins(games)
            entrants = entrant_features(panel, competition, season, teams)
            if not entrants:
                raise ValueError(f"No boundary crossers identified for {competition} {season}")
            labels = realized_labels(panel, competition, season, args.opening_matches)
            final = sanctions.final_adjustments(competition, season, final_cutoff(games))
            promotes = league_rules(competition, season).promotes
            truth = (
                promotion_season_truth(matches, season, games, teams, args.seed, final)
                if promotes
                else season_truth(games, teams, args.seed, final)
            )
            opening = {}
            for team in entrants:
                appearances = [
                    m for m in games if team in (m.fixture.home_team_id, m.fixture.away_team_id)
                ][: args.opening_matches]
                for order, match in enumerate(appearances, start=1):
                    key = match.fixture.match_id
                    opening[key] = min(opening.get(key, order), order)
            cohorts = {
                team: entrants[team]["transition"] if team in entrants else "continuing"
                for team in teams
            }
            for treatment in args.treatments:
                visible = TOP_TWO if treatment == "two_division" else COMPETITION_IDS
                parent = XGQualityTiltFilter(observations, 0.2, **XG_DYNAMICS)
                parent.primary_competition = competition
                parent.entry_prior = {"current": None, "two_division": "memory"}.get(
                    treatment, treatment
                )
                parent.entry_prior_label = args.label
                for index, origin in enumerate(ORIGINS):
                    as_of = origins[origin]
                    print(f"Fitting {competition} {season} {origin} {treatment}", flush=True)
                    parent.fit(
                        [
                            m
                            for m in matches
                            if m.available_on <= as_of and m.fixture.competition_id in visible
                        ],
                        as_of,
                    )
                    model = MatchedStateForecast(parent, teams, season, evolution=True)
                    played = [m for m in games if m.available_on <= as_of]
                    remaining = [m.fixture for m in games if m.available_on > as_of]
                    forecast = simulate_season(
                        model,
                        played,
                        remaining,
                        teams,
                        as_of,
                        args.simulations,
                        args.seed + year * 10 + index,
                        sanctions.known_adjustments(competition, season, as_of),
                        playoff_winner=teams[0] if promotes else None,
                    )
                    base = {
                        "competition_id": competition,
                        "season_id": season,
                        "model_id": treatment,
                        "origin": origin,
                        "as_of": str(as_of),
                    }
                    for row in score_forecast(
                        forecast, truth, set(entrants), args.seed + year, cohorts
                    ):
                        team = row["team_id"]
                        features = entrants.get(team)
                        season_rows.append(
                            {
                                **base,
                                **row,
                                "transition": features["transition"] if features else "continuing",
                                "memory_age": features["memory_age"] if features else None,
                                "age_bucket": age_bucket(features["memory_age"])
                                if features
                                else "continuing",
                            }
                        )
                    if origin != "preseason":
                        continue
                    priors = {team: parent.team_state(team, season) for team in entrants}
                    entry_rows.extend(
                        prior_rows(season, competition, treatment, entrants, priors, labels)
                    )
                    opening_rows.extend(match_rows(model, games, opening, base, entrants))
                    if treatment in ("transition", "source", "memory", "two_division"):
                        model_rows.append(
                            {
                                "treatment": treatment,
                                **parent._entry_model(season, as_of).diagnostics(),
                            }
                        )
    comparisons = []
    for origin in ORIGINS:
        scoped = [r for r in season_rows if r["origin"] == origin]
        crossers = [r for r in scoped if r["entry_cohort"] != "continuing"]
        comparisons += compare(
            crossers, "team_id", "model_id", SEASON_METRICS, args.seed, f"{origin}_crossers"
        )
        comparisons += compare(
            scoped, "team_id", "model_id", SEASON_METRICS, args.seed, f"{origin}_all_clubs"
        )
        for transition in sorted({r["transition"] for r in crossers}):
            comparisons += compare(
                [r for r in crossers if r["transition"] == transition],
                "team_id",
                "model_id",
                SEASON_METRICS,
                args.seed,
                f"{origin}_crossers_by_transition",
                {"transition": transition},
            )
        for bucket in sorted({r["age_bucket"] for r in crossers}):
            comparisons += compare(
                [r for r in crossers if r["age_bucket"] == bucket],
                "team_id",
                "model_id",
                SEASON_METRICS,
                args.seed,
                f"{origin}_crossers_by_age",
                {"age_bucket": bucket},
            )
    match_metrics = ("log_loss", "brier", "score_nll")
    for name, selected in (
        ("opening_five", [r for r in opening_rows if r["appearance"] <= 5]),
        ("opening_ten", opening_rows),
    ):
        comparisons += compare(selected, "match_id", "model_id", match_metrics, args.seed, name)
        for transition in sorted({r["transition"] for r in selected}):
            comparisons += compare(
                [r for r in selected if r["transition"] == transition],
                "match_id",
                "model_id",
                match_metrics,
                args.seed,
                f"{name}_by_transition",
                {"transition": transition},
            )
        for bucket in sorted({r["age_bucket"] for r in selected}):
            comparisons += compare(
                [r for r in selected if r["age_bucket"] == bucket],
                "match_id",
                "model_id",
                match_metrics,
                args.seed,
                f"{name}_by_age",
                {"age_bucket": bucket},
            )
    for target in ("entry", "season"):
        selected = [r for r in entry_rows if r["target"] == target]
        comparisons += compare(
            selected,
            "team_id",
            "treatment",
            ("squared_error", "log_score"),
            args.seed,
            f"entry_strength_{target}",
        )
        for transition in sorted({r["transition"] for r in selected}):
            comparisons += compare(
                [r for r in selected if r["transition"] == transition],
                "team_id",
                "treatment",
                ("squared_error", "log_score"),
                args.seed,
                f"entry_strength_{target}_by_transition",
                {"transition": transition},
            )
        for bucket in sorted({r["age_bucket"] for r in selected}):
            comparisons += compare(
                [r for r in selected if r["age_bucket"] == bucket],
                "team_id",
                "treatment",
                ("squared_error", "log_score"),
                args.seed,
                f"entry_strength_{target}_by_age",
                {"age_bucket": bucket},
            )
    save_rows(args.output / "club_seasons.csv", season_rows)
    save_rows(args.output / "opening_matches.csv", opening_rows)
    save_rows(args.output / "entry_priors.csv", entry_rows)
    write_json(args.output / "entry_models.json", model_rows)
    write_json(args.output / "comparisons.json", comparisons)
    print(args.output / "comparisons.json", flush=True)


if __name__ == "__main__":
    main()
