"""Resolve small availability effects and inspect a large learned-lineup stress case."""

import argparse
import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import numpy as np

from epl_forecast.data.live import LONDON, load_live_season, timestamp
from epl_forecast.data.normalize import load_processed
from epl_forecast.data.squads import (
    Availability,
    PlayerHistory,
    load_player_history,
    snapshot_squads,
)
from epl_forecast.models.player_quality import BayesianPlayerQuality
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--live-players", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    scenario = json.loads(args.scenario.read_text())
    snapshot = Path(scenario["snapshot"])
    live = load_live_season(snapshot)
    captured = load_player_history(args.live_players)
    observed = max([live.observed_at] + [timestamp(r["historical_observed_at"]) for r in captured])
    history = PlayerHistory(
        load_player_history(Path("data/processed/players/player_matches.csv.gz")) + captured
    )
    squads = snapshot_squads(snapshot, observed, history)
    kickoffs = {
        f.match_id: timestamp(live.details[f.match_id]["kickoff_time"]) for f in live.remaining
    }
    matches, _, _ = load_processed(Path("data/processed"))
    as_of = observed.astimezone(LONDON).date()
    training = [m for m in matches if m.fixture.season_id != live.season_id] + live.played
    training = [
        m for m in training if m.available_on <= as_of and m.fixture.season_id >= "2023-2024"
    ]
    model = BayesianPlayerQuality(history, lineup_draws=1024, squads=squads, kickoffs=kickoffs).fit(
        training, as_of
    )
    team, player_id = scenario["team_id"], scenario["player_id"]
    restored = deepcopy(model)
    for member in restored.members:
        member.squads[team] = replace(
            squads[team],
            candidates=tuple(
                replace(p, availability=None) if p.player_id == player_id else p
                for p in squads[team].candidates
            ),
        )
    fixtures = [
        f for f in live.remaining if f.match_id in {r["match_id"] for r in scenario["matches"]}
    ]
    fixture = min(fixtures, key=lambda f: f.match_date)
    quality = {
        p.player_id: sum(
            w * m.mean[m.player_index[p.player_id]]
            for w, m in zip(model.weights, model.members, strict=True)
            if p.player_id in m.player_index
        )
        for p in squads[team].candidates
    }
    important = sorted(
        squads[team].candidates, key=lambda p: -quality[p.player_id] * p.start_weight
    )[:5]
    stress = deepcopy(restored)
    for member in stress.members:
        squad = member.squads[team]
        for p in important:
            squad = squad.with_availability(
                p.player_id,
                Availability(
                    observed, 0, observed + timedelta(days=28), "hypothetical five-player stress"
                ),
            )
        member.squads[team] = squad
    rows = []
    for seed in (610, 611, 612):
        for candidate in (model, restored, stress):
            for member in candidate.members:
                member.seed = seed
        for f in fixtures:
            before = np.array(model.predict_match(f).probabilities)
            after = np.array(restored.predict_match(f).probabilities)
            rows.append(
                {
                    "seed": seed,
                    "match_id": f.match_id,
                    "case": "restore_captured_absence",
                    "probability_change": (after - before).tolist(),
                }
            )
        before = np.array(restored.predict_match(fixture).probabilities)
        after = np.array(stress.predict_match(fixture).probabilities)
        rows.append(
            {
                "seed": seed,
                "match_id": fixture.match_id,
                "case": "five_player_stress",
                "probability_change": (after - before).tolist(),
            }
        )
        print(f"Completed response integration seed {seed}", flush=True)
    summary = []
    for key in sorted({(r["case"], r["match_id"]) for r in rows}):
        differences = np.array(
            [r["probability_change"] for r in rows if (r["case"], r["match_id"]) == key]
        )
        summary.append(
            {
                "case": key[0],
                "match_id": key[1],
                "mean_probability_change": differences.mean(axis=0).tolist(),
                "integration_sd_across_seeds": differences.std(axis=0, ddof=1).tolist(),
            }
        )
    write_json(
        args.output / "response.json",
        {
            "source_scenario": str(args.scenario),
            "source_sha256": file_hash(args.scenario),
            "draws_per_specification": 1024,
            "axis_order": ["home", "draw", "away"],
            "summary": summary,
            "draws": rows,
            "stress_players": [
                {
                    "player_id": p.player_id,
                    "name": p.name,
                    "posterior_mean_quality": quality[p.player_id],
                }
                for p in important
            ],
            "stress_policy": "Hypothetical absence of five players ranked by quality/exposure",
            "restoration_reference": "Same posterior/squad; remove recorded restriction",
        },
    )


if __name__ == "__main__":
    main()
