"""Refine high-information slices and paired day-block uncertainty without refitting."""

import argparse
import csv
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from evaluate_player_quality import information_tags, summarize

from epl_forecast.data.normalize import load_processed, write_csv
from epl_forecast.data.squads import PlayerHistory, load_player_history
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    run = json.loads((args.evaluation / "run.json").read_text())
    history = PlayerHistory(load_player_history(Path(run["arguments"]["players"])))
    observations = defaultdict(list)
    for row in history.rows:
        observations[row["match_id"], row["team_id"]].append(row)
    matches, _, _ = load_processed(Path(run["arguments"]["data"]))
    matches = sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id))
    lookup = {m.fixture.match_id: m for m in matches}
    predictions = list(csv.DictReader((args.evaluation / "predictions.csv").open()))
    refined = {}
    for row in predictions:
        if row["match_id"] in refined:
            continue
        fixture = lookup[row["match_id"]].fixture
        cutoff = datetime.combine(fixture.match_date, datetime.min.time(), UTC)
        tags = set(row["slices"].split("|")) & {"promoted_team", "early_season"}
        for team in (fixture.home_team_id, fixture.away_team_id):
            previous = next(
                (
                    m
                    for m in reversed(matches)
                    if m.available_on <= fixture.match_date
                    and m.fixture.competition_id == "eng-premier-league"
                    and team in (m.fixture.home_team_id, m.fixture.away_team_id)
                ),
                None,
            )
            previous_rows = observations[previous.fixture.match_id, team] if previous else []
            squad = history.retrospective_squad(team, fixture.season_id, cutoff, carry_forward=True)
            tags.update(
                information_tags(observations[fixture.match_id, team], squad, previous_rows)
            )
        refined[row["match_id"]] = "|".join(sorted(tags))
    for row in predictions:
        row["slices"] = refined[row["match_id"]]
        for key in (
            "p_home",
            "p_draw",
            "p_away",
            "outcome_log_loss",
            "score_log_loss",
            "home_probability_change",
        ):
            row[key] = float(row[key])
    write_csv(args.output / "predictions.csv", list(predictions[0]), predictions)
    groups = defaultdict(list)
    parent = {r["match_id"]: r for r in predictions if r["regime"] == "M5_team_only"}
    for row in predictions:
        for tag in ["all"] + row["slices"].split("|"):
            if tag:
                groups[row["regime"], tag].append(row)
    summaries = []
    rng = np.random.default_rng(610)
    for (regime, tag), rows in sorted(groups.items()):
        days = defaultdict(list)
        for row in rows:
            days[row["match_date"]].append(
                row["outcome_log_loss"] - parent[row["match_id"]]["outcome_log_loss"]
            )
        sums = np.array([sum(values) for values in days.values()])
        counts = np.array([len(values) for values in days.values()])
        indices = rng.integers(len(days), size=(2000, len(days)))
        differences = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
        summaries.append(
            {
                "regime": regime,
                "slice": tag,
                **summarize(rows),
                "loss_difference_from_m5": float(sums.sum() / counts.sum()),
                "paired_day_bootstrap_q025": float(np.quantile(differences, 0.025)),
                "paired_day_bootstrap_q975": float(np.quantile(differences, 0.975)),
            }
        )
    write_csv(args.output / "summary.csv", list(summaries[0]), summaries)
    write_json(
        args.output / "diagnostics.json",
        {
            "source": str(args.evaluation),
            "source_predictions_sha256": file_hash(args.evaluation / "predictions.csv"),
            "definitions": {
                "major_lineup_change": "At least four changes from prior observed starting eleven",
                "returning_player": "At least 45 target minutes after two zero-minute appearances",
                "newcomer_or_transfer": "At least 45 target minutes outside cutoff candidate pool",
                "goalkeeper_change": "Previous observed starting goalkeeper is no longer a starter",
                "known_absence": "Unavailable historically; retained in live timestamped scenario",
                "early_season": "At least one team has fewer than five prior season games",
                "promoted_team": "At least one team uses the Championship promotion prior",
            },
            "top_deployable_movements": sorted(
                [r for r in predictions if r["regime"] == "M6_deployable"],
                key=lambda r: -abs(r["home_probability_change"]),
            )[:20],
            "top_oracle_movements_non_deployable": sorted(
                [r for r in predictions if r["regime"] == "M6_oracle_diagnostic"],
                key=lambda r: -abs(r["home_probability_change"]),
            )[:20],
        },
    )


if __name__ == "__main__":
    main()
