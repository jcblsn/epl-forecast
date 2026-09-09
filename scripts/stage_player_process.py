"""Capture bounded historical Understat evidence without competing canonical writes."""

import argparse
import time
from pathlib import Path

from epl_forecast.artifacts import retain_execution
from epl_forecast.data.capture import Fetcher, retain, writer_lock
from epl_forecast.data.understat_ingest import ingest
from epl_forecast.research.readiness import frozen_dataset
from epl_forecast.storage import file_hash, json_bytes, write_immutable, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "publish"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--seasons", nargs="+", type=int, default=[2023, 2024, 2025])
    parser.add_argument("--marker", default="publish_complete.json")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if (
        args.stage.resolve() == args.data.resolve()
        or args.data.resolve() in args.stage.resolve().parents
    ):
        raise ValueError("Staging must be separate from the canonical data root")
    with writer_lock(args.stage):
        retain_execution(args.stage)
        data = frozen_dataset(args.data, args.manifest)
        try:
            matches = data.rows(
                "SELECT DISTINCT match_id, source_match_id, season_id FROM team_process WHERE provider='understat' AND source_match_id IS NOT NULL ORDER BY season_id, match_id"
            )
        finally:
            data.close()
        matches = [m for m in matches if int(m["season_id"][:4]) in args.seasons]
        if not matches:
            raise ValueError("No retained team fixtures for requested seasons")
        metadata = {
            "manifest_sha256": file_hash(args.manifest),
            "seasons": args.seasons,
            "matches": matches,
        }
        write_immutable(args.stage / "manifest.json", json_bytes(metadata))
        fetcher = Fetcher(args.stage)
        if args.action == "capture":
            for index, match in enumerate(matches):
                url = f"https://understat.com/getMatchData/{match['source_match_id']}"
                cached = url in fetcher.latest
                fetcher.get(
                    "understat",
                    url,
                    historical=True,
                    context={"kind": "players", "match_id": match["match_id"]},
                )
                if not cached:
                    time.sleep(1)
                if (index + 1) % 25 == 0:
                    print(f"Captured {index + 1}/{len(matches)}", flush=True)
            write_json(
                args.stage / "capture_complete.json",
                {
                    "matches": len(matches),
                    "manifest_sha256": file_hash(args.stage / "manifest.json"),
                },
            )
        else:
            if not (args.stage / "capture_complete.json").exists():
                raise ValueError("Complete capture before publication")
            selected = matches[: args.limit] if args.limit else matches
            with writer_lock(args.data):
                for index, match in enumerate(selected):
                    url = f"https://understat.com/getMatchData/{match['source_match_id']}"
                    record = fetcher.latest[url]
                    raw = args.stage / record["raw_path"]
                    if file_hash(raw) != record["source_sha256"]:
                        raise ValueError("Staged evidence checksum mismatch")
                    payload = raw.read_bytes()
                    retained = retain(
                        args.data,
                        record["provider"],
                        record["url"],
                        payload,
                        record["retrieved_at"],
                        record["evidence_basis"],
                        record["context"],
                    )
                    ingest(args.data, retained, payload)
                    if (index + 1) % 25 == 0:
                        print(f"Published {index + 1}/{len(selected)}", flush=True)
            write_json(
                args.stage / args.marker,
                {
                    "data_root": str(args.data.resolve()),
                    "matches": len(selected),
                    "manifest_sha256": file_hash(args.stage / "manifest.json"),
                },
            )


if __name__ == "__main__":
    main()
