"""Residual information of team goals, xG, shots and SOT over frozen inputs."""

import argparse
import json
from collections import defaultdict
from itertools import groupby
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance
from epl_forecast.models.gaussian import likelihood_laplace_update, score_laplace_update
from epl_forecast.models.xg_observation import ChanceObservation
from epl_forecast.models.xg_quality_tilt import XG_DYNAMICS, XGQualityTiltFilter
from epl_forecast.research.information_value import (
    correlated_sensor_calibration,
    information_report,
)
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.storage import file_hash, json_bytes, write_immutable, write_json


def extract_rows(data, start, end, horizons=(1, 3, 6)):
    matches, observations = data.matches(), data.process()
    fixtures = {f["match_id"]: f for f in data.fixtures()}
    process = {
        (r["match_id"], r["team_id"], r["provider"]): r
        for r in data.rows("SELECT * FROM team_process")
    }
    teams = defaultdict(list)
    for match in sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id)):
        f = match.fixture
        for team in (f.home_team_id, f.away_team_id):
            teams[f.competition_id, f.season_id, team].append(match)
    targets = {}
    for (_, _, team), games in teams.items():
        for i, match in enumerate(games):
            targets[match.fixture.match_id, team] = {
                lag: games[i + lag] for lag in horizons if i + lag < len(games)
            }
    for league in ("eng-premier-league", "eng-championship"):
        parent = XGQualityTiltFilter(
            observations if league == "eng-premier-league" else (), 0.2, **XG_DYNAMICS
        )
        parent.primary_competition = league
        selected = [
            m
            for m in matches
            if m.fixture.competition_id == league and start <= int(m.fixture.season_id[:4]) <= end
        ]
        last_season = None
        for day, games in groupby(
            sorted(selected, key=lambda m: (m.fixture.match_date, m.fixture.match_id)),
            key=lambda m: m.fixture.match_date,
        ):
            training = [m for m in matches if m.available_on <= day]
            if not any(m.fixture.competition_id == league for m in training):
                continue
            parent.fit(training, day)
            for match in games:
                f = match.fixture
                if f.season_id != last_season:
                    print(f"Extracting {league} {f.season_id}", flush=True)
                    last_season = f.season_id
                source_mean, source_covariance = parent.forecast_moments(f)
                goals = np.array([match.home_goals, match.away_goals])
                _, goals_covariance, _ = score_laplace_update(
                    source_mean, source_covariance, np.eye(2), goals, None
                )
                source_xg = [
                    process.get((f.match_id, t, "understat"), {}).get("xg")
                    for t in (f.home_team_id, f.away_team_id)
                ]
                xg_covariance = None
                if all(value is not None for value in source_xg):
                    _, xg_covariance, _ = likelihood_laplace_update(
                        source_mean,
                        source_covariance,
                        np.eye(2),
                        ChanceObservation(goals, source_xg, 0.2),
                    )
                for side, team in enumerate((f.home_team_id, f.away_team_id)):
                    counts = process.get((f.match_id, team, "football_data"), {})
                    xg = process.get((f.match_id, team, "understat"), {})
                    signal = {
                        "goals": match.home_goals if side == 0 else match.away_goals,
                        "xg": xg.get("xg"),
                        "shots": counts.get("shots"),
                        "shots_on_target": counts.get("shots_on_target"),
                    }
                    for horizon, target in targets[f.match_id, team].items():
                        tf = target.fixture
                        if tf.match_date < match.available_on:
                            continue
                        target_side = 0 if tf.home_team_id == team else 1
                        mean, covariance = parent.forecast_moments(tf)
                        expected = np.exp(
                            mean[target_side] + covariance[target_side, target_side] / 2
                        )
                        yield {
                            "competition_id": league,
                            "season_id": f.season_id,
                            "match_id": f.match_id,
                            "team_id": team,
                            "target_match_id": tf.match_id,
                            "horizon": horizon,
                            "information_available_on": str(match.available_on),
                            "target_available_on": str(target.available_on),
                            "source_retrieved_at": {
                                "goals": str(fixtures[f.match_id]["retrieved_at"]),
                                "xg": str(xg.get("retrieved_at")) if xg else None,
                                "shots": str(counts.get("retrieved_at")) if counts else None,
                            },
                            "source_sha256": {
                                "goals": match.source_sha256,
                                "xg": xg.get("source_sha256"),
                                "shots": counts.get("source_sha256"),
                            },
                            "signals": signal,
                            "log_rate_posterior_variance": {
                                "before_observation": float(source_covariance[side, side]),
                                "goals": float(goals_covariance[side, side]),
                                "goals_xg": float(xg_covariance[side, side])
                                if xg_covariance is not None
                                else None,
                                "shots": None,
                                "shots_on_target": None,
                            },
                            "controls": [
                                float(source_mean[side]),
                                float(source_mean[1 - side]),
                                float(source_covariance[side, side]),
                                float(source_covariance[1 - side, 1 - side]),
                                int(side == 0),
                                float(np.log1p(expected)),
                                float(covariance[target_side, target_side]),
                                int(target_side == 0),
                                (tf.match_date - f.match_date).days / 30,
                            ],
                            "target": float(
                                np.log1p(
                                    target.home_goals if target_side == 0 else target.away_goals
                                )
                            ),
                            "availability_basis": "retrospective next-day assumption; actual retrieval retained separately",
                        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=int, default=2014)
    parser.add_argument("--end", type=int, default=2025)
    args = parser.parse_args()
    if args.start < 2013 or args.end < args.start:
        raise ValueError("Use a reviewed post-2013 process window")
    eligibility = json.loads(args.manifest.read_text())["readiness"]["eligible_cohorts"][
        "goals_information"
    ]
    if any(
        [league, f"{year}-{year + 1}"] not in eligibility
        for league in ("eng-premier-league", "eng-championship")
        for year in range(args.start, args.end + 1)
    ):
        raise ValueError("Requested league season is not a complete eligible research cohort")
    metadata = {
        "execution": execution_provenance(),
        "research_manifest_sha256": file_hash(args.manifest),
        "start": args.start,
        "end": args.end,
        "parent": "M7 fixed p=0.2 member with frozen dynamics; Championship uses goals-only marginal",
        "controls": [
            "source_team_log_rate",
            "source_opponent_log_rate",
            "source_team_rate_variance",
            "source_opponent_rate_variance",
            "source_home",
            "target_log1p_expected_goals",
            "target_rate_variance",
            "target_home",
            "target_gap_months",
        ],
        "horizons": [1, 3, 6],
        "penalty": 0.01,
    }
    write_immutable(args.output / "manifest.json", json_bytes(metadata))
    destination = args.output / "observations.json"
    if destination.exists():
        rows = json.loads(destination.read_text())
    else:
        data = frozen_dataset(args.data, args.manifest)
        try:
            rows = list(extract_rows(data, args.start, args.end))
        finally:
            data.close()
        write_immutable(destination, json_bytes(rows))
    report = information_report(rows)
    report["known_state_sensor_calibration"] = correlated_sensor_calibration()
    predictions = report.pop("predictions")
    write_json(args.output / "predictions.json", predictions)
    write_json(args.output / "report.json", report)
    write_json(
        args.output / "completion.json",
        {
            "observations": len(rows),
            "predictions": len(predictions),
            "comparisons": len(report["comparisons"]),
            "observation_sha256": file_hash(destination),
        },
    )
    print(args.output / "report.json", flush=True)


if __name__ == "__main__":
    main()
