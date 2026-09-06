"""Pin and reconcile historical Understat EPL match xG before modeling."""

import argparse
from pathlib import Path

from epl_forecast.data.normalize import load_processed
from epl_forecast.data.understat import audit_snapshot, fetch_snapshot
from epl_forecast.storage import file_hash, json_bytes, write_immutable, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data"))
    parser.add_argument("--manifest", type=Path, default=Path("configs/understat_snapshot.json"))
    parser.add_argument("--start", type=int, default=2014)
    parser.add_argument("--end", type=int, default=2025)
    parser.add_argument(
        "--report", type=Path, default=Path("docs/experiments/m7/understat_audit.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/understat/matches.json")
    )
    args = parser.parse_args()
    manifest = fetch_snapshot(args.root, args.manifest, args.start, args.end)
    matches, _, _ = load_processed(args.root / "processed")
    records, report = audit_snapshot(args.root, manifest, matches)
    report["canonical_matches_sha256"] = file_hash(args.root / "processed/matches.csv")
    report["manifest_sha256"] = file_hash(args.manifest)
    write_json(args.report, report)
    if not report["passed"]:
        raise ValueError(f"Understat reconciliation failed; inspect {args.report}")
    write_immutable(args.output, json_bytes(records))
    print(f"Reconciled {len(records):,} matches; {args.report}")


if __name__ == "__main__":
    main()
