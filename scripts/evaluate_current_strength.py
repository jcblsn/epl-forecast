"""Does an API-Football team signal say anything the M7 state does not already know?

The season sensitivity says current-state uncertainty dominates future-state
evolution, and the Championship is where the current state is worst informed: no
Understat coverage exists there, so M7's observation channel contributes nothing and
the filter runs on goals alone. The archive does, however, already hold API-Football
per-match team statistics for both leagues, including expected goals from 2022/23.

This asks the cheapest useful question about them. At each source match the frozen
M7 member supplies the team's log-rate mean and variance from strictly earlier
evidence; the candidate signal is the source match's own statistic; the target is the
team's goals one, three or six matches later. A signal that carries current-strength
information the state is missing predicts those later goals after the state has been
regressed out. One that does not is measuring what the filter already absorbed.

Two studies run on one extraction because they have different usable windows. Shots
from inside the box reach back to 2016/17 in both leagues; expected goals begins in
2022/23 and leaves only a few chronologically testable seasons. Extraction is shared
with the retained goals/xG/shots/SOT study in design but not in code, so that study's
observations and hashes stay exactly as published.
"""

import argparse
import json
from collections import defaultdict
from itertools import groupby
from pathlib import Path

import numpy as np

from epl_forecast.artifacts import execution_provenance
from epl_forecast.models.xg_quality_tilt import XG_DYNAMICS, XGQualityTiltFilter
from epl_forecast.research.information_value import information_report
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.storage import file_hash, json_bytes, write_immutable, write_json

LEAGUES = ("eng-premier-league", "eng-championship")
STUDIES = {
    "box_shots": {
        "eng-premier-league": ("goals", "api_shots_inside_box"),
        "eng-championship": ("goals", "api_shots_inside_box"),
    },
    "expected_goals": {
        "eng-premier-league": ("goals", "understat_xg", "api_expected_goals"),
        "eng-championship": ("goals", "api_expected_goals"),
    },
}
CONCEPTS = {
    "goals": "Realized scoring, the observation the filter already admits.",
    "understat_xg": "Understat chance quality; Premier League only.",
    "api_expected_goals": "API-Football chance quality, the first Championship xG in this archive.",
    "api_shots_inside_box": "Shot volume from inside the box, a longer-covered chance-location proxy.",
}


def extract_rows(data, start, end, horizons=(1, 3, 6)):
    """One row per (source match, team, horizon), with state controls and candidates."""
    matches, observations = data.matches(), data.process()
    statistics = {
        (r["match_id"], r["team_id"]): r for r in data.rows("SELECT * FROM team_statistics")
    }
    understat = {
        (r["match_id"], r["team_id"]): r
        for r in data.rows("SELECT * FROM team_process WHERE provider='understat'")
    }
    teams = defaultdict(list)
    for match in sorted(matches, key=lambda m: (m.fixture.match_date, m.fixture.match_id)):
        f = match.fixture
        for team in (f.home_team_id, f.away_team_id):
            teams[f.competition_id, f.season_id, team].append(match)
    targets = {}
    for (_, _, team), games in teams.items():
        for index, match in enumerate(games):
            targets[match.fixture.match_id, team] = {
                lag: games[index + lag] for lag in horizons if index + lag < len(games)
            }
    for league in LEAGUES:
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
                for side, team in enumerate((f.home_team_id, f.away_team_id)):
                    api = statistics.get((f.match_id, team), {})
                    signal = {
                        "goals": match.home_goals if side == 0 else match.away_goals,
                        "understat_xg": understat.get((f.match_id, team), {}).get("xg"),
                        "api_expected_goals": api.get("expected_goals"),
                        "api_shots_inside_box": api.get("shots_inside_box"),
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
                            "source_sha256": {
                                "goals": match.source_sha256,
                                "api": api.get("source_sha256"),
                            },
                            "source_retrieved_at": {
                                "api": str(api["retrieved_at"]) if api else None
                            },
                            "signals": signal,
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


def headline(report, study):
    """Each candidate's incremental effect on next-match squared error."""
    improved = defaultdict(lambda: [0, 0])
    for row in report["stability"]:
        if row["dimension"] != "season_id" or row["horizon"] != 1:
            continue
        key = row["competition_id"], row["candidate"], row["comparator"]
        improved[key][0] += row["mse_difference"] < 0
        improved[key][1] += 1
    return [
        {
            "study": study,
            "competition_id": comparison["competition_id"],
            "candidate": comparison["candidate"],
            "comparator": comparison["comparator"],
            "mse_difference": comparison["difference"],
            "interval_low": (comparison["interval_95"] or [None, None])[0],
            "interval_high": (comparison["interval_95"] or [None, None])[1],
            "seasons_improved": improved[
                comparison["competition_id"], comparison["candidate"], comparison["comparator"]
            ][0],
            "seasons": improved[
                comparison["competition_id"], comparison["candidate"], comparison["comparator"]
            ][1],
            "team_matches": comparison["observations"],
        }
        for comparison in report["comparisons"]
        if comparison["horizon"] == 1
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=int, default=2016)
    parser.add_argument("--end", type=int, default=2025)
    args = parser.parse_args()
    if args.start < 2013 or args.end < args.start:
        raise ValueError("Use a reviewed post-2013 process window")
    metadata = {
        "execution": execution_provenance(),
        "research_manifest_sha256": file_hash(args.manifest),
        "start": args.start,
        "end": args.end,
        "parent": "M7 fixed p=0.2 member with frozen dynamics; Championship uses goals-only marginal",
        "studies": STUDIES,
        "concepts": CONCEPTS,
        "horizons": [1, 3, 6],
        "question": (
            "Whether an API-Football team statistic predicts a team's later goals after "
            "the M7 state's own forecast has been regressed out"
        ),
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
    headlines, completion = [], {"observations": len(rows), "studies": {}}
    for study, signals in STUDIES.items():
        usable = [
            row
            for row in rows
            if all(row["signals"].get(s) is not None for s in signals[row["competition_id"]])
        ]
        report = information_report(usable, signals_by_league=signals)
        predictions = report.pop("predictions")
        write_json(args.output / f"{study}_report.json", report)
        headlines.extend(headline(report, study))
        completion["studies"][study] = {
            "complete_cases": len(usable),
            "seasons": sorted({row["season_id"] for row in usable}),
            "predictions": len(predictions),
            "comparisons": len(report["comparisons"]),
        }
    write_json(args.output / "headlines.json", headlines)
    completion["observation_sha256"] = file_hash(destination)
    write_json(args.output / "completion.json", completion)
    print(args.output / "headlines.json", flush=True)


if __name__ == "__main__":
    main()
