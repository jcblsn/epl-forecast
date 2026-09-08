"""One-time import of local raw evidence; never downloads legacy sources."""

import argparse
import json
from pathlib import Path

from epl_forecast.data import football_data, fpl, understat_ingest
from epl_forecast.data.capture import retain, writer_lock
from epl_forecast.storage import file_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data"))
    args = parser.parse_args()
    root = args.root
    count = 0
    with writer_lock(root):
        for provider, config in [
            ("football_data", "data_snapshot.json"),
            ("understat", "understat_snapshot.json"),
        ]:
            manifest = json.loads((Path(__file__).parent / config).read_text())
            for entry in manifest["files"]:
                path = root / entry["path"]
                if file_hash(path) != entry["sha256"]:
                    raise ValueError(f"Corrupt historical evidence: {path}")
                if provider == "football_data":
                    context = {
                        k: entry[k]
                        for k in ("competition_id", "division", "season_id", "season_start")
                    }
                else:
                    context = {"kind": "league", "season_start": entry["season_start"]}
                record = retain(
                    root,
                    provider,
                    entry["url"],
                    path.read_bytes(),
                    entry["retrieved_at"],
                    "retrospective",
                    context,
                )
                (football_data if provider == "football_data" else understat_ingest).ingest(
                    root, record, path.read_bytes()
                )
                count += 1
        for path in sorted(Path("snapshots").glob("*/manifest.json")):
            manifest = json.loads(path.read_text())
            for entry in manifest["files"]:
                name = entry["name"]
                if name not in (
                    "fpl_bootstrap.json",
                    "football_data_E0.csv",
                    "football_data_E1.csv",
                ):
                    continue
                raw = path.parent / name
                if file_hash(raw) != entry["sha256"]:
                    raise ValueError(f"Corrupt prospective evidence: {raw}")
                season = manifest["season_id"]
                provider = "fpl" if name.startswith("fpl") else "football_data"
                context = {"season_id": season}
                if provider == "football_data":
                    division = "E0" if "_E0" in name else "E1"
                    context.update(
                        {
                            "season_start": int(season[:4]),
                            "division": division,
                            "competition_id": "eng-premier-league"
                            if division == "E0"
                            else "eng-championship",
                        }
                    )
                record = retain(
                    root,
                    provider,
                    entry["url"],
                    raw.read_bytes(),
                    entry["retrieved_at"],
                    "captured",
                    context,
                )
                (fpl if provider == "fpl" else football_data).ingest(root, record, raw.read_bytes())
                count += 1
    print(f"Imported {count} original raw captures with original retrieval times")


if __name__ == "__main__":
    main()
