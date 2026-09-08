"""Recalculate season scores from the committed forecast marginals and final tables."""

import argparse
import gzip
import json
from pathlib import Path

from epl_forecast.cli import save_rows
from epl_forecast.season_evaluation import score_forecast, summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with gzip.open(args.archive, "rt") as stream:
        archive = json.load(stream)
    if archive["schema_version"] != 1:
        raise ValueError("Unsupported season marginal archive")
    rows = []
    seen = set()
    for entry in archive["forecasts"]:
        model, origin, forecast = entry["model_id"], entry["origin"], entry["forecast"]
        season = forecast["season_id"]
        key = (model, origin, season)
        if key in seen:
            raise ValueError("Duplicate model-season-origin")
        seen.add(key)
        rows.extend(
            {
                "model_id": model,
                "season_id": season,
                "origin": origin,
                "as_of": forecast["as_of"],
                "played_matches": forecast["played_matches"],
                **row,
            }
            for row in score_forecast(
                forecast,
                archive["truth"][season],
                set(archive["promoted"][season]),
                forecast["seed"],
            )
        )
    args.output.mkdir(parents=True, exist_ok=True)
    summary, calibration = summarize(rows)
    save_rows(args.output / "club_seasons.csv", rows)
    save_rows(args.output / "summary.csv", summary)
    save_rows(args.output / "calibration.csv", calibration)
    per_season = []
    for season in sorted({r["season_id"] for r in rows}):
        scores, _ = summarize([r for r in rows if r["season_id"] == season])
        per_season.extend({"season_id": season, **r} for r in scores)
    save_rows(args.output / "by_season.csv", per_season)


if __name__ == "__main__":
    main()
