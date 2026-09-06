"""Chronological M5/M6 comparison with explicitly non-deployable oracle diagnostics."""

import argparse
from collections import Counter, defaultdict
from datetime import date
from itertools import groupby
from pathlib import Path

import numpy as np

from epl_forecast.data.normalize import load_processed, write_csv
from epl_forecast.data.squads import PlayerHistory, load_player_history
from epl_forecast.models.player_quality import BayesianPlayerQuality, player_identity
from epl_forecast.models.quality_tilt import BayesianQualityTilt
from epl_forecast.storage import file_hash, write_json


def labels(model, fixture, counts):
    tags = set()
    for team in (fixture.home_team_id, fixture.away_team_id):
        rows = model.observations[fixture.match_id, team]
        actual = {player_identity(r) for r in rows if float(r["minutes"]) > 0}
        starters = {player_identity(r) for r in rows if r["starts"] == "1"}
        squad = model.squad(fixture, team)
        candidates = {p.player_id for p in squad.candidates}
        expected = {p.player_id for p in squad.candidates if p.start_weight > 0.5}
        if len(expected - starters) >= 4:
            tags.add("major_lineup_change")
        if actual - candidates:
            tags.add("newcomer_or_transfer")
        if any(
            p.player_id in actual
            and len(p.history) >= 3
            and all(m == 0 for m, _ in p.history[-2:])
            and any(m > 0 for m, _ in p.history[:-2])
            for p in squad.candidates
        ):
            tags.add("returning_player")
        if any(p.position == "GK" and p.player_id in expected - starters for p in squad.candidates):
            tags.add("goalkeeper_change")
        if counts[fixture.season_id, team] < 5:
            tags.add("early_season")
        if "promotion" in model.team_state(team, fixture.season_id).source:
            tags.add("promoted_team")
    return tags


def summarize(rows):
    return {
        "matches": len(rows),
        "outcome_log_loss": float(np.mean([r["outcome_log_loss"] for r in rows])),
        "score_log_loss": float(np.mean([r["score_log_loss"] for r in rows])),
        "mean_absolute_home_probability_change": float(
            np.mean([abs(r["home_probability_change"]) for r in rows])
        ),
        "max_absolute_home_probability_change": max(
            abs(r["home_probability_change"]) for r in rows
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--players", type=Path, default=Path("data/processed/players/player_matches.csv.gz")
    )
    parser.add_argument("--train-start", type=date.fromisoformat, default=date(2023, 7, 1))
    parser.add_argument("--season", default="2024-2025")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--draws", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    matches, _, _ = load_processed(args.data)
    matches = [m for m in matches if m.fixture.match_date >= args.train_start]
    history = PlayerHistory(load_player_history(args.players))
    parent = BayesianQualityTilt(independent_poisson=True)
    model = BayesianPlayerQuality(history, lineup_draws=args.draws)
    target = sorted(
        [
            m
            for m in matches
            if m.fixture.season_id == args.season
            and m.fixture.competition_id == "eng-premier-league"
        ],
        key=lambda m: (m.fixture.match_date, m.fixture.match_id),
    )
    if args.limit:
        target = target[: args.limit]
    records, counts = [], Counter()
    for day, games in groupby(target, key=lambda m: m.fixture.match_date):
        training = [m for m in matches if m.available_on <= day]
        parent.fit(training, day)
        model.fit(training, day)
        for match in games:
            fixture = match.fixture
            scores = {
                "M5_team_only": parent.predict_match(fixture).scores,
                "M6_deployable": model.predict_match(fixture).scores,
                "M6_oracle_diagnostic": model.oracle_distribution(fixture),
            }
            baseline = scores["M5_team_only"].outcome_probabilities()[0]
            tags = labels(model.members[0], fixture, counts)
            for regime, distribution in scores.items():
                probabilities = distribution.outcome_probabilities()
                records.append(
                    {
                        "match_id": fixture.match_id,
                        "match_date": str(day),
                        "season_id": fixture.season_id,
                        "regime": regime,
                        "deployable": regime != "M6_oracle_diagnostic",
                        "p_home": float(probabilities[0]),
                        "p_draw": float(probabilities[1]),
                        "p_away": float(probabilities[2]),
                        "outcome": match.outcome,
                        "outcome_log_loss": float(
                            -np.log(probabilities["HDA".index(match.outcome)])
                        ),
                        "score_log_loss": -distribution.log_probability(
                            match.home_goals, match.away_goals
                        ),
                        "home_probability_change": float(probabilities[0] - baseline),
                        "slices": "|".join(sorted(tags)),
                    }
                )
            for team in (fixture.home_team_id, fixture.away_team_id):
                counts[fixture.season_id, team] += 1
        print(
            f"Evaluated through {day}: {len(records) // 3} fixtures; "
            f"{len(model.members[0].player_index)} players",
            flush=True,
        )
        write_csv(args.output / "predictions.csv", list(records[0]), records)
    groups = defaultdict(list)
    for row in records:
        groups[row["regime"], "all"].append(row)
        for tag in row["slices"].split("|"):
            if tag:
                groups[row["regime"], tag].append(row)
    summary = [
        {"regime": regime, "slice": tag, **summarize(rows)}
        for (regime, tag), rows in sorted(groups.items())
    ]
    write_csv(args.output / "summary.csv", list(summary[0]), summary)
    write_json(
        args.output / "run.json",
        {
            "arguments": {
                key: str(value) if isinstance(value, (date, Path)) else value
                for key, value in vars(args).items()
            },
            "inputs": {
                str(args.players): file_hash(args.players),
                str(args.data / "matches.csv"): file_hash(args.data / "matches.csv"),
            },
            "comparison": "Matched expanding window; original four Poisson M5 dynamics specs",
            "oracle_policy": "Oracle uses target minutes; fitted posterior is shared",
            "historical_limitations": [
                "Squad publication times unknown; prior-fixture retrospective proxy",
                "Opening-season candidate gaps are reported separately",
                "Known absences unavailable historically; use timestamped live scenarios",
                "Newcomer slice uses first participation, not verified transfer news",
            ],
            "required_slices": {
                tag: sum(
                    tag in r["slices"].split("|") for r in records if r["regime"] == "M6_deployable"
                )
                for tag in (
                    "major_lineup_change",
                    "known_absence",
                    "returning_player",
                    "newcomer_or_transfer",
                    "promoted_team",
                    "early_season",
                    "goalkeeper_change",
                )
            },
            "fit": model.fit_diagnostics,
        },
    )


if __name__ == "__main__":
    main()
