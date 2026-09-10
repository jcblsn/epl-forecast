"""Check a published forecast archive against what the product promises.

The MVP contract is a list of things every archive must contain and every archive
must be internally consistent about: probabilities that are probabilities, a score
matrix that agrees with the match probabilities drawn from it, a season simulation
whose event masses equal the number of places the competition actually awards, the
rules and sanctions in force at the cutoff, a Championship bracket conditioned on the
same paths as the table, and enough provenance to say what was known when.

Every check reads only the archive, so it can be run on an old run as easily as a
fresh one, and it fails loudly rather than reporting a score.
"""

import argparse
import json
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from epl_forecast.artifacts import execution_provenance
from epl_forecast.data.rules import league_rules, reviewed_rules_evidence
from epl_forecast.datasets import Dataset, timestamp
from epl_forecast.sanctions import load_registry
from epl_forecast.storage import write_json

LONDON = ZoneInfo("Europe/London")
PLACES = {
    "eng-premier-league": {"title_probability": 1, "relegation_probability": 3},
    "eng-championship": {
        "title_probability": 1,
        "automatic_promotion_probability": 2,
        "playoff_promotion_probability": 1,
        "promotion_probability": 3,
        "relegation_probability": 3,
    },
}


class Checks:
    def __init__(self):
        self.results = []

    def check(self, name, condition, detail=""):
        self.results.append({"check": name, "passed": bool(condition), "detail": str(detail)})
        return bool(condition)

    @property
    def failures(self):
        return [r for r in self.results if not r["passed"]]


def verify(archive: Path, data: Path) -> dict:
    forecast = json.loads((archive / "forecast.json").read_text())
    run = json.loads((archive / "run.json").read_text())
    checks = Checks()
    competition = forecast["competition_id"]
    season = forecast["season_id"]

    observed = timestamp(forecast["state_observed_at"])
    cutoff_day = date.fromisoformat(forecast["model_results_cutoff"])
    checks.check(
        "model cutoff is the London day of the observation",
        observed.astimezone(LONDON).date() == cutoff_day,
        f"{observed.isoformat()} -> {cutoff_day}",
    )
    checks.check(
        "generation follows observation",
        timestamp(forecast["generated_at"]) >= observed,
    )
    checks.check(
        "training stops before the cutoff day",
        date.fromisoformat(forecast["training_date_max"]) < cutoff_day,
        forecast["training_date_max"],
    )
    checks.check("provenance records the data manifest", bool(run.get("data_manifest")))
    checks.check("provenance records the model specification", bool(run.get("model")))
    checks.check("provenance records the seed and simulation count", "seed" in run)
    checks.check("source files are hashed", all(f.get("sha256") for f in forecast["sources"]))
    checks.check("no source errors", not forecast["source_errors"], forecast["source_errors"])

    upcoming = [m for m in forecast["matches"] if m.get("kickoff_time")]
    checks.check("the archive forecasts remaining fixtures", bool(upcoming), len(upcoming))
    for match in forecast["matches"]:
        probabilities = [match["p_home"], match["p_draw"], match["p_away"]]
        if not checks.check(
            f"match probabilities are a distribution: {match['match_id']}",
            all(0 <= p <= 1 for p in probabilities) and abs(sum(probabilities) - 1) < 1e-9,
            probabilities,
        ):
            break
        grid = np.asarray(match["score_distribution"]["grid_home_rows_away_columns"])
        omitted = match["score_distribution"]["omitted_probability"]
        if not checks.check(
            f"score matrix closes with its omitted tail: {match['match_id']}",
            abs(grid.sum() + omitted - 1) < 1e-9 and (grid >= 0).all() and omitted >= 0,
            f"{grid.sum():.9f} + {omitted:.9f}",
        ):
            break
        home = float(np.tril(grid, -1).sum())
        draw = float(np.trace(grid))
        away = float(np.triu(grid, 1).sum())
        if not checks.check(
            f"score matrix reproduces the outcome probabilities: {match['match_id']}",
            max(
                abs(home - match["p_home"]),
                abs(draw - match["p_draw"]),
                abs(away - match["p_away"]),
            )
            < omitted + 1e-9,
            f"grid {home:.5f}/{draw:.5f}/{away:.5f} vs {probabilities}",
        ):
            break

    simulation = forecast["simulation"]
    if not checks.check(
        "a season projection is published",
        simulation is not None,
        forecast["simulation_unavailable_reason"],
    ):
        return {"checks": checks.results, "failures": len(checks.failures)}

    teams = simulation["teams"]
    expected_teams = 20 if competition == "eng-premier-league" else 24
    checks.check("every club is projected", len(teams) == expected_teams, len(teams))
    for row in teams:
        points = row["points_distribution"]
        checks.check(
            f"points distribution closes: {row['team_id']}",
            abs(sum(points.values()) - 1) < 1e-9 and all(v >= 0 for v in points.values()),
        )
        positions = np.asarray(row["position_probabilities"])
        checks.check(
            f"rank distribution closes over every place: {row['team_id']}",
            len(positions) == expected_teams and abs(positions.sum() - 1) < 1e-9,
        )
        checks.check(
            f"reported intervals are present: {row['team_id']}",
            set(row["points_intervals"]) == {"50", "80", "90"}
            and set(row["position_intervals"]) == {"50", "80", "90"},
        )
    for event, places in PLACES[competition].items():
        total = sum(row[event] for row in teams)
        checks.check(
            f"{event} mass equals the places awarded",
            abs(total - places) < 1e-6,
            f"{total:.6f} against {places}",
        )

    rules = league_rules(competition, season)
    checks.check(
        "the simulation used this season's ranking rules",
        simulation["ranking_rules"] == rules.ranking,
        simulation["ranking_rules"],
    )
    checks.check(
        "reviewed rules evidence is carried when it exists",
        simulation["ranking_rules_evidence"] == reviewed_rules_evidence(competition, season),
    )
    dataset = Dataset(data, observed)
    try:
        expected_adjustments = load_registry(dataset).known_adjustments(
            competition, season, cutoff_day
        )
    finally:
        dataset.close()
    applied = {(a["team_id"], a["points"]) for a in simulation["point_adjustments"]}
    checks.check(
        "sanctions in force at the cutoff are applied",
        applied == {(a["team_id"], a["points"]) for a in expected_adjustments},
        f"applied {sorted(applied)}",
    )

    if competition == "eng-championship":
        model = simulation["playoff_model"]
        checks.check(
            "the bracket is conditioned on each path's own latent state",
            model["state_conditioning"].startswith("path-specific"),
            model["state_conditioning"],
        )
        checks.check(
            "the bracket is the season's reviewed edition",
            model["format"] == "2026-six-team-seven-match"
            if int(season[:4]) >= 2026
            else model["format"] == "legacy-four-team-five-match",
            model["format"],
        )
        checks.check(
            "promotion is automatic promotion plus the bracket",
            all(
                abs(
                    row["promotion_probability"]
                    - row["automatic_promotion_probability"]
                    - row["playoff_promotion_probability"]
                )
                < 1e-9
                for row in teams
            ),
        )

    frequencies = {row["match_id"]: row for row in simulation["match_frequencies"]}
    published = {
        row["match_id"]: row for row in forecast["matches"] if row["match_id"] in frequencies
    }
    gaps = [
        (
            match_id,
            abs(frequencies[match_id]["p_home"] - published[match_id]["p_home"]),
            abs(frequencies[match_id]["p_draw"] - published[match_id]["p_draw"]),
        )
        for match_id in published
    ]
    worst = max((max(g[1], g[2]) for g in gaps), default=0.0)
    tolerance = 5 / np.sqrt(simulation["simulations"])
    checks.check(
        "simulated match frequencies agree with the published match model",
        worst < tolerance,
        f"largest gap {worst:.5f} against Monte Carlo tolerance {tolerance:.5f}",
    )
    return {
        "checks": checks.results,
        "failures": len(checks.failures),
        "matches_forecast": len(forecast["matches"]),
        "simulations": simulation["simulations"],
        "largest_frequency_gap": worst,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, nargs="+", required=True)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"execution": execution_provenance(), "archives": {}}
    for archive in args.archive:
        report["archives"][str(archive)] = verify(archive, args.data)
    report["failures"] = sum(a["failures"] for a in report["archives"].values())
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "verification.json", report)
    for name, result in report["archives"].items():
        passed = len(result["checks"]) - result["failures"]
        print(f"{name}: {passed}/{len(result['checks'])} checks passed", flush=True)
        for failure in (r for r in result["checks"] if not r["passed"]):
            print(f"  FAILED {failure['check']}: {failure['detail']}", flush=True)
    print(args.output / "verification.json")
    if report["failures"]:
        raise SystemExit(f"{report['failures']} product checks failed")


if __name__ == "__main__":
    main()
