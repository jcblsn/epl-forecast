"""Archive current M6 forecasts and an expiring captured-availability counterfactual."""

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

from epl_forecast.data.live import LONDON, load_live_season, timestamp
from epl_forecast.data.normalize import load_processed
from epl_forecast.data.squads import PlayerHistory, load_player_history, snapshot_squads
from epl_forecast.live_forecast import check_freshness, export_forecast
from epl_forecast.models.player_quality import BayesianPlayerQuality
from epl_forecast.models.quality_tilt import BayesianQualityTilt
from epl_forecast.simulation import simulate_season
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--live-players", type=Path, required=True)
    parser.add_argument(
        "--players", type=Path, default=Path("data/processed/players/player_matches.csv.gz")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-start", type=date.fromisoformat, default=date(2023, 7, 1))
    parser.add_argument("--simulations", type=int, default=2000)
    parser.add_argument("--draws", type=int, default=64)
    parser.add_argument("--seed", type=int, default=610)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    live = load_live_season(args.snapshot)
    check_freshness(live, 24)
    if any(
        r["status"] in {"in_progress", "awaiting_result", "unscheduled"}
        for r in live.details.values()
    ):
        raise ValueError("Complete dated fixture state is required for this scenario demonstration")
    captured = load_player_history(args.live_players)
    observed = max([live.observed_at] + [timestamp(r["historical_observed_at"]) for r in captured])
    if observed > datetime.now(UTC):
        raise ValueError("Player observations are in the future")
    history = PlayerHistory(load_player_history(args.players) + captured)
    squads = snapshot_squads(args.snapshot, observed, history)
    kickoffs = {
        f.match_id: timestamp(live.details[f.match_id]["kickoff_time"]) for f in live.remaining
    }
    matches, _, _ = load_processed(Path("data/processed"))
    as_of = observed.astimezone(LONDON).date()
    training = [m for m in matches if m.fixture.season_id != live.season_id] + live.played
    training = [
        m for m in training if m.available_on <= as_of and m.fixture.match_date >= args.train_start
    ]
    model = BayesianPlayerQuality(
        history, lineup_draws=args.draws, seed=args.seed, squads=squads, kickoffs=kickoffs
    ).fit(training, as_of)
    print(
        f"Fitted M6: {len(training)} results, {len(model.members[0].player_index)} players",
        flush=True,
    )
    inputs = {
        str(path): file_hash(path)
        for path in (
            args.players,
            args.live_players,
            args.snapshot / "manifest.json",
            Path("data/processed/matches.csv"),
        )
    }
    run = {
        "model": {"id": "M6-player-quality-v1", "kind": "bayesian_player_quality"},
        "inputs": inputs,
        "information_observed_at": observed.isoformat(),
        "train_start": str(args.train_start),
        "seed": args.seed,
        "simulations": args.simulations,
        "promotion_status": "research; M2 remains default",
    }
    forecast = export_forecast(
        live, model, training, run, args.output / "current", args.simulations, args.seed, 10, []
    )
    print("Archived current M6 forecast", flush=True)
    parent = BayesianQualityTilt(independent_poisson=True).fit(training, as_of)
    parent_forecast = export_forecast(
        live,
        parent,
        training,
        {**run, "model": {"id": "M5-quality-tilt-poisson"}},
        args.output / "parent",
        args.simulations,
        args.seed,
        10,
        [],
    )
    choices = []
    for team, squad in squads.items():
        for player in squad.candidates:
            if player.availability is None or player.availability.probability >= 0.75:
                continue
            quality = sum(
                w * member.mean[member.player_index[player.player_id]]
                for w, member in zip(model.weights, model.members, strict=True)
                if player.player_id in member.player_index
            )
            choices.append((quality * player.start_weight, team, player))
    if not choices:
        raise ValueError("Snapshot has no learned player with restricted availability")
    _, team, player = max(choices, key=lambda choice: choice[0])
    restored = deepcopy(model)
    restored_squad = replace(
        squads[team],
        candidates=tuple(
            replace(p, availability=None) if p.player_id == player.player_id else p
            for p in squads[team].candidates
        ),
    )
    for member in restored.members:
        member.squads[team] = restored_squad
    scenario_simulation = simulate_season(
        restored,
        live.played,
        live.remaining,
        list(live.teams),
        as_of,
        args.simulations,
        args.seed,
        [],
        results_observed_at=live.observed_at,
    )
    write_json(args.output / "restored_season.json", scenario_simulation)
    current_by_id = {r["match_id"]: r for r in forecast["matches"]}
    parent_by_id = {r["match_id"]: r for r in parent_forecast["matches"]}
    changes = []
    for fixture in live.remaining:
        current, baseline = current_by_id[fixture.match_id], parent_by_id[fixture.match_id]
        changes.append(
            {
                "match_id": fixture.match_id,
                "m6_minus_m5": {
                    key: current[key] - baseline[key] for key in ("p_home", "p_draw", "p_away")
                },
            }
        )
    scenario_matches = []
    after_expiry_checked = False
    for fixture in sorted(live.remaining, key=lambda f: (f.match_date, f.match_id)):
        if team not in (fixture.home_team_id, fixture.away_team_id):
            continue
        expired = kickoffs[fixture.match_id] >= player.availability.expires_at
        if expired and after_expiry_checked:
            continue
        current = current_by_id[fixture.match_id]
        restored_p = restored.predict_match(fixture).probabilities
        delta = {
            key: float(p - current[key])
            for key, p in zip(("p_home", "p_draw", "p_away"), restored_p, strict=True)
        }
        if expired:
            if max(abs(value) for value in delta.values()) > 1e-12:
                raise RuntimeError("Expired availability still changes direct forecasts")
            after_expiry_checked = True
        scenario_matches.append(
            {
                "match_id": fixture.match_id,
                "expired": expired,
                "restored_minus_current": delta,
                "current_player_quality": current["player_quality"],
                "restored_player_quality": restored.lineup_summary(fixture),
            }
        )
    if not after_expiry_checked or not any(not r["expired"] for r in scenario_matches):
        raise RuntimeError("Scenario requires fixtures before and after expiry")
    current_table = {r["team_id"]: r for r in forecast["simulation"]["teams"]}
    season_changes = [
        {
            "team_id": r["team_id"],
            **{
                key: r[key] - current_table[r["team_id"]][key]
                for key in (
                    "mean_points",
                    "title_probability",
                    "top_four_probability",
                    "relegation_probability",
                )
            },
        }
        for r in scenario_simulation["teams"]
    ]
    agreement = []
    for row in forecast["simulation"]["match_frequencies"]:
        direct = current_by_id[row["match_id"]]
        for key in ("p_home", "p_draw", "p_away"):
            p = direct[key]
            agreement.append(abs(row[key] - p) / np.sqrt(max(p * (1 - p), 1e-6) / args.simulations))
    write_json(
        args.output / "scenario.json",
        {
            "snapshot": str(args.snapshot),
            "source_hashes": inputs,
            "observed_at": observed.isoformat(),
            "team_id": team,
            "player_id": player.player_id,
            "player_name": player.name,
            "availability": {
                **vars(player.availability),
                "observed_at": player.availability.observed_at.isoformat(),
                "expires_at": player.availability.expires_at.isoformat(),
            },
            "counterfactual": "Restore captured player availability; same fitted model",
            "expiry_policy": "FPL proxy: linear recovery over 28 days; expiry is an assumption",
            "matches": scenario_matches,
            "restored_minus_current_season": season_changes,
            "m6_minus_m5_matches": changes,
            "agreement": {
                "match_outcomes": len(agreement),
                "max_standard_errors": max(agreement),
                "fraction_within_three_standard_errors": float(np.mean(np.array(agreement) < 3)),
                "limitation": "Includes finite lineup-mixture integration error",
            },
            "season_delta_caution": "Monte Carlo deltas may be below sampling noise",
        },
    )
    print(f"Completed availability scenario: {team}, {player.name}", flush=True)


if __name__ == "__main__":
    main()
