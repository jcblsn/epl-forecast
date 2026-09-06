import argparse
import csv
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
from itertools import groupby
from pathlib import Path
from time import perf_counter

import numpy as np

from epl_forecast.artifacts import new_run_directory, provenance, results_markdown
from epl_forecast.cli import load_config, save_rows
from epl_forecast.data.normalize import load_processed
from epl_forecast.evaluation import market_predictions, metrics, rolling_predictions, summarize
from epl_forecast.models.baselines import AttackDefensePoisson
from epl_forecast.models.dynamic import DynamicAttackDefense
from epl_forecast.models.poisson import IndependentPoisson
from epl_forecast.models.promotion import CHAMPIONSHIP, PL, PromotionBridge
from epl_forecast.schema import Fixture, Match, fixture_id
from epl_forecast.storage import write_json

M2 = "M2-attack-defense-v1"
M4 = "M4-dynamic-hierarchical-v1"
POOLED = "M4-cohort-only-prior"
MODE = "M4-posterior-mode"


def read_predictions(paths):
    rows = []
    for directory in paths:
        with (directory / "predictions.csv").open(newline="") as stream:
            for row in csv.DictReader(stream):
                for key, value in row.items():
                    if value == "":
                        row[key] = None
                    elif value in {"True", "False"}:
                        row[key] = value == "True"
                    else:
                        try:
                            row[key] = float(value)
                        except ValueError:
                            pass
                rows.append(row)
    seen = {(r["model_id"], r["match_id"]) for r in rows}
    if len(seen) != len(rows):
        raise ValueError("Evaluation inputs overlap")
    groups = {model: {r["match_id"] for r in rows if r["model_id"] == model} for model in (M2, M4)}
    if not groups[M2] or groups[M2] != groups[M4]:
        raise ValueError("Supply matched M2 and M4 evaluations")
    return rows


def match_slices(matches):
    championship = defaultdict(set)
    for m in matches:
        if m.fixture.competition_id == CHAMPIONSHIP:
            championship[m.fixture.season_id].update(
                [m.fixture.home_team_id, m.fixture.away_team_id]
            )
    appearances = Counter()
    tags = {}
    premier = sorted(
        [m for m in matches if m.fixture.competition_id == PL],
        key=lambda m: (m.fixture.match_date, m.fixture.match_id),
    )
    for _, day in groupby(premier, key=lambda m: m.fixture.match_date):
        day = list(day)
        for m in day:
            season = m.fixture.season_id
            year = int(season[:4])
            promoted = championship[f"{year - 1}-{year}"]
            home, away = m.fixture.home_team_id, m.fixture.away_team_id
            hp, ap = home in promoted, away in promoted
            hn, an = appearances[season, home], appearances[season, away]
            tags[m.fixture.match_id] = {
                "all": True,
                "first_six_appearances": hn < 6 or an < 6,
                "promoted": hp or ap,
                "promoted_first_ten": (hp and hn < 10) or (ap and an < 10),
                "promoted_after_ten": (hp or ap) and not ((hp and hn < 10) or (ap and an < 10)),
                "incumbents_only": not hp and not ap,
            }
        for m in day:
            for team in (m.fixture.home_team_id, m.fixture.away_team_id):
                appearances[m.fixture.season_id, team] += 1
    return tags


def entry_performance(matches, cohorts):
    promoted = defaultdict(set)
    for row in cohorts:
        promoted[row["season_id"]].add(row["team_id"])
    games = defaultdict(list)
    for m in sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id)):
        if m.fixture.competition_id == PL and m.fixture.season_id in promoted:
            games[m.fixture.season_id, m.fixture.home_team_id].append((m.home_goals, m.away_goals))
            games[m.fixture.season_id, m.fixture.away_team_id].append((m.away_goals, m.home_goals))
    records = []
    for (season, team), scores in games.items():
        first = scores[:10]
        records.append(
            {
                "season_id": season,
                "team_id": team,
                "promoted": team in promoted[season],
                "appearances": len(first),
                "points": sum(3 * (h > a) + (h == a) for h, a in first),
                "goals_for": sum(h for h, _ in first),
                "goals_against": sum(a for _, a in first),
            }
        )
    return records


def prior_paths(predictions, matches):
    membership = {
        (m.fixture.season_id, team)
        for m in matches
        if m.fixture.competition_id == CHAMPIONSHIP
        for team in (m.fixture.home_team_id, m.fixture.away_team_id)
    }
    pooled = {r["match_id"]: r for r in predictions if r["model_id"] == POOLED}
    paths = {}
    for row in predictions:
        if row["model_id"] != M4:
            continue
        other = pooled[row["match_id"]]
        for side in ("home", "away"):
            if row[f"{side}_state_source"] != "Championship promotion bridge":
                continue
            year = int(row["season_id"][:4])
            if (f"{year - 1}-{year}", row[f"{side}_team_id"]) not in membership:
                continue
            n = int(row[f"{side}_season_pl_matches"])
            key = row["season_id"], row[f"{side}_team_id"], n
            paths[key] = {
                "season_id": key[0],
                "team_id": key[1],
                "prior_pl_matches": n,
                "attack": row[f"{side}_attack_log_rate"],
                "defense": row[f"{side}_defense_log_rate"],
                "attack_sd": row[f"{side}_attack_sd"],
                "defense_sd": row[f"{side}_defense_sd"],
                "entry_attack_sd": row[f"{side}_entry_attack_sd"],
                "entry_defense_sd": row[f"{side}_entry_defense_sd"],
                "attack_gap_from_cohort_prior": (
                    row[f"{side}_attack_log_rate"] - other[f"{side}_attack_log_rate"]
                ),
                "defense_gap_from_cohort_prior": (
                    row[f"{side}_defense_log_rate"] - other[f"{side}_defense_log_rate"]
                ),
            }
    return list(paths.values())


def synthetic_form_response(seed=20260905):
    rng = np.random.default_rng(seed)
    teams = [f"club-{i:02d}" for i in range(20)]
    attack, defense = np.linspace(-0.25, 0.25, 20), np.linspace(0.2, -0.2, 20)
    rotation = list(range(20))
    rounds = []
    for week in range(19):
        pairs = [(rotation[i], rotation[-i - 1]) for i in range(10)]
        rounds.append([(a, h) if (week + i) % 2 else (h, a) for i, (h, a) in enumerate(pairs)])
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    rounds += [[(a, h) for h, a in pairs] for pairs in rounds.copy()]
    history = []
    models = {M2: AttackDefensePoisson(), M4: DynamicAttackDefense()}
    records = []
    for year in (2018, 2019, 2020):
        season = f"{year}-{year + 1}"
        for week, pairs in enumerate(rounds):
            day = date(year, 8, 1) + timedelta(days=7 * week)
            truth = attack.copy()
            if year == 2020 and week >= 6:
                truth[0] += 0.7
            if year == 2020:
                for name, model in models.items():
                    model.fit(history, day)
                    index = model.team_index[teams[0]]
                    contrast = float(model.attack[index] - np.mean(model.attack))
                    records.append(
                        {
                            "model_id": name,
                            "week": week,
                            "matches_since_shock": week - 6,
                            "true_attack_contrast": float(truth[0] - truth.mean()),
                            "estimated_attack_contrast": contrast,
                        }
                    )
            for h, a in pairs:
                fixture = Fixture(
                    fixture_id(PL, season, teams[h], teams[a]), PL, season, day, teams[h], teams[a]
                )
                history.append(
                    Match(
                        fixture,
                        int(rng.poisson(np.exp(np.log(1.2) + np.log(1.3) + truth[h] - defense[a]))),
                        int(rng.poisson(np.exp(np.log(1.2) + truth[a] - defense[h]))),
                    )
                )
    return records


def main():
    parser = argparse.ArgumentParser(description="Inspect the M4 vertical slice against M2")
    parser.add_argument("--evaluations", type=Path, nargs="+", required=True)
    parser.add_argument("--data", type=Path, default=Path("data/processed"))
    parser.add_argument("--config", type=Path, default=Path("configs/dynamic.toml"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = perf_counter()
    config = load_config(args.config)
    config["bootstrap_samples"] = 1000
    matches, odds, manifest = load_processed(args.data)
    predictions = read_predictions(args.evaluations)
    new_run_directory(args.output)
    spec = deepcopy(next(s for s in config["models"] if s["id"] == M4))
    spec["id"] = POOLED
    spec["parameters"]["promotion_performance"] = False
    dates = [date.fromisoformat(r["match_date"]) for r in predictions]
    ablation = rolling_predictions(
        matches,
        {**config, "models": [spec]},
        min(dates),
        max(dates) + timedelta(days=1),
        progress=True,
    )
    target_ids = {r["match_id"] for r in predictions}
    ablation = [r for r in ablation if r["match_id"] in target_ids]
    modes = []
    for row in predictions:
        if row["model_id"] != M4:
            continue
        scores = IndependentPoisson(
            float(np.exp(row["log_home_rate_mean"])), float(np.exp(row["log_away_rate_mean"]))
        )
        home, draw, away = scores.outcome_probabilities()
        modes.append(
            {
                **row,
                "model_id": MODE,
                "p_home": home,
                "p_draw": draw,
                "p_away": away,
                "score_log_probability": scores.log_probability(
                    int(row["home_goals"]), int(row["away_goals"])
                ),
            }
        )
    predictions += ablation + modes
    markets = market_predictions(predictions, odds)
    summary = summarize(predictions, markets, config)
    tags = match_slices(matches)
    slices = []
    for label in next(iter(tags.values())):
        for model in (M2, M4, POOLED, MODE):
            selected = [
                r for r in predictions if r["model_id"] == model and tags[r["match_id"]][label]
            ]
            if selected:
                score, _ = metrics(selected)
                slices.append({"slice": label, "model_id": model, **score})
    summary["slices"] = slices
    paths = prior_paths(predictions, matches)
    prior_summary = []
    for count in (0, 5, 10, 20, 37):
        rows = [r for r in paths if r["prior_pl_matches"] == count]
        if rows:
            prior_summary.append(
                {
                    "prior_pl_matches": count,
                    "club_seasons": len(rows),
                    **{
                        f"mean_{d}_sd": float(np.mean([r[f"{d}_sd"] for r in rows]))
                        for d in ("attack", "defense")
                    },
                    **{
                        f"rms_{d}_gap_from_cohort_prior": float(
                            np.sqrt(np.mean([r[f"{d}_gap_from_cohort_prior"] ** 2 for r in rows]))
                        )
                        for d in ("attack", "defense")
                    },
                }
            )
    summary["prior_sensitivity"] = prior_summary
    year = int(max(r["season_id"] for r in predictions)[:4]) + 1
    bridge = PromotionBridge(matches, date(year, 7, 1), f"{year}-{year + 1}")
    summary["promotion_bridge"] = bridge.diagnostics()
    entry = entry_performance(matches, bridge.cohorts)
    summary["entry_performance"] = []
    for promoted in (True, False):
        rows = [r for r in entry if r["promoted"] == promoted]
        count = sum(r["appearances"] for r in rows)
        summary["entry_performance"].append(
            {
                "group": "promoted" if promoted else "incumbent",
                "club_seasons": len(rows),
                "appearances": count,
                **{
                    f"{k}_per_match": sum(r[k] for r in rows) / count
                    for k in ("points", "goals_for", "goals_against")
                },
            }
        )
    summary["evaluation_status"] = "exploratory rolling comparison; fixed prototype settings"
    summary["evaluation_note"] = (
        "M4 uses expanding cross-division history; M2 retains its existing PL window. "
        "The cohort-only ablation removes individual Championship performance but retains a "
        "learned promoted population prior. The mode ablation conditions on M4's Gaussian mean. "
        "All seasons are development evidence."
    )
    save_rows(args.output / "predictions.csv", predictions)
    save_rows(args.output / "market_predictions.csv", markets)
    for key in (
        "overall",
        "by_season",
        "calibration",
        "market_matched",
        "slices",
        "prior_sensitivity",
    ):
        save_rows(args.output / f"{key}.csv", summary[key])
    save_rows(args.output / "promotion_cohorts.csv", bridge.cohorts)
    save_rows(args.output / "entry_performance.csv", entry)
    save_rows(args.output / "prior_state_paths.csv", paths)
    save_rows(args.output / "synthetic_form_response.csv", synthetic_form_response())
    summary["diagnostic_runtime_seconds"] = perf_counter() - started
    write_json(args.output / "summary.json", summary)
    write_json(args.output / "paired_comparisons.json", summary["paired_comparisons"])
    write_json(
        args.output / "run.json",
        {
            **provenance(config, manifest),
            "input_evaluations": [str(p) for p in args.evaluations],
            "ablation_spec": spec,
        },
    )
    report = results_markdown(summary)
    (args.output / "results.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
