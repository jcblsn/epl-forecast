"""Gate the published player-process population on identity, exposure and coverage."""

import argparse
import json
from pathlib import Path

from epl_forecast.artifacts import retain_execution
from epl_forecast.datasets import Dataset
from epl_forecast.research.player_signals import player_population_audit
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.storage import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    retain_execution(args.output)
    data = frozen_dataset(args.data, args.manifest) if args.manifest else Dataset(args.data)
    try:
        report = player_population_audit(data, stage=args.stage)
    finally:
        data.close()
    write_json(args.output / "player_population_audit.json", report)
    print(
        json.dumps(
            {
                "by_season": {
                    season: {k: v for k, v in cell.items() if k != "fixtures_without_process"}
                    | {"fixtures_without_process": len(cell["fixtures_without_process"])}
                    for season, cell in report["by_season"].items()
                },
                "many_to_one_collisions": len(report["many_to_one_collisions"]),
                "unlinked_understat_ids": len(report["unlinked_understat_ids"]),
                "most_frequent_unlinked": [
                    {"understat_id": k, **v}
                    for k, v in list(report["unlinked_understat_ids"].items())[:8]
                ],
                "positive_exposure_disagreements": len(report["positive_exposure_disagreements"]),
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
