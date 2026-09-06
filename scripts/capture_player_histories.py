import argparse
import csv
import gzip
import io
from pathlib import Path

from epl_forecast.data.player_live import capture_player_histories, load_captured_player_histories
from epl_forecast.storage import file_hash, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--root", type=Path, default=Path("data/raw/players/live"))
    parser.add_argument(
        "--capture", type=Path, help="Normalize an existing capture without fetching"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.capture and not args.snapshot:
        parser.error("Provide --snapshot for a new capture or --capture to replay")
    args.output.mkdir(parents=True, exist_ok=False)
    directory = args.capture or capture_player_histories(args.snapshot, args.root)
    print(f"Player capture: {directory}", flush=True)
    rows, report = load_captured_player_histories(directory, args.snapshot)
    path = args.output / "player_matches.csv.gz"
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped,
        io.TextIOWrapper(zipped, encoding="utf-8", newline="") as stream,
    ):
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["player_season_id"])
        writer.writeheader()
        writer.writerows(rows)
    write_json(
        args.output / "report.json", {**report, "dataset": str(path), "sha256": file_hash(path)}
    )


if __name__ == "__main__":
    main()
