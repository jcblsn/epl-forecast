import argparse
import json
import sys
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

from epl_forecast.artifacts import new_run_directory, provenance, results_markdown
from epl_forecast.data.crosscheck import crosscheck_openfootball
from epl_forecast.data.live import LONDON, capture_snapshot, load_live_season
from epl_forecast.data.normalize import load_processed, normalize_snapshot, write_csv
from epl_forecast.data.rules import historical_adjustments
from epl_forecast.data.sources import (
    SourceAccessError,
    fetch_snapshot,
    read_snapshot,
    restore_snapshot,
)
from epl_forecast.evaluation import market_predictions, rolling_predictions, summarize
from epl_forecast.live_forecast import check_freshness, export_forecast
from epl_forecast.models import make_model
from epl_forecast.schema import Fixture, fixture_id
from epl_forecast.simulation import EuropeScenario, simulate_season
from epl_forecast.storage import write_json
from epl_forecast.training import training_matches


def load_config(path: Path) -> dict:
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    previous_end = None
    for split in ("development", "validation", "holdout"):
        start, end = (date.fromisoformat(config[f"{split}_{part}"]) for part in ("start", "end"))
        if start >= end or (previous_end and start < previous_end):
            raise ValueError("Experiment splits must be chronological, nonoverlapping intervals")
        previous_end = end
    if config["train_window_days"] < 1 or config["min_train_matches"] < 1:
        raise ValueError("Training limits must be positive")
    return config


def fitted_model(matches: list, config: dict, model_id: str, as_of: date):
    specs = [spec for spec in config["models"] if spec["id"] == model_id]
    if len(specs) != 1:
        raise ValueError(f"Unknown or duplicate model ID: {model_id}")
    training = training_matches(matches, config, specs[0], as_of)
    return make_model(specs[0]).fit(training, as_of), specs[0], training


def save_rows(path: Path, rows: list[dict]) -> None:
    if rows:
        write_csv(path, list(dict.fromkeys(key for row in rows for key in row)), rows)


def evaluate_command(args) -> None:
    config = load_config(args.config)
    matches, odds, manifest = load_processed(args.data)
    start = date.fromisoformat(config[f"{args.split}_start"])
    end = date.fromisoformat(config[f"{args.split}_end"])
    new_run_directory(args.output)
    predictions = rolling_predictions(matches, config, start, end, progress=True)
    markets = market_predictions(predictions, odds)
    summary = summarize(predictions, markets, config)
    evaluation_context = {
        key: config[key] for key in ("evaluation_status", "evaluation_note") if key in config
    }
    summary.update(evaluation_context)
    save_rows(args.output / "predictions.csv", predictions)
    save_rows(args.output / "market_predictions.csv", markets)
    for key in ("overall", "by_season", "calibration", "market_matched"):
        save_rows(args.output / f"{key}.csv", summary[key])
    write_json(args.output / "paired_comparisons.json", summary["paired_comparisons"])
    write_json(args.output / "summary.json", summary)
    write_json(
        args.output / "run.json",
        {
            **provenance(config, manifest),
            **evaluation_context,
            "split": args.split,
            "start": str(start),
            "end": str(end),
            "information_cutoff": "start of match date; no same-day results",
        },
    )
    report = results_markdown(summary)
    (args.output / "results.md").write_text(report)
    print(report)


def simulate_command(args) -> None:
    config = load_config(args.config)
    matches, _, manifest = load_processed(args.data)
    model, spec, training = fitted_model(matches, config, args.model, args.as_of)
    season_matches = [
        m
        for m in matches
        if m.fixture.season_id == args.season and m.fixture.competition_id == "eng-premier-league"
    ]
    if not season_matches:
        raise ValueError(f"No Premier League matches for {args.season}")
    teams = sorted(
        {team for m in season_matches for team in (m.fixture.home_team_id, m.fixture.away_team_id)}
    )
    played = [m for m in season_matches if m.available_on <= args.as_of]
    remaining = [m.fixture for m in season_matches if m.available_on > args.as_of]
    europe = (
        None
        if args.europe_scenario is None
        else EuropeScenario(**json.loads(args.europe_scenario.read_text()))
    )
    adjustments = (
        historical_adjustments(args.season, args.as_of)
        if args.adjustments is None
        else json.loads(args.adjustments.read_text())
    )
    new_run_directory(args.output)
    result = simulate_season(
        model,
        played,
        remaining,
        teams,
        args.as_of,
        args.simulations,
        args.seed,
        adjustments,
        europe,
    )
    write_json(args.output / "simulation.json", result)
    rows = []
    for team in sorted(result["teams"], key=lambda t: t["mean_position"]):
        row = {key: value for key, value in team.items() if not isinstance(value, (dict, list))}
        row.update(team.get("conditional_europe_probabilities", {}))
        rows.append(row)
    save_rows(args.output / "table.csv", rows)
    if hasattr(model, "team_summary"):
        save_rows(
            args.output / "team_strengths.csv",
            [model.team_summary(team, args.season) for team in teams],
        )
    elif hasattr(model, "team_index"):
        save_rows(
            args.output / "team_strengths.csv",
            [
                {
                    "team_id": team,
                    "attack_log_rate": float(model.attack[index]),
                    "defense_log_rate": float(model.defense[index]),
                }
                for team, index in model.team_index.items()
            ],
        )
    write_json(
        args.output / "run.json",
        {
            **provenance(config, manifest),
            "model": spec,
            "as_of": str(args.as_of),
            "season_id": args.season,
            "seed": args.seed,
            "simulations": args.simulations,
            "training_matches": len(training),
            "europe_scenario": result["europe_scenario"],
            "adjustments": adjustments,
        },
    )
    print(
        f"Simulated {len(remaining)} remaining fixtures {args.simulations:,} times; "
        f"saved {args.output / 'simulation.json'}"
    )


def predict_command(args) -> None:
    config = load_config(args.config)
    matches, _, manifest = load_processed(args.data)
    as_of = args.as_of or args.date
    model, spec, training = fitted_model(matches, config, args.model, as_of)
    fixture = Fixture(
        fixture_id(config["competition_id"], args.season, args.home, args.away),
        config["competition_id"],
        args.season,
        args.date,
        args.home,
        args.away,
    )
    known_ids = {team for m in matches for team in (m.fixture.home_team_id, m.fixture.away_team_id)}
    if args.home not in known_ids or args.away not in known_ids:
        raise ValueError("Use canonical team IDs from the normalized data")
    forecast = model.predict_match(fixture)
    output = {
        "model": spec,
        "match_id": fixture.match_id,
        "as_of": str(as_of),
        "match_date": str(args.date),
        "training_matches": len(training),
        "p_home": forecast.probabilities[0],
        "p_draw": forecast.probabilities[1],
        "p_away": forecast.probabilities[2],
        "provenance": provenance(config, manifest),
    }
    if forecast.scores is not None and hasattr(forecast.scores, "grid"):
        grid, tail = forecast.scores.grid(args.max_goals)
        output["score_distribution"] = {
            "home_rate": forecast.scores.home_rate,
            "away_rate": forecast.scores.away_rate,
            "grid_home_rows_away_columns": grid.tolist(),
            "omitted_probability": tail,
        }
    if hasattr(model, "team_summary"):
        output["team_states"] = [model.team_summary(t, args.season) for t in (args.home, args.away)]
        output["fit_diagnostics"] = model.fit_diagnostics
    if args.output:
        write_json(args.output, output)
        print(f"Saved {args.output}")
    else:
        print(json.dumps(output, indent=2, allow_nan=False))


def forecast_command(args) -> None:
    live = load_live_season(args.snapshot)
    check_freshness(live, args.max_snapshot_age_hours)
    config = load_config(args.config)
    history, _, manifest = load_processed(args.data)
    history = [
        match
        for match in history
        if (match.fixture.competition_id, match.fixture.season_id)
        != ("eng-premier-league", live.season_id)
    ] + live.played
    as_of = live.observed_at.astimezone(LONDON).date()
    model, spec, training = fitted_model(history, config, args.model, as_of)
    if spec["kind"] not in {
        "attack_defense_poisson",
        "dynamic_attack_defense",
        "bayesian_quality_tilt",
    }:
        raise ValueError("The live strength export currently requires an attack/defense model")
    europe = (
        EuropeScenario(**json.loads(args.europe_scenario.read_text()))
        if args.europe_scenario
        else None
    )
    adjustments = (
        json.loads(args.adjustments.read_text())
        if args.adjustments
        else historical_adjustments(live.season_id, as_of)
    )
    output = args.output or Path("runs/forecasts") / datetime.now(UTC).strftime(
        "%Y-%m-%dT%H%M%S.%fZ"
    )
    result = export_forecast(
        live,
        model,
        training,
        {
            **provenance(config, manifest),
            "model": spec,
            "snapshot": str(args.snapshot),
            "live_snapshot": live.manifest,
            "seed": args.seed,
            "simulations": args.simulations,
            "max_goals": args.max_goals,
            "europe_scenario": None if europe is None else vars(europe),
            "adjustments": adjustments,
        },
        output,
        args.simulations,
        args.seed,
        args.max_goals,
        adjustments,
        europe,
    )
    print(
        f"Archived {len(result['matches'])} match forecasts and "
        f"{len(result['team_strengths'])} team strengths to {output}"
    )
    if result["simulation"]:
        print(
            f"Fixed {len(live.played)} captured full-time results; "
            f"simulated {len(live.remaining)} fixtures {args.simulations:,} times"
        )
    else:
        print(result["simulation_unavailable_reason"])
    print(f"Open {output / 'index.html'}")


def audit_command(args) -> None:
    _, _, manifest = load_processed(args.data)
    coverage = json.loads((args.data / "coverage.json").read_text())["seasons"]
    rows = []
    for audit in coverage:
        missing = audit["missing_by_column"]
        rows.append(
            {
                **{
                    key: audit[key]
                    for key in (
                        "season_id",
                        "division",
                        "matches",
                        "teams",
                        "complete",
                        "date_min",
                        "date_max",
                    )
                },
                "missing_time": missing.get("Time", audit["matches"]),
                "missing_core": sum(
                    missing[key] for key in ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR")
                ),
                "missing_shots": sum(
                    missing.get(key, audit["matches"]) for key in ("HS", "AS", "HST", "AST")
                ),
                "bet365_valid": audit["odds"]["bet365_preclosing"].get("valid", 0),
                "average_closing_valid": audit["odds"]["market_average_closing"].get("valid", 0),
                "invalid_odds": sum(x.get("invalid", 0) for x in audit["odds"].values()),
                **{
                    key: audit[key]
                    for key in ("mean_home_goals", "mean_away_goals", "goal_covariance")
                },
            }
        )
    save_rows(args.output, rows)
    print(
        f"Audited {manifest['matches']:,} matches in {len(coverage)} season files; "
        f"{sum(row['complete'] for row in coverage)} complete schedules. Saved {args.output}"
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Premier League probabilistic forecasts and season simulation"
    )
    commands = root.add_subparsers(dest="command", required=True)
    data = commands.add_parser("data").add_subparsers(dest="action", required=True)
    snapshot = data.add_parser("snapshot", help="Archive current FPL and Football-Data responses")
    snapshot.add_argument("--root", type=Path, default=Path("snapshots"))
    snapshot.add_argument("--season-start", type=int, required=True)
    for name in ("fetch", "restore", "normalize"):
        command = data.add_parser(name)
        command.add_argument("--root", type=Path, default=Path("data"))
        command.add_argument("--snapshot", type=Path, default=Path("configs/data_snapshot.json"))
        if name == "fetch":
            command.add_argument("--start-season", type=int, default=2010)
            command.add_argument("--end-season", type=int, default=2025)
            command.add_argument("--divisions", nargs="+", default=["E0", "E1"])
        if name == "normalize":
            command.add_argument("--output", type=Path, default=Path("data/processed"))
    audit = data.add_parser("audit")
    audit.add_argument("--data", type=Path, default=Path("data/processed"))
    audit.add_argument("--output", type=Path, default=Path("docs/data_audit.csv"))
    crosscheck = data.add_parser("cross-check")
    crosscheck.add_argument("--data", type=Path, default=Path("data/processed"))
    crosscheck.add_argument(
        "--snapshot", type=Path, default=Path("configs/crosscheck_snapshot.json")
    )
    crosscheck.add_argument("--output", type=Path, default=Path("docs/crosscheck.json"))
    forecast = commands.add_parser("forecast", help="Archive a current-season score-model forecast")
    forecast.add_argument("--snapshot", type=Path, required=True)
    forecast.add_argument("--config", type=Path, default=Path("configs/baselines.toml"))
    forecast.add_argument("--data", type=Path, default=Path("data/processed"))
    forecast.add_argument("--output", type=Path)
    forecast.add_argument("--model", default="M2-attack-defense-v1")
    forecast.add_argument("--simulations", type=int, default=10000)
    forecast.add_argument("--seed", type=int, default=20260905)
    forecast.add_argument("--max-goals", type=int, default=10)
    forecast.add_argument("--max-snapshot-age-hours", type=float, default=24)
    forecast.add_argument("--europe-scenario", type=Path)
    forecast.add_argument("--adjustments", type=Path)
    forecast.set_defaults(func=forecast_command)
    for name in ("evaluate", "simulate", "predict"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, default=Path("configs/baselines.toml"))
        command.add_argument("--data", type=Path, default=Path("data/processed"))
        command.add_argument("--output", type=Path, required=name != "predict")
        if name == "evaluate":
            command.add_argument(
                "--split", choices=["development", "validation", "holdout"], required=True
            )
            command.set_defaults(func=evaluate_command)
        else:
            command.add_argument("--model", default="M2-attack-defense-v1")
            command.add_argument("--season", required=True, help="Season ID, e.g. 2024-2025")
            command.add_argument("--as-of", type=date.fromisoformat, required=name == "simulate")
        if name == "simulate":
            command.add_argument("--simulations", type=int, default=10000)
            command.add_argument("--seed", type=int, default=20260905)
            command.add_argument("--adjustments", type=Path)
            command.add_argument("--europe-scenario", type=Path)
            command.set_defaults(func=simulate_command)
        if name == "predict":
            command.add_argument("--home", required=True)
            command.add_argument("--away", required=True)
            command.add_argument("--date", required=True, type=date.fromisoformat)
            command.add_argument("--max-goals", type=int, default=10)
            command.set_defaults(func=predict_command)
    return root


def main() -> None:
    root = parser()
    args = root.parse_args()
    try:
        if args.command != "data":
            args.func(args)
        elif args.action == "snapshot":
            directory = capture_snapshot(args.root, args.season_start)
            manifest = json.loads((directory / "manifest.json").read_text())
            print(f"Archived {len(manifest['files'])} sources to {directory}")
            if manifest["errors"]:
                raise SourceAccessError(
                    f"{len(manifest['errors'])} sources failed; "
                    "successful responses remain archived"
                )
        elif args.action == "fetch":
            snapshot = fetch_snapshot(
                args.root, args.snapshot, args.start_season, args.end_season, args.divisions
            )
            print(f"Pinned {len(snapshot['files'])} source files in {args.snapshot}")
        elif args.action == "restore":
            snapshot = read_snapshot(args.snapshot)
            restore_snapshot(args.root, snapshot)
            print(f"Verified {len(snapshot['files'])} raw files")
        elif args.action == "normalize":
            manifest = normalize_snapshot(args.root, args.snapshot, args.output)
            print(f"Normalized {manifest['matches']:,} matches to {args.output}")
        elif args.action == "cross-check":
            report = crosscheck_openfootball(args.data, args.snapshot, args.output)
            print(
                f"Compared {report['compared_matches']} matches; all agree: {report['all_agree']}"
            )
            if not report["all_agree"]:
                sys.exit(1)
        else:
            audit_command(args)
    except (ValueError, SourceAccessError, OSError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
