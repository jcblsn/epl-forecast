"""Sample the joint club/player trajectory on an explicitly bounded real-data subset."""

import argparse
from pathlib import Path

import numpy as np

from epl_forecast.data.normalize import load_processed
from epl_forecast.data.squads import PlayerHistory, load_player_history
from epl_forecast.models.player_quality import PlayerQualityFilter
from epl_forecast.research.quality_tilt_reference import (
    compare_posterior,
    prepare,
    sample_reference,
)
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--matches", type=int, default=60)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    path = Path("data/processed/players/player_matches.csv.gz")
    matches, _, _ = load_processed(Path("data/processed"))
    matches = sorted(
        [
            m
            for m in matches
            if m.fixture.season_id == "2023-2024"
            and m.fixture.competition_id == "eng-premier-league"
        ],
        key=lambda m: (m.fixture.match_date, m.fixture.match_id),
    )[: args.matches]
    history = PlayerHistory(load_player_history(path))
    parameters = dict(
        quality_retention=0.85, quality_sd=0.09, tilt_retention=0.5, tilt_sd=0.07, dispersion=None
    )
    data = prepare(matches)
    model = PlayerQualityFilter(history, **parameters).fit(matches, data["cutoff"])
    players = sorted(model.player_index)
    player_index = {key: i for i, key in enumerate(players)}
    design = np.zeros((len(matches), 2, len(players)))
    for i, match in enumerate(matches):
        for team, sign in ((match.fixture.home_team_id, 1), (match.fixture.away_team_id, -1)):
            for key, weight in model.actual_weights(match.fixture, team).items():
                design[i, :, player_index[key]] += np.array([sign, -sign]) * weight
    data.update(player_design=design, player_sd=model.player_sd, parameters=parameters)
    indices = [0, 1] + [2 + 2 * model.team_index[t] + d for t in data["teams"] for d in range(2)]
    indices += [model.player_index[key] for key in players]
    mean, covariance = model.mean[indices], model.covariance[np.ix_(indices, indices)]
    print(f"Sampling {len(matches)} matches, {len(players)} players", flush=True)
    draws, diagnostics = sample_reference(data)
    sampled = draws["final_state"]
    nclub = 2 + 2 * len(data["teams"])
    projection = np.concatenate([data["design"], design], axis=2).reshape(-1, len(mean))
    report = {
        "scope": "Fixed dynamics; fresh population club priors; real opening-season subset",
        "matches": [m.fixture.match_id for m in matches],
        "cutoff": str(data["cutoff"]),
        "players": players,
        "parameters": parameters,
        "player_sd": model.player_sd,
        "diagnostics": diagnostics,
        "joint": compare_posterior(sampled, mean, covariance),
        "players_only": compare_posterior(
            sampled[:, nclub:], mean[nclub:], covariance[nclub:, nclub:]
        ),
        "cutoff_match_log_rates": compare_posterior(
            sampled @ projection.T, projection @ mean, projection @ covariance @ projection.T
        ),
        "inputs": {
            str(path): file_hash(path),
            "data/processed/matches.csv": file_hash(Path("data/processed/matches.csv")),
        },
    }
    write_json(args.output / "reference.json", report)
    print(diagnostics, flush=True)


if __name__ == "__main__":
    main()
