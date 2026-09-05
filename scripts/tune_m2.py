import argparse
from datetime import date
from itertools import product
from pathlib import Path

from epl_forecast.artifacts import new_run_directory, results_markdown
from epl_forecast.cli import save_rows
from epl_forecast.data.normalize import load_processed
from epl_forecast.evaluation import market_predictions, rolling_predictions, summarize
from epl_forecast.storage import write_json
from epl_forecast.tuning import select_by_prior_seasons


def main() -> None:
    parser = argparse.ArgumentParser(description="Small exploratory rolling M2 parameter search")
    parser.add_argument("--data", type=Path, default=Path("data/processed"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--half-lives", type=float, nargs="+", default=[120, 240, 365, 540, 730])
    parser.add_argument("--ridges", type=float, nargs="+", default=[0.5, 1, 2, 5, 10, 20])
    parser.add_argument("--history-days", type=int, default=1095)
    parser.add_argument("--start-season", type=int, default=2015)
    parser.add_argument("--first-test-season", type=int, default=2018)
    parser.add_argument("--end-season", type=int, default=2025)
    args = parser.parse_args()
    if not args.start_season < args.first_test_season <= args.end_season:
        parser.error("Start with earlier selection seasons, followed by at least one test season")
    models = [
        {
            "id": f"M2-h{half_life:g}-r{ridge:g}",
            "kind": "attack_defense_poisson",
            "parameters": {"half_life_days": half_life, "ridge": ridge},
        }
        for half_life, ridge in product(args.half_lives, args.ridges)
    ]
    config = {
        "competition_id": "eng-premier-league",
        "train_window_days": args.history_days,
        "min_train_matches": 700,
        "calibration_bins": 10,
        "bootstrap_samples": 0,
        "models": models,
    }
    matches, odds, manifest = load_processed(args.data)
    new_run_directory(args.output)
    write_json(
        args.output / "run.json",
        {
            "config": config,
            "data_manifest": manifest,
            "start_season": args.start_season,
            "first_test_season": args.first_test_season,
            "end_season": args.end_season,
            "evaluation_status": "exploratory historical rolling CV",
            "selection": "Choose parameters using seasons before each test season; refit daily",
        },
    )
    predictions = rolling_predictions(
        matches,
        config,
        date(args.start_season, 7, 1),
        date(args.end_season + 1, 7, 1),
        progress=True,
    )
    first_test = f"{args.first_test_season}-{args.first_test_season + 1}"
    selection, selected = select_by_prior_seasons(predictions, first_test)
    outer = [row for row in predictions if row["season_id"] >= first_test]
    markets = market_predictions(outer, odds)
    summary = summarize(outer + selected, markets, config)
    summary["evaluation_status"] = "exploratory historical rolling CV"
    summary["evaluation_note"] = (
        "Fixed candidates describe the historical parameter surface. The prior-season selection "
        "row selects parameters before each test season using earlier seasons only. All periods "
        "remain available for development; archived live predictions are the forward test."
    )
    summary["selection"] = selection
    save_rows(args.output / "predictions.csv", predictions)
    save_rows(args.output / "selected_predictions.csv", selected)
    save_rows(args.output / "selection.csv", selection)
    for key in ("overall", "by_season", "calibration", "market_matched"):
        save_rows(args.output / f"{key}.csv", summary[key])
    save_rows(args.output / "market_predictions.csv", markets)
    write_json(args.output / "summary.json", summary)
    report = results_markdown(summary)
    (args.output / "results.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
