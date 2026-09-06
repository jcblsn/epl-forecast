"""Retain chronological lineup predictions and measure candidate-pool blind spots."""

import argparse
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from epl_forecast.data.live import timestamp
from epl_forecast.data.normalize import write_csv
from epl_forecast.data.squads import PlayerHistory, load_player_history
from epl_forecast.lineups import sample_lineups
from epl_forecast.storage import file_hash, write_json


def evaluate(history, seasons, draws, seed):
    groups = defaultdict(list)
    for row in history.rows:
        if row["season_id"] in seasons:
            groups[row["kickoff_time"], row["match_id"], row["team_id"]].append(row)
    rng = np.random.default_rng(seed)
    records, predictions = [], []
    prior_starters = {}
    games = defaultdict(int)
    for (kickoff, match_id, team), outcomes in sorted(groups.items()):
        day = timestamp(kickoff).date()
        cutoff = datetime.combine(day, datetime.min.time(), UTC)
        season = outcomes[0]["season_id"]
        squad = history.retrospective_squad(team, season, cutoff)
        sampled = sample_lineups(squad, timestamp(kickoff), rng, draws)
        predicted = {p["player_id"]: p for p in sampled.summary() if not p["anonymous"]}
        actual = {f"fpl:{r['fpl_player_code']}": r for r in outcomes}
        starters = {key for key, row in actual.items() if row["starts"] == "1"}
        if len(starters) != 11:
            raise ValueError("Lineup evaluation requires eleven observed starters")
        minutes_error, start_error = [], []
        for identity in sorted(set(actual) | set(predicted)):
            observed = actual.get(identity, {})
            forecast = predicted.get(identity, {})
            minutes = float(observed.get("minutes", 0))
            start = float(observed.get("starts", 0))
            expected = forecast.get("expected_minutes", 0)
            probability = forecast.get("start_probability", 0)
            minutes_error.append(abs(expected - minutes))
            start_error.append((probability - start) ** 2)
            predictions.append(
                {
                    "match_id": match_id,
                    "team_id": team,
                    "cutoff": cutoff.isoformat(),
                    "player_id": identity,
                    "candidate": identity in predicted,
                    "minutes": minutes,
                    "expected_minutes": expected,
                    "starts": start,
                    "start_probability": probability,
                }
            )
        key = season, team
        last = prior_starters.get(key)
        records.append(
            {
                "match_id": match_id,
                "season_id": season,
                "team_id": team,
                "cutoff": cutoff.isoformat(),
                "prior_team_matches": games[key],
                "candidates": len(squad.candidates),
                "missing_starters": len(starters - set(predicted)),
                "starter_changes": len(starters - last) if last is not None else "",
                "missing_actual_minutes": sum(
                    float(r["minutes"]) for p, r in actual.items() if p not in predicted
                ),
                "anonymous_expected_minutes": sum(
                    p["expected_minutes"] for p in sampled.summary() if p["anonymous"]
                ),
                "player_union_size": len(minutes_error),
                "minutes_absolute_error_sum": sum(minutes_error),
                "starter_squared_error_sum": sum(start_error),
            }
        )
        prior_starters[key] = starters
        games[key] += 1
        if len(records) % 100 == 0:
            print(f"Evaluated {len(records)}/{len(groups)} fixture sides", flush=True)
    return records, predictions


def summarize(rows):
    count = sum(r["player_union_size"] for r in rows)
    return {
        "fixture_sides": len(rows),
        "starter_candidate_coverage": 1
        - sum(r["missing_starters"] for r in rows) / (11 * len(rows)),
        "missing_actual_minutes_per_side": float(
            np.mean([r["missing_actual_minutes"] for r in rows])
        ),
        "anonymous_expected_minutes_per_side": float(
            np.mean([r["anonymous_expected_minutes"] for r in rows])
        ),
        "minutes_mae_player_union": sum(r["minutes_absolute_error_sum"] for r in rows) / count,
        "starter_brier_player_union": sum(r["starter_squared_error_sum"] for r in rows) / count,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--players", type=Path, default=Path("data/processed/players/player_matches.csv.gz")
    )
    parser.add_argument("--seasons", nargs="+", default=["2023-2024", "2024-2025", "2025-2026"])
    parser.add_argument("--draws", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    history = PlayerHistory(load_player_history(args.players))
    rows, predictions = evaluate(history, args.seasons, args.draws, args.seed)
    slices = {
        "all": rows,
        "first_five": [r for r in rows if r["prior_team_matches"] < 5],
        "after_first_five": [r for r in rows if r["prior_team_matches"] >= 5],
        "four_plus_starter_changes": [
            r for r in rows if r["starter_changes"] != "" and r["starter_changes"] >= 4
        ],
        "newcomer_starter": [r for r in rows if r["missing_starters"] > 0],
    }
    slices.update({s: [r for r in rows if r["season_id"] == s] for s in args.seasons})
    for name, table in (("fixture_sides", rows), ("predictions", predictions)):
        write_csv(args.output / f"{name}.csv", list(table[0]), table)
    write_json(
        args.output / "report.json",
        {
            "input": str(args.players),
            "sha256": file_hash(args.players),
            "draws": args.draws,
            "seed": args.seed,
            "scope": "Retrospective development evidence; candidate pools use earlier UTC dates. "
            "Newcomers omitted from candidate pools receive zero predicted minutes in scoring. "
            "No historical availability or registration claims; anonymous minutes explicit.",
            "slices": {name: summarize(table) for name, table in slices.items() if table},
            "artifacts": {
                name: file_hash(args.output / name)
                for name in ("fixture_sides.csv", "predictions.csv")
            },
        },
    )


if __name__ == "__main__":
    main()
