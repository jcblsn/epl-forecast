"""Report matched uncertainty attribution with dependence sensitivity."""

import argparse
import csv
import json
from pathlib import Path

from epl_forecast.artifacts import execution_provenance
from epl_forecast.research.uncertainty_report import attribution_report
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with (args.run / "club_seasons.csv").open() as stream:
        season_rows = list(csv.DictReader(stream))
    match_rows = json.loads((args.run / "match_scores.json").read_text())
    report = attribution_report(season_rows, match_rows)
    report["execution"] = execution_provenance()
    report["inputs"] = {
        name: file_hash(args.run / name)
        for name in (
            "manifest.json",
            "club_seasons.csv",
            "match_scores.json",
            "calibration_selection.json",
        )
    }
    write_json(args.output, report)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "season_comparisons": len(report["season_comparisons"]),
                "match_comparisons": len(report["match_comparisons"]),
                "missing_comparisons": len(report["missing_comparisons"]),
            }
        )
    )


if __name__ == "__main__":
    main()
