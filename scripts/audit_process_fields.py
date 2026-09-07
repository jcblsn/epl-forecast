"""Audit pinned Football-Data process fields by division and season."""

import argparse
from pathlib import Path

import numpy as np

from epl_forecast.data.sources import csv_rows, read_snapshot
from epl_forecast.storage import file_hash, write_json

FIELDS = ("HS", "AS", "HST", "AST", "HC", "AC", "HF", "AF")


def audit_fields(snapshot_path, data_root):
    rows = []
    for entry in read_snapshot(snapshot_path)["files"]:
        path = data_root / entry["path"]
        if file_hash(path) != entry["sha256"]:
            raise ValueError(f"Source hash mismatch: {path}")
        header, matches = csv_rows(path.read_bytes())
        completed = [r for _, r in matches if r["FTHG"] and r["FTAG"]]
        values = {}
        for field in FIELDS:
            raw = [r.get(field, "") for r in completed]
            parsed, invalid = [], 0
            for value in raw:
                if not value:
                    continue
                try:
                    number = float(value)
                except ValueError:
                    invalid += 1
                    continue
                if not np.isfinite(number) or number < 0 or number != int(number):
                    invalid += 1
                else:
                    parsed.append(number)
            values[field] = {
                "present": field in header,
                "valid": len(parsed),
                "missing": raw.count(""),
                "invalid": invalid,
                "mean": float(np.mean(parsed)) if parsed else None,
                "sd": float(np.std(parsed)) if parsed else None,
                "zero": parsed.count(0),
                "maximum": max(parsed) if parsed else None,
            }
        violations, complete = 0, 0
        for row in completed:
            if all(row.get(f, "").isdigit() for f in ("HS", "AS", "HST", "AST")):
                complete += 1
                violations += int(
                    int(row["HST"]) > int(row["HS"]) or int(row["AST"]) > int(row["AS"])
                )
        rows.append(
            {
                "season": entry["season_id"],
                "division": entry["division"],
                "source_path": str(path),
                "sha256": entry["sha256"],
                "matches": len(completed),
                "fields": values,
                "complete_shot_matches": complete,
                "target_exceeds_shots": violations,
            }
        )
    return {
        "snapshot_sha256": file_hash(snapshot_path),
        "semantics_source": "https://football-data.co.uk/notes.txt",
        "scope": "Pinned historical raw fields; retrospective next-day availability only",
        "semantics_limit": (
            "Counts have stable field labels; provider coding consistency "
            "is not established by coverage alone"
        ),
        "seasons": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("configs/data_snapshot.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Audit output already exists")
    write_json(args.output, audit_fields(args.snapshot, args.data))


if __name__ == "__main__":
    main()
