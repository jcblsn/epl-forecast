"""Export cutoff-safe shooting and creation distributions from a retained snapshot."""

import argparse
import json
from datetime import date
from pathlib import Path

from epl_forecast.artifacts import new_run_directory, provenance
from epl_forecast.research.player_prior import london_date
from epl_forecast.research.portable_players import (
    INTERFACE_VERSION,
    PortablePlayerLayer,
    portable_observation_rows,
)
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.storage import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True)
    parser.add_argument("--player-id", action="append")
    args = parser.parse_args()
    new_run_directory(args.output)
    snapshot = json.loads(args.manifest.read_text())
    data = frozen_dataset(args.data, args.manifest)
    try:
        rows = portable_observation_rows(data)
        data_manifest = data.provenance()
    finally:
        data.close()
    layer = PortablePlayerLayer(rows, snapshot["canonical_snapshot_sha256"])
    ids = args.player_id or sorted(
        {
            row["player_id"]
            for row in rows
            if london_date(row["kickoff_time"]) < args.cutoff
            and (
                row["evidence_basis"] == "retrospective"
                or london_date(row["retrieved_at"]) < args.cutoff
            )
        }
    )
    states = [layer.freeze(pid, args.cutoff).as_dict() for pid in ids]
    write_json(args.output / "players.json", {"interface": INTERFACE_VERSION, "players": states})
    write_json(
        args.output / "provenance.json",
        provenance(
            {
                "cutoff": str(args.cutoff),
                "player_ids": args.player_id,
                "interface": INTERFACE_VERSION,
            },
            data_manifest,
        ),
    )
    print(
        json.dumps(
            {"players": len(states), "cutoff": str(args.cutoff), "interface": INTERFACE_VERSION}
        )
    )


if __name__ == "__main__":
    main()
